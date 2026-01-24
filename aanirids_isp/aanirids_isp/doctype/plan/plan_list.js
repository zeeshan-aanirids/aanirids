frappe.listview_settings["Plan"] = {
    onload: function (listview) {
        listview.page.add_inner_button("Sync Plans", function () {
            frappe.call({
                method: "aanirids_isp.aanirids_isp.doctype.plan.plan.sync_plans",
                freeze: true,
                freeze_message: "Syncing Plans... Please wait",
                callback: function (r) {
                    if (r.message) {
                        frappe.msgprint({
                            title: "✅ Sync Completed",
                            message: `
                Created: <b>${r.message.created}</b><br>
                Updated: <b>${r.message.updated}</b><br>
                Skipped: <b>${r.message.skipped}</b><br>
                Failed: <b>${r.message.failed}</b><br>
                Total API Records: <b>${r.message.total_api_records}</b><br><br>
                <small>${r.message.message}</small>
              `,
                            indicator: "green"
                        });

                        listview.refresh();
                    }
                },
                error: function (err) {
                    frappe.msgprint({
                        title: "❌ Sync Failed",
                        message: err.message || "Something went wrong while syncing.",
                        indicator: "red"
                    });
                }
            });
        });
    }
};
