import frappe
import requests
from frappe.model.document import Document


class Plan(Document):
    pass


PACKAGE_API_URL = "http://172.24.160.1:5003/api/packages/"
TIMEOUT = 30


def map_status(api_status):
    # API assumption: 0 = Active, 1 = Inactive
    return "Active" if int(api_status or 0) == 0 else "Inactive"


def map_billing_type(api_billing_type):
    # API: 1 = Prepaid, 2 = Postpaid
    return "Postpaid" if int(api_billing_type or 0) == 2 else "Prepaid"


def map_duration_type(api_duration_type):
    # API: 1 = Days, 2 = Months
    return "Months" if int(api_duration_type or 0) == 2 else "Days"


@frappe.whitelist()
def sync_plans():
    """
    Sync full Plan fields from Packages API into Plan DocType.
    Upsert using external_id (create if not exists, else update).
    """

    # 1) Fetch API data
    try:
        r = requests.get(PACKAGE_API_URL, timeout=TIMEOUT)
        r.raise_for_status()
        payload = r.json()
    except Exception as e:
        frappe.throw(f"❌ API fetch failed: {str(e)}")

    if not payload.get("success"):
        frappe.throw(f"❌ API returned success=false: {payload}")

    data = payload.get("data") or []

    created = 0
    updated = 0
    skipped = 0
    failed = 0

    # 2) Loop records
    for item in data:
        mapped = {}

        try:
            external_id = item.get("id")
            if not external_id:
                skipped += 1
                continue

            mapped = {
                "external_id": external_id,
                "plan_name": item.get("name"),
                "description": item.get("description"),
                "invoice_description": item.get("invoice_description"),

                "status": map_status(item.get("status")),
                "billing_type": map_billing_type(item.get("billing_type")),

                # stored as Data IDs
                "isp": str(item.get("isp_id")) if item.get("isp_id") is not None else None,
                "branch": str(item.get("branch_id")) if item.get("branch_id") is not None else None,

                "duration": item.get("duration"),
                "duration_type": map_duration_type(item.get("duration_type")),
            }

            # remove None values
            mapped = {k: v for k, v in mapped.items() if v is not None}

            # 3) Upsert
            existing_name = frappe.db.exists("Plan", {"external_id": external_id})

            if existing_name:
                doc = frappe.get_doc("Plan", existing_name)
                doc.update(mapped)
                doc.save(ignore_permissions=True)
                updated += 1
            else:
                doc = frappe.new_doc("Plan")
                doc.update(mapped)
                doc.insert(ignore_permissions=True)
                created += 1

        except Exception as e:
            failed += 1
            frappe.log_error(
                title="Plan Sync Failed",
                message=f"""
External ID: {item.get("id")}
Name: {item.get("name")}
Error: {str(e)}

Mapped Data:
{mapped}
"""
            )

    frappe.db.commit()

    return {
        "success": True,
        "message": f"✅ Sync Completed | Created: {created}, Updated: {updated}, Skipped: {skipped}, Failed: {failed}, Total: {len(data)}",
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "total_api_records": len(data),
    }
