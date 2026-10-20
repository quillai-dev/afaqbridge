frappe.ui.form.on("AO Application Case", {
  refresh(frm) {
    if (frm.is_new()) return;
    frm.dashboard.add_comment(__("Administrative service only. 'SUBMITTED' means staff recorded a submission, not that the customer was accepted."), "blue", true);
    frappe.call({method: "application_office.staff_api.case_actions", args: {case: frm.doc.name}}).then(r => {
      (r.message.transitions || []).forEach(t => {
        frm.add_custom_button(t.to_state, () => {
          const fields = [{fieldname: "reason", fieldtype: "Small Text", label: __("Reason (shown to the customer for correction/missing-document requests)"), reqd: t.requires_reason}];
          frappe.prompt(fields, v => frappe.call({method: "application_office.staff_api.transition",
            args: {case: frm.doc.name, to_state: t.to_state, reason: v.reason || ""}}).then(() => frm.reload_doc()),
            __("Move to {0}", [t.to_state]));
        }, __("Workflow"));
      });
    });
    frm.add_custom_button(__("Final Checklist"), () => frappe.call({method: "application_office.staff_api.final_checklist", args: {case: frm.doc.name}}).then(r => {
      frappe.msgprint(r.message.map(c => `${c.ok ? "✅" : "❌"} ${frappe.utils.escape_html(c.check)}`).join("<br>"), __("Final review checklist"));
    }), __("Review"));
    frm.add_custom_button(__("Reveal Sensitive Intake (audited)"), () => frappe.call({method: "application_office.staff_api.reveal_intake", args: {case: frm.doc.name}}).then(r => {
      frappe.msgprint(r.message.map(f => `<b>${frappe.utils.escape_html(f.label)}</b>: ${frappe.utils.escape_html(String(f.value))}`).join("<br>"), __("Intake"));
    }), __("Review"));
    if (frm.doc.case_state === "READY_FOR_SUBMISSION") {
      frm.add_custom_button(__("Record Manual Official Submission"), () => frappe.new_doc("AO Official Submission", {case: frm.doc.name}), __("Submission"));
    }
    frm.add_custom_button(__("Add Message"), () => frappe.prompt([
      {fieldname: "visibility", fieldtype: "Select", options: "Internal\nCustomer", default: "Internal", label: __("Visibility")},
      {fieldname: "body", fieldtype: "Long Text", reqd: 1, label: __("Message")}], v =>
      frappe.call({method: "application_office.staff_api.add_message", args: {case: frm.doc.name, ...v}}).then(() => frappe.show_alert(__("Saved"))),
      __("Add message")), __("Communicate"));
    frm.add_custom_button(__("Create Invoice"), () => frappe.prompt([
      {fieldname: "description", fieldtype: "Data", reqd: 1, label: __("Service description")},
      {fieldname: "rate", fieldtype: "Currency", reqd: 1, label: __("Amount")}], v =>
      frappe.call({method: "application_office.staff_api.create_invoice", args: {case: frm.doc.name, items: JSON.stringify([v])}})
        .then(r => frappe.set_route("Form", "Sales Invoice", r.message.invoice)), __("Draft invoice")), __("Finance"));
  },
});
