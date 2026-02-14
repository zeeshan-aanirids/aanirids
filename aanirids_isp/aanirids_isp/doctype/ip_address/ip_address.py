# Copyright (c) 2026, Mohammed Zeeshan and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from aanirids_isp.aanirids_isp.api_client import get_json

class IPAddress(Document):
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
def sync_ip_addresses():
    """
    Sync IP Addresses from API into IPAddress DocType
    Upsert based on external_id (id)
    Works if API returns LIST or {success:true,data:[...]}"""
    try:
        payload = get_json("/ip-addresses", scope=True)
    except Exception as e:
        frappe.throw(f"❌ IP Addresses API fetch failed: {str(e)}")
    
    if isinstance(payload, list):
        ip_addresses = payload
    elif isinstance(payload, dict):
        if not payload.get("success"):
            frappe.throw(f"❌ API returned success=false: {payload}")
        ip_addresses = payload.get("data") or []
    else:
        frappe.throw(f"❌ Unexpected API response format: {type(payload)}")
    
    created = 0
    updated = 0
    skipped = 0
    failed = 0
    
    for ip in ip_addresses:
        mapped = {}
        try:
            external_id = ip.get("id")
            if not external_id:
                skipped += 1
                continue
            
            ip_pool_name = None
            if ip.get("ip_pool_id"):
                ip_pool_name = frappe.db.get_value(
                    "IP Pool", 
                    {"external_id":ip.get("ip_pool_id")},
                    "name"
                )
            
            isp_name = None
            if ip.get("isp_id"):
                isp_name = frappe.db.get_value(
                    "ISP", 
                    {"external_id":ip.get("isp_id")},
                    "name"
                )
            
            branch_name = None
            if ip.get("branch_id"):
                branch_name = frappe.db.get_value(
                    "Branch", 
                    {"custom_external_id":ip.get("branch_id")},
                    "name"
                )
            
            mapped = {
                "external_id": external_id,
                "ip_pool": ip_pool_name,
                "ip_address": ip.get("ip_address"),
                "isp": isp_name,
                "branch": branch_name,
                "created_by": ip.get("created_by_username"),
                "created_at": clean_datetime(ip.get("created_at")),
                "updated_at": clean_datetime(ip.get("updated_at")),
            }
            
            # remove None values
            mapped = {k: v for k, v in mapped.items() if v is not None}
            
            existing = frappe.db.exists("IP Address", {"external_id": external_id})
            
            if existing:
                doc = frappe.get_doc("IP Address", existing)
                doc.update(mapped)
                doc.save(ignore_permissions=True)
                updated += 1
            else:
                doc = frappe.new_doc("IP Address")
                doc.update(mapped)
                doc.insert(ignore_permissions=True)
                created += 1
        except Exception as e:
            failed += 1
            frappe.log_error(
                title="IPAddress Sync Failed",
                message=f"""
External ID: {ip.get("id")}
IP Address: {ip.get("ip_address")}
Error: {str(e)}

Mapped Data:
{mapped}
"""
            )
    
    frappe.db.commit()
    
    return {
        "success": True,
        "message": f"✅ IPAddress Sync Completed | Created: {created}, Updated: {updated}, Skipped: {skipped}, Failed: {failed}, Total: {len(ip_addresses)}",
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "total_api_records": len(ip_addresses),
    }
