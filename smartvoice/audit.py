"""Audit trail — one place that decides what an audit entry looks like.

Every staff action that changes data (or grants access) is appended to the
`audit_log` table through `record()`. Nothing in the codebase updates or deletes
those rows: the log is the history, so it has to outlive whatever it describes.

Kept free of Streamlit imports so it stays unit-testable; `ui_helpers.audit()`
is the thin wrapper that fills the actor in from the signed-in session.
"""

from __future__ import annotations

import sqlite3

from smartvoice import db
from smartvoice.logger import get_logger

log = get_logger(__name__)

# ── Actions ──────────────────────────────────────────────────────────────
CREATE = "create"
UPDATE = "update"
DELETE = "delete"          # for customers/warranties this means "hidden"
RESTORE = "restore"
LOGIN = "login"
LOGIN_FAILED = "login_failed"
LOGOUT = "logout"
CLAIM = "claim"            # a staff member takes ownership of a case
RELEASE = "release"        # a case's owner is cleared (by them or a supervisor)

# ── Entities ─────────────────────────────────────────────────────────────
ENTITY_CUSTOMER = "customer"
ENTITY_WARRANTY = "warranty"
ENTITY_USER = "user"
ENTITY_CALL = "call"
ENTITY_CASE = "case"
ENTITY_SESSION = "session"
ENTITY_SETTINGS = "settings"

ACTION_LABELS_TH = {
    CREATE: "เพิ่ม",
    UPDATE: "แก้ไข",
    DELETE: "ลบ/ซ่อน",
    RESTORE: "กู้คืน",
    LOGIN: "เข้าสู่ระบบ",
    LOGIN_FAILED: "เข้าสู่ระบบไม่สำเร็จ",
    LOGOUT: "ออกจากระบบ",
    CLAIM: "รับเคส",
    RELEASE: "คืนเคส",
}

ENTITY_LABELS_TH = {
    ENTITY_CUSTOMER: "ลูกค้า",
    ENTITY_WARRANTY: "ทะเบียนรับประกัน",
    ENTITY_USER: "บัญชีผู้ใช้",
    ENTITY_CALL: "สายสนทนา",
    ENTITY_CASE: "เคส",
    ENTITY_SESSION: "การเข้าใช้งาน",
    ENTITY_SETTINGS: "ตั้งค่าระบบ",
}

# Never write these into the log, whatever the caller passes.
_SECRET_FIELDS = {
    "password", "password_hash", "confirm", "hf_token", "token",
    # Anyone holding the webhook URL can post into the team's channel.
    "discord_webhook_url",
}


def redact(changes: dict | None) -> dict | None:
    """Drop secret values, keeping the field name so the change is still visible."""
    if not changes:
        return changes
    return {
        field: ("***" if field.lower() in _SECRET_FIELDS else value)
        for field, value in changes.items()
    }


def diff_fields(before: dict, after: dict) -> dict[str, list]:
    """{field: [before, after]} for the values that actually changed."""
    return {
        field: [before.get(field), value]
        for field, value in after.items()
        if before.get(field) != value
    }


def record(
    action: str,
    entity: str,
    entity_id: int | None = None,
    entity_label: str | None = None,
    actor: str | None = None,
    actor_role: str | None = None,
    changes: dict | None = None,
) -> int | None:
    """Append one audit entry. Never raises — a failed log must not lose the action."""
    try:
        return db.log_action(
            action=action,
            entity=entity,
            entity_id=entity_id,
            entity_label=entity_label,
            actor=actor,
            actor_role=actor_role,
            changes=redact(changes),
        )
    except sqlite3.Error:
        log.exception("Could not write audit entry: %s %s #%s", action, entity, entity_id)
        return None
