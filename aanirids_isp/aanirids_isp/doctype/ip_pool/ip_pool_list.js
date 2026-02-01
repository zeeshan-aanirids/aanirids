frappe.listview_settings["IP Pool"] = {
    onload(listview) {
        listview.page.add_inner_button("Sync IP Pools", () => {
            frappe.call({
                method: "aanirids_isp.aanirids_isp.doctype.ip_pool.ip_pool.sync_ip_pools",
                freeze: true,
                freeze_message: "Syncing IP Pools...",
                callback(r) {
                    if (!r.exc) {
                        frappe.msgprint({
                            title: "IP Pools Synced",
                            message: `
                                Total: ${r.message.total}<br>
                                Created: ${r.message.created}<br>
                                Updated: ${r.message.updated}
                            `,
                            indicator: "green"
                        });
                        listview.refresh();
                    }
                }
            });
        });
    }
}