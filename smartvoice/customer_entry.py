"""Validation + persistence helpers for the manual customer / warranty entry page.

Deliberately free of Streamlit imports so every rule here stays unit-testable:
`pages/6_➕_Data_Entry.py` only collects widget values and renders the messages
this module returns.
"""

from __future__ import annotations

import calendar
import re
import sqlite3
from datetime import date, datetime

from smartvoice import audit, db

# Thai numerals show up in pasted CDR/marketplace exports.
_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
_PHONE_JUNK_RE = re.compile(r"[\s\-().]")
_PHONE_RE = re.compile(r"^0\d{8,9}$")
_REGISTRATION_RE = re.compile(r"^[A-Za-z0-9._/-]{3,}$")

# Dropdown vocabularies — mirrors what `scripts/seed_mock_data.py` writes so the
# Customers page filters keep grouping cleanly.
GENDERS = ("MALE", "FEMALE", "OTHER")
CATEGORIES = ("Mattress", "Pillow", "Topper", "Bed Frame", "Bedding", "อื่นๆ")
BRANDS = ("Omazz", "Dunlopillo", "Sealy", "Restonic", "อื่นๆ")
PURCHASE_CHANNELS = (
    "Store", "Shopee", "Lazada", "TikTok Shop", "LINE", "Facebook", "Call Center", "อื่นๆ"
)
CHANNELS = ("Omazz", "Dunlopillo", "อื่นๆ")


# ── Normalisation ────────────────────────────────────────────────────────

def normalize_phone(raw: str | None) -> str:
    """Strip formatting and Thai numerals from a phone number."""
    if not raw:
        return ""
    return _PHONE_JUNK_RE.sub("", str(raw).translate(_THAI_DIGITS).strip())


def clean(value: str | None) -> str | None:
    """Trim a free-text field, mapping blanks to None so the DB stores NULL."""
    if value is None:
        return None
    trimmed = str(value).strip()
    return trimmed or None


def _as_iso(value: date | datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return clean(value)


# ── Warranty expiry ──────────────────────────────────────────────────────

def add_months(start: date, months: int) -> date:
    """Shift `start` by `months`, clamping to the last day of the target month."""
    total = start.month - 1 + int(months)
    year = start.year + total // 12
    month = total % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def compute_expiry_date(
    date_of_purchase: date | str | None, warranty_period_months: int | None
) -> str | None:
    """Return the ISO expiry date implied by purchase date + warranty length."""
    iso = _as_iso(date_of_purchase)
    if not iso or not warranty_period_months:
        return None
    try:
        start = date.fromisoformat(iso)
    except ValueError:
        return None
    return add_months(start, int(warranty_period_months)).isoformat()


# ── Validation ───────────────────────────────────────────────────────────

def validate_customer(
    first_name: str,
    last_name: str,
    phone: str | None,
    exclude_id: int | None = None,
) -> str | None:
    """Return an error message, or None when the customer may be saved.

    `exclude_id` is the row being edited — its own phone must not count as a
    duplicate of itself.
    """
    if not clean(first_name):
        return "กรุณากรอกชื่อ"
    if not clean(last_name):
        return "กรุณากรอกนามสกุล"

    normalized = normalize_phone(phone)
    if normalized:
        if not _PHONE_RE.match(normalized):
            return "เบอร์โทรต้องขึ้นต้นด้วย 0 และมี 9-10 หลัก (เช่น 0812345678)"
        # `phone` is UNIQUE, so a hidden customer still owns the number — say so
        # instead of letting the insert fail on the constraint.
        existing = db.get_customer_by_phone(normalized, include_deleted=True)
        if existing and existing["id"] != exclude_id:
            who = f"{existing['first_name']} {existing['last_name']} (id={existing['id']})"
            if existing.get("deleted_at"):
                return (
                    f"เบอร์ `{normalized}` เป็นของลูกค้าที่ถูกซ่อนไว้ — {who} "
                    "กู้คืนจาก 🗄 รายการที่ซ่อนไว้ แทนการสร้างใหม่"
                )
            return f"เบอร์ `{normalized}` มีลูกค้าอยู่แล้ว — {who}"
    return None


def validate_warranty(
    registration_no: str,
    customer_id: int | None,
    exclude_id: int | None = None,
) -> str | None:
    """Return an error message, or None when the warranty may be saved.

    `exclude_id` is the row being edited — keeping its own registration number
    is not a duplicate.
    """
    reg = clean(registration_no)
    if not reg:
        return "กรุณากรอกเลขทะเบียนรับประกัน"
    if not _REGISTRATION_RE.match(reg):
        return "เลขทะเบียนใช้ได้เฉพาะ A-Z 0-9 . _ - / และยาวอย่างน้อย 3 ตัวอักษร"
    if not customer_id:
        return "กรุณาเลือกลูกค้าเจ้าของทะเบียนรับประกัน"
    existing = db.get_warranty_by_registration(reg, include_deleted=True)
    if existing and existing["id"] != exclude_id:
        if existing.get("deleted_at"):
            return (
                f"เลขทะเบียน `{reg}` เป็นของรายการที่ถูกซ่อนไว้ (id={existing['id']}) — "
                "กู้คืนจาก 🗄 รายการที่ซ่อนไว้ แทนการสร้างใหม่"
            )
        return f"เลขทะเบียน `{reg}` มีอยู่แล้วในระบบ"
    return None


# ── Persistence ──────────────────────────────────────────────────────────

def _customer_payload(fields: dict) -> dict:
    """Normalise raw widget values into the columns `customers` expects."""
    payload = {key: clean(value) for key, value in fields.items()}
    payload["first_name"] = clean(fields.get("first_name"))
    payload["last_name"] = clean(fields.get("last_name"))
    payload["phone"] = normalize_phone(fields.get("phone")) or None
    payload["date_of_birth"] = _as_iso(fields.get("date_of_birth"))
    payload["country"] = payload.get("country") or "Thailand"
    return payload


def _warranty_payload(fields: dict) -> dict:
    """Normalise raw widget values into the columns `warranty_registrations` expects."""
    payload = {
        key: clean(value)
        for key, value in fields.items()
        if key not in {"customer_id", "warranty_period_months"}
    }
    payload["customer_id"] = int(fields["customer_id"])
    payload["warranty_period_months"] = int(fields.get("warranty_period_months") or 0)
    payload["date_of_purchase"] = _as_iso(fields.get("date_of_purchase"))
    payload["date_of_delivery"] = _as_iso(fields.get("date_of_delivery"))
    payload["expiry_date"] = _as_iso(fields.get("expiry_date")) or compute_expiry_date(
        payload["date_of_purchase"], payload["warranty_period_months"]
    )
    return payload


ENTITY_CUSTOMER = audit.ENTITY_CUSTOMER
ENTITY_WARRANTY = audit.ENTITY_WARRANTY

diff_fields = audit.diff_fields


def customer_label(row: dict) -> str:
    return f"{row.get('first_name') or ''} {row.get('last_name') or ''}".strip() or "—"


def warranty_label(row: dict) -> str:
    return row.get("registration_no") or "—"


def _log(action, entity, entity_id, entity_label, actor, actor_role, changes=None):
    """Write one audit row; a logging failure must never lose the user's edit."""
    audit.record(
        action=action,
        entity=entity,
        entity_id=entity_id,
        entity_label=entity_label,
        actor=actor,
        actor_role=actor_role,
        changes=changes,
    )


def create_customer(
    actor: str | None = None, actor_role: str | None = None, **fields
) -> tuple[int | None, str | None]:
    """Validate then insert a customer. Returns (customer_id, error_message)."""
    error = validate_customer(
        fields.get("first_name", ""), fields.get("last_name", ""), fields.get("phone")
    )
    if error:
        return None, error

    payload = _customer_payload(fields)
    try:
        customer_id = db.insert_customer(**payload)
    except sqlite3.Error as exc:  # pragma: no cover - defensive
        return None, f"บันทึกไม่สำเร็จ: {exc}"

    _log(
        "create", ENTITY_CUSTOMER, customer_id, customer_label(payload), actor, actor_role,
        {key: value for key, value in payload.items() if value not in (None, "")},
    )
    return customer_id, None


def create_warranty(
    actor: str | None = None, actor_role: str | None = None, **fields
) -> tuple[int | None, str | None]:
    """Validate then insert a warranty registration. Returns (id, error_message)."""
    error = validate_warranty(fields.get("registration_no", ""), fields.get("customer_id"))
    if error:
        return None, error

    payload = _warranty_payload(fields)
    try:
        warranty_id = db.insert_warranty(**payload)
    except sqlite3.Error as exc:  # pragma: no cover - defensive
        return None, f"บันทึกไม่สำเร็จ: {exc}"

    _log(
        "create", ENTITY_WARRANTY, warranty_id, warranty_label(payload), actor, actor_role,
        {key: value for key, value in payload.items() if value not in (None, "")},
    )
    return warranty_id, None


def update_customer(
    customer_id: int, actor: str | None = None, actor_role: str | None = None, **fields
) -> str | None:
    """Validate then patch an existing customer. Returns an error, or None."""
    before = db.get_customer_by_id(customer_id)
    if not before:
        return "ไม่พบลูกค้ารายนี้แล้ว — อาจถูกซ่อนไว้ก่อนหน้านี้"

    error = validate_customer(
        fields.get("first_name", ""),
        fields.get("last_name", ""),
        fields.get("phone"),
        exclude_id=customer_id,
    )
    if error:
        return error

    payload = _customer_payload(fields)
    changes = diff_fields(before, payload)
    if not changes:
        return None

    try:
        db.update_customer(customer_id, **payload)
    except sqlite3.Error as exc:  # pragma: no cover - defensive
        return f"บันทึกไม่สำเร็จ: {exc}"

    _log(
        "update", ENTITY_CUSTOMER, customer_id, customer_label(payload),
        actor, actor_role, changes,
    )
    return None


def update_warranty(
    warranty_id: int, actor: str | None = None, actor_role: str | None = None, **fields
) -> str | None:
    """Validate then patch an existing warranty. Returns an error, or None."""
    before = db.get_warranty_by_id(warranty_id)
    if not before:
        return "ไม่พบทะเบียนรับประกันนี้แล้ว — อาจถูกซ่อนไว้ก่อนหน้านี้"

    error = validate_warranty(
        fields.get("registration_no", ""),
        fields.get("customer_id"),
        exclude_id=warranty_id,
    )
    if error:
        return error

    payload = _warranty_payload(fields)
    changes = diff_fields(before, payload)
    if not changes:
        return None

    try:
        db.update_warranty(warranty_id, **payload)
    except sqlite3.Error as exc:  # pragma: no cover - defensive
        return f"บันทึกไม่สำเร็จ: {exc}"

    _log(
        "update", ENTITY_WARRANTY, warranty_id, warranty_label(payload),
        actor, actor_role, changes,
    )
    return None


# ── Hiding & restoring ───────────────────────────────────────────────────
#
# Nothing here removes a row. "ลบ" in the UI means the row is stamped with
# `deleted_at` so it drops out of the app, while the record — and the audit
# entry describing who hid it — stays in the database.

def describe_dependencies(counts: dict[str, int]) -> str:
    """Thai summary of what is attached to a customer."""
    parts = []
    if counts.get("warranties"):
        parts.append(f"ทะเบียนรับประกัน {counts['warranties']} รายการ")
    if counts.get("calls"):
        parts.append(f"การเชื่อมสาย {counts['calls']} รายการ")
    if counts.get("cases"):
        parts.append(f"เคส {counts['cases']} เคส")
    return " · ".join(parts)


def hide_customer(
    customer_id: int, actor: str | None = None, actor_role: str | None = None
) -> tuple[dict, str | None]:
    """Hide a customer and their warranties. Returns (result, error_message)."""
    row = db.get_customer_by_id(customer_id)
    if not row:
        return {}, "ไม่พบลูกค้ารายนี้แล้ว — อาจถูกซ่อนไว้ก่อนหน้านี้"

    dependencies = db.count_customer_dependencies(customer_id)
    result = db.soft_delete_customer(customer_id, actor=actor)
    if not result.get("customer"):
        return result, "ลูกค้ารายนี้ถูกซ่อนไว้อยู่แล้ว"

    _log(
        "delete", ENTITY_CUSTOMER, customer_id, customer_label(row), actor, actor_role,
        {"hidden_warranties": result["warranties"], **dependencies},
    )
    return result, None


def restore_customer(
    customer_id: int, actor: str | None = None, actor_role: str | None = None
) -> tuple[dict, str | None]:
    """Un-hide a customer and the warranties hidden with them."""
    row = db.get_customer_by_id(customer_id, include_deleted=True)
    if not row:
        return {}, "ไม่พบลูกค้ารายนี้"

    result = db.restore_customer(customer_id)
    if not result.get("customer"):
        return result, "ลูกค้ารายนี้ไม่ได้ถูกซ่อนไว้"

    _log(
        "restore", ENTITY_CUSTOMER, customer_id, customer_label(row), actor, actor_role,
        {"restored_warranties": result["warranties"]},
    )
    return result, None


def hide_warranty(
    warranty_id: int, actor: str | None = None, actor_role: str | None = None
) -> str | None:
    """Hide a warranty registration. Returns an error, or None."""
    row = db.get_warranty_by_id(warranty_id)
    if not row:
        return "ไม่พบทะเบียนรับประกันนี้แล้ว — อาจถูกซ่อนไว้ก่อนหน้านี้"

    if not db.soft_delete_warranty(warranty_id, actor=actor):
        return "ทะเบียนนี้ถูกซ่อนไว้อยู่แล้ว"

    _log("delete", ENTITY_WARRANTY, warranty_id, warranty_label(row), actor, actor_role)
    return None


def restore_warranty(
    warranty_id: int, actor: str | None = None, actor_role: str | None = None
) -> str | None:
    """Un-hide a warranty registration. Returns an error, or None."""
    row = db.get_warranty_by_id(warranty_id, include_deleted=True)
    if not row:
        return "ไม่พบทะเบียนรับประกันนี้"
    if row.get("customer_id") and not db.get_customer_by_id(row["customer_id"]):
        return "ลูกค้าเจ้าของทะเบียนนี้ยังถูกซ่อนอยู่ — กู้คืนลูกค้าก่อน"

    if not db.restore_warranty(warranty_id):
        return "ทะเบียนนี้ไม่ได้ถูกซ่อนไว้"

    _log("restore", ENTITY_WARRANTY, warranty_id, warranty_label(row), actor, actor_role)
    return None
