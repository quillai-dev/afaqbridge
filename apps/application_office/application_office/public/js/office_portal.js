/* AfaqBridge customer portal. All server-provided text is inserted with textContent (never innerHTML).
 * Text is translated through Frappe's gettext catalogue (locale/ar.po): the server sends {english: translated}
 * in window.AO_I18N (see www/office-portal.py). Identifiers, dates, e-mails and URLs are wrapped in <bdi> so they
 * keep their own direction inside Arabic sentences. */
(function () {
  "use strict";
  const root = document.getElementById("ao-app");
  let csrfValue = "";
  const csrf = () => csrfValue;
  const M = "application_office.portal_api.";
  const LANG = root.dataset.lang || "ar";
  let I18N = {};
  try { I18N = JSON.parse(document.getElementById("ao-i18n").textContent || "{}"); } catch (e) { /* untranslated fallback */ }
  let dirty = false;

  const t = (s) => (Object.prototype.hasOwnProperty.call(I18N, s) && I18N[s]) || s;
  // Translate a sentence with {0}, {1}… placeholders; string values become direction-isolated <bdi> nodes.
  function tn(s, ...args) {
    return t(s).split(/(\{\d+\})/).map((part) => {
      const m = /^\{(\d+)\}$/.exec(part);
      if (!m) return part;
      const v = args[+m[1]];
      return v instanceof Node ? v : bdi(v);
    });
  }
  const tx = (s, ...args) => tn(s, ...args).map((n) => (n instanceof Node ? n.textContent : n)).join("");
  const bdi = (v) => { const e = document.createElement("bdi"); e.textContent = v == null ? "" : String(v); return e; };

  function h(tag, attrs, ...kids) {
    const e = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (k === "class") e.className = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else if (v !== false && v != null) e.setAttribute(k, v);
    });
    kids.flat(Infinity).forEach(k => e.append(k instanceof Node ? k : document.createTextNode(k == null ? "" : String(k))));
    return e;
  }
  // Children may be Nodes, strings or (nested) arrays of either; flatten and drop empties before touching the DOM.
  const kids = a => a.flat(Infinity).filter(x => x !== "" && x != null && x !== false);
  const add = (...a) => root.append(...kids(a));
  const reset = (...a) => { dirty = false; root.replaceChildren(langBar(), ...kids(a)); };
  function serverMessage(r) {
    try { const m = JSON.parse(r._server_messages || "[]"); return m.map(x => JSON.parse(x).message).join(" ").replace(/<[^>]*>/g, ""); } catch (e) { return ""; }
  }
  async function api(method, args, post, form) {
    const url = "/api/method/" + (method.includes(".") ? method : M + method);
    let res;
    if (!post) res = await fetch(url + (args ? "?" + new URLSearchParams(args) : ""), {credentials: "same-origin"});
    else res = await fetch(url, {method: "POST", credentials: "same-origin", headers: Object.assign({"X-Frappe-CSRF-Token": csrf()}, form ? {} : {"Content-Type": "application/x-www-form-urlencoded"}),
      body: form || new URLSearchParams(args || {})});
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(serverMessage(data) || tx("Request failed ({0})", res.status));
    return data.message;
  }
  const toast = (m, bad) => { const b = h("div", {class: "ao-msg " + (bad ? "ao-warn" : "ao-ok"), role: "alert"}, m); root.prepend(b); setTimeout(() => b.remove(), 6000); };
  const run = fn => async (...a) => { try { await fn(...a); } catch (e) { toast(e.message, true); } };
  root.addEventListener("input", () => { dirty = true; });

  // Language switch: same URL, reload in place. Unsaved form input is protected by a confirmation.
  function langBar() {
    const btn = (code, label) => h("button", {type: "button", class: "ao-lang" + (LANG === code ? " active" : ""), lang: code,
      "aria-pressed": LANG === code ? "true" : "false",
      onclick: run(async () => {
        if (LANG === code) return;
        if (dirty && !confirm(t("You have unsaved changes. Switch language anyway?"))) return;
        await api("application_office.localization.set_language", {lang: code}, true);
        document.cookie = "preferred_language=" + code + "; path=/; max-age=31536000; samesite=lax";
        window.location.reload();
      })}, label);
    return h("div", {class: "ao-langbar", role: "group", "aria-label": t("Language")}, btn("ar", "العربية"), btn("en", "English"));
  }

  let boot;
  async function start() {
    boot = await api("bootstrap");
    if (boot.user) csrfValue = await api("csrf_token");
    reset(h("div", {class: "ao-banner"}, boot.disclaimer));
    if (!boot.user) return guestView();
    if (!boot.user.consents_ok) return consentView();
    return dashboard();
  }

  function guestView() {
    const f = {};
    const inp = (k, label, type) => h("div", {}, h("label", {for: "f-" + k}, label), f[k] = h("input", {id: "f-" + k, type: type || "text", autocomplete: "off", dir: type === "email" ? "ltr" : "auto"}));
    const chk = (k, text) => h("label", {}, f[k] = h("input", {type: "checkbox"}), " ", text);
    add(h("h2", {}, t("Sign in or register")),
      h("p", {}, h("a", {href: "/login?redirect-to=/office-portal"}, t("Sign in to your account"))),
      h("div", {class: "ao-card"}, h("h3", {}, t("Create an account")), inp("name", t("Full name")), inp("email", t("E-mail"), "email"),
        chk("terms", [t("I accept the service terms"), boot.terms_url ? [" (", bdi(boot.terms_url), ")"] : ""]),
        chk("privacy", [t("I have read the privacy notice"), boot.privacy_url ? [" (", bdi(boot.privacy_url), ")"] : ""]),
        chk("sens", boot.sensitive_consent_text),
        h("p", {}, h("button", {onclick: run(async () => {
          const r = await api("register", {email: f.email.value, full_name: f.name.value, language: LANG, accept_terms: +f.terms.checked, accept_privacy: +f.privacy.checked, accept_sensitive: +f.sens.checked}, true);
          toast(r.message);
        })}, t("Register")))));
  }

  function consentView() {
    add(h("h2", {}, t("Please review and accept")), h("div", {class: "ao-card"},
      h("p", {}, tn("Service terms version {0}, privacy notice version {1}.", boot.terms_version, boot.privacy_version)),
      h("p", {}, boot.sensitive_consent_text),
      h("button", {onclick: run(async () => { await api("accept_current_consents", {}, true); start(); })}, t("I accept"))));
  }

  const REQUEST_TYPES = [["Access / Export", "Access / Export"], ["Correction", "Correction"], ["Erasure", "Erasure"], ["Account Closure", "Account Closure"]];

  async function dashboard() {
    const [cases, services, invoices] = await Promise.all([api("list_cases"), api("list_services"), api("list_invoices")]);
    add(h("h2", {}, tn("Hello, {0}", boot.user.name)),
      h("h3", {}, t("Your applications")),
      cases.length ? cases.map(c => h("div", {class: "ao-card"}, h("div", {class: "ao-row"}, h("b", {}, c.program_name), h("span", {class: "ao-badge"}, c.status_label), c.deadline ? h("span", {}, tn("Deadline on record: {0}", c.deadline)) : ""),
        h("button", {class: "secondary", onclick: () => caseView(c.name)}, tn("Open {0}", c.name)))) : h("p", {}, t("No applications yet.")),
      h("h3", {}, t("Available services")),
      services.map(s => h("div", {class: "ao-card"}, h("b", {}, s.program_name), " ", h("span", {class: "ao-badge"}, s.category),
        h("p", {}, s.eligibility), s.closing ? h("p", {}, tn("Closing (as verified by our staff on {0}): {1}", s.last_verified_on, s.closing)) : "",
        s.requirements_url ? h("p", {}, tn("Official requirements: {0}", s.requirements_url)) : "",
        h("p", {}, tn("Documents: {0}", s.documents.map(d => d.category + (d.required ? "" : " (" + t("optional") + ")")).join("، "))),
        s.startable ? h("button", {onclick: run(async () => { const r = await api("start_case", {program: s.name}, true); caseView(r.case); })}, t("Start")) : h("em", {}, t(s.unavailable_reason)))),
      h("h3", {}, t("Invoices")),
      invoices.length ? invoices.map(i => h("div", {class: "ao-row"}, bdi(i.name), " ", bdi(i.grand_total + " " + i.currency), h("span", {class: "ao-badge"}, i.status), i.case ? bdi(i.case) : "")) : h("p", {}, t("No invoices.")),
      h("h3", {}, t("Privacy")),
      h("div", {class: "ao-card"}, h("p", {}, t("You can request access to, correction of, or erasure of your data, or close your account. Some records must be kept by law.")),
        REQUEST_TYPES.map(([v, label]) => h("button", {class: "secondary", style: "margin:2px", onclick: run(async () => { await api("data_request", {request_type: v}, true); toast(tx("Request recorded: {0}", t(label))); })}, t(label)))));
  }

  async function caseView(name) {
    const c = await api("get_case", {case: name});
    const intakeInputs = {};
    reset(h("div", {class: "ao-banner"}, c.disclaimer),
      h("button", {class: "secondary", onclick: start}, t("← Back")),
      h("h2", {}, c.program_name, " — ", bdi(c.name)), h("p", {}, h("span", {class: "ao-badge"}, c.status_label), c.deadline ? ["  ", tn("Deadline on record: {0}", c.deadline)] : ""),
      c.customer_visible_notes ? h("div", {class: "ao-card"}, c.customer_visible_notes) : "",
      h("h3", {}, t("Information form")),
      h("div", {class: "ao-card"}, c.intake.map(f => h("div", {}, h("label", {}, f.label + (f.required ? " *" : "")),
        intakeInputs[f.field_key] = f.field_type === "Long Text" ? h("textarea", {dir: "auto"}, f.value) : f.field_type === "Select" ? h("select", {}, f.options.map(o => h("option", {value: o, selected: o === f.value}, o))) : f.field_type === "Checkbox" ? h("input", {type: "checkbox", checked: f.value ? "checked" : false}) : h("input", {type: f.field_type === "Date" ? "date" : "text", value: f.value, autocomplete: "off", dir: "auto"}))),
        c.can_edit ? h("p", {}, h("button", {onclick: run(async () => { await api("save_intake", {case: name, values: JSON.stringify(Object.fromEntries(Object.entries(intakeInputs).map(([k, i]) => [k, i.type === "checkbox" ? i.checked : i.value]))), complete: 1}, true); toast(t("Saved")); caseView(name); })}, t("Save and mark complete"))) : ""),
      h("h3", {}, t("Documents")),
      c.documents.map(d => h("div", {class: "ao-card"}, h("div", {class: "ao-row"}, h("b", {}, d.document_category), d.required ? t("(required)") : t("(optional)"),
          h("span", {class: "ao-badge"}, d.upload_status === "Uploaded" ? tn("uploaded (v{0}) — {1}", d.current_version, t(d.review_status)) : t("missing"))),
        d.customer_feedback ? h("p", {class: "ao-warn"}, tn("Feedback: {0}", d.customer_feedback)) : "", d.instructions ? h("small", {}, d.instructions) : "",
        c.can_edit && d.review_status !== "Approved" ? (() => { const fi = h("input", {type: "file", accept: ".pdf,.jpg,.jpeg,.png"}); return h("div", {class: "ao-row"}, fi, h("button", {class: "secondary", onclick: run(async () => { if (!fi.files[0]) throw new Error(t("Choose a file")); const fd = new FormData(); fd.append("file", fi.files[0]); fd.append("case", name); fd.append("required_document", d.name); await api("upload_document", null, true, fd); toast(t("Uploaded")); caseView(name); })}, t("Upload"))); })() : "",
        d.upload_status === "Uploaded" ? h("a", {href: "/api/method/" + M + "download_document?" + new URLSearchParams({case: name, required_document: d.name})}, t("Download my file")) : "")),
      c.can_submit_to_office ? h("p", {}, h("button", {onclick: run(async () => { await api("submit_to_office", {case: name}, true); toast(t("Sent to our office for review")); caseView(name); })}, t("Send to our office for review"))) : "",
      c.can_approve ? h("div", {class: "ao-card"}, h("h3", {}, t("Please review and approve")), h("p", {}, t("Check all information and documents above. Nothing is submitted until you approve; our staff then submit it on the official website.")),
        c.forms.filter(f => f.approval_mode === "DocuSeal Signature").map(f => h("p", {}, f.form_template, ": ", t(f.signature_status), " ", f.signature_status !== "Signed" ? h("button", {class: "secondary", onclick: run(async () => { const r = await api("get_signing_url", {case: name, form_approval: f.name}, true); window.location.href = r.url; })}, t("Sign")) : "")),
        c.approval_status === "Approved" ? h("p", {class: "ao-ok"}, t("You approved this information. We are waiting for the signature above to be completed.")) : [
        h("label", {}, h("input", {type: "checkbox", id: "ao-confirm"}), " ", t("I confirm the information is correct and complete")),
        h("button", {onclick: run(async () => { await api("approve_case", {case: name, statement_accepted: +document.getElementById("ao-confirm").checked}, true); caseView(name); })}, t("Approve")),
        h("button", {class: "secondary", onclick: run(async () => { const m = prompt(t("What needs to change?")); if (m) { await api("request_changes", {case: name, message: m}, true); caseView(name); } })}, t("Request changes"))]) : "",
      c.submission ? h("div", {class: "ao-card"}, h("h3", {}, t("Submission record")), h("p", {}, tn("Our staff recorded a submission on {0} via {1}. Confirmation reference: {2}. This does not mean the application was accepted or selected.", c.submission.submitted_on, c.submission.portal, c.submission.confirmation)), c.submission.update ? h("p", {}, c.submission.update) : "",
        c.submission.receipt_available ? h("a", {href: "/api/method/" + M + "download_receipt?case=" + encodeURIComponent(name)}, t("Download receipt")) : "") : "",
      h("h3", {}, t("Messages")),
      c.messages.map(m => h("div", {class: "ao-msg " + m.direction.toLowerCase()}, (m.direction === "Staff" ? t("Office:") : t("You:")) + " ", m.body)),
      (() => { const ta = h("textarea", {maxlength: 5000, dir: "auto"}); return h("div", {}, ta, h("button", {class: "secondary", onclick: run(async () => { await api("send_message", {case: name, body: ta.value}, true); caseView(name); })}, t("Send message"))); })(),
      c.invoices.length ? [h("h3", {}, t("Invoices for this case")), c.invoices.map(i => h("div", {}, bdi(i.name), " — ", bdi(i.grand_total + " " + i.currency), " — ", i.status))] : "");
  }
  start().catch(e => { root.textContent = tx("Could not load the portal: {0}", e.message); });
})();
