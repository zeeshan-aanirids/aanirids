frappe.listview_settings["ISP"] = {
    onload: function (listview) {
        listview.page.add_inner_button("Sync ISP", function () {
            frappe.call({
                method: "aanirids_isp.aanirids_isp.doctype.isp.isp.sync_isps",
                freeze: true,
                freeze_message: "Syncing ISP...",
                callback: function (r) {
                    if (r.message) {
                        frappe.msgprint({
                            title: "✅ Sync Completed",
                            message: `
                Created: <b>${r.message.created}</b><br>
                Updated: <b>${r.message.updated}</b><br>
                Total: <b>${r.message.total}</b>
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
