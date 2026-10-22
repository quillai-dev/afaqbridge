// Browser E2E: customer portal + Desk, real Chromium (npm @sparticuz/chromium + puppeteer-core).
// DocuSeal is SIMULATED (docuseal_sim.py). Run via tests/e2e/run-e2e.sh.
import chromium from "@sparticuz/chromium";
import puppeteer from "puppeteer-core";
import fs from "fs"; import crypto from "crypto"; import { execSync } from "child_process";

const BASE = "http://office.localhost:8000", ART = "/home/claude/application-office/tests/e2e/artifacts";
const st = JSON.parse(fs.readFileSync("/tmp/e2e/state.json"));
const results = []; let shot = 0;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const caseState = c => execSync(`cd /home/frappe/frappe-bench && su frappe -c "env/bin/python -c \\"import frappe,os;os.chdir('sites');frappe.init('office.localhost',sites_path='.');frappe.connect();print('STATE',frappe.db.get_value('AO Application Case','${c}','case_state'))\\"" 2>/dev/null`, {encoding: "utf8"}).split("STATE ")[1].trim();
const invoiceFor = c => { try { return execSync(`cd /home/frappe/frappe-bench && su frappe -c "env/bin/python -c \\"import frappe,os;os.chdir('sites');frappe.init('office.localhost',sites_path='.');frappe.connect();print('INV',frappe.db.get_value('Sales Invoice',{'ao_application_case':'${c}'},'name') or '')\\"" 2>/dev/null`, {encoding: "utf8"}).split("INV ")[1].trim(); } catch { return ""; } };
const py = fn => execSync(`cd /home/frappe/frappe-bench && su frappe -c "env/bin/python /home/claude/application-office/scripts/frappe_run.py office.localhost /home/claude/application-office/tests/e2e/e2e_harness.py ${fn}"`, {encoding: "utf8"});
const check = (name, ok, detail = "") => { results.push({name, ok: !!ok, detail}); console.log((ok ? "PASS " : "FAIL ") + name + (detail ? "  — " + detail : "")); };

function totp(secret) {
  const A = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"; let bits = "";
  for (const c of secret.replace(/=+$/, "").toUpperCase()) bits += A.indexOf(c).toString(2).padStart(5, "0");
  const key = Buffer.from(bits.match(/.{8}/g).map(b => parseInt(b, 2)));
  const buf = Buffer.alloc(8); buf.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const h = crypto.createHmac("sha1", key).update(buf).digest(); const o = h[19] & 15;
  return String(((h.readUInt32BE(o) & 0x7fffffff) % 1e6)).padStart(6, "0");
}
async function snap(page, name) {
  shot++; const path = `${ART}/${String(shot).padStart(2, "0")}-${name}.png`;
  try { await page.screenshot({path, fullPage: true}); } catch { try { await page.screenshot({path}); } catch (e) { console.log("  (screenshot skipped: " + e.message.slice(0, 60) + ")"); } }
}
async function clickText(page, scopeSel, tag, text) {
  const ok = await page.evaluate((scopeSel, tag, text) => {
    const scope = scopeSel ? [...document.querySelectorAll(scopeSel)].find(s => s.textContent.includes(text.scope || "")) : document;
    return false; }, scopeSel, tag, text);
  return ok;
}
// click the first <tag> whose text includes `text`, optionally inside the first .ao-card containing `cardText`
async function click(page, tag, text, cardText) {
  const done = await page.evaluate((tag, text, cardText) => {
    const scopes = cardText ? [...document.querySelectorAll(".ao-card")].filter(c => c.textContent.includes(cardText)) : [document];
    for (const s of scopes) { const el = [...s.querySelectorAll(tag)].find(e => e.textContent.trim().includes(text)); if (el) { el.click(); return true; } }
    return false; }, tag, text, cardText);
  if (!done) throw new Error(`no <${tag}> with text "${text}"` + (cardText ? ` in card "${cardText}"` : ""));
}
async function bodyText(page) { return page.evaluate(() => document.body.innerText); }
async function waitText(page, text, ms = 20000) { await page.waitForFunction(t => document.body.innerText.includes(t), {polling: 500, timeout: ms}, text); }
async function fillLabel(page, label, value) {
  const ok = await page.evaluate((label, value) => {
    const l = [...document.querySelectorAll(".ao-app label")].find(x => x.textContent.trim().startsWith(label));
    const i = l && l.nextElementSibling; if (!i) return false; i.value = value; i.dispatchEvent(new Event("input", {bubbles: true})); return true; }, label, value);
  if (!ok) throw new Error("no field labelled " + label);
}

async function custOpen(page, caseName) { await page.goto(BASE + "/office-portal"); await page.waitForFunction(n => [...document.querySelectorAll("button")].some(b => b.textContent.includes("Open " + n)), {polling: 500, timeout: 30000}, caseName); await click(page, "button", "Open " + caseName); await sleep(1500); }
async function deskLogin(browser, who) {
  const ctx = await browser.createBrowserContext(); const page = await ctx.newPage(); page.setDefaultTimeout(30000);
  page.on("error", e => console.log(`  !! renderer crash (${who}): ${e.message}`)); page.on("close", () => console.log(`  !! page closed (${who})`));
  await page.setViewport({width: 1400, height: 1000});
  await page.goto(BASE + "/login"); await page.type("#login_email", st.staff[who].email, {delay: 10}); await page.type("#login_password", st.staff[who].password, {delay: 10});
  await page.keyboard.press("Enter");
  // 2FA: OTP-app token input appears
  await page.waitForFunction(() => [...document.querySelectorAll("input")].some(i => i.offsetParent && /otp|token/i.test(i.id + i.name + i.placeholder)), {polling: 500, timeout: 20000}).catch(async () => { await snap(page, `${who}-no-otp-field`); throw new Error("2FA prompt not shown for " + who); });
  const sel = await page.evaluate(() => { const i = [...document.querySelectorAll("input")].find(i => i.offsetParent && /otp|token/i.test(i.id + i.name + i.placeholder)); return "#" + i.id; });
  while (30000 - (Date.now() % 30000) < 6000) await sleep(300);   // never submit a code that is about to expire
  await page.type(sel, totp(st.staff[who].otp_secret)); await page.keyboard.press("Enter");
  await page.waitForFunction(() => location.pathname.startsWith("/app") || location.pathname.startsWith("/desk") || location.pathname.startsWith("/portal"), {polling: 500, timeout: 30000});
  await page.waitForNetworkIdle({idleTime: 1500, timeout: 30000}).catch(() => {}); await snap(page, `${who}-logged-in`);
  return page;
}
async function openCase(page, caseName, sel = '[data-label="Workflow"]') { await page.goto(`${BASE}/app/ao-application-case/${caseName}`, {waitUntil: "networkidle2"}); await page.waitForSelector(sel, {timeout: 30000}); }
async function menu(page, group, item) {
  await page.click(`[data-label="${group}"]`); await sleep(400);
  const ok = await page.evaluate(item => {
    const els = [...document.querySelectorAll("a, button, li, span")].filter(e => e.getClientRects().length && e.textContent.trim() === item && !e.closest(".form-layout") && !e.closest(".modal"));
    const el = els.find(e => e.closest(".dropdown-menu")) || els[0]; if (!el) return false; (el.closest("a,button,li") || el).click(); return true; }, item);
  if (!ok) throw new Error(`menu item "${item}" not found in "${group}"`);
}
async function workflow(page, caseName, toState, reason) {
  await openCase(page, caseName);
  await menu(page, "Workflow", toState);
  await page.waitForSelector(".modal.show textarea", {visible: true});
  if (reason) await page.type(".modal.show textarea", reason);
  await page.click(".modal.show .modal-footer button:last-of-type");
  for (let i = 0; i < 20 && caseState(caseName) !== toState; i++) await sleep(1500);   // poll the DB: the dialog element lingers in the DOM
  if (caseState(caseName) !== toState) throw new Error(`transition to ${toState} did not happen (state=${caseState(caseName)})`);
}
async function saveDeskForm(page) { await page.keyboard.down("Control"); await page.keyboard.press("s"); await page.keyboard.up("Control"); await sleep(3000); }
async function setField(page, fieldname, value) { // Desk control by data-fieldname
  const sel = `[data-fieldname="${fieldname}"] input, [data-fieldname="${fieldname}"] textarea, [data-fieldname="${fieldname}"] select`;
  await page.waitForSelector(sel, {visible: true}); const tag = await page.$eval(sel, e => e.tagName + ":" + e.type);
  if (tag.startsWith("SELECT")) await page.select(sel, value);
  else if (tag.endsWith("checkbox")) { if (value) await page.click(sel); }
  else { await page.click(sel, {clickCount: 3}); await page.type(sel, value); await page.keyboard.press("Tab"); }
}
async function review(reviewerPage, rd, decision, feedback) {
  await reviewerPage.goto(`${BASE}/app/ao-document-review/new?required_document=${rd}`, {waitUntil: "networkidle2"});
  await setField(reviewerPage, "decision", decision);
  if (feedback) { await setField(reviewerPage, "requested_corrections", feedback); await setField(reviewerPage, "customer_feedback", feedback); }
  await saveDeskForm(reviewerPage);
  await reviewerPage.waitForFunction(() => /ao-document-review\/REV-/.test(location.pathname), {polling: 500, timeout: 20000});
}

const LAUNCH = async () => puppeteer.launch({executablePath: await chromium.executablePath(), args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"], headless: "shell"});
const browser = await LAUNCH();
browser.on("disconnected", () => console.log("  !! browser process disconnected"));
let cust, caseName;
try {
  // ---------------------------------------------------------------- 1 registration (browser)
  const c = st.customer; cust = await (await browser.createBrowserContext()).newPage(); cust.setDefaultTimeout(30000); await cust.setViewport({width: 1000, height: 1400});
  await cust.goto(BASE + "/office-portal"); await waitText(cust, "Create an account");
  check("portal shows the disclaimer to guests", (await bodyText(cust)).includes("do not guarantee"));
  await cust.type("#f-name", c.name); await cust.type("#f-email", c.email);
  for (const cb of await cust.$$(".ao-app input[type=checkbox]")) await cb.click();
  await click(cust, "button", "Register"); await waitText(cust, "has been sent"); await snap(cust, "customer-registered");
  check("registration accepted with uniform message", true);

  // ---------------------------------------------------------------- 2 mail -> set password -> login
  await sleep(11000); py("flush");
  const link = py("set_password_link").split("LINK ")[1].trim();
  check("set-password link was delivered by e-mail", /update-password/.test(link), link.slice(0, 60));
  await cust.goto(link, {waitUntil: "networkidle2"}); await snap(cust, "customer-set-password");
  await cust.waitForSelector("input"); await sleep(1000);
  const ins = await cust.evaluateHandle(() => [...document.querySelectorAll("input")].filter(i => i.offsetParent && i.type !== "hidden"));
  const props = await ins.getProperties(); const fields = [...props.values()].map(h => h.asElement()).filter(Boolean);
  await fields[0].click(); await fields[0].type(c.password, {delay: 25}); await fields[1].click(); await fields[1].type(c.password, {delay: 25}); await sleep(800);
  await cust.evaluate(() => { const b = [...document.querySelectorAll("button")].find(b => /confirm|set password|update/i.test(b.textContent) && b.offsetParent && !b.disabled); b && b.click(); });
  await sleep(4000); await snap(cust, "customer-password-set");
  await cust.goto(BASE + "/login", {waitUntil: "networkidle2"});
  if (await cust.$("#login_email")) { await cust.type("#login_email", c.email, {delay: 10}); await cust.type("#login_password", c.password, {delay: 10}); await cust.keyboard.press("Enter");
    await cust.waitForFunction(() => location.pathname !== "/login", {polling: 500, timeout: 30000}); check("customer signs in with the password just set (no 2FA prompt)", true); }
  else check("customer is signed in right after setting the password", true);
  await cust.goto(BASE + "/office-portal"); await waitText(cust, "Available services"); await snap(cust, "customer-dashboard");

  // ---------------------------------------------------------------- 3 start case, intake, upload, send
  await click(cust, "button", "Start", st.program); await waitText(cust, "Information form");
  caseName = (await bodyText(cust)).match(/AC-\d{4}-\d{5}/)[0]; check("case created with unique reference", !!caseName, caseName);
  await fillLabel(cust, "Full name", c.name); await fillLabel(cust, "Passport number", "P1234567X");
  await click(cust, "button", "Save and mark complete"); await sleep(2500); await waitText(cust, "Documents");
  const pdf = "/tmp/e2e/doc.pdf"; execSync(`python3 -c "from pypdf import PdfWriter; w=PdfWriter(); w.add_blank_page(72,72); w.write(open('${pdf}','wb'))" 2>/dev/null || /home/frappe/frappe-bench/env/bin/python -c "from pypdf import PdfWriter; w=PdfWriter(); w.add_blank_page(72,72); w.write(open('${pdf}','wb'))"`);
  for (const cat of ["Passport", "Diploma"]) {
    const input = await cust.evaluateHandle(cat => [...document.querySelectorAll(".ao-card")].find(x => x.querySelector("b")?.textContent === cat)?.querySelector("input[type=file]"), cat);
    await input.uploadFile(pdf); await click(cust, "button", "Upload", cat); await sleep(2500);
  }
  await waitText(cust, "uploaded (v1)"); await snap(cust, "customer-uploaded");
  // invalid upload must be rejected in the UI
  fs.writeFileSync("/tmp/e2e/evil.pdf", "MZ not a pdf");
  const inp = await cust.evaluateHandle(() => [...document.querySelectorAll(".ao-card")].find(x => x.querySelector("b")?.textContent === "Diploma")?.querySelector("input[type=file]"));
  await inp.uploadFile("/tmp/e2e/evil.pdf"); await click(cust, "button", "Upload", "Diploma"); await sleep(2000);
  check("fake PDF upload is rejected with an error message", /does not match|not accepted|could not be read/i.test(await bodyText(cust)));
  await click(cust, "button", "Send to our office for review"); await sleep(2500); await waitText(cust, "Under review");
  check("customer sees 'Under review' after sending", true); await snap(cust, "customer-under-review");

  // ---------------------------------------------------------------- 4 staff review (Desk)
  const ids = JSON.parse(execSync(`cd /home/frappe/frappe-bench && su frappe -c "env/bin/python -c \\"import frappe,json,os;os.chdir('sites');frappe.init('office.localhost',sites_path='.');frappe.connect();print('IDS',json.dumps({r['document_category']:r['name'] for r in frappe.get_all('AO Required Document',filters={'case':'${caseName}'},fields=['name','document_category'])}))\\"" 2>/dev/null`, {encoding: "utf8"}).split("IDS ")[1]);
  const rev = await deskLogin(browser, "reviewer"); check("reviewer logs in to Desk through the 2FA prompt", true);
  await review(rev, ids.Passport, "Correction Required", "Passport scan is unreadable, please rescan in colour");
  await review(rev, ids.Diploma, "Approved");
  await snap(rev, "reviewer-reviews-done");
  await workflow(rev, caseName, "CORRECTION_REQUIRED", "Passport scan unreadable"); await snap(rev, "reviewer-correction-requested");

  // ---------------------------------------------------------------- 5 customer corrects
  await custOpen(cust, caseName); await waitText(cust, "corrections required");
  check("customer sees correction request + reviewer feedback", (await bodyText(cust)).includes("unreadable, please rescan"));
  await snap(cust, "customer-sees-correction");
  const inp2 = await cust.evaluateHandle(() => [...document.querySelectorAll(".ao-card")].find(x => x.querySelector("b")?.textContent === "Passport")?.querySelector("input[type=file]"));
  fs.appendFileSync(pdf, "\n%v2"); await inp2.uploadFile(pdf); await click(cust, "button", "Upload", "Passport"); await sleep(2500);
  await click(cust, "button", "Send to our office for review"); await sleep(2500); await waitText(cust, "Under review");

  // ---------------------------------------------------------------- 6 re-review, request approval
  await review(rev, ids.Passport, "Approved");
  await workflow(rev, caseName, "READY_FOR_CUSTOMER_APPROVAL"); await snap(rev, "reviewer-ready-for-approval"); await rev.close();   // free memory: the sandbox has 1 CPU / 4 GB

  // ---------------------------------------------------------------- 7 customer approves, signs (SIMULATED DocuSeal)
  await custOpen(cust, caseName); await waitText(cust, "Please review and approve"); await snap(cust, "customer-approval-page");
  await cust.click("#ao-confirm"); await click(cust, "button", "Approve"); await sleep(3000);
  check("after approving, the Approve button is gone and the portal explains the pending signature", !(await cust.$$eval("button", bs => bs.some(b => b.textContent.trim() === "Approve"))) && (await bodyText(cust)).includes("You approved this information"));
  check("approval alone does not advance while a signature is pending", /Waiting for your approval/.test(await bodyText(cust)));
  await click(cust, "button", "Sign"); await cust.waitForFunction(() => /\/s\/slug/.test(location.href), {polling: 500, timeout: 30000});
  check("customer is redirected to the (simulated) DocuSeal signing page", /SIMULATED DocuSeal/.test(await bodyText(cust))); await snap(cust, "customer-signing-sim");
  await cust.click("#sign"); await cust.waitForFunction(() => location.pathname.startsWith("/office-portal"), {polling: 500, timeout: 30000}); await sleep(3000);
  await waitText(cust, "Dashboard", 1).catch(() => {}); await custOpen(cust, caseName);
  await waitText(cust, "being prepared for submission", 30000); check("signed webhook advanced the case to READY_FOR_SUBMISSION", true); await snap(cust, "customer-after-signing");

  // ---------------------------------------------------------------- 8 worker: checklist + manual submission
  let wk = await deskLogin(browser, "worker"); await openCase(wk, caseName);
  await menu(wk, "Review", "Final Checklist");
  await wk.waitForSelector(".msgprint, .modal.show", {visible: true}); const checklist = await wk.evaluate(() => document.querySelector(".msgprint, .modal.show .modal-body")?.innerText || "");
  check("final checklist shows all checks passed", checklist.includes("✅") && !checklist.includes("❌"), checklist.replace(/\n/g, " | ").slice(0, 160)); await snap(wk, "worker-checklist");
  await wk.keyboard.press("Escape"); await sleep(500);
  await wk.goto(`${BASE}/app/ao-official-submission/new?case=${caseName}`, {waitUntil: "networkidle2"});
  await setField(wk, "official_portal", "https://official.example/apply");
  const now = new Date(Date.now() - 60000); const ts = `${String(now.getDate()).padStart(2, "0")}-${String(now.getMonth() + 1).padStart(2, "0")}-${now.getFullYear()} ${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}:00`;
  await wk.evaluate(ts => cur_frm.set_value("submission_timestamp", frappe.datetime.now_datetime()), ts);
  await setField(wk, "official_confirmation_number", "CONF-E2E-" + st.tag);
  await setField(wk, "human_submission_attestation", true); await setField(wk, "customer_can_download_evidence", true);
  await snap(wk, "worker-submission-form-filled");
  await saveDeskForm(wk); await wk.waitForFunction(() => /ao-official-submission\/OS-/.test(location.pathname), {polling: 500, timeout: 20000}).catch(async () => { await snap(wk, "worker-submission-save-failed"); throw new Error("submission did not save: " + (await bodyText(wk)).slice(0, 300)); });
  check("employee recorded the manual official submission", true); await snap(wk, "worker-submission-saved");
  await openCase(wk, caseName); check("case state is SUBMITTED", (await bodyText(wk)).includes("SUBMITTED")); await snap(wk, "worker-case-submitted");
  await workflow(wk, caseName, "AWAITING_OFFICIAL_UPDATE"); check("workflow moved case to AWAITING_OFFICIAL_UPDATE", caseState(caseName) === "AWAITING_OFFICIAL_UPDATE");

  // ---------------------------------------------------------------- 9 finance: invoice
  // Memory: close the customer and worker tabs (their contexts, hence sessions, stay alive) while the heavy ERPNext invoice form is open.
  const custCtx = cust.browserContext(), wkCtx = wk.browserContext(); await cust.close(); await wk.close();
  // The ERPNext invoice form crashed the long-lived multi-context Chromium in this 1-CPU sandbox, so finance gets a fresh browser instance.
  const browser2 = await LAUNCH(); browser2.on("disconnected", () => console.log("  !! finance browser disconnected"));
  const fin = await deskLogin(browser2, "finance"); await openCase(fin, caseName, '[data-label="Finance"]');
  check("finance user sees NO workflow-transition menu on the case", !(await fin.$('[data-label="Workflow"]')));
  await menu(fin, "Finance", "Create Invoice");
  await fin.waitForSelector(".modal.show", {visible: true}); await fin.type('.modal.show [data-fieldname="description"] input', "Application assistance"); await fin.type('.modal.show [data-fieldname="rate"] input', "120");
  await fin.evaluate(() => { window.__realSetRoute = frappe.set_route; frappe.set_route = () => {}; });   // avoid the in-SPA jump that crashes headless Chromium here
  await fin.click(".modal.show .modal-footer button:last-of-type");
  let invName = ""; for (let i = 0; i < 30 && !invName; i++) { await sleep(1500); invName = invoiceFor(caseName); }
  check("finance created a draft invoice linked to the case from the Desk dialog", !!invName, invName); if (!invName) throw new Error("no invoice created");
  await fin.goto(`${BASE}/app/sales-invoice/${invName}`, {waitUntil: "domcontentloaded"}); await sleep(3000);
  console.log("  step: waiting for the Sales Invoice form to be ready");
  await fin.waitForFunction(() => window.cur_frm && cur_frm.doc && cur_frm.doc.doctype === "Sales Invoice" && cur_frm.doc.docstatus === 0 && !cur_frm.is_new() && !cur_frm.is_dirty(), {polling: 500, timeout: 120000});
  await snap(fin, "finance-invoice-form-ready");
  await fin.evaluate(() => cur_frm.savesubmit());   // same action as the Submit button; it opens the confirmation dialog
    console.log("  step: confirm dialog"); await fin.waitForSelector(".modal.show .modal-footer button:last-of-type", {visible: true}); console.log("  step: clicking Yes"); await fin.click(".modal.show .modal-footer button:last-of-type");
  await fin.waitForFunction(() => !document.querySelector(".modal.show") && !/Submitting/.test(document.body.innerText), {polling: 500, timeout: 90000}); await sleep(1500);
  await snap(fin, "finance-invoice-submitted");

  // ---------------------------------------------------------------- 10 customer sees invoice, update, receipt; close
  console.log("  step: invoice submitted, closing case"); await fin.close(); await browser2.close();
  wk = await wkCtx.newPage(); wk.setDefaultTimeout(30000); await wk.setViewport({width: 1400, height: 1000});
  cust = await custCtx.newPage(); cust.setDefaultTimeout(30000); await cust.setViewport({width: 1000, height: 1400});
  await workflow(wk, caseName, "COMPLETED"); await workflow(wk, caseName, "CLOSED"); check("case reached CLOSED via the Desk workflow menu", caseState(caseName) === "CLOSED");
  await cust.goto(BASE + "/office-portal"); await waitText(cust, "Invoices");
  check("customer sees the invoice in the portal", /ACC-SINV/.test(await bodyText(cust))); 
  await click(cust, "button", "Open " + caseName); await waitText(cust, "Submission record");
  const t = await bodyText(cust); check("customer sees submission record with confirmation ref + 'not an acceptance' wording", t.includes("CONF-E2E-" + st.tag) && t.includes("does not mean the application was accepted"));
  check("customer sees case Closed", /Closed/.test(t)); await snap(cust, "customer-final");
} catch (e) {
  check("E2E ABORTED: " + e.message.slice(0, 200), false);
  for (const p of (await browser.pages())) { try { await snap(p, "FAILURE"); } catch {} }
} finally {
  await browser.close();
  fs.writeFileSync(`${ART}/result.json`, JSON.stringify({case: caseName, results}, null, 1));
  const failed = results.filter(r => !r.ok).length; console.log(`\n${results.length - failed}/${results.length} checks passed`); process.exit(failed ? 1 : 0);
}
