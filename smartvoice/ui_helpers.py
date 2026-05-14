"""Shared UI helpers for Streamlit pages — CSS, badges, processing launchers."""

import threading

import streamlit as st

from smartvoice import db, pipeline
from smartvoice.config import WHISPER_MODEL, OLLAMA_MODEL, MOCK_STT
from smartvoice.logger import get_logger

log = get_logger(__name__)

# ── Shared CSS ───────────────────────────────────────────────────────────

_CSS = """
.stApp { background-color: #0f1117; }
section[data-testid="stSidebar"] { background-color: #1a1d27; }
.metric-card {
    background: linear-gradient(135deg, #1e2130, #252a3a);
    border: 1px solid #2d3250;
    border-radius: 12px;
    padding: 20px;
    text-align: center;
}
.metric-value { font-size: 2.5rem; font-weight: 700; color: #7c83f0; }
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
    .metric-value { color: #3730a3 !important; }
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


# ── Simple staff login (no password — captures who did what for audit log) ──

STAFF_ROLES = ["Admin", "Supervisor", "Agent", "QA"]


def render_login_widget():
    """Render a lightweight login at the top of the sidebar.

    Captures `current_user` (name) + `current_user_role` into session state.
    No password — this is an **audit-trail** feature, not security. For a
    hardened multi-tenant deployment, replace with proper auth (e.g.
    streamlit-authenticator + hashed credentials).
    """
    with st.sidebar:
        user = st.session_state.get("current_user")
        role = st.session_state.get("current_user_role")

        if user:
            st.success(f"👤 **{user}**  \n_{role}_")
            if st.button("🚪 Logout", use_container_width=True, key="_logout_btn"):
                st.session_state.pop("current_user", None)
                st.session_state.pop("current_user_role", None)
                st.rerun()
        else:
            st.markdown("### 🔑 เข้าสู่ระบบ")
            name = st.text_input("ชื่อ-นามสกุล", key="_login_name", placeholder="เช่น สุภาพร จันทร์แก้ว")
            role_pick = st.selectbox("บทบาท", STAFF_ROLES, key="_login_role")
            if st.button("✅ Login", use_container_width=True, key="_login_btn"):
                name_clean = (name or "").strip()
                if not name_clean:
                    st.error("กรุณาใส่ชื่อ")
                else:
                    st.session_state["current_user"] = name_clean
                    st.session_state["current_user_role"] = role_pick
                    st.rerun()


def get_current_user() -> tuple[str | None, str | None]:
    """Return (name, role) of the logged-in user, or (None, None)."""
    return (
        st.session_state.get("current_user"),
        st.session_state.get("current_user_role"),
    )


def render_sidebar_info():
    """Render STT/LLM info in the sidebar."""
    with st.sidebar:
        st.markdown("---")
        if MOCK_STT:
            st.caption("STT Mode: **🧪 Mock STT**")
        else:
            short = WHISPER_MODEL.split("/")[-1] if "/" in WHISPER_MODEL else WHISPER_MODEL
            st.caption(f"STT Mode: **🎙 Whisper ({short})**")
        st.caption(f"LLM: `{OLLAMA_MODEL}`")


def init_page():
    """Call at the top of every page (after st.set_page_config)."""
    db.init_db()
    inject_css()
    render_login_widget()
    render_sidebar_info()


# ── Badge / emoji helpers ────────────────────────────────────────────────

def sentiment_emoji(s: str) -> str:
    return {"positive": "😊 Positive", "neutral": "😐 Neutral", "negative": "😠 Negative"}.get(
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
