/* Customer portal. All server-provided text is inserted with textContent (never innerHTML). */
(function () {
  "use strict";
  const root = document.getElementById("ao-app");
  let csrfValue = "";
  const csrf = () => csrfValue;
  const M = "application_office.portal_api.";

  function h(tag, attrs, ...kids) {
    const e = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (k === "class") e.className = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else if (v !== false && v != null) e.setAttribute(k, v);
    });
    kids.flat().forEach(k => e.append(k instanceof Node ? k : document.createTextNode(k == null ? "" : String(k))));
    return e;
  }
  // Children may be Nodes, strings or (nested) arrays of either; flatten and drop empties before touching the DOM.
  const kids = a => a.flat(Infinity).filter(x => x !== "" && x != null && x !== false);
  const add = (...a) => root.append(...kids(a));
  const reset = (...a) => root.replaceChildren(...kids(a));
  function serverMessage(r) {
    try { const m = JSON.parse(r._server_messages || "[]"); return m.map(x => JSON.parse(x).message).join(" ").replace(/<[^>]*>/g, ""); } catch (e) { return ""; }
  }
  async function api(method, args, post, form) {
    const url = "/api/method/" + M + method;
    let res;
    if (!post) res = await fetch(url + (args ? "?" + new URLSearchParams(args) : ""), {credentials: "same-origin"});
    else res = await fetch(url, {method: "POST", credentials: "same-origin", headers: Object.assign({"X-Frappe-CSRF-Token": csrf()}, form ? {} : {"Content-Type": "application/x-www-form-urlencoded"}),
      body: form || new URLSearchParams(args || {})});
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(serverMessage(data) || ("Request failed (" + res.status + ")"));
    return data.message;
  }
  const toast = (t, bad) => { const b = h("div", {class: "ao-msg " + (bad ? "ao-warn" : "ao-ok"), role: "alert"}, t); root.prepend(b); setTimeout(() => b.remove(), 6000); };
  const run = fn => async (...a) => { try { await fn(...a); } catch (e) { toast(e.message, true); } };

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
    const inp = (k, label, type) => h("div", {}, h("label", {for: "f-" + k}, label), f[k] = h("input", {id: "f-" + k, type: type || "text", autocomplete: "off"}));
    const chk = (k, text) => h("label", {}, f[k] = h("input", {type: "checkbox"}), " " + text);
    add(h("h2", {}, "Sign in or register"),
      h("p", {}, h("a", {href: "/login?redirect-to=/office-portal"}, "Sign in to your account")),
      h("div", {class: "ao-card"}, h("h3", {}, "Create an account"), inp("name", "Full name"), inp("email", "E-mail", "email"),
        chk("terms", "I accept the service terms" + (boot.terms_url ? " (" + boot.terms_url + ")" : "")),
        chk("privacy", "I have read the privacy notice" + (boot.privacy_url ? " (" + boot.privacy_url + ")" : "")),
        chk("sens", boot.sensitive_consent_text),
        h("p", {}, h("button", {onclick: run(async () => {
          const r = await api("register", {email: f.email.value, full_name: f.name.value, accept_terms: +f.terms.checked, accept_privacy: +f.privacy.checked, accept_sensitive: +f.sens.checked}, true);
          toast(r.message);
        })}, "Register"))));
  }

  function consentView() {
    add(h("h2", {}, "Please review and accept"), h("div", {class: "ao-card"},
      h("p", {}, "Service terms version " + boot.terms_version + ", privacy notice version " + boot.privacy_version + "."),
      h("p", {}, boot.sensitive_consent_text),
      h("button", {onclick: run(async () => { await api("accept_current_consents", {}, true); start(); })}, "I accept")));
  }

  async function dashboard() {
    const [cases, services, invoices] = await Promise.all([api("list_cases"), api("list_services"), api("list_invoices")]);
    add(h("h2", {}, "Hello, " + boot.user.name),
      h("h3", {}, "Your applications"),
      cases.length ? cases.map(c => h("div", {class: "ao-card"}, h("div", {class: "ao-row"}, h("b", {}, c.program_name), h("span", {class: "ao-badge"}, c.status_label), c.deadline ? h("span", {}, "Deadline on record: " + c.deadline) : ""),
        h("button", {class: "secondary", onclick: () => caseView(c.name)}, "Open " + c.name))) : h("p", {}, "No applications yet."),
      h("h3", {}, "Available services"),
      services.map(s => h("div", {class: "ao-card"}, h("b", {}, s.program_name), " ", h("span", {class: "ao-badge"}, s.category),
        h("p", {}, s.eligibility), s.closing ? h("p", {}, "Closing (as verified by our staff on " + s.last_verified_on + "): " + s.closing) : "",
        s.requirements_url ? h("p", {}, "Official requirements: " + s.requirements_url) : "",
        h("p", {}, "Documents: " + s.documents.map(d => d.category + (d.required ? "" : " (optional)")).join(", ")),
        s.startable ? h("button", {onclick: run(async () => { const r = await api("start_case", {program: s.name}, true); caseView(r.case); })}, "Start") : h("em", {}, s.unavailable_reason))),
      h("h3", {}, "Invoices"),
      invoices.length ? invoices.map(i => h("div", {class: "ao-row"}, i.name, " ", i.grand_total + " " + i.currency, h("span", {class: "ao-badge"}, i.status), i.case || "")) : h("p", {}, "No invoices."),
      h("h3", {}, "Privacy"),
      h("div", {class: "ao-card"}, h("p", {}, "You can request access to, correction of, or erasure of your data, or close your account. Some records must be kept by law."),
        ["Access / Export", "Correction", "Erasure", "Account Closure"].map(t => h("button", {class: "secondary", style: "margin:2px", onclick: run(async () => { await api("data_request", {request_type: t}, true); toast("Request recorded: " + t); })}, t))));
  }

  async function caseView(name) {
    const c = await api("get_case", {case: name});
    const intakeInputs = {};
    reset(h("div", {class: "ao-banner"}, c.disclaimer),
      h("button", {class: "secondary", onclick: start}, "← Back"),
      h("h2", {}, c.program_name + " — " + c.name), h("p", {}, h("span", {class: "ao-badge"}, c.status_label), c.deadline ? "  Deadline on record: " + c.deadline : ""),
      c.customer_visible_notes ? h("div", {class: "ao-card"}, c.customer_visible_notes) : "",
      h("h3", {}, "Information form"),
      h("div", {class: "ao-card"}, c.intake.map(f => h("div", {}, h("label", {}, f.label + (f.required ? " *" : "")),
        intakeInputs[f.field_key] = f.field_type === "Long Text" ? h("textarea", {}, f.value) : f.field_type === "Select" ? h("select", {}, f.options.map(o => h("option", {value: o, selected: o === f.value}, o))) : f.field_type === "Checkbox" ? h("input", {type: "checkbox", checked: f.value ? "checked" : false}) : h("input", {type: f.field_type === "Date" ? "date" : "text", value: f.value, autocomplete: "off"}))),
        c.can_edit ? h("p", {}, h("button", {onclick: run(async () => { await api("save_intake", {case: name, values: JSON.stringify(Object.fromEntries(Object.entries(intakeInputs).map(([k, i]) => [k, i.type === "checkbox" ? i.checked : i.value]))), complete: 1}, true); toast("Saved"); caseView(name); })}, "Save and mark complete")) : ""),
      h("h3", {}, "Documents"),
      c.documents.map(d => h("div", {class: "ao-card"}, h("div", {class: "ao-row"}, h("b", {}, d.document_category), d.required ? "(required)" : "(optional)", h("span", {class: "ao-badge"}, d.upload_status === "Uploaded" ? "uploaded (v" + d.current_version + ") — " + d.review_status : "missing")),
        d.customer_feedback ? h("p", {class: "ao-warn"}, "Feedback: " + d.customer_feedback) : "", d.instructions ? h("small", {}, d.instructions) : "",
        c.can_edit && d.review_status !== "Approved" ? (() => { const fi = h("input", {type: "file", accept: ".pdf,.jpg,.jpeg,.png"}); return h("div", {class: "ao-row"}, fi, h("button", {class: "secondary", onclick: run(async () => { if (!fi.files[0]) throw new Error("Choose a file"); const fd = new FormData(); fd.append("file", fi.files[0]); fd.append("case", name); fd.append("required_document", d.name); await api("upload_document", null, true, fd); toast("Uploaded"); caseView(name); })}, "Upload")); })() : "",
        d.upload_status === "Uploaded" ? h("a", {href: "/api/method/" + M + "download_document?" + new URLSearchParams({case: name, required_document: d.name})}, "Download my file") : "")),
      c.can_submit_to_office ? h("p", {}, h("button", {onclick: run(async () => { await api("submit_to_office", {case: name}, true); toast("Sent to our office for review"); caseView(name); })}, "Send to our office for review")) : "",
      c.can_approve ? h("div", {class: "ao-card"}, h("h3", {}, "Please review and approve"), h("p", {}, "Check all information and documents above. Nothing is submitted until you approve; our staff then submit it on the official website."),
        c.forms.filter(f => f.approval_mode === "DocuSeal Signature").map(f => h("p", {}, f.form_template + ": " + f.signature_status + " ", f.signature_status !== "Signed" ? h("button", {class: "secondary", onclick: run(async () => { const r = await api("get_signing_url", {case: name, form_approval: f.name}, true); window.location.href = r.url; })}, "Sign") : "")),
        c.approval_status === "Approved" ? h("p", {class: "ao-ok"}, "You approved this information. We are waiting for the signature above to be completed.") : [
        h("label", {}, h("input", {type: "checkbox", id: "ao-confirm"}), " I confirm the information is correct and complete"),
        h("button", {onclick: run(async () => { await api("approve_case", {case: name, statement_accepted: +document.getElementById("ao-confirm").checked}, true); caseView(name); })}, "Approve"),
        h("button", {class: "secondary", onclick: run(async () => { const m = prompt("What needs to change?"); if (m) { await api("request_changes", {case: name, message: m}, true); caseView(name); } })}, "Request changes")]) : "",
      c.submission ? h("div", {class: "ao-card"}, h("h3", {}, "Submission record"), h("p", {}, "Our staff recorded a submission on " + c.submission.submitted_on + " via " + c.submission.portal + ". Confirmation reference: " + c.submission.confirmation + ". This does not mean the application was accepted or selected."), c.submission.update ? h("p", {}, c.submission.update) : "",
        c.submission.receipt_available ? h("a", {href: "/api/method/" + M + "download_receipt?case=" + encodeURIComponent(name)}, "Download receipt") : "") : "",
      h("h3", {}, "Messages"),
      c.messages.map(m => h("div", {class: "ao-msg " + m.direction.toLowerCase()}, (m.direction === "Staff" ? "Office: " : "You: ") + m.body)),
      (() => { const t = h("textarea", {maxlength: 5000}); return h("div", {}, t, h("button", {class: "secondary", onclick: run(async () => { await api("send_message", {case: name, body: t.value}, true); caseView(name); })}, "Send message")); })(),
      c.invoices.length ? [h("h3", {}, "Invoices for this case"), c.invoices.map(i => h("div", {}, i.name + " — " + i.grand_total + " " + i.currency + " — " + i.status))] : "");
  }
  start().catch(e => { root.textContent = "Could not load the portal: " + e.message; });
})();
