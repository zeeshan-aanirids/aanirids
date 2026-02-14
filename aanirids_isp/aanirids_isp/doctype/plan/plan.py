import frappe
from frappe.model.document import Document

from aanirids_isp.aanirids_isp.api_client import get_json


# ==============================
# DocType Controller
# ==============================
class Plan(Document):
    def autoname(self):
        """
        Naming Rule: By script
        Title Field: plan_name

        name        → Megha 30mbps UL 1M - 2148
        plan_name   → Megha 30mbps UL 1M
        """
        if self.plan_name and self.price is not None:
            self.name = f"{self.plan_name} - {self.price}"


# ==============================
# Helper Mappers
# ==============================
def map_status(val):
    return "Active" if int(val or 0) == 0 else "Inactive"


def map_billing_type(val):
    return "Postpaid" if int(val or 0) == 2 else "Prepaid"


def map_duration_type(val):
    return "Months" if int(val or 0) == 2 else "Days"


# ==============================
# Sync API (same file)
# ==============================
@frappe.whitelist()
def sync_plans():
    try:
        pkg_data = (get_json("/packages", scope=True) or {}).get("data", [])
        acc_data = get_json("/package-accounting", scope=True) or []

    except Exception as e:
        frappe.throw(f"API connection failed: {e}")

    # {(package_id, branch_id): price}
    price_map = {
        (a.get("package_id"), a.get("branch_id")): a.get("price")
        for a in acc_data
    }

    created = updated = failed = 0

    for item in pkg_data:
        try:
            external_id = item.get("id")
            branch_id = item.get("branch_id")
            if not external_id:
                continue

            price = price_map.get((external_id, branch_id), 0)

            plan_text = item.get("name")  # 🔑 ONLY PLAN NAME (no price)

            isp_name = frappe.db.get_value(
                "ISP", {"external_id": item.get("isp_id")}, "name"
            )
            branch_name = frappe.db.get_value(
                "Branch", {"custom_external_id": branch_id}, "name"
            )

            values = {
                "external_id": external_id,
                "plan_name": plan_text,
                "price": price,
                "status": map_status(item.get("status")),
                "billing_type": map_billing_type(item.get("billing_type")),
                "isp": isp_name,
                "branch": branch_name,
                "duration": item.get("duration"),
                "duration_type": map_duration_type(item.get("duration_type")),
            }

            existing = frappe.db.get_value(
                "Plan", {"external_id": external_id}, "name"
            )

            final_name = f"{plan_text} - {price}"

            if existing:
                doc = frappe.get_doc("Plan", existing)

                # Rename if price OR plan name changed
                if existing != final_name:
                    frappe.rename_doc(
                        "Plan", existing, final_name, force=True
                    )

                doc.update(values)
                doc.save(ignore_permissions=True)
                updated += 1

            else:
                doc = frappe.new_doc("Plan")
                doc.name = final_name
                doc.update(values)
                doc.insert(ignore_permissions=True)
                created += 1

        except Exception:
            failed += 1
            frappe.log_error(
                frappe.get_traceback(),
                "Plan Sync Error"
            )

    frappe.db.commit()

    return {
        "success": True,
        "created": created,
        "updated": updated,
        "failed": failed,
        "total": len(pkg_data),
    }
