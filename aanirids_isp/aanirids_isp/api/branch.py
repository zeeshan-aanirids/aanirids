import frappe
import requests
from frappe.utils import get_datetime

AANIRIDS_BRANCH_API = "http://172.24.160.1:5003/api/branches"


@frappe.whitelist()
def sync_branches():
    """
    Fetch branches from Aanirids API
    Create or update Branch records in Frappe
    """

    try:
        response = requests.get(AANIRIDS_BRANCH_API, timeout=20)
        response.raise_for_status()
        branches = response.json()
    except Exception as e:
        frappe.throw(f"Failed to fetch branches: {str(e)}")

    created = 0
    updated = 0

    for row in branches:
        external_id = row.get("id")

        # Check if branch already exists
        branch_name = frappe.db.get_value(
            "Branch",
            {"custom_external_id": external_id},
            "name"
        )

        if branch_name:
            doc = frappe.get_doc("Branch", branch_name)
            updated += 1
        else:
            doc = frappe.new_doc("Branch")
            created += 1
        
        isp_name = frappe.db.get_value(
            "ISP",
            {"external_id": row.get("isp_id")},
            "name"
        )

        # -------- Field Mapping --------
        doc.custom_external_id = row.get("id")
        doc.branch = row.get("name")
        doc.custom_isp_id = isp_name
        doc.custom_description = row.get("description")
        doc.custom_unique_token = row.get("unique_token")
        doc.custom_register_token = row.get("register_token")
        doc.custom_created_by = row.get("created_by")
        doc.custom_updated_by = row.get("updated_by")

        if row.get("created_at"):
            doc.custom_created_at = get_datetime(row.get("created_at")).replace(tzinfo=None)

        if row.get("updated_at"):
            doc.custom_updated_at = get_datetime(row.get("updated_at")).replace(tzinfo=None)

        doc.save(ignore_permissions=True)

    frappe.db.commit()

    return {
        "status": "success",
        "created": created,
        "updated": updated,
        "total": len(branches)
    }
