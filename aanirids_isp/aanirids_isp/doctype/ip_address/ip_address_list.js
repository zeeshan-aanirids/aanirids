frappe.listview_settings["IP Address"] = {
    onload: function (listview) {
        listview.page.add_inner_button("Sync IP Address", function () {
            frappe.call({
                method: "aanirids_isp.aanirids_isp.doctype.ip_address.ip_address.sync_ip_addresses",
                freeze: true,
                freeze_message: "Syncing IP Address...",
                callback: function (r) {
                    if (r.message) {
                        frappe.msgprint({
                            title: "✅ Sync Completed",
                            message: `
                Created: <b>${r.message.created}</b><br>
                Updated: <b>${r.message.updated}</b><br>
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
