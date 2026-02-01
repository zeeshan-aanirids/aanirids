import frappe
import requests
import json
from frappe.utils import getdate, now_datetime
from frappe.model.document import Document

API_URL = "http://172.24.160.1:5003/api/subscribers"
RAD_CHECK_URL = "http://172.24.160.1:5003/api/radcheck"
RADUSERGROUP_URL = "http://172.24.160.1:5003/api/radusergroup"
SUBSCRIBER_SERVICES_URL = "http://172.24.160.1:5003/api/subscriber-services"

TIMEOUT = 60
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
        "connection_status": 1 if doc.status == "Active" else 0,
        "password": doc.password,
        "connection_password": doc.connection_password,
        "address": doc.billing_address,
        "city": doc.billing_city,
        "zip": doc.billing_zip,
        "cpe_ip_address": doc.cpe_ip_address,
        "latitude": float(doc.latitude or 0),
        "longitude": float(doc.longitude or 0),
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
    
    if doc.branch:
        branch_external_id = frappe.db.get_value("Branch", doc.branch, "external_id")
        if branch_external_id:
            payload["branch_id"] = int(branch_external_id)

    # ✅ Remove None values
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


def create_radcheck_for_subscriber(doc):
    if not doc.username:
        frappe.throw("Username is required for Radcheck")

    payload = {"username": doc.username}

    r = requests.post(RAD_CHECK_URL, json=payload, timeout=TIMEOUT)
    if r.status_code not in (200, 201):
        frappe.throw(f"Radcheck Create Error {r.status_code}: {r.text}")

    return r.json()


def create_radusergroup_for_subscriber(doc):
    if not doc.username:
        frappe.throw("Username is required for Radusergroup")

    payload = {"username": doc.username}

    r = requests.post(RADUSERGROUP_URL, json=payload, timeout=TIMEOUT)
    if r.status_code not in (200, 201):
        frappe.throw(f"Radusergroup Create Error {r.status_code}: {r.text}")

    return r.json()


def create_subscriber_services_for_subscriber(doc):
    if not doc.external_id:
        frappe.throw("External ID is required for Subscriber Services")

    package_id = frappe.db.get_value("Plan", doc.package_link, "external_id")
    if not package_id:
        frappe.throw(f"Package external_id not found for {doc.package_link}")

    payload = {
        "subscriber_id": doc.external_id,
        "package_id": package_id,
        "created_at": str(now_datetime()),
        "updated_at": str(now_datetime()),
    }

    r = requests.post(SUBSCRIBER_SERVICES_URL, json=payload, timeout=TIMEOUT)
    if r.status_code not in (200, 201):
        frappe.throw(f"Subscriber Services Create Error {r.status_code}: {r.text}")
    
    return r.json()


# ============================================================
# ✅ ROLLBACK HELPER - Delete backend subscriber if Frappe save fails
# ============================================================
def rollback_backend_subscriber(external_id):
    """Delete subscriber from backend (used when Frappe save fails)."""
    if not external_id:
        return
    
    try:
        url = f"{API_URL}/{external_id}"
        requests.delete(url, timeout=TIMEOUT)
        frappe.log_error(
            title="✅ Backend Rollback Success",
            message=f"Deleted external_id={external_id} due to Frappe validation failure"
        )
    except Exception as e:
        frappe.log_error(
            title="⚠️ Backend Rollback Failed",
            message=f"Failed to delete external_id={external_id}: {str(e)}"
        )


# ============================================================
# ✅ DOC CONTROLLER (OPTIMIZED CRUD)
# ============================================================
class Subscriber(Document):

    def validate(self):
        """
        ✅ VALIDATION BEFORE ANY API CALLS
        Add all your validation logic here
        """
        # Skip validation for backend sync
        if getattr(self.flags, "from_backend_sync", False):
            return

        # Add your validation rules
        if not self.username:
            frappe.throw("Username is required")
        
        if not self.full_name:
            frappe.throw("Full Name is required")
        
        # Add more validations as needed
        # This ensures Frappe validates BEFORE we call backend APIs


    def after_insert(self):
        """
        ✅ ONLY CREATE BACKEND RECORDS AFTER FRAPPE SUCCESSFULLY SAVES
        This runs AFTER Frappe validation passes and document is inserted
        """
        if getattr(self.flags, "from_backend_sync", False):
            return

        created_external_id = None
        
        try:
            # Step 1: Create subscriber in backend
            created_external_id = backend_create_subscriber(self)
            
            # Step 2: Update Frappe with external_id (without triggering on_update)
            frappe.db.set_value(
                "Subscriber",
                self.name,
                {
                    "external_id": created_external_id,
                    "details_synced": 1,
                    "details_synced_on": now_datetime()
                },
                update_modified=False
            )
            
            # Update doc object for subsequent operations
            self.external_id = created_external_id
            
            # Step 3: Create Radcheck
            create_radcheck_for_subscriber(self)
            frappe.log_error(
                title="✅ RADCHECK CREATED",
                message=f"Subscriber={self.name}, external_id={self.external_id}, username={self.username}"
            )
            
            # Step 4: Create Radusergroup
            create_radusergroup_for_subscriber(self)
            frappe.log_error(
                title="✅ RADUSERGROUP CREATED",
                message=f"Subscriber={self.name}, external_id={self.external_id}, username={self.username}"
            )
            
            # Step 5: Create Subscriber Services
            if self.package_link:
                create_subscriber_services_for_subscriber(self)
                frappe.log_error(
                    title="✅ SUBSCRIBER SERVICES CREATED",
                    message=f"Subscriber={self.name}, external_id={self.external_id}, username={self.username}"
                )
            
            frappe.db.commit()
            
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

        try:
            backend_delete_subscriber(self)
        except Exception as e:
            frappe.log_error(
                title="❌ Backend Delete Failed",
                message=f"Subscriber={self.name}\nError: {str(e)}"
            )
            # Don't throw here - allow Frappe deletion even if backend fails


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