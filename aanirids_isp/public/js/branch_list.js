frappe.listview_settings["Branch"] = {
    onload(listview) {
        listview.page.add_inner_button("Fetch Branches", () => {
            frappe.call({
                method: "aanirids_isp.aanirids_isp.api.branch.sync_branches",
                freeze: true,
                freeze_message: "Fetching branches...",
                callback(r) {
                    if (!r.exc) {
                        frappe.msgprint({
                            title: "Branches Synced",
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
};
