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

from smartvoice import db

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
        existing = db.get_customer_by_phone(normalized)
        if existing and existing["id"] != exclude_id:
            return (
                f"เบอร์ `{normalized}` มีลูกค้าอยู่แล้ว — "
                f"{existing['first_name']} {existing['last_name']} (id={existing['id']})"
            )
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
    existing = db.get_warranty_by_registration(reg)
    if existing and existing["id"] != exclude_id:
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


def create_customer(**fields) -> tuple[int | None, str | None]:
    """Validate then insert a customer. Returns (customer_id, error_message)."""
    error = validate_customer(
        fields.get("first_name", ""), fields.get("last_name", ""), fields.get("phone")
    )
    if error:
        return None, error

    try:
        return db.insert_customer(**_customer_payload(fields)), None
    except sqlite3.Error as exc:  # pragma: no cover - defensive
        return None, f"บันทึกไม่สำเร็จ: {exc}"


def create_warranty(**fields) -> tuple[int | None, str | None]:
    """Validate then insert a warranty registration. Returns (id, error_message)."""
    error = validate_warranty(fields.get("registration_no", ""), fields.get("customer_id"))
    if error:
        return None, error

    try:
        return db.insert_warranty(**_warranty_payload(fields)), None
    except sqlite3.Error as exc:  # pragma: no cover - defensive
        return None, f"บันทึกไม่สำเร็จ: {exc}"


def update_customer(customer_id: int, **fields) -> str | None:
    """Validate then patch an existing customer. Returns an error, or None."""
    if not db.get_customer_by_id(customer_id):
        return "ไม่พบลูกค้ารายนี้แล้ว — อาจถูกลบไปก่อนหน้านี้"

    error = validate_customer(
        fields.get("first_name", ""),
        fields.get("last_name", ""),
        fields.get("phone"),
        exclude_id=customer_id,
    )
    if error:
        return error

    try:
        db.update_customer(customer_id, **_customer_payload(fields))
    except sqlite3.Error as exc:  # pragma: no cover - defensive
        return f"บันทึกไม่สำเร็จ: {exc}"
    return None


def update_warranty(warranty_id: int, **fields) -> str | None:
    """Validate then patch an existing warranty. Returns an error, or None."""
    if not db.get_warranty_by_id(warranty_id):
        return "ไม่พบทะเบียนรับประกันนี้แล้ว — อาจถูกลบไปก่อนหน้านี้"

    error = validate_warranty(
        fields.get("registration_no", ""),
        fields.get("customer_id"),
        exclude_id=warranty_id,
    )
    if error:
        return error

    try:
        db.update_warranty(warranty_id, **_warranty_payload(fields))
    except sqlite3.Error as exc:  # pragma: no cover - defensive
        return f"บันทึกไม่สำเร็จ: {exc}"
    return None


# ── Deletion ─────────────────────────────────────────────────────────────

def describe_dependencies(counts: dict[str, int]) -> str:
    """Thai summary of what a customer delete would take with it."""
    parts = []
    if counts.get("warranties"):
        parts.append(f"ทะเบียนรับประกัน {counts['warranties']} รายการ")
    if counts.get("calls"):
        parts.append(f"การเชื่อมสาย {counts['calls']} รายการ")
    if counts.get("cases"):
        parts.append(f"เคส {counts['cases']} เคส")
    return " · ".join(parts)


def delete_customer(customer_id: int, cascade: bool = False) -> tuple[dict, str | None]:
    """Delete a customer. Returns (result, error_message).

    Without `cascade`, a customer that still has warranties, call links or cases
    is refused and the error names what is blocking it.
    """
    if not db.get_customer_by_id(customer_id):
        return {}, "ไม่พบลูกค้ารายนี้แล้ว"

    result = db.delete_customer(customer_id, cascade=cascade)
    if not result.get("deleted"):
        blocking = describe_dependencies(result)
        return result, (
            f"ลูกค้ารายนี้ยังมีข้อมูลผูกอยู่ ({blocking}) — "
            "ติ๊กยืนยันเพื่อลบข้อมูลเหล่านี้ไปพร้อมกัน"
        )
    return result, None


def delete_warranty(warranty_id: int) -> str | None:
    """Delete a warranty registration. Returns an error, or None."""
    if not db.get_warranty_by_id(warranty_id):
        return "ไม่พบทะเบียนรับประกันนี้แล้ว"
    db.delete_warranty(warranty_id)
    return None
