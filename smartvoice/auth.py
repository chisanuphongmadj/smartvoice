"""Staff authentication + role-based page permissions.

Accounts live in the `users` table (see `smartvoice.db`) and are managed from
the "จัดการผู้ใช้" page by an Admin. `SMARTVOICE_USERS` in `.env` is kept as a
break-glass fallback for accounts that are not in the database:

    username|role|pbkdf2_sha256$260000$salt_hex$hash_hex

Multiple users are separated by semicolons. Keep that value in `.env`, never in
source control.

Lookup order is DB first, `.env` second — the database is the source of truth,
so a password changed in the UI takes effect immediately.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from dataclasses import dataclass

from smartvoice import db


HASH_ALGORITHM = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 260_000

MIN_PASSWORD_LENGTH = 8
MIN_USERNAME_LENGTH = 3
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9._-]+$")

# First-run bootstrap account. The login page keeps nagging until the password
# is changed, so an unattended install can never silently stay on the default.
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin1234"

# ── Roles & page permissions ─────────────────────────────────────────────

ROLES = ("Admin", "Supervisor", "QA", "Agent")

ROLE_LABELS_TH = {
    "Admin": "ผู้ดูแลระบบ",
    "Supervisor": "หัวหน้างาน",
    "QA": "ฝ่ายควบคุมคุณภาพ",
    "Agent": "พนักงานรับสาย",
}

PAGE_HOME = "home"
PAGE_ADMIN = "admin"
PAGE_DASHBOARD = "dashboard"            # Dashboard → ภาพรวม
PAGE_INSIGHTS = "insights"              # Dashboard → คีย์เวิร์ด แบรนด์ ช่องทาง
PAGE_ANOMALY = "anomaly"                # Dashboard → ความผิดปกติ
PAGE_AGENT_PERFORMANCE = "agent_performance"  # Dashboard → ผลงาน Agent
PAGE_CALLS = "calls"                    # Dashboard → รายการสาย
PAGE_CASES = "cases"                    # จัดการเคส (รับเคส / ปิดเคส)
PAGE_CUSTOMERS = "customers"
PAGE_SALES_ORDERS = "sales_orders"     # ใบสั่งขาย (SO)
PAGE_DATA_ENTRY = "data_entry"
PAGE_AUDIT = "audit"
PAGE_SETTINGS = "settings"
PAGE_USERS = "users"

# Order here is the order of the sidebar navigation.
PAGE_ORDER = (
    PAGE_HOME,
    PAGE_ADMIN,
    PAGE_DASHBOARD,
    PAGE_INSIGHTS,
    PAGE_ANOMALY,
    PAGE_AGENT_PERFORMANCE,
    PAGE_CALLS,
    PAGE_CASES,
    PAGE_CUSTOMERS,
    PAGE_SALES_ORDERS,
    PAGE_DATA_ENTRY,
    PAGE_AUDIT,
    PAGE_SETTINGS,
    PAGE_USERS,
)

# The Dashboard used to be one long page; it is now split into these pages,
# shown together under one "Dashboard" heading in the sidebar. They share the
# call filters (smartvoice.dashboard_common) and the same role permissions.
DASHBOARD_PAGES = (
    PAGE_DASHBOARD,
    PAGE_INSIGHTS,
    PAGE_ANOMALY,
    PAGE_AGENT_PERFORMANCE,
    PAGE_CALLS,
)

PAGE_LABELS_TH = {
    PAGE_HOME: "หน้าแรก",
    PAGE_ADMIN: "อัปโหลดและประมวลผลเสียง",
    PAGE_DASHBOARD: "Dashboard — ภาพรวม",
    PAGE_INSIGHTS: "Dashboard — คีย์เวิร์ด แบรนด์ ช่องทาง",
    PAGE_ANOMALY: "Dashboard — สายที่ผิดปกติ",
    PAGE_AGENT_PERFORMANCE: "Dashboard — ผลงานพนักงาน",
    PAGE_CALLS: "Dashboard — รายการสาย",
    PAGE_CASES: "จัดการเคส",
    PAGE_CUSTOMERS: "ลูกค้าและการรับประกัน",
    PAGE_SALES_ORDERS: "ใบสั่งขาย (SO)",
    PAGE_DATA_ENTRY: "เพิ่ม/แก้ไขข้อมูลลูกค้า",
    PAGE_AUDIT: "ประวัติการใช้งาน",
    PAGE_SETTINGS: "ตั้งค่าระบบ",
    PAGE_USERS: "จัดการผู้ใช้",
}

# Agent (พนักงานรับสาย) and QA intentionally have no `admin`, `settings` or
# `users` entry — those pages are neither shown in the sidebar nor reachable
# by typing the URL.
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "Admin": frozenset(
        {
            PAGE_HOME,
            PAGE_ADMIN,
            *DASHBOARD_PAGES,
            PAGE_CASES,
            PAGE_CUSTOMERS,
            PAGE_SALES_ORDERS,
            PAGE_DATA_ENTRY,
            PAGE_AUDIT,
            PAGE_SETTINGS,
            PAGE_USERS,
        }
    ),
    "Supervisor": frozenset(
        {
            PAGE_HOME,
            PAGE_ADMIN,
            *DASHBOARD_PAGES,
            PAGE_CASES,
            PAGE_CUSTOMERS,
            PAGE_SALES_ORDERS,
            PAGE_AUDIT,
            PAGE_SETTINGS,
        }
    ),
    "QA": frozenset({PAGE_HOME, *DASHBOARD_PAGES, PAGE_CASES, PAGE_CUSTOMERS, PAGE_SALES_ORDERS}),
    "Agent": frozenset({PAGE_HOME, *DASHBOARD_PAGES, PAGE_CASES, PAGE_CUSTOMERS, PAGE_SALES_ORDERS}),
}

# Anything we don't recognise falls back to the least-privileged role.
FALLBACK_ROLE = "Agent"


def normalize_role(role: str | None) -> str:
    """Map a stored/typed role onto a known role, defaulting to least privilege."""
    candidate = (role or "").strip().lower()
    for known in ROLES:
        if known.lower() == candidate:
            return known
    return FALLBACK_ROLE


def role_label(role: str | None) -> str:
    normalized = normalize_role(role)
    return f"{normalized} ({ROLE_LABELS_TH[normalized]})"


def can_access(role: str | None, page: str) -> bool:
    """True when `role` is allowed to open `page` (one of the PAGE_* keys)."""
    return page in ROLE_PERMISSIONS[normalize_role(role)]


def visible_pages(role: str | None) -> list[str]:
    """Pages this role may open, in sidebar order."""
    allowed = ROLE_PERMISSIONS[normalize_role(role)]
    return [page for page in PAGE_ORDER if page in allowed]


@dataclass(frozen=True)
class UserRecord:
    username: str
    role: str
    password_hash: str
    display_name: str = ""
    user_id: int | None = None
    source: str = "env"

    @property
    def label(self) -> str:
        return self.display_name or self.username


# ── Password hashing ─────────────────────────────────────────────────────

def hash_password(password: str, salt: bytes | None = None) -> str:
    """Return a PBKDF2-SHA256 password hash suitable for SMARTVOICE_USERS."""
    if salt is None:
        salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        DEFAULT_ITERATIONS,
    )
    return f"{HASH_ALGORITHM}${DEFAULT_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded_hash: str) -> bool:
    """Verify a plain password against a stored PBKDF2 hash."""
    try:
        algorithm, iterations_raw, salt_hex, expected_hex = encoded_hash.split("$", 3)
        if algorithm != HASH_ALGORITHM:
            return False
        iterations = int(iterations_raw)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(expected_hex)
    except (AttributeError, TypeError, ValueError):
        return False

    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual, expected)


# ── .env fallback source ─────────────────────────────────────────────────

def parse_users(raw: str | None = None) -> dict[str, UserRecord]:
    """Parse SMARTVOICE_USERS into a username -> UserRecord map."""
    raw = os.getenv("SMARTVOICE_USERS", "") if raw is None else raw
    users: dict[str, UserRecord] = {}
    for item in raw.split(";"):
        item = item.strip()
        if not item:
            continue
        parts = [part.strip() for part in item.split("|", 2)]
        if len(parts) != 3:
            continue
        username, role, password_hash = parts
        if username and role and password_hash:
            users[username.lower()] = UserRecord(
                username=username,
                role=normalize_role(role),
                password_hash=password_hash,
                display_name=username,
                source="env",
            )
    return users


def is_auth_configured() -> bool:
    """True when at least one login account exists (DB account or .env entry)."""
    if parse_users():
        return True
    try:
        return db.count_users() > 0
    except sqlite3.Error:
        return False


# ── Account bootstrap ────────────────────────────────────────────────────

def ensure_default_admin() -> bool:
    """Create the first Admin account when no account exists anywhere.

    Returns True when an account was created. Safe to call on every rerun.
    """
    if parse_users():
        return False
    try:
        if db.count_users() > 0:
            return False
        db.create_user(
            username=DEFAULT_ADMIN_USERNAME,
            display_name="ผู้ดูแลระบบ",
            role="Admin",
            password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
        )
    except sqlite3.IntegrityError:
        # Another session seeded it first — nothing to do.
        return False
    except sqlite3.Error:
        return False
    return True


def default_admin_password_unchanged() -> bool:
    """True while the bootstrap admin still uses the shipped default password."""
    try:
        row = db.get_user_by_username(DEFAULT_ADMIN_USERNAME)
    except sqlite3.Error:
        return False
    if not row or not row["is_active"]:
        return False
    return verify_password(DEFAULT_ADMIN_PASSWORD, row["password_hash"])


# ── Authentication ───────────────────────────────────────────────────────

def authenticate(username: str, password: str) -> UserRecord | None:
    """Verify credentials against the DB first, then the .env fallback."""
    username = (username or "").strip()
    if not username:
        return None

    try:
        row = db.get_user_by_username(username)
    except sqlite3.Error:
        row = None

    if row:
        if not row["is_active"]:
            return None
        if not verify_password(password or "", row["password_hash"]):
            return None
        try:
            db.touch_user_login(row["id"])
        except sqlite3.Error:
            pass
        return UserRecord(
            username=row["username"],
            role=normalize_role(row["role"]),
            password_hash=row["password_hash"],
            display_name=row["display_name"] or row["username"],
            user_id=row["id"],
            source="db",
        )

    record = parse_users().get(username.lower())
    if not record:
        return None
    if not verify_password(password or "", record.password_hash):
        return None
    return record


# ── User management validation ───────────────────────────────────────────

def validate_username(username: str) -> str | None:
    """Return an error message, or None when the username is acceptable."""
    username = (username or "").strip()
    if len(username) < MIN_USERNAME_LENGTH:
        return f"Username ต้องยาวอย่างน้อย {MIN_USERNAME_LENGTH} ตัวอักษร"
    if not _USERNAME_RE.match(username):
        return "Username ใช้ได้เฉพาะ a-z A-Z 0-9 . _ - เท่านั้น"
    return None


def validate_password(password: str, confirm: str | None = None) -> str | None:
    """Return an error message, or None when the password is acceptable."""
    password = password or ""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"รหัสผ่านต้องยาวอย่างน้อย {MIN_PASSWORD_LENGTH} ตัวอักษร"
    if confirm is not None and password != confirm:
        return "รหัสผ่านทั้งสองช่องไม่ตรงกัน"
    return None


def create_user(
    username: str,
    password: str,
    role: str,
    display_name: str = "",
    confirm: str | None = None,
) -> tuple[int | None, str | None]:
    """Create a staff account. Returns (user_id, error_message)."""
    error = validate_username(username) or validate_password(password, confirm)
    if error:
        return None, error

    username = username.strip()
    if db.get_user_by_username(username):
        return None, f"มีผู้ใช้ชื่อ `{username}` อยู่แล้ว"

    try:
        user_id = db.create_user(
            username=username,
            display_name=(display_name or "").strip() or username,
            role=normalize_role(role),
            password_hash=hash_password(password),
        )
    except sqlite3.IntegrityError:
        return None, f"มีผู้ใช้ชื่อ `{username}` อยู่แล้ว"
    return user_id, None


def change_password(
    user_id: int | None,
    current_password: str,
    new_password: str,
    confirm: str,
) -> str | None:
    """Let a signed-in user rotate their own password. Returns an error or None."""
    if user_id is None:
        return "บัญชีนี้มาจากไฟล์ `.env` จึงเปลี่ยนรหัสผ่านจากหน้าเว็บไม่ได้"

    row = db.get_user_by_id(user_id)
    if not row:
        return "ไม่พบบัญชีผู้ใช้นี้แล้ว กรุณาเข้าสู่ระบบใหม่"
    if not verify_password(current_password or "", row["password_hash"]):
        return "รหัสผ่านปัจจุบันไม่ถูกต้อง"

    error = validate_password(new_password, confirm)
    if error:
        return error
    if verify_password(new_password, row["password_hash"]):
        return "รหัสผ่านใหม่ต้องไม่ซ้ำกับรหัสผ่านเดิม"

    db.update_user_password(user_id, hash_password(new_password))
    return None


# NOTE: there is deliberately no admin-initiated password reset. A password
# belongs to its owner: only `change_password` above can set one, and it demands
# the current password. An Admin who needs to cut off access disables the
# account instead (`db.update_user(is_active=False)`), which is auditable and
# reversible. Do not add a reset helper here — `tests/test_auth.py` fails if one
# reappears.


def would_remove_last_admin(
    user_id: int,
    new_role: str | None = None,
    new_active: bool | None = None,
) -> bool:
    """True when the edit would leave the app with zero enabled Admin accounts."""
    row = db.get_user_by_id(user_id)
    if not row or normalize_role(row["role"]) != "Admin" or not row["is_active"]:
        return False

    still_admin = normalize_role(new_role) == "Admin" if new_role is not None else True
    still_active = bool(new_active) if new_active is not None else True
    if still_admin and still_active:
        return False

    return db.count_active_admins(exclude_user_id=user_id) == 0
