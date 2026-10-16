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
    PAGE_SALES_ORDERS,
    PAGE_DASHBOARD,
    PAGE_DATA_ENTRY,
    PAGE_HOME,
    PAGE_INSIGHTS,
    PAGE_SETTINGS,
    PAGE_USERS,
    can_access,
    role_label,
    visible_pages,
)
from smartvoice.preflight import run_preflight_checks
from smartvoice.ui_helpers import (
    bootstrap_app,
    current_case_actor,
    get_current_user,
    metric_card,
    render_login_page,
    render_sidebar_account,
    render_sidebar_info,
)

bootstrap_app()


# ── Navigation specs (also used by the home page's shortcuts) ────────────

# Every page gets a Material icon so the menu reads as one set — without one,
# Streamlit borrows the emoji in some page file names and leaves the rest bare.
_PAGE_SPECS = {
    PAGE_HOME: dict(page=None, title="หน้าแรก", icon=":material/home:", url_path="home", default=True),
    PAGE_ADMIN: dict(page="pages/1_📤_Admin.py", title="อัปโหลดและประมวลผลเสียง", icon=":material/upload_file:", url_path="admin"),
    PAGE_DASHBOARD: dict(page="pages/2_📊_Dashboard.py", title="ภาพรวม", icon=":material/dashboard:", url_path="dashboard"),
    PAGE_INSIGHTS: dict(page="pages/8_Dashboard_Insights.py", title="คีย์เวิร์ด แบรนด์ ช่องทาง", icon=":material/sell:", url_path="insights"),
    PAGE_ANOMALY: dict(page="pages/9_Dashboard_Anomaly.py", title="สายที่ผิดปกติ", icon=":material/warning:", url_path="anomaly"),
    PAGE_AGENT_PERFORMANCE: dict(page="pages/10_Agent_Performance.py", title="ผลงานพนักงาน", icon=":material/leaderboard:", url_path="agent-performance"),
    PAGE_CALLS: dict(page="pages/12_Call_Summaries.py", title="รายการสาย", icon=":material/call:", url_path="calls"),
    PAGE_CASES: dict(page="pages/11_Cases.py", title="จัดการเคส", icon=":material/assignment:", url_path="cases"),
    PAGE_CUSTOMERS: dict(page="pages/3_👥_Customers.py", title="ลูกค้าและการรับประกัน", icon=":material/groups:", url_path="customers"),
    PAGE_SALES_ORDERS: dict(page="pages/13_Sales_Orders.py", title="ใบสั่งขาย (SO)", icon=":material/receipt_long:", url_path="sales-orders"),
    PAGE_DATA_ENTRY: dict(page="pages/6_➕_Data_Entry.py", title="เพิ่ม/แก้ไขข้อมูลลูกค้า", icon=":material/person_add:", url_path="data-entry"),
    PAGE_AUDIT: dict(page="pages/7_📜_Audit_Log.py", title="ประวัติการใช้งาน", icon=":material/history:", url_path="audit-log"),
    PAGE_SETTINGS: dict(page="pages/4_Settings.py", title="ตั้งค่าระบบ", icon=":material/settings:", url_path="settings"),
    PAGE_USERS: dict(page="pages/5_👤_Users.py", title="จัดการผู้ใช้", icon=":material/manage_accounts:", url_path="users"),
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
    PAGE_SALES_ORDERS: "งานลูกค้า",
    PAGE_DATA_ENTRY: "งานลูกค้า",
    PAGE_ADMIN: "จัดการระบบ",
    PAGE_AUDIT: "จัดการระบบ",
    PAGE_SETTINGS: "จัดการระบบ",
    PAGE_USERS: "จัดการระบบ",
}
_SECTION_ORDER = ("", "Dashboard", "งานลูกค้า", "จัดการระบบ", "อื่นๆ")


# ── Home page ────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def _cached_preflight_checks():
    """Readiness checks, cached for 5 minutes — they hit the network."""
    return run_preflight_checks()


def _shortcut(
    role: str, page_key: str, label: str, query_params: dict | None = None, stretch: bool = False
) -> None:
    """A link to `page_key`, drawn only when this role may open that page."""
    if can_access(role, page_key):
        spec = _PAGE_SPECS[page_key]
        st.page_link(
            spec["page"], label=label, icon=spec["icon"], query_params=query_params,
            width="stretch" if stretch else "content",
        )


def _work_card(
    key: str, value: int, label: str, color: str,
    role: str, page_key: str, link_label: str, query_params: dict | None = None,
) -> None:
    """Number + label + the link that acts on it, all inside one card."""
    with st.container(key=f"workcard_{key}"):
        st.markdown(
            f'<div class="work-value" style="color:{color}">{value:,}</div>'
            f'<div class="work-label">{label}</div>',
            unsafe_allow_html=True,
        )
        _shortcut(role, page_key, link_label, query_params, stretch=True)


def home_page():
    st.title("Thai Call Analytics")
    st.caption(
        "AI-powered Call Center Analytics for Thai Customer Calls — "
        "ระบบถอดเสียงสายลูกค้า สรุปเรื่อง และติดตามเคสอัตโนมัติ"
    )

    user, role = get_current_user()
    st.markdown(f"#### สวัสดี {user}")
    st.caption(f"บทบาท: {role_label(role)}")

    # ── งานที่รอคุณ — what needs a person right now ──────────────────────
    # All counts are single SQL aggregates: loading rows to count them would
    # drag every transcript along (~300 ms and ~57 MB per view at 5,000 calls).
    case_counts = db.get_case_counts()
    username = current_case_actor().username or "-"
    my_open = db.count_cases(status="open", assignee=username) + db.count_cases(
        status="follow_up", assignee=username
    )
    anomalies = db.count_anomaly_calls()
    counts = db.count_calls_by_status()

    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("งานที่รอคุณ")
    w1, w2, w3 = st.columns(3)
    with w1:
        _work_card(
            "unassigned", case_counts["unassigned"], "เคสที่ยังไม่มีคนรับ", "#a78bfa",
            role, PAGE_CASES, "ไปเลือกรับเคส", {"owner": "unassigned"},
        )
    with w2:
        _work_card(
            "mine", my_open, "เคสของฉันที่ยังไม่ปิด", "#22c55e",
            role, PAGE_CASES, "ดูเคสของฉัน", {"owner": "mine"},
        )
    with w3:
        _work_card(
            "anomaly", anomalies["high"],
            f"สายผิดปกติระดับรุนแรง<br>(ผิดปกติทั้งหมด {anomalies['total']:,} สาย)", "#ef4444",
            role, PAGE_ANOMALY, "ดูสายที่ผิดปกติ",
        )

    # ── Call processing status ──────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    head_col, link_col = st.columns([3, 1], vertical_alignment="bottom")
    with head_col:
        st.subheader("สถานะสายในระบบ")
    with link_col:
        _shortcut(role, PAGE_ADMIN, "อัปโหลด / ประมวลผลเสียง", stretch=True)
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(metric_card(counts["total"], "สายทั้งหมด"), unsafe_allow_html=True)
    with col2:
        st.markdown(metric_card(counts["done"], "วิเคราะห์เสร็จแล้ว", "#22c55e"), unsafe_allow_html=True)
    with col3:
        st.markdown(metric_card(counts["processing"], "กำลังประมวลผล", "#3b82f6"), unsafe_allow_html=True)
    with col4:
        st.markdown(metric_card(counts["uploaded"] + counts["error"], "รอประมวลผล / ผิดพลาด", "#eab308"), unsafe_allow_html=True)

    # ── How to start, per role ──────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("เริ่มต้นใช้งาน — ทำอะไรได้ที่ไหน", expanded=False):
        steps = []
        if can_access(role, PAGE_ADMIN):
            steps.append("**อัปโหลดเสียง** — เมนู *อัปโหลดและประมวลผลเสียง* → ลากไฟล์ .wav/.mp3 มาวาง แล้วกด *ประมวลผลทั้งหมดที่รออยู่*")
        steps.append("**รับเคส** — เมนู *จัดการเคส* → อ่านว่าลูกค้าแจ้งเรื่องอะไร คลิกแถว แล้วกด *รับเคสนี้* (คนอื่นจะรับซ้ำไม่ได้)")
        steps.append("**ปิดเคส** — เปิดเคสของคุณ (ตัวกรอง *ผู้รับเคส → เคสของฉัน*) แล้วกด *ปิดเคส* เมื่อจัดการเสร็จ")
        steps.append("**ดูภาพรวม** — หมวด *Dashboard* ใน sidebar: ภาพรวม, คีย์เวิร์ด, สายที่ผิดปกติ, ผลงานพนักงาน, รายการสาย")
        steps.append("**ค้นหาลูกค้า / ประกัน** — เมนู *ลูกค้าและการรับประกัน*")
        if can_access(role, PAGE_DATA_ENTRY):
            steps.append("**เพิ่ม/แก้ไขลูกค้า** — เมนู *เพิ่ม/แก้ไขข้อมูลลูกค้า*")
        if can_access(role, PAGE_USERS):
            steps.append("**เพิ่มพนักงาน** — เมนู *จัดการผู้ใช้*")
        st.markdown("\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1)))
        st.caption("การรีเฟรชหน้าเว็บ (F5) จะออกจากระบบ — ใช้เมนูด้านซ้ายเปลี่ยนหน้าแทน")

    if can_access(role, PAGE_SETTINGS):
        with st.expander("ตรวจความพร้อมของระบบ (สำหรับผู้ดูแล)", expanded=False):
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


_PAGE_SPECS[PAGE_HOME]["page"] = home_page


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

# expanded=True: by default Streamlit folds anything past 10 links behind
# "View more", which hid Audit / Settings / Users from Admins.
_page = st.navigation(_build_navigation(_role), expanded=True)
render_sidebar_account()
render_sidebar_info()
_page.run()
