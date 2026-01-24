import frappe
import requests
from frappe.model.document import Document


class Salesperson(Document):
    pass


USERS_API_URL = "http://172.24.160.1:5003/api/users"
TIMEOUT = 30


@frappe.whitelist()
def sync_salespersons():
    """
    Sync Users from API into Salesperson DocType
    Upsert based on external_id (id)
    Works if API returns LIST or {success:true,data:[...]}
    """

    # 1) Fetch users
    try:
        r = requests.get(USERS_API_URL, timeout=TIMEOUT)
        r.raise_for_status()
        payload = r.json()
    except Exception as e:
        frappe.throw(f"❌ Users API fetch failed: {str(e)}")

    # ✅ 2) Handle response type (LIST or DICT)
    if isinstance(payload, list):
        users = payload
    elif isinstance(payload, dict):
        if not payload.get("success"):
            frappe.throw(f"❌ API returned success=false: {payload}")
        users = payload.get("data") or []
    else:
        frappe.throw(f"❌ Unexpected API response format: {type(payload)}")

    created = 0
    updated = 0
    skipped = 0
    failed = 0

    # 3) Upsert loop
    for u in users:
        mapped = {}

        try:
            external_id = u.get("id")
            if not external_id:
                skipped += 1
                continue

            mapped = {
                "external_id": external_id,
                "full_name": u.get("name"),
                "email": u.get("email"),
                "username": u.get("username"),
                "dob": u.get("dob"),
                "phone": u.get("phone"),
                "address": u.get("address"),
            }

            # remove None values
            mapped = {k: v for k, v in mapped.items() if v is not None}

            existing = frappe.db.exists("Salesperson", {"external_id": external_id})

            if existing:
                doc = frappe.get_doc("Salesperson", existing)
                doc.update(mapped)
                doc.save(ignore_permissions=True)
                updated += 1
            else:
                doc = frappe.new_doc("Salesperson")
                doc.update(mapped)
                doc.insert(ignore_permissions=True)
                created += 1

        except Exception as e:
            failed += 1
            frappe.log_error(
                title="Salesperson Sync Failed",
                message=f"""
External ID: {u.get("id")}
Name: {u.get("name")}
Error: {str(e)}

Mapped Data:
{mapped}
"""
            )

    frappe.db.commit()

    return {
        "success": True,
        "message": f"✅ Salesperson Sync Completed | Created: {created}, Updated: {updated}, Skipped: {skipped}, Failed: {failed}, Total: {len(users)}",
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "total_api_records": len(users),
    }
