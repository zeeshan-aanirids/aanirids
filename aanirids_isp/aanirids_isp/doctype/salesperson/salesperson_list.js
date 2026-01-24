frappe.listview_settings["Salesperson"] = {
    onload: function (listview) {
        listview.page.add_inner_button("Sync Salespersons", function () {
            frappe.call({
                method: "aanirids_isp.aanirids_isp.doctype.salesperson.salesperson.sync_salespersons",
                freeze: true,
                freeze_message: "Syncing Salespersons...",
                callback: function (r) {
                    if (r.message) {
                        frappe.msgprint({
                            title: "✅ Sync Completed",
                            message: `
                Created: <b>${r.message.created}</b><br>
                Updated: <b>${r.message.updated}</b><br>
                Skipped: <b>${r.message.skipped}</b><br>
                Failed: <b>${r.message.failed}</b><br>
                Total API Records: <b>${r.message.total_api_records}</b>
              `,
                            indicator: "green"
                        });
                        listview.refresh();
                    }
                }
            });
        });
    }
};
