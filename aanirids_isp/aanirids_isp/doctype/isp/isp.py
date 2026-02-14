import frappe
from frappe.model.document import Document

from aanirids_isp.aanirids_isp.api_client import get_json

class ISP(Document):
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
def sync_isps():
    """
    Sync ISPs from API into ISP DocType
    Upsert based on external_id
    """
    try:
        payload = get_json("/isps", scope=True)
    except Exception as e:
        frappe.throw(f"❌ ISPs API fetch failed: {str(e)}")
    
    if isinstance(payload, list):
        isps = payload
    elif isinstance(payload, dict):
        if payload.get("success") is False:
            frappe.throw(f"❌ API returned success=false: {payload}")
        isps = payload.get("data") or []
    else:
        frappe.throw(f"❌ Unexpected API response format: {type(payload)}")
    
    created = 0
    updated = 0
    
    for row in isps:
        external_id = row.get("id")
        if not external_id:
            continue

        mapped = {
            "external_id": external_id,
            "company_name": row.get("company_name"),
            "owner_name": row.get("owner_name"),
            "email": row.get("email"),
            "phone": row.get("phone"),
            "website": row.get("website"),
            "registered_number": row.get("regis_num"),
            "country": row.get("country"),
            "created_at": clean_datetime(row.get("created_at")),
            "updated_at": clean_datetime(row.get("updated_at")),
        }

        # remove None values
        mapped = {k: v for k, v in mapped.items() if v is not None}

        existing = frappe.db.exists("ISP", {"external_id": external_id})

        if existing:
            doc = frappe.get_doc("ISP", existing)
            doc.flags.from_backend_sync = True
            doc.update(mapped)
            doc.save(ignore_permissions=True)
            updated += 1
        else:
            doc = frappe.new_doc("ISP")
            doc.flags.from_backend_sync = True
            doc.update(mapped)
            doc.insert(ignore_permissions=True)
            created += 1

    frappe.db.commit()

    return {
        "status": "success",
        "total": len(isps),
        "created": created,
        "updated": updated
    }
