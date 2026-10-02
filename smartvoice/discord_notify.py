"""Discord notifications for case ownership — who claimed, released, closed.

Posts to a Discord *incoming webhook* (channel settings → Integrations →
Webhooks → Copy Webhook URL), saved as `DISCORD_WEBHOOK_URL` in `.env` from
the Settings page. No webhook configured → nothing is sent and nothing fails.

Kept free of Streamlit imports so it stays unit-testable. Sending never raises
and runs on a background thread by default: a slow or unreachable Discord must
not hold up — or undo — the staff member's action, which is already saved.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta, timezone

import requests

from smartvoice.logger import get_logger

log = get_logger(__name__)

ENV_KEY = "DISCORD_WEBHOOK_URL"
TIMEOUT_SECONDS = 5

_WEBHOOK_PREFIXES = (
    "https://discord.com/api/webhooks/",
    "https://discordapp.com/api/webhooks/",
    "https://ptb.discord.com/api/webhooks/",
    "https://canary.discord.com/api/webhooks/",
)

# ── Events ───────────────────────────────────────────────────────────────
EVENT_CLAIM = "claim"
EVENT_RELEASE = "release"
EVENT_CLOSE = "close"
EVENT_REOPEN = "reopen"
EVENT_STATUS = "status"
EVENT_TEST = "test"

_EVENT_TITLES_TH = {
    EVENT_CLAIM: "รับเคส",
    EVENT_RELEASE: "คืนเคส / ปลดผู้รับเคส",
    EVENT_CLOSE: "ปิดเคส",
    EVENT_REOPEN: "เปิดเคสอีกครั้ง",
    EVENT_STATUS: "เปลี่ยนสถานะเคส",
}

# Discord embed side-bar colours.
_EVENT_COLORS = {
    EVENT_CLAIM: 0x22C55E,    # green
    EVENT_RELEASE: 0xEAB308,  # yellow
    EVENT_CLOSE: 0xEF4444,    # red
    EVENT_REOPEN: 0x38BDF8,   # blue
    EVENT_STATUS: 0x94A3B8,   # grey
    EVENT_TEST: 0x38BDF8,
}

STATUS_LABELS_TH = {"open": "เปิด", "follow_up": "ติดตาม", "closed": "ปิด"}

_BANGKOK = timezone(timedelta(hours=7))


def webhook_url() -> str:
    """The saved webhook URL ('' when not configured). Read on every call so a
    URL saved from the Settings page works without restarting the app."""
    return os.getenv(ENV_KEY, "").strip()


def is_valid_webhook_url(url: str | None) -> bool:
    url = (url or "").strip()
    return any(url.startswith(prefix) and len(url) > len(prefix) for prefix in _WEBHOOK_PREFIXES)


def mask_phone(phone: str | None) -> str:
    """Keep only the last 4 digits — a chat channel is no place for a full
    customer phone number."""
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if len(digits) < 4:
        return "-"
    return "x" * (len(digits) - 4) + digits[-4:]


def _bangkok_time(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.astimezone(_BANGKOK).strftime("%Y-%m-%d %H:%M น.")


def build_case_payload(
    event: str,
    case: dict,
    actor: str,
    actor_role: str | None = None,
    previous_assignee: str | None = None,
    now: datetime | None = None,
) -> dict:
    """Discord webhook JSON for one case event.

    `case` is a `db.get_case_detail()` row read *after* the change.
    """
    title = f"{_EVENT_TITLES_TH.get(event, event)} — เคส #{case['id']}"
    who = f"**{actor}**" + (f" ({actor_role})" if actor_role else "")
    if event == EVENT_CLAIM:
        description = f"{who} รับเคสนี้แล้ว — คนอื่นจะรับซ้ำไม่ได้จนกว่าจะคืนเคส"
    elif event == EVENT_RELEASE:
        if previous_assignee and previous_assignee != actor:
            description = f"{who} ปลด **{previous_assignee}** ออกจากเคสนี้ — เคสว่าง รอคนรับใหม่"
        else:
            description = f"{who} คืนเคสนี้ — เคสว่าง รอคนรับใหม่"
    elif event == EVENT_CLOSE:
        description = f"{who} ปิดเคสนี้แล้ว"
    elif event == EVENT_REOPEN:
        description = f"{who} เปิดเคสนี้อีกครั้ง"
    else:
        description = f"{who} เปลี่ยนสถานะเป็น **{STATUS_LABELS_TH.get(case.get('status'), case.get('status'))}**"

    customer = f"{case.get('first_name') or ''} {case.get('last_name') or ''}".strip() or "-"
    fields = [
        {"name": "หัวข้อ", "value": case.get("subject") or "-", "inline": False},
        {"name": "ลูกค้า", "value": f"{customer} ({mask_phone(case.get('phone'))})", "inline": True},
        {
            "name": "สถานะ",
            "value": STATUS_LABELS_TH.get(case.get("status"), case.get("status") or "-"),
            "inline": True,
        },
        {"name": "ผู้รับเคส", "value": case.get("assignee_name") or "ยังไม่มีคนรับ", "inline": True},
        {"name": "จำนวนสาย", "value": str(case.get("call_count") or 0), "inline": True},
        {"name": "เวลา", "value": _bangkok_time(now), "inline": True},
    ]
    return {
        "username": "SmartVoice",
        # Subjects come from the LLM and customer names from staff input —
        # never let either ping @everyone / @here / a role.
        "allowed_mentions": {"parse": []},
        "embeds": [{
            "title": title,
            "description": description,
            "color": _EVENT_COLORS.get(event, 0x94A3B8),
            "fields": fields,
        }],
    }


def build_test_payload(actor: str) -> dict:
    return {
        "username": "SmartVoice",
        "allowed_mentions": {"parse": []},
        "embeds": [{
            "title": "ทดสอบการแจ้งเตือน SmartVoice",
            "description": f"**{actor}** ส่งข้อความทดสอบจากหน้า Settings — ถ้าเห็นข้อความนี้แปลว่าตั้งค่าถูกต้อง",
            "color": _EVENT_COLORS[EVENT_TEST],
            "fields": [{"name": "เวลา", "value": _bangkok_time(), "inline": True}],
        }],
    }


def post(payload: dict, url: str | None = None) -> tuple[bool, str]:
    """Send one message right now. Returns (ok, detail). Never raises."""
    url = (url if url is not None else webhook_url()).strip()
    if not url:
        return False, "ยังไม่ได้ตั้งค่า Discord webhook"
    if not is_valid_webhook_url(url):
        return False, "URL นี้ไม่ใช่ Discord webhook (ต้องขึ้นต้นด้วย https://discord.com/api/webhooks/)"
    try:
        resp = requests.post(url, json=payload, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        log.warning("Discord webhook failed: %s", exc.__class__.__name__)
        return False, f"ส่งไม่สำเร็จ: เชื่อมต่อ Discord ไม่ได้ ({exc.__class__.__name__})"
    if resp.status_code >= 400:
        log.warning("Discord webhook returned HTTP %s", resp.status_code)
        return False, f"ส่งไม่สำเร็จ: Discord ตอบกลับ HTTP {resp.status_code}"
    return True, "ส่งแล้ว"


def send(payload: dict, background: bool = True) -> bool:
    """Fire-and-forget delivery of `payload` to the saved webhook.

    Returns False (and sends nothing) when no webhook is configured. With
    `background=True` the HTTP request runs on a daemon thread so the page
    never waits on Discord.
    """
    url = webhook_url()
    if not url:
        return False
    if background:
        threading.Thread(target=post, args=(payload, url), daemon=True).start()
        return True
    return post(payload, url)[0]
