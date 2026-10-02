"""Thai Call Analytics — AI-powered Call Center Analytics (entrypoint + router).

This file is the app's router. It authenticates the visitor first, then builds
the sidebar navigation from the pages that the signed-in role is allowed to
open (`smartvoice.auth.visible_pages`). Calling `st.navigation` also switches
Streamlit off the automatic `pages/` menu, so a role that cannot access a page
never sees a link to it.
"""

import streamlit as st

st.set_page_config(
    page_title="Thai Call Analytics",
    layout="wide",
    initial_sidebar_state="expanded",
)

from smartvoice import db
from smartvoice.auth import (
    PAGE_ADMIN,
    PAGE_AGENT_PERFORMANCE,
    PAGE_ANOMALY,
    PAGE_AUDIT,
    PAGE_CALLS,
    PAGE_CASES,
    PAGE_CUSTOMERS,
    PAGE_DASHBOARD,
    PAGE_DATA_ENTRY,
    PAGE_HOME,
    PAGE_INSIGHTS,
    PAGE_SETTINGS,
    PAGE_USERS,
    role_label,
    visible_pages,
)
from smartvoice.preflight import run_preflight_checks
from smartvoice.ui_helpers import (
    bootstrap_app,
    get_current_user,
    metric_card,
    render_login_page,
    render_sidebar_account,
    render_sidebar_info,
)

bootstrap_app()


# ── Home page ────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def _cached_preflight_checks():
    """Readiness checks, cached for 5 minutes — they hit the network."""
    return run_preflight_checks()


def home_page():
    st.title("Thai Call Analytics")
    st.markdown("**AI-powered Call Center Analytics for Thai Customer Calls** — transcribes Thai audio, diarizes speakers, and runs LLM quality analysis.")

    user, role = get_current_user()
    st.caption(f"เข้าสู่ระบบในชื่อ **{user}** — บทบาท _{role_label(role)}_")

    st.divider()

    # Quick stats — counted with a single SQL GROUP BY. Loading the rows to
    # count them in Python would drag every transcript along with them: ~300 ms
    # and ~57 MB per page view at 5,000 calls, growing linearly from there.
    counts = db.count_calls_by_status()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(metric_card(counts["total"], "สายทั้งหมด"), unsafe_allow_html=True)
    with col2:
        st.markdown(metric_card(counts["done"], "เสร็จแล้ว", "#22c55e"), unsafe_allow_html=True)
    with col3:
        st.markdown(
            metric_card(counts["processing"], "กำลังประมวลผล", "#3b82f6"), unsafe_allow_html=True
        )
    with col4:
        st.markdown(
            metric_card(counts["uploaded"], "รอประมวลผล", "#eab308"), unsafe_allow_html=True
        )

    st.markdown("<br>", unsafe_allow_html=True)
    st.info("เลือกหน้าจาก sidebar เพื่อเริ่มใช้งาน")

    with st.expander("Deployment readiness", expanded=False):
        # Streamlit runs an expander's body even while it is collapsed, and these
        # checks call out to Ollama and HuggingFace over the network (~2.6 s).
        # Cached so opening the home page doesn't pay for them every rerun.
        col_refresh, _ = st.columns([1, 3])
        if col_refresh.button("ตรวจสอบใหม่", key="_refresh_preflight"):
            _cached_preflight_checks.clear()

        checks = _cached_preflight_checks()
        for check in checks:
            if check.ok:
                st.success(f"{check.name}: {check.detail}")
            elif check.severity == "error":
                st.error(f"{check.name}: {check.detail}")
            else:
                st.warning(f"{check.name}: {check.detail}")


# ── Navigation ───────────────────────────────────────────────────────────

_PAGE_SPECS = {
    PAGE_HOME: dict(page=home_page, title="หน้าแรก", url_path="home", default=True),
    PAGE_ADMIN: dict(page="pages/1_📤_Admin.py", title="Admin", url_path="admin"),
    PAGE_DASHBOARD: dict(page="pages/2_📊_Dashboard.py", title="ภาพรวม", url_path="dashboard"),
    PAGE_INSIGHTS: dict(page="pages/8_Dashboard_Insights.py", title="คีย์เวิร์ด แบรนด์ ช่องทาง", url_path="insights"),
    PAGE_ANOMALY: dict(page="pages/9_Dashboard_Anomaly.py", title="ความผิดปกติ", url_path="anomaly"),
    PAGE_AGENT_PERFORMANCE: dict(page="pages/10_Agent_Performance.py", title="ผลงาน Agent", url_path="agent-performance"),
    PAGE_CALLS: dict(page="pages/12_Call_Summaries.py", title="รายการสาย", url_path="calls"),
    PAGE_CASES: dict(page="pages/11_Cases.py", title="จัดการเคส", url_path="cases"),
    PAGE_CUSTOMERS: dict(page="pages/3_👥_Customers.py", title="Customers", url_path="customers"),
    PAGE_DATA_ENTRY: dict(page="pages/6_➕_Data_Entry.py", title="เพิ่มข้อมูล", url_path="data-entry"),
    PAGE_AUDIT: dict(page="pages/7_📜_Audit_Log.py", title="ประวัติการใช้งาน", url_path="audit-log"),
    PAGE_SETTINGS: dict(page="pages/4_Settings.py", title="Settings", url_path="settings"),
    PAGE_USERS: dict(page="pages/5_👤_Users.py", title="จัดการผู้ใช้", url_path="users"),
}


# Sidebar headings. "" puts the home page above every heading. A page missing
# from this map would land in "อื่นๆ" rather than vanish from the menu.
_SECTIONS = {
    PAGE_HOME: "",
    PAGE_DASHBOARD: "Dashboard",
    PAGE_INSIGHTS: "Dashboard",
    PAGE_ANOMALY: "Dashboard",
    PAGE_AGENT_PERFORMANCE: "Dashboard",
    PAGE_CALLS: "Dashboard",
    PAGE_CASES: "งานลูกค้า",
    PAGE_CUSTOMERS: "งานลูกค้า",
    PAGE_DATA_ENTRY: "งานลูกค้า",
    PAGE_ADMIN: "ผู้ดูแลระบบ",
    PAGE_AUDIT: "ผู้ดูแลระบบ",
    PAGE_SETTINGS: "ผู้ดูแลระบบ",
    PAGE_USERS: "ผู้ดูแลระบบ",
}
_SECTION_ORDER = ("", "Dashboard", "งานลูกค้า", "ผู้ดูแลระบบ", "อื่นๆ")


def _build_navigation(role: str) -> dict[str, list]:
    """{sidebar heading: [pages]} holding only the pages `role` may open."""
    grouped: dict[str, list] = {section: [] for section in _SECTION_ORDER}
    for key in visible_pages(role):
        grouped[_SECTIONS.get(key, "อื่นๆ")].append(st.Page(**_PAGE_SPECS[key]))
    return {section: pages for section, pages in grouped.items() if pages}


_user, _role = get_current_user()

if not _user:
    # Anonymous visitors get exactly one page and no sidebar menu.
    login = st.Page(render_login_page, title="เข้าสู่ระบบ", url_path="login", default=True)
    st.navigation([login], position="hidden").run()
    st.stop()

_page = st.navigation(_build_navigation(_role))
render_sidebar_account()
render_sidebar_info()
_page.run()
