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
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

from smartvoice import db
from smartvoice.auth import (
    PAGE_ADMIN,
    PAGE_CUSTOMERS,
    PAGE_DASHBOARD,
    PAGE_DATA_ENTRY,
    PAGE_HOME,
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

def home_page():
    st.title("🎙️ Thai Call Analytics")
    st.markdown("**AI-powered Call Center Analytics for Thai Customer Calls** — transcribes Thai audio, diarizes speakers, and runs LLM quality analysis.")

    user, role = get_current_user()
    st.caption(f"เข้าสู่ระบบในชื่อ **{user}** — บทบาท _{role_label(role)}_")

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


# ── Navigation ───────────────────────────────────────────────────────────

_PAGE_SPECS = {
    PAGE_HOME: dict(page=home_page, title="หน้าแรก", icon="🎙️", url_path="home", default=True),
    PAGE_ADMIN: dict(page="pages/1_📤_Admin.py", title="Admin", icon="📤", url_path="admin"),
    PAGE_DASHBOARD: dict(page="pages/2_📊_Dashboard.py", title="Dashboard", icon="📊", url_path="dashboard"),
    PAGE_CUSTOMERS: dict(page="pages/3_👥_Customers.py", title="Customers", icon="👥", url_path="customers"),
    PAGE_DATA_ENTRY: dict(page="pages/6_➕_Data_Entry.py", title="เพิ่มข้อมูล", icon="➕", url_path="data-entry"),
    PAGE_SETTINGS: dict(page="pages/4_Settings.py", title="Settings", icon="⚙️", url_path="settings"),
    PAGE_USERS: dict(page="pages/5_👤_Users.py", title="จัดการผู้ใช้", icon="👤", url_path="users"),
}


def _build_navigation(role: str):
    return [st.Page(**_PAGE_SPECS[key]) for key in visible_pages(role)]


_user, _role = get_current_user()

if not _user:
    # Anonymous visitors get exactly one page and no sidebar menu.
    login = st.Page(render_login_page, title="เข้าสู่ระบบ", icon="🔑", url_path="login", default=True)
    st.navigation([login], position="hidden").run()
    st.stop()

_page = st.navigation(_build_navigation(_role))
render_sidebar_account()
render_sidebar_info()
_page.run()
