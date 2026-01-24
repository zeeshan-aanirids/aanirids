import frappe
import requests
from frappe.model.document import Document


class NAS(Document):
    pass


NAS_API_URL = "http://172.24.160.1:5003/api/nas/"
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
def sync_nas():
    """
    Sync NAS records from API into NAS DocType
    Upsert based on external_id (id).
    """

    # 1) Fetch API data
    try:
        r = requests.get(NAS_API_URL, timeout=TIMEOUT)
        r.raise_for_status()
        payload = r.json()
    except Exception as e:
        frappe.throw(f"❌ NAS API fetch failed: {str(e)}")

    # 2) Validate response
    if not payload.get("success"):
        frappe.throw(f"❌ API returned success=false: {payload}")

    records = payload.get("data") or []

    created = 0
    updated = 0
    skipped = 0
    failed = 0

    # 3) Upsert loop
    for row in records:
        mapped = {}

        try:
            external_id = row.get("id")
            if not external_id:
                skipped += 1
                continue

            mapped = {
                "external_id": external_id,
                "nasname": row.get("nasname"),
                "shortname": row.get("shortname"),
                "type": row.get("type"),
                "ports": row.get("ports"),
                "secret": row.get("secret"),
                "server": row.get("server"),
                "community": row.get("community"),
                "description": row.get("description"),
                "created_at": clean_datetime(row.get("created_at")),
                "updated_at": clean_datetime(row.get("updated_at")),
            }

            # remove None values
            mapped = {k: v for k, v in mapped.items() if v is not None}

            existing = frappe.db.exists("NAS", {"external_id": external_id})

            if existing:
                doc = frappe.get_doc("NAS", existing)
                doc.update(mapped)
                doc.save(ignore_permissions=True)
                updated += 1
            else:
                doc = frappe.new_doc("NAS")
                doc.update(mapped)
                doc.insert(ignore_permissions=True)
                created += 1

        except Exception as e:
            failed += 1
            frappe.log_error(
                title="NAS Sync Failed",
                message=f"""
External ID: {row.get("id")}
NAS Name: {row.get("nasname")}
Error: {str(e)}

Mapped Data:
{mapped}
"""
            )

    frappe.db.commit()

    return {
        "success": True,
        "message": f"✅ NAS Sync Completed | Created: {created}, Updated: {updated}, Skipped: {skipped}, Failed: {failed}, Total: {len(records)}",
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "total_api_records": len(records),
    }
