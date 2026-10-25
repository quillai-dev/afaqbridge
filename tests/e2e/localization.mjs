// Browser regression test: Arabic-first, RTL, language switching (public pages + customer portal + desk).
// Run: BASE_URL=http://afaqbridge.localhost:8088 ADMIN_PASSWORD=... node tests/e2e/localization.mjs   (needs puppeteer-core + @sparticuz/chromium)
import chromium from '@sparticuz/chromium';
import puppeteer from 'puppeteer-core';
import fs from 'node:fs';

const BASE = process.env.BASE_URL || 'http://afaqbridge.localhost:8000';
const PASS = process.env.ADMIN_PASSWORD || '';
const OUT = process.env.SHOTS || '/tmp/loc-shots'; fs.mkdirSync(OUT, {recursive: true});
const results = [];
const check = (name, ok, detail = '') => { results.push([name, !!ok]); console.log((ok ? 'PASS ' : 'FAIL ') + name + (detail ? '  -> ' + detail : '')); };
const browser = await puppeteer.launch({args: [...chromium.args.filter(a => !/single-process|no-zygote/.test(a)), '--lang=en-US', '--disable-dev-shm-usage'], executablePath: await chromium.executablePath(), headless: 'shell'});

async function fresh() {            // new incognito context = a first-time visitor whose browser asks for ENGLISH
  const ctx = await browser.createBrowserContext(); const p = await ctx.newPage();
  await p.setViewport({width: 1100, height: 800}); await p.setExtraHTTPHeaders({'Accept-Language': 'en-US,en;q=0.9'});
  p.setDefaultTimeout(20000); return [ctx, p];
}
const dirInfo = (p) => p.evaluate(() => ({dir: document.documentElement.dir, lang: document.documentElement.lang, bodyDir: getComputedStyle(document.body).direction}));
const settle = (p) => p.waitForNetworkIdle({idleTime: 600, timeout: 15000}).catch(() => {});

try {
  // ---------- 1. login page, first visit, English browser
  let [ctx, p] = await fresh();
  await p.goto(BASE + '/login', {waitUntil: 'networkidle2'});
  let d = await dirInfo(p);
  check('fresh visitor with English browser gets Arabic + RTL (login)', d.dir === 'rtl' && d.lang === 'ar' && d.bodyDir === 'rtl', JSON.stringify(d));
  const h = await p.evaluate(() => document.querySelector('.page-card-head, h4, h1')?.textContent.trim());
  check('login heading is Arabic', /[\u0600-\u06FF]/.test(h || ''), h);
  check('login page shows AfaqBridge logo', await p.evaluate(() => [...document.images].some(i => /afaqbridge/.test(i.src))));
  await p.screenshot({path: `${OUT}/login-ar.png`});
  const picker = await p.evaluate(() => { const s = document.querySelector('#language-switcher select'); return s ? {opts: [...s.options].map(o => o.value), val: s.value} : null; });
  check('language picker offers exactly ar + en, preselected ar', picker && picker.opts.sort().join() === 'ar,en' && picker.val === 'ar', JSON.stringify(picker));

  // ---------- 2. switch to English through the picker, same URL
  await Promise.all([p.waitForNavigation({waitUntil: 'networkidle2'}), p.select('#language-switcher select', 'en')]);
  d = await dirInfo(p);
  check('picker -> English renders LTR', d.dir === 'ltr' && d.lang === 'en' && d.bodyDir === 'ltr', JSON.stringify(d));
  check('English login heading is English', /login|sign/i.test(await p.evaluate(() => document.body.innerText)));
  check('URL stayed /login', new URL(p.url()).pathname === '/login', p.url());
  await p.screenshot({path: `${OUT}/login-en.png`});
  await p.reload({waitUntil: 'networkidle2'}); d = await dirInfo(p);
  check('English choice persists after reload', d.lang === 'en' && d.dir === 'ltr');
  await Promise.all([p.waitForNavigation({waitUntil: 'networkidle2'}), p.select('#language-switcher select', 'ar')]);
  d = await dirInfo(p); check('picker -> Arabic again', d.lang === 'ar' && d.dir === 'rtl');
  await ctx.close();

  // ---------- 3. customer portal
  [ctx, p] = await fresh();
  await p.goto(BASE + '/office-portal', {waitUntil: 'networkidle2'});
  await p.waitForSelector('#ao-app h2');
  d = await dirInfo(p);
  const txt = await p.$eval('#ao-app', e => e.innerText);
  check('portal first visit: Arabic + RTL', d.dir === 'rtl' && d.lang === 'ar' && /تسجيل الدخول أو إنشاء حساب/.test(txt), JSON.stringify(d));
  check('portal has no leftover English UI text', !/Sign in or register|Create an account|Full name|Register/.test(txt), txt.slice(0, 120).replace(/\n/g, ' | '));
  check('email input is LTR inside RTL page', await p.$eval('#f-email', e => getComputedStyle(e).direction) === 'ltr');
  check('portal AR/EN switch visible', (await p.$$('.ao-langbar button')).length === 2);
  await p.screenshot({path: `${OUT}/portal-ar.png`});
  // unsaved work is protected
  await p.type('#f-name', 'Test User'); let dialogs = 0;
  p.once('dialog', async (dl) => { dialogs++; await dl.dismiss(); });
  await p.evaluate(() => [...document.querySelectorAll('.ao-lang')].find(b => b.lang === 'en').click()); await new Promise(r => setTimeout(r, 800));
  check('switching with unsaved input asks first; Cancel keeps Arabic + the typed text', dialogs === 1 && (await dirInfo(p)).lang === 'ar' && await p.$eval('#f-name', e => e.value) === 'Test User');
  p.once('dialog', async (dl) => { await dl.accept(); });
  await Promise.all([p.waitForNavigation({waitUntil: 'networkidle2'}), p.evaluate(() => [...document.querySelectorAll('.ao-lang')].find(b => b.lang === 'en').click())]);
  await p.waitForSelector('#ao-app h2'); d = await dirInfo(p); const en = await p.$eval('#ao-app', e => e.innerText);
  check('portal -> English: LTR, English text, same URL', d.dir === 'ltr' && /Sign in or register/.test(en) && new URL(p.url()).pathname === '/office-portal', JSON.stringify(d));
  await p.screenshot({path: `${OUT}/portal-en.png`});
  await ctx.close();

  // ---------- 4. desk (needs a completed setup + admin password)
  if (PASS) {
    [ctx, p] = await fresh();
    await p.goto(BASE + '/login', {waitUntil: 'networkidle2'});
    await p.type('#login_email', 'Administrator'); await p.type('#login_password', PASS);
    await Promise.all([p.waitForNavigation({waitUntil: 'networkidle2'}).catch(() => {}), p.keyboard.press('Enter')]);
    await p.goto(BASE + '/app/ao-application-case', {waitUntil: 'networkidle2'}); await settle(p);
    const boot = await p.evaluate(() => ({lang: window.frappe?.boot?.lang, dir: document.documentElement.dir, path: location.pathname}));
    check('desk after login: Arabic + RTL', boot.lang === 'ar' && boot.dir === 'rtl', JSON.stringify(boot));
    await p.screenshot({path: `${OUT}/desk-ar.png`});
    const title = await p.evaluate(() => document.title); check('desk title mentions AfaqBridge or Arabic doctype name', /AfaqBridge|ملف طلب/.test(title), title);
    const ws = await p.evaluate(async () => { for (let i = 0; i < 30; i++) { if (frappe.realtime?.socket?.connected) return true; await new Promise(r => setTimeout(r, 300)); } return false; });
    check('WebSocket (socket.io) connected from the desk', ws);
    const sw = await p.evaluate(() => typeof application_office !== 'undefined' && typeof application_office.switch_language);
    check('desk language switch function loaded', sw === 'function');
    await Promise.all([p.waitForNavigation({waitUntil: 'networkidle2'}), p.evaluate(() => application_office.switch_language('en'))]); await settle(p);
    const en2 = await p.evaluate(() => ({lang: frappe.boot.lang, dir: document.documentElement.dir, path: location.pathname}));
    check('desk -> English: LTR and SAME page', en2.lang === 'en' && en2.dir === 'ltr' && en2.path === boot.path, JSON.stringify(en2));
    await p.screenshot({path: `${OUT}/desk-en.png`});
    await Promise.all([p.waitForNavigation({waitUntil: 'networkidle2'}), p.evaluate(() => application_office.switch_language('ar'))]);
    check('desk -> Arabic again', (await p.evaluate(() => frappe.boot.lang)) === 'ar');
    await ctx.close();
  } else console.log('SKIP desk checks (ADMIN_PASSWORD not set)');
} catch (e) { check('test run completed without exception', false, e.stack.split('\n').slice(0, 3).join(' ')); }
await browser.close();
const failed = results.filter(r => !r[1]).length;
console.log(`\n${results.length - failed}/${results.length} checks passed; screenshots in ${OUT}`);
process.exit(failed ? 1 : 0);
