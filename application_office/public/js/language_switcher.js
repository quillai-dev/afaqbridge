/* Desk language switch (AR <-> EN). Invoked by the two "Navbar Settings > Settings dropdown" items that
 * apply_branding_and_language() creates. Saves the choice on the User (server side) and reloads the SAME URL.
 * If the open form has unsaved changes the user is asked first, so no work is lost silently. */
window.application_office = window.application_office || {};
application_office.switch_language = function (lang) {
	const current = frappe.boot && frappe.boot.lang;
	if (current === lang) return;
	const dirty = window.cur_frm && cur_frm.is_dirty && cur_frm.is_dirty();
	const go = () =>
		frappe
			.call({ method: "application_office.localization.set_language", args: { lang }, freeze: true })
			.then(() => {
				document.cookie = "preferred_language=" + lang + "; path=/; max-age=31536000; samesite=lax";
				window.location.reload();
			});
	if (dirty) {
		frappe.confirm(__("You have unsaved changes. Switch language anyway?"), go);
	} else {
		go();
	}
};
