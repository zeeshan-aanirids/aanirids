# Copyright (c) 2026, Mohammed Zeeshan and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from aanirids_isp.aanirids_isp.api_client import get_json

class IPPool(Document):
	pass

def clean_datetime(dt):
    """
    Convert API datetime string to frappe datetime string.
    Example: "2025-09-23T03:39:11.000Z" -> "2025-09-23 03:39:11"
    """
    if not dt:
        return None
    try:
        dt = str(dt).replace("T", " ").replace("Z", "")
        # remove milliseconds if present
        if "." in dt:
            dt = dt.split(".")[0]
        return dt.strip()
    except Exception:
        return None

@frappe.whitelist()
def sync_ip_pools():
    """
    Sync IP Pools from API into IP Pool DocType
    Upsert based on external_id
    """
    try:
        payload = get_json("/ip-pools", scope=True)
    except Exception as e:
        frappe.throw(f"❌ IP Pools API fetch failed: {str(e)}")
    
    if isinstance(payload, list):
        ip_pools = payload
    elif isinstance(payload, dict):
        if payload.get("success") is False:
            frappe.throw(f"❌ API returned success=false: {payload}")
        ip_pools = payload.get("data") if "data" in payload else [payload]
    else:
        frappe.throw(f"❌ Unexpected API response format: {type(payload)}")
    
    created = 0
    updated = 0
    
    for row in ip_pools:
        external_id = row.get("id")
        if not external_id:
            continue

        nas_name = None
        if row.get("nas_id"):
            nas_name = frappe.db.get_value(
                "NAS",
                {"external_id": row.get("nas_id")},
                "name"
            )
        
        branch_name = None
        if row.get("branch_id"):
            branch_name = frappe.db.get_value(
                "Branch",
                {"custom_external_id": row.get("branch_id")},
                "name"
            )
        
        isp_name = None
        if row.get("isp_id"):
            isp_name = frappe.db.get_value(
                "ISP",
                {"external_id": row.get("isp_id")},
                "name"
            )

        mapped = {
            "external_id": external_id,
            "pool_name": row.get("pool_name"),
            "network": row.get("network"),
            "subnet": row.get("subnet"),
            "nas": nas_name,
            "isp": isp_name,
            "branch": branch_name,
            "created_by": row.get("created_by_username"),
            "created_at": clean_datetime(row.get("created_at")),
            "updated_at": clean_datetime(row.get("updated_at")),
        }

        # remove None values
        mapped = {k: v for k, v in mapped.items() if v is not None}

        existing = frappe.db.exists("IP Pool", {"external_id": external_id})

        if existing:
            doc = frappe.get_doc("IP Pool", existing)
            doc.update(mapped)
            doc.save(ignore_permissions=True)
            updated += 1
        else:
            doc = frappe.new_doc("IP Pool")
            doc.update(mapped)
            doc.insert(ignore_permissions=True)
            created += 1

    frappe.db.commit()

    return {
        "total": len(ip_pools),
        "created": created,
        "updated": updated
    }
