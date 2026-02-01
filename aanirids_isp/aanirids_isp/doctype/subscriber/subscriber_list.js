frappe.listview_settings["Subscriber"] = {
    onload(listview) {
        listview.page.add_inner_button(__("Fetch Subscribers"), () => {
            frappe.call({
                method: "aanirids_isp.aanirids_isp.doctype.subscriber.subscriber.sync_list_and_enqueue_bulk_details",
                freeze: true,
                freeze_message: __("Fetching subscribers..."),
                callback: function (r) {
                    if (r.message && r.message.status === "success") {
                        frappe.msgprint({
                            title: __("Subscribers Synced"),
                            indicator: "green",
                            message: `
                                <b>Basic List Sync:</b><br>
                                Total Fetched: ${r.message.total_fetched}<br>
                                Created: ${r.message.created}<br>
                                Updated: ${r.message.updated}<br><br>
                                <i>Detailed sync for all subscribers has been queued in the background.</i>
                            `
                        });
                        listview.refresh();
                    }
                }
            });
        });
    }
};
