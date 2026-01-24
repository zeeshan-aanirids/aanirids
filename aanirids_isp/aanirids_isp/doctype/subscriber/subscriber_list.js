frappe.listview_settings["Subscriber"] = {
    onload(listview) {
        listview.page.add_inner_button("Fetch Subscribers", () => {
            frappe.call({
                method: "aanirids_isp.aanirids_isp.doctype.subscriber.subscriber.sync_list_and_enqueue_bulk_details",
                callback: function (r) {
                    frappe.msgprint(r.message.message || "Done ✅");
                    listview.refresh();
                }
            });
        });
    }
};
