import frappe
import requests
import json
from frappe.utils import getdate, now_datetime
from frappe.model.document import Document

API_URL = "http://172.24.160.1:5003/api/subscribers"

RAD_CHECK_URL = "http://172.24.160.1:5003/api/radcheck"
RADUSERGROUP_URL = "http://172.24.160.1:5003/api/radusergroup"
SUBSCRIBER_SERVICES_URL = "http://172.24.160.1:5003/api/subscriber-services"

TIMEOUT = 30
DEFAULT_LIMIT = 50


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


def build_payload(doc):
    payload = {
        "username": doc.username,
        "fullname": doc.full_name,
        "phone": doc.phone,
        "email": doc.email,

        "gender": (doc.gender or "").capitalize() if doc.gender else None,
        "country": doc.country,
        "dob": str(doc.date_of_birth) if doc.date_of_birth else None,

        # backend usually expects connection_status not "status"
        "connection_status": 1 if doc.status == "Active" else 0,

        "password": doc.password,
        "connection_password": doc.connection_password,

        # Billing address
        "address": doc.billing_address,
        "city": doc.billing_city,
        "zip": doc.billing_zip,

        # Portal / Tech
        "cpe_ip_address": doc.cpe_ip_address,
        "latitude": float(doc.latitude or 0),
        "longitude": float(doc.longitude or 0),

        # Documents
        "identity_type": doc.id_proof_type,
        "identity": doc.id_proof_number,
    }

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

    # ✅ Remove None values (backend validation will fail sometimes)
    payload = {k: v for k, v in payload.items() if v is not None}

    return payload



# ============================================================
# ✅ BACKEND CRUD HELPERS
# ============================================================
def backend_create_subscriber(doc):
    """POST create subscriber in backend and return external_id."""
    payload = build_payload(doc)

    r = requests.post(API_URL, json=payload, timeout=TIMEOUT)
    if r.status_code not in (200, 201):
        frappe.throw(f"Create API Error {r.status_code}: {r.text}")

    data = r.json()
    external_id = data.get("id") or (data.get("data") or {}).get("id")

    if not external_id:
        frappe.throw("Backend did not return created subscriber id (external_id)")

    return str(external_id)


def backend_update_subscriber(doc):
    if not doc.external_id:
        frappe.throw("External ID missing. Cannot update backend.")

    payload = build_payload(doc)
    url = f"{API_URL}/{doc.external_id}"

    frappe.log_error(
        title="UPDATE PAYLOAD DEBUG",
        message=json.dumps(payload, indent=2)
    )

    r = requests.put(url, json=payload, timeout=TIMEOUT)

    if r.status_code not in (200, 201):
        frappe.throw(f"Update API Error {r.status_code}: {r.text}")



def backend_delete_subscriber(doc):
    """DELETE subscriber in backend."""
    if not doc.external_id:
        return

    url = f"{API_URL}/{doc.external_id}"
    r = requests.delete(url, timeout=TIMEOUT)
    if r.status_code not in (200, 204):
        frappe.throw(f"Delete API Error {r.status_code}: {r.text}")

def upload_document_to_backend(doc):
    """
    Upload document to backend Documents API:
    owner_id = external_id
    owner_username = username
    document_type = document_name
    file = document_upload
    """
    if not doc.external_id:
        return

    if not getattr(doc, "document_upload", None):
        return  # no document uploaded

    if not getattr(doc, "document_name", None):
        frappe.throw("Document Name is required before saving.")

    # ✅ Fetch attached file info from Frappe
    file_doc = frappe.get_doc("File", {"file_url": doc.document_upload})
    file_path = file_doc.get_full_path()

    with open(file_path, "rb") as f:
        files = {"file": f}
        data = {
            "owner_id": doc.external_id,
            "owner_username": doc.username,
            "document_type": doc.id_proof_type,
            "file_name": doc.document_name,
        }

        r = requests.post(
            "http://172.24.160.1:5003/api/documents",
            data=data,
            files=files,
            timeout=TIMEOUT
        )
    
    frappe.log_error(
        title="FILE DEBUG",
        message=f"file_url={doc.document_upload}\nfile_name={file_doc.file_name}\npath={file_path}"
    )

    if r.status_code not in (200, 201):
        frappe.throw(f"Document Upload Error {r.status_code}: {r.text}")

    return r.json()

def create_radcheck_for_subscriber(doc):
    if not doc.username:
        frappe.throw("Username is required for Radcheck")

    # pwd = doc.connection_password or doc.password
    # if not pwd:
    #     frappe.throw("Password / Connection Password is required for Radcheck")

    payload = {
        "username": doc.username,
        }

    r = requests.post(RAD_CHECK_URL, json=payload, timeout=TIMEOUT)
    if r.status_code not in (200, 201):
        frappe.throw(f"Radcheck Create Error {r.status_code}: {r.text}")

    return r.json()

def create_radusergroup_for_subscriber(doc):
    if not doc.username:
        frappe.throw("Username is required for Radusergroup")

    payload = {
        "username": doc.username,
    }

    r = requests.post(RADUSERGROUP_URL, json=payload, timeout=TIMEOUT)
    if r.status_code not in (200, 201):
        frappe.throw(f"Radusergroup Create Error {r.status_code}: {r.text}")

    return r.json()

def create_subscriber_services_for_subscriber(doc):
    if not doc.external_id:
        frappe.throw("External ID is required for Subscriber Services")

    payload = {
        "subscriber_id": doc.external_id,
        "package_id": frappe.db.get_value("Plan", doc.package_link, "external_id"),
        "created_at": now_datetime(),
        "updated_at": now_datetime(),
    }

    r = requests.post(SUBSCRIBER_SERVICES_URL, json=payload, timeout=TIMEOUT)
    if r.status_code not in (200, 201):
        frappe.throw(f"Subscriber Services Create Error {r.status_code}: {r.text}")
    return r.json()

# ============================================================
# ✅ DOC CONTROLLER (AUTO CRUD)
# ============================================================
class Subscriber(Document):

    def before_insert(self):
        """
        ✅ Create in backend only when user creates manually in Frappe
        """
        if getattr(self.flags, "from_backend_sync", False):
            return

        # POST create in backend
        external_id = backend_create_subscriber(self)
        self.external_id = str(external_id)

        # optional flags
        self.details_synced = 1
        self.details_synced_on = now_datetime()
    
    def after_insert(self):
        # """
        # ✅ After Subscriber is created locally + external_id exists,
        # upload documents automatically on same Save.
        # """
        # if getattr(self.flags, "from_backend_sync", False):
        #     return

        # try:
        #     upload_document_to_backend(self)
        # except Exception as e:
        #     frappe.log_error(str(e), "Document Upload Failed")

        """
        Call Radcheck only after backend subscriber is created successfully.
        """
        if getattr(self.flags, "from_backend_sync", False):
            return

        # ✅ Ensure backend subscriber exists
        if not self.external_id:
            frappe.throw("Subscriber external_id missing. Cannot create Radcheck.")

        # ✅ Create Radcheck
        create_radcheck_for_subscriber(self)

        # ✅ (Optional) log success
        frappe.log_error(
            title="✅ RADCHECK CREATED",
            message=f"Subscriber={self.name}, external_id={self.external_id}, username={self.username}"
        )

        """
        Call Radusergroup only after backend subscriber is created successfully.
        """
        if getattr(self.flags, "from_backend_sync", False):
            return

        # ✅ Ensure backend subscriber exists
        if not self.external_id:
            frappe.throw("Subscriber external_id missing. Cannot create Radusergroup.")

        # ✅ Create Radusergroup
        create_radusergroup_for_subscriber(self)

        # ✅ (Optional) log success
        frappe.log_error(
            title="✅ RADUSERGROUP CREATED",
            message=f"Subscriber={self.name}, external_id={self.external_id}, username={self.username}"
        )

        """
        Call Subscriber Services only after backend subscriber is created successfully.
        """
        if getattr(self.flags, "from_backend_sync", False):
            return

        # ✅ Ensure backend subscriber exists
        if not self.external_id:
            frappe.throw("Subscriber external_id missing. Cannot create Subscriber Services.")

        # ✅ Create Subscriber Services
        create_subscriber_services_for_subscriber(self)

        # ✅ (Optional) log success
        frappe.log_error(
            title="✅ SUBSCRIBER SERVICES CREATED",
            message=f"Subscriber={self.name}, external_id={self.external_id}, username={self.username}"
        )

    def on_update(self):
        """
        ✅ Update backend only when user updates manually in Frappe
        """
        # Skip updates coming from API sync jobs
        if getattr(self.flags, "from_backend_sync", False):
            return

        # ✅ SUPER IMPORTANT:
        # Frappe calls on_update after insert also. Prevent PUT immediately after POST.
        if getattr(self.flags, "in_insert", False):
            return

        # Only update if backend record exists
        if not self.external_id:
            return

        backend_update_subscriber(self)

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
    params = {"limit": limit, "offset": offset}
    r = requests.get(API_URL, params=params, timeout=TIMEOUT)

    if r.status_code != 200:
        frappe.throw(f"API Error {r.status_code}: {r.text}")

    return r.json()


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


# ============================================================
# ✅ SINGLE SUBSCRIBER DETAIL SYNC LOGIC
# ============================================================
def sync_single_subscriber_details(subscriber_name):
    doc = frappe.get_doc("Subscriber", subscriber_name)

    if not doc.external_id:
        return

    url = f"{API_URL}/{doc.external_id}"
    r = requests.get(url, timeout=TIMEOUT)

    if r.status_code != 200:
        raise Exception(f"API Error {r.status_code}: {r.text}")

    data = r.json()

    # Basic
    doc.full_name = data.get("fullname") or doc.full_name
    doc.phone = data.get("phone")
    doc.email = data.get("email")
    doc.gender = data.get("gender").capitalize() if data.get("gender") else None
    doc.country = data.get("country") or doc.country

    doc.date_of_birth = clean_date(data.get("dob"))
    doc.status = "Active" if str(data.get("connection_status")) == "1" else "Inactive"

    # passwords (if allowed)
    doc.password = data.get("password")
    doc.connection_password = data.get("connection_password")

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
    doc.salesperson = data.get("salesperson_name")

    # Address
    doc.billing_address = data.get("address")
    doc.billing_city = data.get("city")
    doc.billing_zip = data.get("zip")

    # Installation
    install = data.get("installation_address")
    if install:
        try:
            install = json.loads(install) if isinstance(install, str) else install
            doc.installation_address = install.get("address")
            doc.installation_city = install.get("city")
            doc.installation_zip = install.get("zip")
        except Exception:
            pass

    # Tech
    doc.cpe_ip_address = data.get("cpe_ip_address")
    doc.latitude = float(data.get("latitude") or 0)
    doc.longitude = float(data.get("longitude") or 0)
    doc.enable_portal_login = 1 if data.get("self_activation_status") else 0

    # Documents
    doc.id_proof_type = data.get("identity_type")
    doc.id_proof_number = data.get("identity")

    # ✅ Flags
    doc.details_synced = 1
    doc.details_synced_on = now_datetime()

    # ✅ very important to avoid CRUD loop
    doc.flags.from_backend_sync = True
    doc.save(ignore_permissions=True)
