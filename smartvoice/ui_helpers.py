"""Shared UI helpers for Streamlit pages — CSS, login, badges, processing launchers."""

import threading
import time

import streamlit as st

from smartvoice import audit as audit_trail
from smartvoice import db, pipeline
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
    padding: 20px;
    text-align: center;
}
.metric-value { font-size: 2.5rem; font-weight: 700; color: #38bdf8; }
.metric-label { font-size: 0.85rem; color: #9ca3af; margin-top: 4px; }
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
            username = st.text_input("Username", key="_login_username")
            password = st.text_input("Password", type="password", key="_login_password")
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
                        f"Username หรือ Password ไม่ถูกต้อง (เหลืออีก {remaining} ครั้ง)"
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
    """Render STT/LLM info in the sidebar."""
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
    return {"positive": "Positive", "neutral": "Neutral", "negative": "Negative"}.get(
        s or "", "—"
    )


def status_badge(s: str) -> str:
    cls = f"badge-{s}"
    return f'<span class="status-badge {cls}">{s.upper()}</span>'


def metric_card(value, label: str, color: str | None = None) -> str:
    style = f' style="color:{color}"' if color else ""
    return (
        f'<div class="metric-card">'
        f'<div class="metric-value"{style}>{value}</div>'
        f'<div class="metric-label">{label}</div></div>'
    )


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

    def _run():
        try:
            pipeline.process_call(call_id)
        except Exception:
            # Already logged + DB status marked 'error' inside pipeline
            log.error("Background processing crashed for call_id=%s", call_id)

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

    def _run_queue():
        global _queue_running
        try:
            for cid in queued_ids:
                try:
                    pipeline.process_call(cid)
                except Exception:
                    # Already logged + DB marked 'error' inside pipeline — continue queue
                    log.error("Queue item failed for call_id=%s — continuing", cid)
        finally:
            with _queue_lock:
                _queue_running = False

    threading.Thread(target=_run_queue, daemon=True).start()
    return queued_ids
