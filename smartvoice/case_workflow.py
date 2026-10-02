"""Case ownership — claim, release and status rules.

A case nobody has claimed is up for grabs. Once a staff member claims it, it is
theirs: only they can move it to ติดตาม / ปิด or give it back, and nobody else
can claim it on top of them. An Admin or Supervisor can *release* someone's
claim (staff leave, go on holiday) — that frees the case, it does not hand it
to the supervisor; they would have to claim it like anyone else.

The owner checks are repeated inside the SQL UPDATE (`db.claim_case` and
friends), so a page that went stale between render and click still cannot
take a case someone else got first.

Every change is written to the audit trail and announced on Discord. Kept free
of Streamlit imports so it stays unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass

from smartvoice import audit, db, discord_notify
from smartvoice.auth import normalize_role

STATUSES = ("open", "follow_up", "closed")
STATUS_LABELS_TH = discord_notify.STATUS_LABELS_TH

# QA reviews calls, it does not work cases.
CLAIM_ROLES = frozenset({"Admin", "Supervisor", "Agent"})
# May free a case someone else holds.
RELEASE_OTHERS_ROLES = frozenset({"Admin", "Supervisor"})


@dataclass(frozen=True)
class Actor:
    username: str
    name: str
    role: str

    @property
    def normalized_role(self) -> str:
        return normalize_role(self.role)


def is_owner(case: dict, actor: Actor) -> bool:
    owner = (case.get("assignee_username") or "").strip().lower()
    return bool(owner) and owner == (actor.username or "").strip().lower()


def assignee_label(case: dict) -> str:
    return case.get("assignee_name") or "ยังไม่มีคนรับ"


# ── Checks (return an error message, or None when allowed) ───────────────

def claim_error(case: dict | None, actor: Actor) -> str | None:
    if not case:
        return "ไม่พบเคสนี้ — อาจถูกรวมเข้ากับเคสอื่นไปแล้ว"
    if not actor.username:
        return "ไม่พบชื่อผู้ใช้ของบัญชีนี้ — กรุณาออกจากระบบแล้วเข้าใหม่"
    if actor.normalized_role not in CLAIM_ROLES:
        return f"บทบาท {actor.normalized_role} รับเคสไม่ได้"
    if case.get("status") == "closed":
        return "เคสนี้ปิดไปแล้ว รับไม่ได้"
    if case.get("assignee_username"):
        if is_owner(case, actor):
            return "คุณรับเคสนี้ไว้อยู่แล้ว"
        return f"เคสนี้ {assignee_label(case)} รับไปแล้ว — รับซ้ำไม่ได้"
    return None


def status_error(case: dict | None, actor: Actor, new_status: str) -> str | None:
    if not case:
        return "ไม่พบเคสนี้ — อาจถูกรวมเข้ากับเคสอื่นไปแล้ว"
    if new_status not in STATUSES:
        return f"สถานะ {new_status!r} ไม่ถูกต้อง"
    if not case.get("assignee_username"):
        return "ต้องกดรับเคสก่อน จึงจะเปลี่ยนสถานะหรือปิดเคสได้"
    if not is_owner(case, actor):
        return f"เปลี่ยนสถานะได้เฉพาะผู้รับเคส ({assignee_label(case)})"
    if case.get("status") == new_status:
        return "สถานะเดิมอยู่แล้ว"
    return None


def release_error(case: dict | None, actor: Actor) -> str | None:
    if not case:
        return "ไม่พบเคสนี้ — อาจถูกรวมเข้ากับเคสอื่นไปแล้ว"
    if not case.get("assignee_username"):
        return "เคสนี้ยังไม่มีคนรับ"
    if case.get("status") == "closed":
        # A closed case keeps the name of whoever closed it.
        return "เคสนี้ปิดไปแล้ว — ต้องเปิดเคสอีกครั้งก่อนจึงจะคืนเคสได้"
    if is_owner(case, actor) or actor.normalized_role in RELEASE_OTHERS_ROLES:
        return None
    return f"คืนเคสได้เฉพาะผู้รับเคส ({assignee_label(case)}) หรือหัวหน้างาน"


# ── Actions (return (ok, message)) ───────────────────────────────────────

def _log(action: str, case: dict, actor: Actor, changes: dict) -> None:
    audit.record(
        action,
        audit.ENTITY_CASE,
        entity_id=case["id"],
        entity_label=case.get("subject"),
        actor=actor.name,
        actor_role=actor.role,
        changes=changes,
    )


def _notify(event: str, case_id: int, actor: Actor, previous_assignee: str | None = None) -> None:
    case = db.get_case_detail(case_id)
    if case:
        discord_notify.send(discord_notify.build_case_payload(
            event, case, actor.name, actor.role, previous_assignee=previous_assignee,
        ))


def claim(case_id: int, actor: Actor) -> tuple[bool, str]:
    case = db.get_case_detail(case_id)
    error = claim_error(case, actor)
    if error:
        return False, error
    if not db.claim_case(case_id, actor.username, actor.name):
        # Someone claimed (or closed) it between our read and our write.
        latest = db.get_case_detail(case_id)
        return False, claim_error(latest, actor) or "รับเคสไม่สำเร็จ — กรุณาลองใหม่"
    _log(audit.CLAIM, case, actor, {"assignee": [None, actor.name]})
    _notify(discord_notify.EVENT_CLAIM, case_id, actor)
    return True, f"รับเคส #{case_id} แล้ว — เคสนี้เป็นของคุณ"


def release(case_id: int, actor: Actor) -> tuple[bool, str]:
    case = db.get_case_detail(case_id)
    error = release_error(case, actor)
    if error:
        return False, error
    previous = case.get("assignee_name") or case.get("assignee_username")
    if not db.release_case(case_id, case["assignee_username"]):
        return False, "ผู้รับเคสเปลี่ยนไปแล้ว — โหลดหน้าใหม่แล้วลองอีกครั้ง"
    _log(audit.RELEASE, case, actor, {"assignee": [previous, None]})
    _notify(discord_notify.EVENT_RELEASE, case_id, actor, previous_assignee=previous)
    return True, f"คืนเคส #{case_id} แล้ว — เคสว่าง รอคนรับใหม่"


def change_status(case_id: int, new_status: str, actor: Actor) -> tuple[bool, str]:
    case = db.get_case_detail(case_id)
    error = status_error(case, actor, new_status)
    if error:
        return False, error
    if not db.set_case_status_as_assignee(case_id, new_status, actor.username, actor.name):
        return False, "เคสนี้ไม่ได้เป็นของคุณแล้ว — โหลดหน้าใหม่แล้วตรวจสอบอีกครั้ง"
    old_status = case.get("status")
    _log(audit.UPDATE, case, actor, {"status": [old_status, new_status]})
    if new_status == "closed":
        event = discord_notify.EVENT_CLOSE
    elif old_status == "closed":
        event = discord_notify.EVENT_REOPEN
    else:
        event = discord_notify.EVENT_STATUS
    _notify(event, case_id, actor)
    return True, f"เคส #{case_id} → {STATUS_LABELS_TH[new_status]}"
