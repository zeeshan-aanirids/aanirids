import frappe
import requests
from frappe.utils import get_url


def send_task_assignment_whatsapp(doc, method=None):

    # Only trigger for Task assignment
    if doc.reference_type != "Task":
        return

    try:
        # Get Task details
        task_id = doc.reference_name
        task_subject = frappe.db.get_value("Task", task_id, "subject")

        # Who assigned the task
        assigned_by = doc.owner
        assigned_by_name = frappe.utils.get_fullname(assigned_by)

        # Get assigned user
        assigned_user = doc.allocated_to
        if not assigned_user:
            frappe.log_error("No allocated user found", "WHATSAPP STOPPED")
            return

        # Get mobile number
        raw_phone = frappe.db.get_value("User", assigned_user, "phone")

        frappe.log_error(
            "WHATSAPP TRACE",
            f"User: {assigned_user} | Raw Phone: {raw_phone}"
        )

        if not raw_phone:
            frappe.log_error("No mobile number found", "WHATSAPP STOPPED")
            return

        # Clean phone number
        phone_digits = ''.join(filter(str.isdigit, str(raw_phone)))

        if len(phone_digits) == 10:
            phone_digits = "91" + phone_digits
        elif phone_digits.startswith("0") and len(phone_digits) == 11:
            phone_digits = "91" + phone_digits[1:]

        # Generate Task URL (local is fine for now)
        task_url = get_url(f"/app/task/{task_id}")

        # Config values
        conf = frappe.conf
        phone_id = conf.get("whatsapp_phone_id")
        api_base = conf.get("whatsapp_api_base")
        bearer_token = conf.get("whatsapp_bearer_token")
        template_name = conf.get("whatsapp_template_name")

        if not all([phone_id, api_base, bearer_token, template_name]):
            frappe.log_error("WhatsApp config missing in site_config", "WHATSAPP CONFIG ERROR")
            return

        url = f"{api_base}/{phone_id}/messages"

        payload = {
            "to": phone_digits,
            "recipient_type": "individual",
            "type": "template",
            "template": {
                "name": template_name,
                "language": {
                    "policy": "deterministic",
                    "code": "en"
                },
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": str(task_id)},           # {{1}}
                            {"type": "text", "text": str(assigned_by_name)},  # {{2}}
                            {"type": "text", "text": str(task_subject)},      # {{3}}
                            {"type": "text", "text": str(task_url)}           # {{4}}
                        ]
                    }
                ]
            }
        }

        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json"
        }

        response = requests.post(url, headers=headers, json=payload, timeout=15)

        frappe.log_error(
            "WHATSAPP RESPONSE",
            f"Status: {response.status_code}\nResponse: {response.text}"
        )

    except Exception:
        frappe.log_error(frappe.get_traceback(), "WHATSAPP CRASH")
