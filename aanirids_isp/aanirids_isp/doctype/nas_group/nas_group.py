# Copyright (c) 2026, Mohammed Zeeshan and contributors
# For license information, please see license.txt

import frappe
import requests
from frappe.model.document import Document



class NASGroup(Document):
	pass

NASGroup_API_URL = "http://172.24.160.1:5003/api/nas-groups"
TIMEOUT = 30

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
def sync_nas_groups():
    """
    Sync NAS Groups from API into NASGroup DocType
    Upsert based on external_id (id)
    Works if API returns LIST or {success:true,data:[...]}"""
    try:
        r = requests.get(NASGroup_API_URL, timeout=TIMEOUT)
        r.raise_for_status()
        payload = r.json()
    except Exception as e:
        frappe.throw(f"❌ NAS Groups API fetch failed: {str(e)}")
    
    if isinstance(payload, list):
        nas_groups = payload
    elif isinstance(payload, dict):
        if not payload.get("success"):
            frappe.throw(f"❌ API returned success=false: {payload}")
        nas_groups = payload.get("data") or []
    else:
        frappe.throw(f"❌ Unexpected API response format: {type(payload)}")
    
    created = 0
    updated = 0
    skipped = 0
    failed = 0
    
    for ng in nas_groups:
        mapped = {}
        try:
            external_id = ng.get("id")
            if not external_id:
                skipped += 1
                continue
            
            isp_name = None
            if ng.get("isp_id"):
                isp_name = frappe.db.get_value(
                    "ISP", 
                    {"external_id":ng.get("isp_id")},
                    "name"
                )
            
            branch_name = None
            if ng.get("branch_id"):
                branch_name = frappe.db.get_value(
                    "Branch", 
                    {"custom_external_id":ng.get("branch_id")},
                    "name"
                )

            nas_name = None
            if ng.get("nas_id"):
                nas_name = frappe.db.get_value(
                    "NAS", 
                    {"external_id":ng.get("nas_id")},
                    "name"
                )
            
            mapped = {
                "external_id": external_id,
                "group_name": ng.get("group_name"),
                "nas_name": nas_name,
                "isp": isp_name,
                "branch": branch_name,
                "created_at": clean_datetime(ng.get("created_at")),
                "updated_at": clean_datetime(ng.get("updated_at")),
            }
            
            # remove None values
            mapped = {k: v for k, v in mapped.items() if v is not None}
            
            existing = frappe.db.exists("NAS Group", {"external_id": external_id})
            
            if existing:
                doc = frappe.get_doc("NAS Group", existing)
                doc.update(mapped)
                doc.save(ignore_permissions=True)
                updated += 1
            else:
                doc = frappe.new_doc("NAS Group")
                doc.update(mapped)
                doc.insert(ignore_permissions=True)
                created += 1
        except Exception as e:
            failed += 1
            frappe.log_error(
                title="NASGroup Sync Failed",
                message=f"""
External ID: {ng.get("id")}
Group Name: {ng.get("group_name")}
NAS Name: {ng.get("nas_name")}
Error: {str(e)}

Mapped Data:
{mapped}
"""
            )
    
    frappe.db.commit()
    
    return {
        "success": True,
        "message": f"✅ NASGroup Sync Completed | Created: {created}, Updated: {updated}, Skipped: {skipped}, Failed: {failed}, Total: {len(nas_groups)}",
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "total_api_records": len(nas_groups),
    }
