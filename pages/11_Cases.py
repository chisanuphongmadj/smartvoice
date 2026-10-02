"""จัดการเคส — case list, claim / close, and the calls inside each case.

Reads cases straight from SQL (filters + paging in the query), so unlike the
Dashboard pages it doesn't load any calls up front.
"""

import math

import pandas as pd
import streamlit as st

st.set_page_config(page_title="SmartVoice — จัดการเคส", layout="wide")

from smartvoice import db
from smartvoice.auth import PAGE_CASES
from smartvoice.dashboard_common import inject_dashboard_css
from smartvoice.ui_helpers import (
    current_case_actor,
    init_page,
    metric_card,
    render_case_ownership,
)

init_page(PAGE_CASES)
inject_dashboard_css()

st.title("จัดการเคส")
st.caption(
    "คลิกแถวในตารางเพื่อเปิดเคส แล้วกด **รับเคสนี้** — เคสที่มีคนรับแล้ว คนอื่นรับซ้ำไม่ได้ "
    "และเปลี่ยนสถานะ/ปิดเคสได้เฉพาะผู้รับเคส (ทุกการรับ/ปิดเคสแจ้งเข้า Discord)"
)

case_counts = db.get_case_counts()
case_actor = current_case_actor()

cs_col1, cs_col2, cs_col3, cs_col4, cs_col5 = st.columns(5)
with cs_col1:
    st.markdown(metric_card(case_counts["total"], "Total Cases"), unsafe_allow_html=True)
with cs_col2:
    st.markdown(metric_card(case_counts["unassigned"], "ยังไม่มีคนรับ", "#a78bfa"), unsafe_allow_html=True)
with cs_col3:
    st.markdown(metric_card(case_counts["open"], "เปิด (Open)", "#22c55e"), unsafe_allow_html=True)
with cs_col4:
    st.markdown(metric_card(case_counts["follow_up"], "ติดตาม (Follow-up)", "#eab308"), unsafe_allow_html=True)
with cs_col5:
    st.markdown(metric_card(case_counts["closed"], "ปิด (Closed)", "#ef4444"), unsafe_allow_html=True)

if case_counts["total"] > 0:
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Filter row — push status/search down to SQL ─────────────────────
    _STATUS_OPTIONS = {
        "ทั้งหมด": None,
        "เปิด (Open)": "open",
        "ติดตาม (Follow-up)": "follow_up",
        "ปิด (Closed)": "closed",
    }
    _OWNER_OPTIONS = ("ทั้งหมด", "เคสของฉัน", "ยังไม่มีคนรับ")
    cf_status_col, cf_owner_col, cf_search_col, cf_size_col = st.columns([1.1, 1.1, 2, 0.9])
    with cf_status_col:
        cs_status_label = st.selectbox(
            "Status",
            list(_STATUS_OPTIONS.keys()),
            key="case_status_filter",
        )
    with cf_owner_col:
        cs_owner_label = st.selectbox(
            "ผู้รับเคส",
            _OWNER_OPTIONS,
            key="case_owner_filter",
        )
    with cf_search_col:
        cs_search = st.text_input(
            "ค้นหา (Subject / ชื่อลูกค้า / เบอร์ / ผู้รับเคส)",
            key="case_search",
            placeholder="เช่น แจ้งปัญหา, สุภาพร, 0819999336",
        )
    with cf_size_col:
        cs_page_size = st.selectbox(
            "แถวต่อหน้า",
            [10, 25, 50, 100],
            index=1,
            key="case_page_size",
        )

    # ดึงจำนวน + page ตาม filter (SQL-level — เร็วแม้ DB ใหญ่)
    cs_status = _STATUS_OPTIONS[cs_status_label]
    cs_search_clean = cs_search.strip() or None
    cs_owner_filter = {
        # "-" never matches a username, so an account without one sees no cases.
        "assignee": (case_actor.username or "-") if cs_owner_label == "เคสของฉัน" else None,
        "unassigned": cs_owner_label == "ยังไม่มีคนรับ",
    }
    cs_total_filtered = db.count_cases(status=cs_status, search=cs_search_clean, **cs_owner_filter)
    cs_n_pages = max(1, math.ceil(cs_total_filtered / cs_page_size)) if cs_total_filtered else 1
    if st.session_state.get("case_page", 1) > cs_n_pages:
        st.session_state["case_page"] = 1

    pg_col, info_col = st.columns([1, 3])
    with pg_col:
        cs_page = st.number_input(
            f"หน้า (รวม {cs_n_pages:,} หน้า)",
            min_value=1,
            max_value=cs_n_pages,
            step=1,
            key="case_page",
        )
    cs_start = (cs_page - 1) * cs_page_size
    cs_end = cs_start + cs_page_size
    with info_col:
        if cs_total_filtered == 0:
            st.markdown(
                "<div style='padding-top:1.95rem;color:#fbbf24;font-size:0.95rem;font-weight:500'>"
                "ไม่พบเคสที่ตรงกับเงื่อนไข — ลองล้าง search หรือเปลี่ยน Status</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<div style='padding-top:1.95rem;color:#cbd5e1;font-size:0.95rem;font-weight:500'>"
                f"แถว <b style='color:#38bdf8'>{cs_start + 1:,}–{min(cs_end, cs_total_filtered):,}</b> "
                f"จาก <b style='color:#38bdf8'>{cs_total_filtered:,}</b> เคส "
                f"(ในระบบทั้งหมด <b style='color:#38bdf8'>{case_counts['total']:,}</b>)</div>",
                unsafe_allow_html=True,
            )

    all_cases = db.get_all_cases(
        limit=cs_page_size,
        offset=cs_start,
        status=cs_status,
        search=cs_search_clean,
        **cs_owner_filter,
    )

    if all_cases:
        case_rows = []
        _case_badge = {"open": "เปิด", "follow_up": "ติดตาม", "closed": "ปิด"}
        for cs in all_cases:
            customer_name = (
                f"{cs.get('first_name', '')} {cs.get('last_name', '')}".strip() or "—"
            )
            case_rows.append({
                "Case ID": cs["id"],
                "Subject": cs["subject"],
                "Customer": customer_name,
                "Phone": cs.get("phone") or "—",
                "Calls": cs.get("call_count", 0),
                "Status": _case_badge.get(cs["status"], cs["status"]),
                "ผู้รับเคส": cs.get("assignee_name") or "ยังไม่มีคนรับ",
                "Updated": cs.get("updated_at", "")[:10],
            })
        cases_df = pd.DataFrame(case_rows)
        case_table = st.dataframe(
            cases_df,
            width="stretch",
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="case_table",
            column_config={
                "Subject": st.column_config.TextColumn(width="large"),
                "Customer": st.column_config.TextColumn(width="medium"),
                "ผู้รับเคส": st.column_config.TextColumn(width="medium"),
            },
        )

        # ── Selected case: owner + claim / status / release ────────────
        picked_rows = [i for i in case_table.selection.rows if i < len(all_cases)]
        if not picked_rows:
            st.caption("คลิกแถวในตารางเพื่อรับเคส ปิดเคส หรือดูสายในเคส")
        else:
            picked = db.get_case_detail(all_cases[picked_rows[0]]["id"])
            if picked:
                with st.container(border=True):
                    picked_customer = (
                        f"{picked.get('first_name') or ''} {picked.get('last_name') or ''}".strip() or "—"
                    )
                    st.markdown(f"#### เคส #{picked['id']}: {picked['subject']}")
                    st.caption(
                        f"ลูกค้า: {picked_customer} ({picked.get('phone') or '-'})  •  "
                        f"สถานะ: {_case_badge.get(picked['status'], picked['status'])}  •  "
                        f"{picked.get('call_count') or 0} สาย"
                    )
                    render_case_ownership(picked, key_suffix="dash")
                    picked_calls = db.get_calls_by_case(picked["id"])
                    with st.expander(f"สายในเคสนี้ ({len(picked_calls)})"):
                        for pc in picked_calls:
                            st.markdown(f"**{pc['filename']}** — {pc.get('topic') or '-'}")
                            if pc.get("summary"):
                                st.write(pc["summary"])
else:
    st.caption("ยังไม่มีเคสในระบบ — เคสจะถูกสร้างอัตโนมัติหลัง process สาย")
