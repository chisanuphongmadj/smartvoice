"""SmartVoice — AI-powered Call Center Analytics (home page)."""

import streamlit as st

st.set_page_config(
    page_title="SmartVoice",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

from smartvoice import db
from smartvoice.preflight import run_preflight_checks
from smartvoice.ui_helpers import init_page, metric_card

init_page()

# ── Home page ────────────────────────────────────────────────────────────
st.title("🎙️ SmartVoice")
st.markdown("**AI-powered Call Center Analytics** — transcribes Thai audio, diarizes speakers, and runs LLM quality analysis.")

st.divider()

# Quick stats
calls = db.get_all_calls()
total = len(calls)
done = sum(1 for c in calls if c["status"] == "done")
processing = sum(1 for c in calls if c["status"] == "processing")
pending = sum(1 for c in calls if c["status"] == "uploaded")

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown(metric_card(total, "Total Calls"), unsafe_allow_html=True)
with col2:
    st.markdown(metric_card(done, "Done", "#22c55e"), unsafe_allow_html=True)
with col3:
    st.markdown(metric_card(processing, "Processing", "#3b82f6"), unsafe_allow_html=True)
with col4:
    st.markdown(metric_card(pending, "Pending", "#eab308"), unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)
st.info("👈 เลือกหน้าจาก sidebar เพื่อเริ่มใช้งาน")

with st.expander("Deployment readiness", expanded=False):
    checks = run_preflight_checks()
    for check in checks:
        if check.ok:
            st.success(f"{check.name}: {check.detail}")
        elif check.severity == "error":
            st.error(f"{check.name}: {check.detail}")
        else:
            st.warning(f"{check.name}: {check.detail}")
