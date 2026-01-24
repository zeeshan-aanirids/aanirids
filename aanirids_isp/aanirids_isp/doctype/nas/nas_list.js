frappe.listview_settings["NAS"] = {
    onload: function (listview) {
        listview.page.add_inner_button("Sync NAS", function () {
            frappe.call({
                method: "aanirids_isp.aanirids_isp.doctype.nas.nas.sync_nas",
                freeze: true,
                freeze_message: "Syncing NAS...",
                callback: function (r) {
                    if (r.message) {
                        frappe.msgprint({
                            title: "✅ Sync Completed",
                            message: `
                Created: <b>${r.message.created}</b><br>
                Updated: <b>${r.message.updated}</b><br>
                Skipped: <b>${r.message.skipped}</b><br>
                Failed: <b>${r.message.failed}</b><br>
                Total: <b>${r.message.total_api_records}</b>
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
