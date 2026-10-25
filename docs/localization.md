# Arabic-first localisation

**Mechanisms used (all Frappe-native):** System Settings → language `ar`; `Language` records (only `ar`, `en` enabled); gettext catalogue
`apps/application_office/application_office/locale/ar.po` (merged with Frappe's and ERPNext's official `ar.po`); `preferred_language` cookie; per-user `User.language`;
Website Settings → *Show Language Picker*; Navbar Settings dropdown items (AR / EN). Frappe flips layout to RTL itself (`<html dir="rtl">` + its `*-rtl` bundles).

**The one custom behaviour** (`localization.py`): stock Frappe prefers the browser's `Accept-Language` over System Settings for anonymous visitors, so an English
browser would open in English. `before_request` makes Arabic the *initial* language of a guest who has no cookie and no `?_lang=`, and sets the cookie so
Frappe's language picker shows the language actually rendered. An explicit choice is never overridden. New `User` records default to the visitor's current language, else Arabic.

**Customer portal** (`/office-portal`): its JS contains no Arabic. Every string is a `_()` literal in `portal_strings.py` → `ar.po`; the server embeds `{english: translated}` for
the current language; identifiers, e-mails, dates and URLs are wrapped in `<bdi>` so they keep their direction inside Arabic sentences. AR/EN switch at the top: same URL,
page reload, confirmation if form input would be lost. Desk: AR/EN items in the user menu (`application_office.switch_language`), which saves `User.language` and reloads the same page
(asks first when the open form has unsaved changes). E-mails use `<event>-ar` / `<event>-en` templates chosen by the customer's language.

**Translation coverage:** 464 strings translated for this app + 13 gap-fills for strings missing from Frappe's official Arabic file (login/forgot-password pages).
**The Arabic was written by the developer assistant and has NOT been reviewed by a professional translator** - have it reviewed. Regenerate the catalogue source list with `python scripts/extract_messages.py`.
`apply_branding_and_language()` (also run after every `bench migrate`) enables the languages, sets Arabic default and branding, and replaces only *stock* values, never administrator edits.

## Known limitations (do not claim otherwise)
- Text stored in the database is one language only: AO Settings disclaimer/consent text (translated automatically only while unchanged), program names/descriptions, intake field labels, notes, customer-entered data.
- Frappe's login page `<title>` is hard-coded English upstream ("AfaqBridge - Login").
- The internal module is still named "Application Office" (renaming breaks module paths); it shows as "AfaqBridge" in Arabic only. ERPNext's name in the app switcher is kept.
- ERPNext's official Arabic is ~79 % complete, Frappe's ~90 %; untranslated upstream strings stay English. Only 5 desk pages were scanned for English leftovers.
- Calendar widgets (e.g. "Today") come from a library and may stay English. Numbers use Latin digits (`#,###.##`) on purpose, for readability of amounts and identifiers.
- **DocuSeal 3.3.2:** Arabic exists in its locale list, but the language is a *per-account* setting changed in DocuSeal's UI (not an environment variable), so it is not configured by this repo - set it after first login. Its signing form contains RTL handling, but this was **not tested** (only a simulator was available).
- Only Chromium was used; no Firefox/Safari/mobile test.

## Tests
`apps/.../tests/test_localization.py` (12 in-app tests), `tests/e2e/localization.mjs` (21 browser checks), `tests/edge/test_edge_nginx.py` (10 proxy tests; real nginx, mock upstreams), `tests/e2e/chain-native.sh` (sandbox emulation of the Docker chain).
