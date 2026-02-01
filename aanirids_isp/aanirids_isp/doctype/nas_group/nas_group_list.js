frappe.listview_settings["NAS Group"] = {
    onload: function (listview) {
        listview.page.add_inner_button("Sync NASGroup", function () {
            frappe.call({
                method: "aanirids_isp.aanirids_isp.doctype.nas_group.nas_group.sync_nas_groups",
                freeze: true,
                freeze_message: "Syncing NASGroup...",
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
