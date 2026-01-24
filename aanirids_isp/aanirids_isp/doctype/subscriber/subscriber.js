frappe.ui.form.on("Subscriber", {
  refresh(frm) {
    // ✅ Button to sync details manually
    frm.add_custom_button("Sync Details", () => {
      frappe.call({
        method: "aanirids_isp.aanirids_isp.doctype.subscriber.subscriber.fetch_subscriber_details_direct",
        args: { subscriber_name: frm.doc.name },
        callback: function () {
          frappe.msgprint("Details synced ✅");
          frm.reload_doc();
        }
      });
    });

    // ✅ Only auto sync when user refreshes manually
    // (we detect manual refresh using a flag)
    if (frm.__manual_refresh_triggered) {
      frm.__manual_refresh_triggered = false;

      frappe.call({
        method: "aanirids_isp.aanirids_isp.doctype.subscriber.subscriber.fetch_subscriber_details_direct",
        args: { subscriber_name: frm.doc.name },
        callback: function () {
          frappe.show_alert({
            message: "Auto details sync done ✅",
            indicator: "green"
          });
          frm.reload_doc();
        }
      });
    }
  }
});

// ✅ Detect refresh button click (top right refresh icon)
$(document).on("click", ".btn-refresh", function () {
  if (cur_frm && cur_frm.doctype === "Subscriber") {
    cur_frm.__manual_refresh_triggered = true;
  }
});
