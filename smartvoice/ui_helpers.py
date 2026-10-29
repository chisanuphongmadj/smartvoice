"""Shared UI helpers for Streamlit pages — CSS, login, badges, processing launchers."""

import html
import json
import os
import re
import threading
import time

import streamlit as st

from smartvoice import audit as audit_trail
from smartvoice import case_workflow, db, labels, pipeline, processing_control
from smartvoice.auth import (
    DEFAULT_ADMIN_PASSWORD,
    DEFAULT_ADMIN_USERNAME,
    PAGE_LABELS_TH,
    authenticate,
    can_access,
    change_password,
    default_admin_password_unchanged,
    ensure_default_admin,
    role_label,
)
from smartvoice.config import (
    WHISPER_MODEL,
    OLLAMA_MODEL,
    MOCK_STT,
    PROCESSING_STALE_MINUTES,
)
from smartvoice.logger import get_logger
from smartvoice.preflight import get_ollama_readiness

log = get_logger(__name__)

# ── Shared CSS ───────────────────────────────────────────────────────────

_CSS = """
.stApp { background-color: #0f1117; }
section[data-testid="stSidebar"] { background-color: #1a1d27; }
.metric-card {
    background: linear-gradient(135deg, #0b1a2b, #15243a);
    border: 1px solid #1e3a5f;
    border-radius: 12px;
    padding: 18px 12px;
    text-align: center;
    min-height: 118px;
    display: flex;
    flex-direction: column;
    justify-content: center;
}
.metric-value { font-size: 2.5rem; font-weight: 700; color: #38bdf8; }

/* Action cards (home page): number, label and the link that acts on it, in
   one box — a link hanging loose under a card reads as stray text. */
div[class*="st-key-workcard"] {
    background: linear-gradient(135deg, #0b1a2b, #15243a);
    border: 1px solid #1e3a5f;
    border-radius: 12px;
    padding: 18px 14px 14px;
}
.work-value { font-size: 2.5rem; font-weight: 700; line-height: 1.1; text-align: center; }
.work-label {
    font-size: 0.9rem; color: #cbd5e1; text-align: center; margin: 4px 0 8px;
    line-height: 1.35; height: 2.7em;  /* two lines for every card, so the row lines up */
    display: flex; align-items: center; justify-content: center;
}

/* Shortcut links in the page body look like buttons, not plain text. */
[data-testid="stMain"] [data-testid="stPageLink"] a {
    border: 1px solid #1e3a5f;
    border-radius: 8px;
    background: #13233a;
    padding: 6px 14px;
    justify-content: center;
    transition: background 0.15s, border-color 0.15s;
}
[data-testid="stMain"] [data-testid="stPageLink"] a:hover {
    background: #1b3150;
    border-color: #38bdf8;
}
.metric-label { font-size: 0.9rem; color: #cbd5e1; margin-top: 4px; line-height: 1.35; }
.status-badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
}
.badge-done { background: #14532d; color: #86efac; }
.badge-processing { background: #1e3a5f; color: #93c5fd; }
.badge-error { background: #450a0a; color: #fca5a5; }
.badge-uploaded { background: #312e81; color: #c4b5fd; }

@media print {
    section[data-testid="stSidebar"],
    header[data-testid="stHeader"],
    div[data-testid="stToolbar"],
    div[data-testid="stDecoration"],
    div[data-testid="stStatusWidget"],
    footer,
    #MainMenu,
    button[kind="header"],
    .stDeployButton { display: none !important; }

    .stApp, body, html {
        background-color: #ffffff !important;
        color: #111111 !important;
    }

    section.main > div,
    .block-container {
        padding: 0.5rem 1rem !important;
        max-width: 100% !important;
    }

    .metric-card {
        background: #f3f4f6 !important;
        border: 1px solid #d1d5db !important;
        color: #111111 !important;
        break-inside: avoid;
    }
    .metric-value { color: #0369a1 !important; }
    .metric-label { color: #374151 !important; }

    .stPlotlyChart,
    .stDataFrame,
    [data-testid="stVerticalBlock"] > div {
        break-inside: avoid;
    }

    hr { border-color: #d1d5db !important; }

    p, span, div, h1, h2, h3, h4, label {
        color: #111111 !important;
    }

    .js-plotly-plot .plotly text,
    .js-plotly-plot .plotly .gtitle,
    .js-plotly-plot .plotly .xtitle,
    .js-plotly-plot .plotly .ytitle,
    .js-plotly-plot .plotly .ytick text,
    .js-plotly-plot .plotly .xtick text,
    .js-plotly-plot .plotly .legendtext {
        fill: #111111 !important;
        color: #111111 !important;
    }

    .js-plotly-plot .plotly .bg,
    .js-plotly-plot .plotly .paper_bgcolor {
        fill: #ffffff !important;
    }

    .js-plotly-plot .plotly .gridlayer path,
    .js-plotly-plot .plotly .zerolinelayer path {
        stroke: #d1d5db !important;
    }
}
"""


def inject_css():
    """Inject shared CSS into the current page."""
    st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)


# ── Staff login ────────────────────────────────────────────────────────────
#
# Every account is verified against a PBKDF2 hash (DB first, then the
# SMARTVOICE_USERS fallback in .env). There is no self-service role picker:
# the role always comes from the stored account, so a พนักงาน cannot grant
# themselves Admin by typing it into a dropdown.

LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCK_SECONDS = 60

_SESSION_KEYS = (
    "current_user",
    "current_user_role",
    "current_username",
    "current_user_id",
    "current_user_source",
)


def _login_lock_remaining() -> int:
    """Seconds left on the failed-attempt lockout (0 when not locked)."""
    locked_until = st.session_state.get("_login_locked_until", 0.0)
    return max(0, int(locked_until - time.time()))


def _register_login_failure() -> None:
    fails = st.session_state.get("_login_fail_count", 0) + 1
    st.session_state["_login_fail_count"] = fails
    if fails >= LOGIN_MAX_ATTEMPTS:
        st.session_state["_login_fail_count"] = 0
        st.session_state["_login_locked_until"] = time.time() + LOGIN_LOCK_SECONDS


def audit(
    action: str,
    entity: str,
    entity_id: int | None = None,
    entity_label: str | None = None,
    changes: dict | None = None,
) -> None:
    """Append an audit entry for the signed-in user (see smartvoice.audit)."""
    user, role = get_current_user()
    audit_trail.record(
        action=action,
        entity=entity,
        entity_id=entity_id,
        entity_label=entity_label,
        actor=user,
        actor_role=role,
        changes=changes,
    )


def start_session(record) -> None:
    """Store an authenticated UserRecord in the Streamlit session."""
    st.session_state["current_user"] = record.label
    st.session_state["current_user_role"] = record.role
    st.session_state["current_username"] = record.username
    st.session_state["current_user_id"] = record.user_id
    st.session_state["current_user_source"] = record.source
    st.session_state["_login_fail_count"] = 0
    st.session_state["_login_locked_until"] = 0.0
    audit_trail.record(
        audit_trail.LOGIN,
        audit_trail.ENTITY_SESSION,
        entity_id=record.user_id,
        entity_label=record.username,
        actor=record.label,
        actor_role=record.role,
        changes={"source": record.source},
    )


def end_session() -> None:
    user, role = get_current_user()
    if user:
        audit_trail.record(
            audit_trail.LOGOUT,
            audit_trail.ENTITY_SESSION,
            entity_id=get_current_user_id(),
            entity_label=st.session_state.get("current_username"),
            actor=user,
            actor_role=role,
        )
    for key in _SESSION_KEYS:
        st.session_state.pop(key, None)


def render_login_page():
    """Full-page login form — the only screen an anonymous visitor can reach."""
    _, center, _ = st.columns([1, 1.4, 1])
    with center:
        st.markdown("## เข้าสู่ระบบ SmartVoice")
        st.caption("ระบบวิเคราะห์สายสนทนา Call Center — กรุณาเข้าสู่ระบบด้วยบัญชีพนักงาน")

        locked_for = _login_lock_remaining()
        if locked_for:
            st.error(
                f"ใส่รหัสผ่านผิดเกิน {LOGIN_MAX_ATTEMPTS} ครั้ง "
                f"— กรุณารออีก {locked_for} วินาทีแล้วลองใหม่"
            )

        with st.form("_login_form"):
            username = st.text_input("ชื่อผู้ใช้ (Username)", key="_login_username")
            password = st.text_input("รหัสผ่าน", type="password", key="_login_password")
            submitted = st.form_submit_button(
                "เข้าสู่ระบบ", use_container_width=True, disabled=bool(locked_for)
            )

        if submitted and not locked_for:
            record = authenticate(username, password)
            if record:
                start_session(record)
                st.rerun()
            else:
                _register_login_failure()
                # Failed attempts are the entries a security review asks for first.
                audit_trail.record(
                    audit_trail.LOGIN_FAILED,
                    audit_trail.ENTITY_SESSION,
                    entity_label=(username or "").strip() or "—",
                    actor=(username or "").strip() or None,
                    changes={"locked": bool(_login_lock_remaining())},
                )
                remaining = LOGIN_MAX_ATTEMPTS - st.session_state.get("_login_fail_count", 0)
                if _login_lock_remaining():
                    st.error(f"ผิดหลายครั้งเกินไป — ถูกล็อก {LOGIN_LOCK_SECONDS} วินาที")
                else:
                    st.error(
                        f"ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง (ลองได้อีก {remaining} ครั้ง)"
                    )

        if default_admin_password_unchanged():
            st.info(
                "เข้าใช้งานครั้งแรก: ใช้บัญชี "
                f"`{DEFAULT_ADMIN_USERNAME}` / `{DEFAULT_ADMIN_PASSWORD}` "
                "แล้วเปลี่ยนรหัสผ่านทันทีที่กล่องบัญชีใน sidebar"
            )


def render_sidebar_account():
    """Show who is logged in + change password / logout in the sidebar."""
    user, role = get_current_user()
    if not user:
        return
    with st.sidebar:
        st.success(f"**{user}**  \n_{role_label(role)}_")
        render_change_password()
        if st.button("ออกจากระบบ", use_container_width=True, key="_logout_btn"):
            end_session()
            st.rerun()
        if role == "Admin" and default_admin_password_unchanged():
            st.warning("บัญชี `admin` ยังใช้รหัสผ่านเริ่มต้น — เปลี่ยนได้ที่ เปลี่ยนรหัสผ่าน ด้านบน")


def render_change_password():
    """Self-service password change — same box on every page, for every role."""
    with st.popover("เปลี่ยนรหัสผ่าน", use_container_width=True):
        user_id = get_current_user_id()
        if user_id is None:
            # .env accounts have no `users` row to update.
            st.caption("บัญชีนี้มาจากไฟล์ `.env` จึงเปลี่ยนรหัสผ่านจากหน้าเว็บไม่ได้")
            return

        with st.form("_change_password_form"):
            current = st.text_input("รหัสผ่านปัจจุบัน", type="password")
            new_password = st.text_input("รหัสผ่านใหม่", type="password")
            confirm = st.text_input("ยืนยันรหัสผ่านใหม่", type="password")
            submitted = st.form_submit_button("บันทึกรหัสผ่านใหม่", use_container_width=True)

        if submitted:
            error = change_password(user_id, current, new_password, confirm)
            if error:
                st.error(error)
            else:
                audit(
                    audit_trail.UPDATE,
                    audit_trail.ENTITY_USER,
                    entity_id=user_id,
                    entity_label=st.session_state.get("current_username"),
                    changes={"password": "เปลี่ยนรหัสผ่านด้วยตนเอง"},
                )
                st.success("เปลี่ยนรหัสผ่านเรียบร้อยแล้ว")


def recover_stale_processing_once() -> None:
    if st.session_state.get("_stale_processing_checked"):
        return
    st.session_state["_stale_processing_checked"] = True
    recovered = db.recover_stale_processing(PROCESSING_STALE_MINUTES)
    if recovered:
        log.warning("Recovered %s stale processing calls", recovered)
        st.sidebar.warning(f"Recovered {recovered} stale processing call(s).")


def get_current_user() -> tuple[str | None, str | None]:
    """Return (name, role) of the logged-in user, or (None, None)."""
    return (
        st.session_state.get("current_user"),
        st.session_state.get("current_user_role"),
    )


def get_current_user_id() -> int | None:
    """Row id of the logged-in user in the `users` table (None for .env accounts)."""
    return st.session_state.get("current_user_id")


def require_page(page_key: str) -> tuple[str, str]:
    """Stop the page unless the logged-in role may open it.

    The navigation already hides pages a role cannot use; this is the
    server-side check that also covers hand-typed URLs and stale browser tabs.
    """
    user, role = get_current_user()
    if not user:
        st.warning("กรุณาเข้าสู่ระบบก่อนใช้งาน")
        st.stop()
    if not can_access(role, page_key):
        st.error(
            f"บทบาท **{role_label(role)}** ไม่มีสิทธิ์เข้าหน้า "
            f"**{PAGE_LABELS_TH.get(page_key, page_key)}**"
        )
        st.stop()
    return user, role


def render_sidebar_info():
    """Render STT/LLM info in the sidebar — Admin only: model names mean
    nothing to the staff who use the app day to day."""
    _, role = get_current_user()
    if role != "Admin":
        return
    with st.sidebar:
        st.markdown("---")
        if MOCK_STT:
            st.caption("STT Mode: **Mock STT**")
        else:
            short = WHISPER_MODEL.split("/")[-1] if "/" in WHISPER_MODEL else WHISPER_MODEL
            st.caption(f"STT Mode: **Whisper ({short})**")
        st.caption(f"LLM: `{OLLAMA_MODEL}`")


def bootstrap_app():
    """Idempotent per-rerun setup, called by the Home.py router."""
    db.init_db()
    if not st.session_state.get("_default_admin_checked"):
        st.session_state["_default_admin_checked"] = True
        if ensure_default_admin():
            log.warning(
                "No account found — seeded default admin '%s'. Change its password.",
                DEFAULT_ADMIN_USERNAME,
            )
    recover_stale_processing_once()
    inject_css()


def init_page(page_key: str) -> tuple[str, str]:
    """Call at the top of every page (after st.set_page_config).

    Re-applies the shared CSS (each page runs in its own script slot) and
    enforces the role permission for `page_key`. Returns (user, role).
    """
    inject_css()
    return require_page(page_key)


# ── Badge / emoji helpers ────────────────────────────────────────────────

def sentiment_emoji(s: str) -> str:
    """Thai word for a sentiment code (the name predates the no-emoji rule)."""
    return labels.sentiment(s)


def status_badge(s: str) -> str:
    cls = f"badge-{s}"
    return f'<span class="status-badge {cls}">{labels.call_status(s)}</span>'


def metric_card(value, label: str, color: str | None = None) -> str:
    style = f' style="color:{color}"' if color else ""
    return (
        f'<div class="metric-card">'
        f'<div class="metric-value"{style}>{value}</div>'
        f'<div class="metric-label">{label}</div></div>'
    )


# ── Case ownership panel ─────────────────────────────────────────────────

def current_case_actor() -> case_workflow.Actor:
    user, role = get_current_user()
    return case_workflow.Actor(
        username=st.session_state.get("current_username") or "",
        name=user or "",
        role=role or "",
    )


def render_case_ownership(case: dict, key_suffix: str | int = "") -> None:
    """Who owns `case`, plus the claim / status / release buttons this user may press.

    `case` is a `db.get_case_detail()` / `db.get_all_cases()` row. `key_suffix`
    keeps widget keys unique when one case is drawn more than once on a page
    (the Admin page shows it under every call it contains).
    """
    case_id = case["id"]
    actor = current_case_actor()
    flash_key = f"_case_flash_{case_id}"
    flash = st.session_state.pop(flash_key, None)
    if flash:
        (st.success if flash[0] else st.error)(flash[1])

    def _key(name: str) -> str:
        return f"case_{name}_{case_id}_{key_suffix}"

    def _apply(result: tuple[bool, str]) -> None:
        st.session_state[flash_key] = result
        st.rerun()

    status = case.get("status")
    owner = case.get("assignee_name") or case.get("assignee_username")
    mine = case_workflow.is_owner(case, actor)

    if owner:
        you = " (คุณ)" if mine else ""
        st.markdown(f"**ผู้รับเคส:** {owner}{you} — รับเมื่อ {labels.thai_time(case.get('assigned_at'))}")
    else:
        st.markdown("**ผู้รับเคส:** ยังไม่มีคนรับ")
    if status == "closed" and case.get("closed_by"):
        st.caption(f"ปิดเคสโดย {case['closed_by']} เมื่อ {labels.thai_time(case.get('closed_at'))}")

    if not owner:
        error = case_workflow.claim_error(case, actor)
        if error is None:
            if st.button("รับเคสนี้", key=_key("claim"), type="primary"):
                _apply(case_workflow.claim(case_id, actor))
        else:
            st.caption(error)
        return

    if mine:
        if status == "closed":
            if st.button("เปิดเคสอีกครั้ง", key=_key("reopen")):
                _apply(case_workflow.change_status(case_id, "open", actor))
            return
        c1, c2, c3 = st.columns(3)
        with c1:
            if status == "open":
                if st.button("ตั้งเป็น ติดตาม", key=_key("follow"), use_container_width=True):
                    _apply(case_workflow.change_status(case_id, "follow_up", actor))
            elif st.button("กลับเป็น เปิด", key=_key("open"), use_container_width=True):
                _apply(case_workflow.change_status(case_id, "open", actor))
        with c2:
            if st.button("ปิดเคส", key=_key("close"), type="primary", use_container_width=True):
                _apply(case_workflow.change_status(case_id, "closed", actor))
        with c3:
            if st.button("คืนเคส", key=_key("release"), use_container_width=True,
                         help="ยกเลิกการรับเคส ให้คนอื่นรับต่อได้"):
                _apply(case_workflow.release(case_id, actor))
        return

    st.info(f"เคสนี้ {owner} รับไว้แล้ว — เปลี่ยนสถานะหรือปิดเคสได้เฉพาะผู้รับเคส")
    if case_workflow.release_error(case, actor) is None:
        if st.button(f"ปลด {owner} ออกจากเคส", key=_key("force_release"),
                     help="สำหรับหัวหน้างาน เช่น ผู้รับเคสลาออก/ลาพัก — เคสจะว่างให้คนอื่นรับ"):
            _apply(case_workflow.release(case_id, actor))


# ── Transcript ───────────────────────────────────────────────────────────

def _speaker_role(speaker: str, mapping: dict) -> str:
    """'SPEAKER_01' / 'Speaker 1' / 'speaker_1' → the role the pipeline mapped it to."""
    if speaker in mapping:
        return mapping[speaker]
    lowered = speaker.lower()
    for key, value in mapping.items():
        if key.lower() == lowered:
            return value
    nums = re.findall(r"\d+", speaker)
    if nums:
        n = int(nums[-1])
        for candidate in (f"SPEAKER_{n:02d}", f"Speaker {n}", f"speaker_{n}"):
            if candidate in mapping:
                return mapping[candidate]
        for key, value in mapping.items():
            key_nums = re.findall(r"\d+", key)
            if key_nums and int(key_nums[-1]) == n:
                return value
    return speaker


def render_proof(path: str | None, key: str, width: int = 280) -> None:
    """A warranty's proof of purchase: the picture itself, or a download for a PDF."""
    if not path:
        st.caption("ยังไม่มีหลักฐานการซื้อ")
        return
    if not os.path.exists(path):
        st.caption("ไม่พบไฟล์หลักฐานในเครื่อง (อาจถูกย้ายหรือลบ)")
        return
    if path.lower().endswith(".pdf"):
        with open(path, "rb") as fh:
            st.download_button("ดาวน์โหลดหลักฐาน (PDF)", fh.read(), file_name=os.path.basename(path),
                               mime="application/pdf", key=key)
    else:
        st.image(path, width=width)


def render_transcript(call: dict) -> None:
    """The call's transcript, one line per turn, labelled [พนักงาน] / [ลูกค้า]."""
    transcript = call.get("transcript") or ""
    if not transcript:
        st.caption("ยังไม่มีบทสนทนา — สายอาจยังประมวลผลไม่เสร็จ")
        return
    try:
        mapping = json.loads(call.get("speaker_mapping") or "{}")
    except (json.JSONDecodeError, TypeError):
        mapping = {}
    if not isinstance(mapping, dict):
        mapping = {}
    # Lines look like "SPEAKER_00: ..." (needs the map) or already "Agent: ...".
    for raw_line in transcript.splitlines():
        if ": " not in raw_line:
            st.markdown(html.escape(raw_line))
            continue
        speaker, text = raw_line.split(": ", 1)
        role = _speaker_role(speaker.strip(), mapping)
        color = {"Agent": "#93c5fd", "Customer": "#86efac"}.get(role, "#cbd5e1")
        who = {"Agent": "พนักงาน", "Customer": "ลูกค้า"}.get(role)
        if who is None:
            # A turn diarization couldn't assign ("Speaker 0" / "SPEAKER_01").
            nums = re.findall(r"\d+", role)
            who = f"ไม่ทราบผู้พูด {int(nums[-1]) + 1}" if nums else role
        # Transcript text comes from speech recognition — never let it be HTML.
        st.markdown(
            f'<span style="color:{color};font-weight:600">[{html.escape(who)}]</span> {html.escape(text)}',
            unsafe_allow_html=True,
        )


# ── Click a table row to read it ─────────────────────────────────────────

# Pass as st.dataframe(selection_mode=...). With "single-cell" a click on ANY
# cell counts. Row mode is left out on purpose: it adds a checkbox column, and
# un-ticking a box while the clicked cell stayed selected reopened the dialog.
TABLE_CLICK_MODES = ["single-cell"]


def picked_row(event, memory_key: str) -> tuple[int | None, bool]:
    """(row position the user clicked, whether it is a new click).

    "New" lets a page open its detail dialog once per click instead of on
    every rerun after it. Only a selection that *gains* something is a click —
    removing part of it (deselecting) never opens anything. Clearing the
    selection resets it, so clicking the same row again reopens the dialog.
    """
    selection = event.selection
    rows = list(selection.get("rows", []))
    cells = [tuple(c) for c in selection.get("cells", [])]
    row = rows[0] if rows else (cells[0][0] if cells else None)
    if row is None:
        st.session_state.pop(memory_key, None)
        return None, False
    picked = {("row", r) for r in rows} | {("cell", *c) for c in cells}
    is_new = bool(picked - st.session_state.get(memory_key, set()))
    st.session_state[memory_key] = picked
    return row, is_new


# ── Background processing ────────────────────────────────────────────────
#
# NOTE on durability:
#   Background pipeline work runs in daemon threads. If the Streamlit process
#   is killed mid-processing, in-flight calls stay stuck in 'processing' state
#   in the DB. Re-opening the Admin page lets the user re-process them manually.
#   For production multi-user deployments, consider replacing this with a
#   persistent job queue (Celery + Redis, or a PostgreSQL-backed LISTEN/NOTIFY).

_processing_lock = threading.Lock()
_queue_lock = threading.Lock()
_queue_running = False


def launch_processing(call_id: int) -> None:
    """Run pipeline.process_call in a background thread."""
    ollama_ready, _ = get_ollama_readiness()
    if not ollama_ready:
        return
    with _processing_lock:
        call = db.get_call_by_id(call_id)
        if not call or call["status"] == "processing":
            return
        db.update_call_status(call_id, "processing")

    processing_control.begin([call_id])

    def _run():
        try:
            pipeline.process_call(call_id)
        except processing_control.ProcessingCancelled:
            pass  # pipeline already put the call back to 'uploaded'
        except Exception:
            # Already logged + DB status marked 'error' inside pipeline
            log.error("Background processing crashed for call_id=%s", call_id)
        finally:
            processing_control.finish()

    threading.Thread(target=_run, daemon=True).start()


def launch_processing_queue(call_ids: list) -> list | None:
    """Process a list of calls sequentially in a single background thread."""
    ollama_ready, _ = get_ollama_readiness()
    if not ollama_ready:
        return None
    global _queue_running
    with _queue_lock:
        if _queue_running:
            return None
        _queue_running = True

    queued_ids = []
    for call_id in call_ids:
        call = db.get_call_by_id(call_id)
        if call and call["status"] == "uploaded":
            db.update_call_status(call_id, "processing")
            queued_ids.append(call_id)

    processing_control.begin(queued_ids)

    def _run_queue():
        global _queue_running
        try:
            for cid in queued_ids:
                if processing_control.stop_requested():
                    break
                try:
                    pipeline.process_call(cid)
                except processing_control.ProcessingCancelled:
                    break
                except Exception:
                    # Already logged + DB marked 'error' inside pipeline — continue queue
                    log.error("Queue item failed for call_id=%s — continuing", cid)
        finally:
            # Stopped: the calls that never started were marked 'processing'
            # up front — put them back in the queue.
            db.reset_calls_to_uploaded(queued_ids)
            processing_control.finish()
            with _queue_lock:
                _queue_running = False

    threading.Thread(target=_run_queue, daemon=True).start()
    return queued_ids
