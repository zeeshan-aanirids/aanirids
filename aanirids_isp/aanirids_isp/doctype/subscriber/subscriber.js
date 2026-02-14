function apply_field_editability(frm) {
  const always_read_only_fields = [
    "external_id",
    "created_at",
    "details_synced",
    "details_synced_on",
    "status",
    "isp",
    "mac_address",
    "ip_address",
    "login_log_status",
  ];

  always_read_only_fields.forEach((fieldname) => {
    frm.set_df_property(fieldname, "read_only", 1);
  });

  const service_settings_after_create = [
    "sms_status",
    "email_status",
    "auto_renew_status",
    "mac_lock_status",
    "profile_status",
    "connection_type",
    "expiration_date",
    "lock_volume_status",
    "total_data_quota",
    "used_data_quota",
    "lock_session_status",
    "total_session_quota",
    "used_session_quota",
    "discount_type",
    "discount",
  ];

  service_settings_after_create.forEach((fieldname) => {
    frm.set_df_property(fieldname, "read_only", frm.is_new() ? 1 : 0);
  });
}

frappe.ui.form.on("Subscriber", {
  // ✅ NEW: Auto-fill Salesperson & Branch on load for new records
  onload: function (frm) {
    frm.__prev_billing_address = frm.doc.billing_address || "";
    frm.__prev_billing_city = frm.doc.billing_city || "";
    frm.__prev_billing_zip = frm.doc.billing_zip || "";

    // Prevent auto-save on attachment upload for Subscriber Document child rows.
    // Default Frappe behavior calls frm.save() after uploading an Attach field,
    // which is disruptive while the user is still filling the form.
    if (!frappe.__aanirids_isp_no_autosave_attach_patched) {
      frappe.__aanirids_isp_no_autosave_attach_patched = true;

      const originalOnUploadComplete =
        frappe.ui.form.ControlAttach &&
        frappe.ui.form.ControlAttach.prototype &&
        frappe.ui.form.ControlAttach.prototype.on_upload_complete;

      if (typeof originalOnUploadComplete === "function") {
        frappe.ui.form.ControlAttach.prototype.on_upload_complete = async function (attachment) {
          const isSubscriberDocRow =
            this.frm &&
            this.frm.doctype === "Subscriber" &&
            this.doc &&
            this.doc.doctype === "Subscriber Document" &&
            this.df &&
            this.df.fieldname === "document_file";

          if (isSubscriberDocRow) {
            await this.parse_validate_and_set_in_model(attachment.file_url);
            this.frm.attachments.update_attachment(attachment);
            this.set_value(attachment.file_url);
            this.toggle_reload_button && this.toggle_reload_button();
            return;
          }

          return await originalOnUploadComplete.call(this, attachment);
        };
      }
    }

    if (frm.is_new()) {
      if (!frm.doc.status) {
        frm.set_value("status", "Active");
      }
      if (!frm.doc.profile_status) {
        frm.set_value("profile_status", "Active (*)");
      }
      if (!frm.doc.connection_type) {
        frm.set_value("connection_type", "Radius PPPoE (*)");
      }
      if (!frm.doc.password) {
        frm.set_value("password", "WavesNett123");
      }
      if (frm.doc.sms_status === null || frm.doc.sms_status === undefined || frm.doc.sms_status === "") {
        frm.set_value("sms_status", 1);
      }
      if (frm.doc.email_status === null || frm.doc.email_status === undefined || frm.doc.email_status === "") {
        frm.set_value("email_status", 1);
      }

      // Check if the user is already logged in (not Guest)
      if (frappe.session.user !== 'Guest') {
        frappe.db.get_value('Salesperson', { user: frappe.session.user }, ['name', 'branch'])
          .then(r => {
            if (r && r.message) {
              // Set the Salesperson
              frm.set_value('salesperson', r.message.name);

              // Set the Branch if available in the Salesperson record
              if (r.message.branch) {
                frm.set_value('branch', r.message.branch);
              }
            }
          });
      }
    }
  },

  username: function (frm) {
    if (!frm.doc.username) return;
    const cleaned = String(frm.doc.username)
      .replace(/[^a-zA-Z0-9]/g, "")
      .toLowerCase();
    if (cleaned !== frm.doc.username) {
      frm.set_value("username", cleaned);
    }
  },

  billing_address: function (frm) {
    const previous = frm.__prev_billing_address || "";
    const current = frm.doc.billing_address || "";
    const installation = frm.doc.installation_address || "";
    if (!installation || installation === previous) {
      frm.set_value("installation_address", current);
    }
    frm.__prev_billing_address = current;
  },

  billing_city: function (frm) {
    const previous = frm.__prev_billing_city || "Gulbarga";
    const current = frm.doc.billing_city || "";
    const installation = frm.doc.installation_city || "";
    if (!installation || installation === previous || installation === "Gulbarga") {
      frm.set_value("installation_city", current);
    }
    frm.__prev_billing_city = current;
  },

  billing_zip: function (frm) {
    const previous = frm.__prev_billing_zip || "585104";
    const current = frm.doc.billing_zip || "";
    const installation = frm.doc.installation_zip || "";
    if (!installation || installation === previous || installation === "585104") {
      frm.set_value("installation_zip", current);
    }
    frm.__prev_billing_zip = current;
  },

  refresh: function (frm) {
    apply_field_editability(frm);

    if (!frm.is_new()) {
      frm.add_custom_button("Service Settings", () => {
        frm.scroll_to_field("section_service_settings");
      });
    }

    // ✅ Button to sync details manually
    frm.add_custom_button("Sync Details", () => {
      frappe.call({
        method: "aanirids_isp.aanirids_isp.doctype.subscriber.subscriber.fetch_subscriber_details_direct",
        args: { subscriber_name: frm.doc.name },
        callback: function () {
          frappe.msgprint("Details synced ✅");
          frm.reload_doc();
        }
      });
    });

    if (!frm.is_new() && frm.doc.external_id && frm.doc.username) {
      frm.add_custom_button("Reset Password", () => {
        frappe.prompt(
          [
            { fieldname: "portal_password", label: "Portal Password", fieldtype: "Password" },
            { fieldname: "connection_password", label: "Connection Password", fieldtype: "Password" },
          ],
          (values) => {
            if (!values.portal_password && !values.connection_password) {
              frappe.msgprint("Enter at least one password.");
              return;
            }
            frappe.call({
              method: "aanirids_isp.aanirids_isp.doctype.subscriber.subscriber.reset_subscriber_password",
              args: {
                subscriber_name: frm.doc.name,
                portal_password: values.portal_password || null,
                connection_password: values.connection_password || null,
              },
              callback: () => frappe.show_alert({ message: "Password updated", indicator: "green" }),
            });
          },
          "Reset Subscriber Password",
          "Update"
        );
      }, "Actions");

      frm.add_custom_button("Disconnect Session", () => {
        frappe.call({
          method: "aanirids_isp.aanirids_isp.doctype.subscriber.subscriber.disconnect_subscriber_session",
          args: { subscriber_name: frm.doc.name },
          callback: () => frappe.show_alert({ message: "Disconnect requested", indicator: "green" }),
        });
      }, "Actions");

      frm.add_custom_button("Disable Net", () => {
        frappe.call({
          method: "aanirids_isp.aanirids_isp.doctype.subscriber.subscriber.disable_subscriber_net",
          args: { subscriber_name: frm.doc.name },
          callback: () => frappe.show_alert({ message: "Network disabled", indicator: "orange" }),
        });
      }, "Actions");

      frm.add_custom_button("Enable Net", () => {
        frappe.call({
          method: "aanirids_isp.aanirids_isp.doctype.subscriber.subscriber.enable_subscriber_net",
          args: { subscriber_name: frm.doc.name },
          callback: () => frappe.show_alert({ message: "Network enabled", indicator: "green" }),
        });
      }, "Actions");

      frm.add_custom_button("Disable Profile", () => {
        frappe.confirm("Disable this subscriber profile in backend?", () => {
          frappe.call({
            method: "aanirids_isp.aanirids_isp.doctype.subscriber.subscriber.disable_subscriber_profile",
            args: { subscriber_name: frm.doc.name },
            callback: () => frm.reload_doc(),
          });
        });
      }, "Actions");

      frm.add_custom_button("Enable Profile", () => {
        frappe.confirm("Enable this subscriber profile in backend?", () => {
          frappe.call({
            method: "aanirids_isp.aanirids_isp.doctype.subscriber.subscriber.enable_subscriber_profile",
            args: { subscriber_name: frm.doc.name },
            callback: () => frm.reload_doc(),
          });
        });
      }, "Actions");

      frm.add_custom_button("Revoke Recharge", () => {
        frappe.confirm("Revoke last recharge for this subscriber?", () => {
          frappe.call({
            method: "aanirids_isp.aanirids_isp.doctype.subscriber.subscriber.revoke_subscriber_recharge",
            args: { subscriber_name: frm.doc.name },
            callback: () => frm.reload_doc(),
          });
        });
      }, "Actions");
    }

    // ✅ Only auto sync when user refreshes manually
    // (we detect manual refresh using a flag)
    if (frm.__manual_refresh_triggered) {
      frm.__manual_refresh_triggered = false;

      frappe.call({
        method: "aanirids_isp.aanirids_isp.doctype.subscriber.subscriber.fetch_subscriber_details_direct",
        args: { subscriber_name: frm.doc.name },
        callback: function () {
          frappe.show_alert({
            message: "Auto details sync done ✅",
            indicator: "green"
          });
          frm.reload_doc();
        }
      });
    }
  }
});

// ✅ Detect refresh button click (top right refresh icon)
$(document).on("click", ".btn-refresh", function () {
  if (cur_frm && cur_frm.doctype === "Subscriber") {
    cur_frm.__manual_refresh_triggered = true;
  }
});
