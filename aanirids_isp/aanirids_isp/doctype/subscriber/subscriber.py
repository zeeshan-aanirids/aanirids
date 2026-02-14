import frappe
import json
import mimetypes
import os
from dateutil.parser import isoparse
import pytz

from frappe.utils import get_system_timezone, getdate, now_datetime
from frappe.model.document import Document

DEFAULT_LIMIT = 50

from aanirids_isp.aanirids_isp.api_client import (
	delete as api_delete,
	get_json,
	post_json,
	put_json,
	request as api_request,
)

PROFILE_STATUS_TO_CODE = {
    "Register": 1,
    "Active (*)": 2,
    "Disable": 3,
    "Terminate": 4,
}
PROFILE_CODE_TO_STATUS = {str(v): k for k, v in PROFILE_STATUS_TO_CODE.items()}

CONNECTION_TYPE_TO_CODE = {
    "Radius PPPoE (*)": 1,
    "Radius Hotspot": 2,
}
CONNECTION_CODE_TO_TYPE = {str(v): k for k, v in CONNECTION_TYPE_TO_CODE.items()}

DISCOUNT_TYPE_TO_CODE = {
    "Percentage (%)": 1,
    "Fixed Amount": 2,
}
DISCOUNT_CODE_TO_TYPE = {str(v): k for k, v in DISCOUNT_TYPE_TO_CODE.items()}


# ============================================================
# ✅ UTILITIES
# ============================================================
def clean_date(dt):
    if not dt:
        return None
    try:
        return getdate(str(dt).split("T")[0])
    except Exception:
        return None

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


def normalize_identity_type(value) -> str | None:
    """
    Backend stores identity_type as string, but legacy data may have numeric codes.
    Subscriber.id_proof_type is a Select with allowed values: "", "Aadhaar Card", "PAN Card".
    """
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    allowed = {"Aadhaar Card", "PAN Card"}
    if text in allowed:
        return text

    lower = text.lower()
    if lower in {"aadhaar", "aadhar", "aadhaar card", "aadhar card", "uidai"}:
        return "Aadhaar Card"
    if lower in {"pan", "pan card"}:
        return "PAN Card"

    # Legacy numeric mapping (observed values like "2")
    if text == "1":
        return "Aadhaar Card"
    if text == "2":
        return "PAN Card"

    return None


def format_radius_datetime(iso_date_string: str) -> str:
    """
    Match the React UI formatting used for radcheck Expiration:
    "DD Mon YYYY HH:mm:ss" in the server's local timezone.
    """
    dt = isoparse(iso_date_string)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=pytz.UTC)

    tz = pytz.timezone(get_system_timezone() or "UTC")
    dt_local = dt.astimezone(tz)

    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return (
        f"{dt_local.day:02d} {months[dt_local.month - 1]} {dt_local.year} "
        f"{dt_local.hour:02d}:{dt_local.minute:02d}:{dt_local.second:02d}"
    )


def normalize_select_to_code(value, mapping: dict[str, int]) -> int | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    return mapping.get(text)


def map_code_to_select_label(value, reverse_mapping: dict[str, str]) -> str | None:
    if value in (None, ""):
        return None
    key = str(value).strip()
    return reverse_mapping.get(key, key)

def get_settings_default_ids() -> tuple[int | None, int | None]:
    if not frappe.db.exists("DocType", "Aanirids ISP Settings"):
        return None, None
    settings = frappe.get_single("Aanirids ISP Settings")
    default_isp_id = int(settings.default_isp_id) if settings.default_isp_id else None
    default_branch_id = int(settings.default_branch_id) if settings.default_branch_id else None
    return default_isp_id, default_branch_id

def resolve_isp_external_id(doc) -> int | None:
    if doc.isp:
        explicit_isp_id = frappe.db.get_value("ISP", doc.isp, "external_id")
        if explicit_isp_id:
            return int(explicit_isp_id)

    if doc.salesperson:
        salesperson_isp = frappe.db.get_value("Salesperson", doc.salesperson, "isp")
        if salesperson_isp:
            salesperson_isp_id = frappe.db.get_value("ISP", salesperson_isp, "external_id")
            if salesperson_isp_id:
                return int(salesperson_isp_id)

    settings_isp_id, _ = get_settings_default_ids()
    return settings_isp_id

def resolve_branch_external_id(doc) -> int | None:
    if doc.branch:
        explicit_branch_id = frappe.db.get_value("Branch", doc.branch, "custom_external_id")
        if explicit_branch_id:
            return int(explicit_branch_id)

    _, settings_branch_id = get_settings_default_ids()
    return settings_branch_id


def build_payload(
    doc,
    *,
    password: str | None = None,
    connection_password: str | None = None,
    include_created_by: bool = False,
):
    is_create_payload = include_created_by
    quota_fields = (
        "total_data_quota",
        "used_data_quota",
        "total_session_quota",
        "used_session_quota",
    )

    installation_payload = None
    install_address = doc.installation_address or doc.billing_address
    install_city = doc.installation_city or doc.billing_city
    install_zip = doc.installation_zip or doc.billing_zip
    if install_address or install_city or install_zip:
        installation_payload = json.dumps(
            {
                "address": install_address or "",
                "city": install_city or "",
                "zip": install_zip or "",
            }
        )

    profile_status_code = normalize_select_to_code(getattr(doc, "profile_status", None), PROFILE_STATUS_TO_CODE)
    if profile_status_code is None and is_create_payload:
        profile_status_code = PROFILE_STATUS_TO_CODE["Active (*)"]

    connection_type_code = normalize_select_to_code(getattr(doc, "connection_type", None), CONNECTION_TYPE_TO_CODE)
    if connection_type_code is None and is_create_payload:
        connection_type_code = CONNECTION_TYPE_TO_CODE["Radius PPPoE (*)"]

    sms_status_value = 1 if getattr(doc, "sms_status", 0) else 0
    email_status_value = 1 if getattr(doc, "email_status", 0) else 0

    # New subscriber screen in main UI always sends SMS/Email status enabled.
    if is_create_payload and getattr(doc, "sms_status", None) in (None, ""):
        sms_status_value = 1
    if is_create_payload and getattr(doc, "email_status", None) in (None, ""):
        email_status_value = 1

    payload = {
        "username": doc.username,
        "fullname": doc.full_name,
        "phone": doc.phone,
        "email": doc.email,
        "gender": (doc.gender or "").capitalize() if doc.gender else None,
        "country": doc.country,
        "company": getattr(doc, "company", None),
        "dob": str(doc.date_of_birth) if doc.date_of_birth else None,
        "connection_status": 1 if doc.status == "Active" else 0,
        "address": doc.billing_address,
        "city": doc.billing_city,
        "zip": doc.billing_zip,
        "cpe_ip_address": doc.cpe_ip_address,
        "latitude": float(doc.latitude) if doc.latitude not in (None, "") else None,
        "longitude": float(doc.longitude) if doc.longitude not in (None, "") else None,
        "installation_address": installation_payload,
        "identity_type": doc.id_proof_type,
        "identity": doc.id_proof_number,
        "simultaneous_use": int(doc.simultaneous_use) if doc.simultaneous_use not in (None, "") else None,
        "profile_status": profile_status_code,
        "connection_type": connection_type_code,
        "expiration_date": str(doc.expiration_date) if getattr(doc, "expiration_date", None) else None,
        "mac_address": doc.mac_address,
        "static_ip": doc.ip_address,
        "auto_renew_status": 1 if doc.auto_renew_status else 0,
        "sms_status": sms_status_value,
        "email_status": email_status_value,
        "mac_lock_status": 1 if doc.mac_lock_status else 0,
        "lock_volume_status": 1 if getattr(doc, "lock_volume_status", 0) else 0,
        "total_data_quota": float(doc.total_data_quota) if getattr(doc, "total_data_quota", None) not in (None, "") else None,
        "used_data_quota": float(doc.used_data_quota) if getattr(doc, "used_data_quota", None) not in (None, "") else None,
        "login_log_status": 1 if getattr(doc, "login_log_status", 0) else 0,
        "lock_session_status": 1 if getattr(doc, "lock_session_status", 0) else 0,
        "total_session_quota": int(doc.total_session_quota) if getattr(doc, "total_session_quota", None) not in (None, "") else None,
        "used_session_quota": int(doc.used_session_quota) if getattr(doc, "used_session_quota", None) not in (None, "") else None,
        "discount_type": normalize_select_to_code(getattr(doc, "discount_type", None), DISCOUNT_TYPE_TO_CODE),
        "discount": float(doc.discount) if getattr(doc, "discount", None) not in (None, "") else None,
    }

    if password is not None:
        payload["password"] = password

    if connection_password is not None:
        payload["connection_password"] = connection_password

    # ✅ SAFE Links: only send if value exists + external_id exists
    if doc.salesperson:
        sp_external_id = frappe.db.get_value("Salesperson", doc.salesperson, "external_id")
        if sp_external_id:
            payload["salesperson_id"] = int(sp_external_id)

    if doc.package_link:
        plan_external_id = frappe.db.get_value("Plan", doc.package_link, "external_id")
        if plan_external_id:
            payload["package_id"] = int(plan_external_id)
    
    if doc.nas_server:
        nas_external_id = frappe.db.get_value("NAS", doc.nas_server, "external_id")
        if nas_external_id:
            payload["nas_id"] = int(nas_external_id)
    
    branch_external_id = resolve_branch_external_id(doc)
    if branch_external_id:
        payload["branch_id"] = int(branch_external_id)

    isp_external_id = resolve_isp_external_id(doc)
    if isp_external_id:
        payload["isp_id"] = int(isp_external_id)

    if getattr(doc, "ip_pool", None):
        ip_pool_external_id = frappe.db.get_value("IP Pool", doc.ip_pool, "external_id")
        if ip_pool_external_id:
            payload["ip_pool_id"] = int(ip_pool_external_id)

    if getattr(doc, "ip_address_link", None):
        ip_address_external_id = frappe.db.get_value("IP Address", doc.ip_address_link, "external_id")
        if ip_address_external_id:
            payload["ip_address_id"] = int(ip_address_external_id)

    if include_created_by:
        created_by_id = None
        created_by_username = None

        if doc.salesperson:
            created_by_id = frappe.db.get_value("Salesperson", doc.salesperson, "external_id")
            created_by_username = frappe.db.get_value("Salesperson", doc.salesperson, "username")

        if created_by_username is None and frappe.session.user and frappe.session.user != "Guest":
            user_name = frappe.db.get_value("User", frappe.session.user, "username")
            created_by_username = user_name or frappe.session.user

        if created_by_id not in (None, ""):
            payload["created_by_id"] = int(created_by_id)
        if created_by_username:
            payload["created_by_username"] = str(created_by_username)

    # On create, let backend DB defaults own quota initialization.
    if is_create_payload:
        for key in quota_fields:
            payload.pop(key, None)

    # ✅ Remove None values
    payload = {k: v for k, v in payload.items() if v is not None}

    return payload


# ============================================================
# ✅ BACKEND CRUD HELPERS
# ============================================================
def backend_create_subscriber(doc):
    """POST create subscriber in backend and return external_id."""
    connection_password = doc.get_password("connection_password") if hasattr(doc, "get_password") else None

    # Backend requires non-null password, but does NOT hash on create.
    # We'll set the real portal password via /subscribers/:id/reset-password immediately after create.
    temp_password = f"TEMP-{frappe.generate_hash(length=12)}"

    payload = build_payload(
        doc,
        password=temp_password,
        connection_password=connection_password,
        include_created_by=True,
    )
    data = post_json("/subscribers", json=payload, scope=True)

    external_id = data.get("id") or (data.get("data") or {}).get("id")
    if not external_id:
        frappe.throw("Backend did not return created subscriber id (external_id)")

    return data


def backend_update_subscriber(doc):
    if not doc.external_id:
        frappe.throw("External ID missing. Cannot update backend.")

    payload = build_payload(doc)
    put_json(f"/subscribers/{doc.external_id}", json=payload, scope=True)


def backend_delete_subscriber(doc):
    """DELETE subscriber in backend."""
    if not doc.external_id:
        return

    api_delete(f"/subscribers/{doc.external_id}", scope=True, expected_statuses=(200, 204, 404))


def backend_reset_passwords_and_radcheck(
    subscriber_id: str,
    *,
    username: str,
    portal_password: str | None = None,
    connection_password: str | None = None,
):
    """
    Uses backend endpoint that hashes portal_password (bcrypt) and keeps radcheck Cleartext-Password in sync.
    """
    payload: dict[str, str] = {"username": username}
    if portal_password is not None and portal_password.strip() != "":
        payload["portal_password"] = portal_password
    if connection_password is not None and connection_password.strip() != "":
        payload["connection_password"] = connection_password

    if len(payload) <= 1:
        return

    put_json(
        f"/subscribers/{subscriber_id}/reset-password",
        json=payload,
        scope=True,
        expected_statuses=(200,),
    )


def backend_set_radcheck_expiration(username: str, expiration_iso: str):
    put_json(
        f"/radcheck/username/{username}/expiration",
        json={"expirationDate": format_radius_datetime(expiration_iso)},
        scope=True,
        expected_statuses=(200,),
    )


def backend_create_radusergroup(username: str, groupname: str):
    post_json(
        "/radusergroup",
        json={"username": username, "groupname": groupname, "priority": 1},
        scope=True,
        expected_statuses=(200, 201),
    )


def backend_create_subscriber_services(
    subscriber_id: str | int,
    package_id: str | int,
    *,
    description: str | None = None,
    action_by_id: int | None = None,
    action_by_username: str | None = None,
):
    payload = {
        "subscriber_id": int(subscriber_id),
        "package_id": int(package_id),
        "created_at": str(now_datetime()),
        "updated_at": str(now_datetime()),
    }
    if description:
        payload["description"] = description
    if action_by_id is not None:
        payload["action_by_id"] = int(action_by_id)
    if action_by_username:
        payload["action_by_username"] = action_by_username

    return post_json("/subscriber-services", json=payload, scope=True, expected_statuses=(200, 201))


def resolve_action_by(doc) -> tuple[int | None, str | None]:
    action_by_id = None
    action_by_username = None

    if getattr(doc, "salesperson", None):
        action_by_id = frappe.db.get_value("Salesperson", doc.salesperson, "external_id")
        action_by_username = frappe.db.get_value("Salesperson", doc.salesperson, "username")

    if not action_by_username and frappe.session.user and frappe.session.user != "Guest":
        user_name = frappe.db.get_value("User", frappe.session.user, "username")
        action_by_username = user_name or frappe.session.user

    if action_by_id in ("", None):
        action_by_id = None
    else:
        action_by_id = int(action_by_id)

    return action_by_id, action_by_username


def backend_upload_document(
	*,
	file_path: str,
	original_filename: str,
	document_name: str,
	subscriber_id: int,
	subscriber_username: str,
	uploaded_by_id: int | None,
	uploaded_by_username: str | None,
	isp_id: int | None,
	branch_id: int | None,
) -> dict:
	now_iso = now_datetime().isoformat()

	data = {
		"file_name": document_name,
		"subscriber_id": str(subscriber_id),
		"owner_type": "2",  # 2 = Subscriber
		"owner_id": str(subscriber_id),
		"owner_username": subscriber_username,
		"uploaded_by_id": str(uploaded_by_id) if uploaded_by_id is not None else "",
		"uploaded_by_username": uploaded_by_username or "",
		"isp_id": str(isp_id) if isp_id is not None else "",
		"branch_id": str(branch_id) if branch_id is not None else "",
		"verification_status": "0",
		"created_at": now_iso,
		"updated_at": now_iso,
	}
	# remove empty strings (backend sanitizeData turns "" into null, but keep payload small)
	data = {k: v for k, v in data.items() if v not in (None, "")}

	content_type = mimetypes.guess_type(original_filename)[0] or "application/octet-stream"
	with open(file_path, "rb") as f:
		files = {"file": (original_filename, f, content_type)}
		resp = api_request(
			"POST",
			"/documents",
			data=data,
			files=files,
			scope=True,
			expected_statuses=(201,),
		)
		return resp.json()


def backend_delete_document(document_id: int) -> None:
	api_delete(f"/documents/{int(document_id)}", scope=True, expected_statuses=(200, 204, 404))


def backend_disconnect_user(username: str) -> None:
	post_json(
		"/radacct/disconnect",
		json={"username": username},
		scope=True,
		expected_statuses=(200, 201),
	)


def backend_disable_net(username: str) -> None:
	post_json(
		"/radcheck/disable-net",
		json={"username": username},
		scope=True,
		expected_statuses=(200, 201),
	)


def backend_enable_net(username: str) -> None:
	post_json(
		"/radcheck/enable-net",
		json={"username": username},
		scope=True,
		expected_statuses=(200, 201),
	)


def backend_disable_profile(subscriber_id: int | str) -> None:
	put_json(
		f"/subscribers/{subscriber_id}/disable-profile",
		json={},
		scope=True,
		expected_statuses=(200, 201),
	)


def backend_enable_profile(subscriber_id: int | str) -> None:
	put_json(
		f"/subscribers/{subscriber_id}/enable-profile",
		json={},
		scope=True,
		expected_statuses=(200, 201),
	)


def backend_revoke_recharge(subscriber_id: int | str) -> None:
	post_json(
		f"/subscribers/{subscriber_id}/revoke-recharge",
		json={},
		scope=True,
		expected_statuses=(200, 201),
	)


def upload_documents_for_subscriber(doc, *, backend_subscriber_id: int, backend_username: str) -> None:
	"""
	Uploads child-table documents to backend /documents.
	Does not raise if a single document fails; records the error on the row.
	"""
	if not getattr(doc, "documents", None):
		return

	uploaded_by_id = None
	uploaded_by_username = None
	if doc.salesperson:
		uploaded_by_id = frappe.db.get_value("Salesperson", doc.salesperson, "external_id")
		uploaded_by_username = frappe.db.get_value("Salesperson", doc.salesperson, "username")

	isp_external_id = None
	if doc.isp:
		isp_external_id = frappe.db.get_value("ISP", doc.isp, "external_id")

	branch_external_id = None
	if doc.branch:
		branch_external_id = frappe.db.get_value("Branch", doc.branch, "custom_external_id")

	for row in doc.documents:
		try:
			if row.get("uploaded") and row.get("backend_document_id"):
				continue

			file_url = row.get("document_file")
			if not file_url:
				continue

			file_path = frappe.get_site_path(file_url.lstrip("/"))
			if not os.path.exists(file_path):
				raise Exception(f"File not found on disk for {file_url}")

			original_filename = os.path.basename(file_path)
			document_name = row.get("document_name") or original_filename

			resp = backend_upload_document(
				file_path=file_path,
				original_filename=original_filename,
				document_name=document_name,
				subscriber_id=int(backend_subscriber_id),
				subscriber_username=backend_username,
				uploaded_by_id=int(uploaded_by_id) if uploaded_by_id is not None else None,
				uploaded_by_username=uploaded_by_username,
				isp_id=int(isp_external_id) if isp_external_id is not None else None,
				branch_id=int(branch_external_id) if branch_external_id is not None else None,
			)

			backend_doc_id = (resp.get("data") or {}).get("id") or resp.get("id")
			backend_file_link = (resp.get("data") or {}).get("file_link") or resp.get("file_link")
			verification_status = (resp.get("data") or {}).get("verification_status")
			frappe.db.set_value(
				"Subscriber Document",
				row.name,
				{
					"backend_document_id": backend_doc_id,
					"backend_file_link": backend_file_link,
					"verification_status": verification_status,
					"uploaded": 1,
					"uploaded_on": now_datetime(),
					"upload_error": None,
				},
				update_modified=False,
			)
		except Exception as exc:
			frappe.db.set_value(
				"Subscriber Document",
				row.name,
				{
					"uploaded": 0,
					"uploaded_on": None,
					"upload_error": str(exc),
				},
				update_modified=False,
			)
			frappe.log_error(
				title="Subscriber Document Upload Failed",
				message=f"Subscriber={doc.name} | Row={row.name}\n{frappe.get_traceback()}",
			)


# ============================================================
# ✅ ROLLBACK HELPER - Delete backend subscriber if Frappe save fails
# ============================================================
def rollback_backend_subscriber(external_id):
    """Delete subscriber from backend (used when Frappe save fails)."""
    if not external_id:
        return
    
    try:
        api_delete(f"/subscribers/{external_id}", scope=True, expected_statuses=(200, 204, 404))
    except Exception as e:
        frappe.log_error(
            title="⚠️ Backend Rollback Failed",
            message=f"Failed to delete external_id={external_id}: {str(e)}"
        )


# ============================================================
# ✅ DOC CONTROLLER (OPTIMIZED CRUD)
# ============================================================
class Subscriber(Document):

    def before_insert(self):
        """
        ✅ Auto-fill Salesperson & Branch based on the logged-in Session User.
        """
        # 1. Skip if this doc is being created by the Backend Sync process
        if getattr(self.flags, "from_backend_sync", False):
            return

        # 2. Skip if the user manually selected a salesperson already
        if self.salesperson:
            return

        # 3. Get the current logged-in user
        current_user = frappe.session.user
        
        if not current_user or current_user == "Guest":
            return

        # 4. Find the Salesperson record linked to this System User
        # We fetch 'name' (ID) and 'branch'
        sp_data = frappe.db.get_value(
            "Salesperson", 
            {"user": current_user}, 
            ["name", "branch"], 
            as_dict=True
        )

        # 5. Assign the values
        if sp_data:
            self.salesperson = sp_data.name
            
            # Auto-fill branch if it wasn't selected manually
            if not self.branch and sp_data.branch:
                self.branch = sp_data.branch

    def validate(self):
        """
        ✅ VALIDATION BEFORE ANY API CALLS
        Add all your validation logic here
        """
        # Skip validation for backend sync
        if getattr(self.flags, "from_backend_sync", False):
            return

        # Match main New Subscriber UI defaults for fields not entered manually.
        if self.is_new():
            if not self.status:
                self.status = "Active"
            if not self.profile_status:
                self.profile_status = "Active (*)"
            if not self.connection_type:
                self.connection_type = "Radius PPPoE (*)"
            if self.sms_status in (None, ""):
                self.sms_status = 1
            if self.email_status in (None, ""):
                self.email_status = 1

            if not self.password:
                self.password = "WavesNett123"

        # Add your validation rules
        if not self.username:
            frappe.throw("Username is required")
        
        if not self.full_name:
            frappe.throw("Full Name is required")

        if not self.phone:
            frappe.throw("Phone is required")

        if not self.email:
            frappe.throw("Email is required")

        if not self.salesperson:
            frappe.throw("Salesperson is required")

        salesperson_external_id = frappe.db.get_value("Salesperson", self.salesperson, "external_id")
        if not salesperson_external_id:
            frappe.throw(f"Salesperson external_id not found for {self.salesperson}")

        if not self.package_link:
            frappe.throw("Plan is required")

        package_external_id = frappe.db.get_value("Plan", self.package_link, "external_id")
        if not package_external_id:
            frappe.throw(f"Plan external_id not found for {self.package_link}")

        # Align with main create form expectations: address blocks are required.
        if not self.billing_address or not self.billing_city or not self.billing_zip:
            frappe.throw("Billing Address, Billing City and Billing ZIP are required.")

        if not self.installation_address or not self.installation_city or not self.installation_zip:
            frappe.throw("Installation Address, Installation City and Installation ZIP are required.")

        if self.is_new():
            if not self.id_proof_type:
                frappe.throw("ID Proof Type is required.")
            if not self.id_proof_number:
                frappe.throw("ID Proof Number is required.")
            if not (self.get("documents") or []):
                frappe.throw("At least one document is required for new subscriber.")

        if self.is_new():
            portal_password = self.get_password("password")
            connection_password = self.get_password("connection_password")

            if not portal_password:
                frappe.throw("Portal Password is required (will be encrypted in backend).")

            if not connection_password:
                frappe.throw("Connection Password is required.")

        # Validate documents child rows: allow backend-synced docs without Frappe attachment,
        # but block completely empty rows.
        for idx, row in enumerate(self.get("documents") or [], start=1):
            has_local_file = bool(row.get("document_file"))
            has_backend_file = bool(row.get("backend_document_id")) or bool(row.get("backend_file_link"))
            if not has_local_file and not has_backend_file:
                frappe.throw(f"Subscriber Document Row #{idx}: Value missing for: Document File")

        # Track removed backend documents so we can delete them from backend on save.
        if not self.is_new():
            previous = self.get_doc_before_save()
            if previous:
                prev_ids = {
                    int(r.get("backend_document_id"))
                    for r in (previous.get("documents") or [])
                    if r.get("backend_document_id")
                }
                current_ids = {
                    int(r.get("backend_document_id"))
                    for r in (self.get("documents") or [])
                    if r.get("backend_document_id")
                }
                removed_ids = sorted(prev_ids - current_ids)
                if removed_ids:
                    self.flags.removed_backend_document_ids = removed_ids
        
        # Add more validations as needed
        # This ensures Frappe validates BEFORE we call backend APIs

        # Track password inputs (Password fields become "*****" after save)
        portal_password_input = self.get("password")
        if portal_password_input and not self.is_dummy_password(portal_password_input):
            self.flags.portal_password_input = portal_password_input

        connection_password_input = self.get("connection_password")
        if connection_password_input and not self.is_dummy_password(connection_password_input):
            self.flags.connection_password_input = connection_password_input

        # Track package change for history row
        if not self.is_new() and self.has_value_changed("package_link"):
            self.flags.package_changed = True

        # Track document changes (upload new rows on update)
        if not self.is_new() and getattr(self, "documents", None):
            self.flags.has_pending_documents = any(
                (not d.get("uploaded")) or (not d.get("backend_document_id")) for d in (self.documents or [])
            )

    def after_insert(self):
        """
        ✅ ONLY CREATE BACKEND RECORDS AFTER FRAPPE SUCCESSFULLY SAVES
        This runs AFTER Frappe validation passes and document is inserted
        """
        if getattr(self.flags, "from_backend_sync", False):
            return

        if self.external_id:
            return

        portal_password = self.get_password("password")
        connection_password = self.get_password("connection_password")
        if not portal_password or not connection_password:
            frappe.throw("Password and Connection Password are required for backend provisioning.")

        created_external_id = None
        created_username = None
        
        try:
            # Step 1: Create subscriber in backend
            created = backend_create_subscriber(self)
            created_external_id = created.get("id") or (created.get("data") or {}).get("id")
            created_username = created.get("username") or (created.get("data") or {}).get("username") or self.username

            if not created_external_id:
                frappe.throw("Backend did not return subscriber id (external_id)")

            # Step 2: If backend changed username, rename local doc to match
            if created_username and created_username != self.name:
                old_name = self.name
                # Frappe versions differ on rename_doc kwargs. Try the richer
                # signature first, then fallback to a minimal compatible call.
                try:
                    frappe.rename_doc(
                        "Subscriber",
                        old_name,
                        created_username,
                        force=True,
                        ignore_permissions=True,
                        show_alert=False,
                        rebuild_search=False,
                    )
                except TypeError:
                    frappe.rename_doc(
                        "Subscriber",
                        old_name,
                        created_username,
                        force=True,
                    )
                self.name = created_username
                self.username = created_username
                frappe.db.set_value(
                    "Subscriber",
                    self.name,
                    {"username": created_username},
                    update_modified=False,
                )

            # Step 3: Update Frappe with external_id (without triggering on_update)
            frappe.db.set_value(
                "Subscriber",
                self.name,
                {
                    "external_id": created_external_id,
                    "details_synced": 1,
                    "details_synced_on": now_datetime(),
                    "created_at": clean_datetime(created.get("created_at")) if created.get("created_at") else None,
                },
                update_modified=False
            )
            
            # Update doc object for subsequent operations
            self.external_id = str(created_external_id)

            # Step 4: Hash portal password + sync radcheck Cleartext-Password in backend
            backend_reset_passwords_and_radcheck(
                str(created_external_id),
                username=created_username,
                portal_password=portal_password,
                connection_password=connection_password,
            )

            # Step 5: Ensure radcheck Expiration exists/updated
            expiration_iso = created.get("expiration_date") or (created.get("data") or {}).get("expiration_date")
            if expiration_iso:
                backend_set_radcheck_expiration(created_username, expiration_iso)

            # Step 6: Create radusergroup using package.policy_group
            package_external_id = frappe.db.get_value("Plan", self.package_link, "external_id")
            pkg = get_json(f"/packages/{package_external_id}", scope=True) or {}
            policy_group = (pkg.get("data") or pkg).get("policy_group")
            if policy_group:
                backend_create_radusergroup(created_username, str(policy_group))

            # Step 7: Create subscriber_services record
            if package_external_id:
                action_by_id, action_by_username = resolve_action_by(self)
                backend_create_subscriber_services(
                    created_external_id,
                    package_external_id,
                    description=f"Subscribed to {self.package_link}",
                    action_by_id=action_by_id,
                    action_by_username=action_by_username,
                )

            # Step 8: Upload documents (non-blocking)
            try:
                upload_documents_for_subscriber(
                    self,
                    backend_subscriber_id=int(created_external_id),
                    backend_username=created_username,
                )
            except Exception:
                frappe.log_error(
                    title="Subscriber Document Upload Failed (Non-blocking)",
                    message=f"Subscriber={self.name}\n{frappe.get_traceback()}",
                )
            
        except Exception as e:
            # ⚠️ CRITICAL: Rollback backend if anything fails
            frappe.log_error(
                title="❌ Backend Creation Failed",
                message=f"Subscriber={self.name}\nError: {str(e)}\nRolling back..."
            )
            
            # Rollback backend subscriber
            if created_external_id:
                rollback_backend_subscriber(created_external_id)
            
            # Re-raise to show error to user
            frappe.throw(f"Failed to create subscriber in backend: {str(e)}")


    def on_update(self):
        """
        ✅ Update backend only when user updates manually in Frappe
        """
        # Skip updates coming from API sync jobs
        if getattr(self.flags, "from_backend_sync", False):
            return

        # Skip if this is part of insert flow
        if getattr(self.flags, "in_insert", False):
            return

        # Only update if backend record exists
        if not self.external_id:
            return

        try:
            backend_update_subscriber(self)

            # If user entered new passwords, sync via backend unified endpoint
            portal_password_input = getattr(self.flags, "portal_password_input", None)
            connection_password_input = getattr(self.flags, "connection_password_input", None)

            if portal_password_input or connection_password_input:
                backend_reset_passwords_and_radcheck(
                    str(self.external_id),
                    username=self.username,
                    portal_password=portal_password_input,
                    connection_password=connection_password_input,
                )

            # If plan changed, create a subscriber_services history row (UI does this on create; keep parity on change)
            if getattr(self.flags, "package_changed", False) and self.package_link:
                package_external_id = frappe.db.get_value("Plan", self.package_link, "external_id")
                if package_external_id:
                    action_by_id, action_by_username = resolve_action_by(self)
                    backend_create_subscriber_services(
                        int(self.external_id),
                        int(package_external_id),
                        description="Package updated from ERPNext",
                        action_by_id=action_by_id,
                        action_by_username=action_by_username,
                    )

            # Upload any newly added documents
            if getattr(self.flags, "has_pending_documents", False):
                upload_documents_for_subscriber(
                    self,
                    backend_subscriber_id=int(self.external_id),
                    backend_username=self.username,
                )

            # Delete any removed backend documents (matches UI behavior)
            removed_ids = getattr(self.flags, "removed_backend_document_ids", None) or []
            for doc_id in removed_ids:
                backend_delete_document(int(doc_id))

        except Exception as e:
            frappe.log_error(
                title="❌ Backend Update Failed",
                message=f"Subscriber={self.name}\nError: {str(e)}"
            )
            frappe.throw(f"Failed to update subscriber in backend: {str(e)}")


    def on_trash(self):
        """
        ✅ Delete backend record when user deletes manually in Frappe
        """
        if getattr(self.flags, "from_backend_sync", False):
            return

        backend_delete_subscriber(self)


# ============================================================
# ✅ FETCH LIST (PAGINATION)
# ============================================================
def fetch_subscribers_page(limit=DEFAULT_LIMIT, offset=0):
    return get_json("/subscribers", params={"limit": limit, "offset": offset}, scope=True)


# ============================================================
# ✅ LIST SYNC ONLY (AUTO + MANUAL)
# ============================================================
def sync_subscribers_list_only(limit=DEFAULT_LIMIT):
    created = 0
    updated = 0
    total_fetched = 0
    offset = 0

    while True:
        data = fetch_subscribers_page(limit=limit, offset=offset)

        rows = data.get("data", []) if isinstance(data, dict) else data
        pagination = data.get("pagination", {}) if isinstance(data, dict) else {}

        if not rows:
            break

        total_fetched += len(rows)

        for s in rows:
            try:
                external_id = s.get("id")
                username = s.get("username")

                if not external_id or not username:
                    continue

                external_id = str(external_id)

                existing = frappe.db.get_value(
                    "Subscriber", {"external_id": external_id}, "name"
                )

                if existing:
                    doc = frappe.get_doc("Subscriber", existing)
                    is_new = False
                else:
                    doc = frappe.new_doc("Subscriber")
                    doc.external_id = external_id
                    is_new = True

                    doc.details_synced = 0
                    doc.details_synced_on = None

                # ✅ LIST FIELDS
                doc.username = username
                doc.full_name = s.get("fullname") or ""
                doc.phone = s.get("phone")
                doc.email = s.get("email")
                doc.status = "Active" if str(s.get("connection_status")) == "1" else "Inactive"

                # ✅ critical to avoid CRUD loop
                doc.flags.from_backend_sync = True
                doc.save(ignore_permissions=True)

                if is_new:
                    created += 1
                else:
                    updated += 1

            except Exception as e:
                frappe.log_error(str(e), "Subscriber List Sync Error")

        frappe.db.commit()

        # Pagination
        if pagination.get("hasMore") is True:
            offset += limit
            continue

        if len(rows) < limit:
            break

        offset += limit

    return {
        "total_fetched": total_fetched,
        "created": created,
        "updated": updated
    }


# ============================================================
# ✅ AUTO + MANUAL PIPELINE
# LIST SYNC + QUEUE BULK DETAILS
# ============================================================
@frappe.whitelist()
def sync_list_and_enqueue_bulk_details(limit=DEFAULT_LIMIT):
    """
    ✅ Use this for:
    - Auto scheduler hourly
    - Manual list button
    """
    result = sync_subscribers_list_only(limit=limit)
    enqueue_bulk_details_sync()

    return {
        "status": "success",
        "message": "List synced ✅ + Bulk details queued ✅",
        **result
    }


# ============================================================
# ✅ BULK DETAILS SYNC (BACKGROUND)
# ============================================================
@frappe.whitelist()
def enqueue_bulk_details_sync():
    frappe.enqueue(
        method="aanirids_isp.aanirids_isp.doctype.subscriber.subscriber.sync_subscriber_details_bulk_job",
        queue="long",
        timeout=7200,
        is_async=True
    )
    return {"status": "queued", "message": "Bulk details sync queued ✅"}


def sync_subscriber_details_bulk_job():
    subscriber_names = frappe.get_all("Subscriber", pluck="name")

    total = len(subscriber_names)
    success = 0
    failed = 0
    batch_commit = 25

    for i, name in enumerate(subscriber_names, start=1):
        try:
            sync_single_subscriber_details(name)
            success += 1

            if i % batch_commit == 0:
                frappe.db.commit()

        except Exception as e:
            failed += 1
            frappe.log_error(
                title="Subscriber Bulk Details Sync Error",
                message=f"{name}\n{str(e)}"
            )

    frappe.db.commit()

    frappe.log_error(
        title="✅ Bulk Subscriber Details Sync Completed",
        message=f"Total={total} | Success={success} | Failed={failed}"
    )


# ============================================================
# ✅ DIRECT DETAILS SYNC (FORM BUTTON / DIRECT CALL)
# ============================================================
@frappe.whitelist()
def fetch_subscriber_details_direct(subscriber_name):
    """
    Direct sync (not background).
    Recommended only for button action.
    """
    sync_single_subscriber_details(subscriber_name)
    frappe.db.commit()
    return {"status": "success", "message": "Details synced directly ✅"}


# ============================================================
# ✅ ENQUEUE DETAILS SYNC (FORM OPEN SAFE)
# ============================================================
@frappe.whitelist()
def enqueue_fetch_subscriber_details(subscriber_name):
    """
    Background sync for form open (no refresh conflict).
    """
    frappe.enqueue(
        method="aanirids_isp.aanirids_isp.doctype.subscriber.subscriber.fetch_subscriber_details_job",
        queue="long",
        timeout=600,
        subscriber_name=subscriber_name
    )
    return {"status": "queued", "message": "Subscriber details sync queued ✅"}


def fetch_subscriber_details_job(subscriber_name):
    sync_single_subscriber_details(subscriber_name)
    frappe.db.commit()


def _get_backend_subscriber_or_throw(subscriber_name: str):
	doc = frappe.get_doc("Subscriber", subscriber_name)
	if not doc.external_id:
		frappe.throw("External ID missing on Subscriber.")
	if not doc.username:
		frappe.throw("Username missing on Subscriber.")
	return doc


@frappe.whitelist()
def reset_subscriber_password(subscriber_name: str, portal_password: str | None = None, connection_password: str | None = None):
	doc = _get_backend_subscriber_or_throw(subscriber_name)
	if not (portal_password or connection_password):
		frappe.throw("Provide at least one password value.")

	backend_reset_passwords_and_radcheck(
		str(doc.external_id),
		username=doc.username,
		portal_password=portal_password,
		connection_password=connection_password,
	)
	return {"status": "success", "message": "Password updated in backend."}


@frappe.whitelist()
def disable_subscriber_net(subscriber_name: str):
	doc = _get_backend_subscriber_or_throw(subscriber_name)
	backend_disable_net(doc.username)
	return {"status": "success", "message": "User network disabled."}


@frappe.whitelist()
def enable_subscriber_net(subscriber_name: str):
	doc = _get_backend_subscriber_or_throw(subscriber_name)
	backend_enable_net(doc.username)
	return {"status": "success", "message": "User network enabled."}


@frappe.whitelist()
def disconnect_subscriber_session(subscriber_name: str):
	doc = _get_backend_subscriber_or_throw(subscriber_name)
	backend_disconnect_user(doc.username)
	return {"status": "success", "message": "Disconnect request sent."}


@frappe.whitelist()
def disable_subscriber_profile(subscriber_name: str):
	doc = _get_backend_subscriber_or_throw(subscriber_name)
	backend_disable_profile(doc.external_id)
	sync_single_subscriber_details(doc.name)
	return {"status": "success", "message": "Subscriber profile disabled."}


@frappe.whitelist()
def enable_subscriber_profile(subscriber_name: str):
	doc = _get_backend_subscriber_or_throw(subscriber_name)
	backend_enable_profile(doc.external_id)
	sync_single_subscriber_details(doc.name)
	return {"status": "success", "message": "Subscriber profile enabled."}


@frappe.whitelist()
def revoke_subscriber_recharge(subscriber_name: str):
	doc = _get_backend_subscriber_or_throw(subscriber_name)
	backend_revoke_recharge(doc.external_id)
	sync_single_subscriber_details(doc.name)
	return {"status": "success", "message": "Recharge revoked in backend."}


# ============================================================
# ✅ SINGLE SUBSCRIBER DETAIL SYNC LOGIC
# ============================================================
def sync_single_subscriber_details(subscriber_name):
    doc = frappe.get_doc("Subscriber", subscriber_name)

    if not doc.external_id:
        return

    data = get_json(f"/subscribers/{doc.external_id}", scope=True)

    # Basic
    doc.full_name = data.get("fullname") or doc.full_name
    doc.phone = data.get("phone")
    doc.email = data.get("email")
    doc.gender = data.get("gender").capitalize() if data.get("gender") else None
    doc.country = data.get("country") or doc.country

    doc.date_of_birth = clean_date(data.get("dob"))
    doc.status = "Active" if str(data.get("connection_status")) == "1" else "Inactive"
    doc.profile_status = map_code_to_select_label(data.get("profile_status"), PROFILE_CODE_TO_STATUS)
    doc.connection_type = map_code_to_select_label(data.get("connection_type"), CONNECTION_CODE_TO_TYPE)
    doc.expiration_date = clean_datetime(data.get("expiration_date"))

    # NAS
    doc.nas_server = None
    nas_id = data.get("nas_id")
    if nas_id is not None:
        doc.nas_server = frappe.db.get_value(
            "NAS",
            {"external_id": str(nas_id)},
            "name"
        )

    # Plan
    doc.package_link = None
    package_id = data.get("package_id")
    if package_id:
        doc.package_link = frappe.db.get_value(
            "Plan",
            {"external_id": str(package_id)},
            "name"
        )

    # Salesperson
    doc.salesperson = None
    salesperson_id = data.get("salesperson_id")
    if salesperson_id is not None:
        doc.salesperson = frappe.db.get_value(
            "Salesperson",
            {"external_id": str(salesperson_id)},
            "name",
        )
    if not doc.salesperson and data.get("salesperson_name"):
        salesperson_name = str(data.get("salesperson_name"))
        doc.salesperson = (
            frappe.db.exists("Salesperson", salesperson_name)
            or frappe.db.get_value("Salesperson", {"full_name": salesperson_name}, "name")
            or None
        )

    # Branch
    doc.branch = None
    branch_id = data.get("branch_id")
    if branch_id:
        doc.branch = frappe.db.get_value(
            "Branch",
            {"custom_external_id": str(branch_id)},
            "name"
        )

    # Address
    doc.billing_address = data.get("address")
    doc.billing_city = data.get("city")
    doc.billing_zip = data.get("zip")

    # Installation
    install = data.get("installation_address")
    if install:
        if isinstance(install, dict):
            doc.installation_address = install.get("address")
            doc.installation_city = install.get("city")
            doc.installation_zip = install.get("zip")
        elif isinstance(install, str):
            try:
                parsed = json.loads(install)
                if isinstance(parsed, dict):
                    doc.installation_address = parsed.get("address")
                    doc.installation_city = parsed.get("city")
                    doc.installation_zip = parsed.get("zip")
                else:
                    doc.installation_address = install
            except Exception:
                doc.installation_address = install

    # Tech
    doc.cpe_ip_address = data.get("cpe_ip_address")
    doc.latitude = float(data.get("latitude")) if data.get("latitude") not in (None, "") else None
    doc.longitude = float(data.get("longitude")) if data.get("longitude") not in (None, "") else None
    doc.enable_portal_login = 1 if data.get("self_activation_status") else 0
    doc.mac_address = data.get("mac_address")

    doc.auto_renew_status = 1 if str(data.get("auto_renew_status") or "0") == "1" else 0
    doc.sms_status = 1 if str(data.get("sms_status") or "0") == "1" else 0
    doc.email_status = 1 if str(data.get("email_status") or "0") == "1" else 0
    doc.mac_lock_status = 1 if str(data.get("mac_lock_status") or "0") == "1" else 0

    # IP Pool
    doc.ip_pool = None
    ip_pool_id = data.get("ip_pool_id")
    if ip_pool_id is not None:
        doc.ip_pool = frappe.db.get_value(
            "IP Pool",
            {"external_id": str(ip_pool_id)},
            "name",
        )

    doc.ip_address_link = None
    ip_address_id = data.get("ip_address_id")
    if ip_address_id is not None:
        doc.ip_address_link = frappe.db.get_value(
            "IP Address",
            {"external_id": str(ip_address_id)},
            "name",
        )

    doc.lock_volume_status = 1 if str(data.get("lock_volume_status") or "0") == "1" else 0
    doc.total_data_quota = data.get("total_data_quota")
    doc.used_data_quota = data.get("used_data_quota")
    doc.login_log_status = 1 if str(data.get("login_log_status") or "0") == "1" else 0
    doc.lock_session_status = 1 if str(data.get("lock_session_status") or "0") == "1" else 0
    doc.total_session_quota = data.get("total_session_quota")
    doc.used_session_quota = data.get("used_session_quota")
    doc.discount_type = map_code_to_select_label(data.get("discount_type"), DISCOUNT_CODE_TO_TYPE)
    doc.discount = data.get("discount")
    doc.ip_address = data.get("static_ip")

    # Documents
    doc.id_proof_type = normalize_identity_type(data.get("identity_type"))
    doc.id_proof_number = data.get("identity")

    # ✅ Flags
    doc.details_synced = 1
    doc.details_synced_on = now_datetime()

    doc.created_at = clean_datetime(data.get("created_at"))

    # ✅ very important to avoid CRUD loop
    doc.flags.from_backend_sync = True
    doc.save(ignore_permissions=True)

    # Sync documents after saving subscriber fields (child table updates)
    sync_backend_documents_into_child_table(doc)


def sync_backend_documents_into_child_table(doc):
    """
    Fetch backend documents for subscriber and upsert into Subscriber Document child table.
    We only add/update rows with backend_document_id, and keep any pending local rows.
    """
    if not doc.external_id:
        return

    try:
        payload = get_json(f"/documents/subscriber/{doc.external_id}", scope=True) or {}
    except Exception:
        frappe.log_error(title="Subscriber Documents Sync Failed", message=frappe.get_traceback())
        return

    backend_docs = (payload.get("data") or []) if isinstance(payload, dict) else (payload or [])
    backend_docs_by_id = {int(d.get("id")): d for d in backend_docs if d.get("id") is not None}

    existing_rows = list(doc.get("documents") or [])
    backend_ids = set(backend_docs_by_id.keys())
    rows_by_backend_id = {}
    for r in existing_rows:
        if r.get("backend_document_id"):
            try:
                rows_by_backend_id[int(r.backend_document_id)] = r
            except Exception:
                continue

    # Update existing rows that are present in backend
    for backend_id, backend_doc in backend_docs_by_id.items():
        row = rows_by_backend_id.get(backend_id)
        if not row:
            row = doc.append("documents", {})

        row.document_name = backend_doc.get("file_name") or row.document_name
        row.note = backend_doc.get("note")
        row.backend_document_id = backend_id
        row.backend_file_link = backend_doc.get("file_link")
        row.verification_status = backend_doc.get("verification_status")
        row.uploaded = 1
        row.uploaded_on = clean_datetime(backend_doc.get("created_at")) or now_datetime()
        row.upload_error = None

    # Remove rows that were synced earlier but no longer exist in backend.
    # Keep local pending rows (without backend_document_id) untouched.
    rows_to_remove = []
    for row in existing_rows:
        backend_id = row.get("backend_document_id")
        if not backend_id:
            continue
        try:
            backend_id_int = int(backend_id)
        except Exception:
            continue
        if backend_id_int not in backend_ids:
            rows_to_remove.append(row)

    for row in rows_to_remove:
        doc.remove(row)

    # Save child table changes without triggering backend update
    doc.flags.from_backend_sync = True
    doc.save(ignore_permissions=True)
