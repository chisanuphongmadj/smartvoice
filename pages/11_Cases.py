"""จัดการเคส — case list, claim / close, and the calls inside each case.

Reads cases straight from SQL (filters + paging in the query), then the calls
of just the cases on screen — enough to say what each case is about
(`case_workflow.case_brief`) without loading the whole calls table.
"""

import math

import pandas as pd
import streamlit as st

st.set_page_config(page_title="SmartVoice — จัดการเคส", layout="wide")

from smartvoice import case_workflow, db, labels
from smartvoice.auth import PAGE_CASES
from smartvoice.customer_entry import compute_expiry_date
from smartvoice.dashboard_common import inject_dashboard_css
from smartvoice.ui_helpers import (
    TABLE_CLICK_MODES,
    current_case_actor,
    init_page,
    metric_card,
    picked_row,
    render_case_ownership,
    sentiment_emoji,
)

init_page(PAGE_CASES)
inject_dashboard_css()

st.title("จัดการเคส")
st.caption(
    "คลิกที่เคสไหนก็ได้ในตาราง เพื่อเปิดอ่านรายละเอียดเต็ม แล้วกด **รับเคสนี้** ในหน้าต่างนั้น "
    "— เคสที่มีคนรับแล้ว คนอื่นรับซ้ำไม่ได้ และเปลี่ยนสถานะ/ปิดเคสได้เฉพาะผู้รับเคส "
    "(ทุกการรับ/ปิดเคสแจ้งเข้า Discord)"
)


@st.dialog("รายละเอียดเคส", width="large")
def _case_dialog(case_id: int) -> None:
    """Everything about one case, then the claim / status buttons."""
    picked = db.get_case_detail(case_id)
    if not picked:
        st.warning("ไม่พบเคสนี้แล้ว — อาจถูกรวมเข้ากับเคสอื่น")
        return
    picked_calls = db.get_calls_for_cases([case_id]).get(case_id, [])
    brief = case_workflow.case_brief(picked_calls)
    picked_customer = (
        f"{picked.get('first_name') or ''} {picked.get('last_name') or ''}".strip() or "—"
    )
    st.markdown(f"#### เคส #{picked['id']}: {brief['issue'] or picked['subject']}")
    st.caption(
        f"ความเร่งด่วน: {brief['priority']}  •  "
        f"ลูกค้า: {picked_customer} ({picked.get('phone') or '-'})  •  "
        f"สถานะ: {labels.case_status(picked['status'])}  •  "
        f"{picked.get('call_count') or 0} สาย"
    )

    for anomaly in brief["anomalies"]:
        sev = case_workflow.SEVERITY_LABELS_TH.get(anomaly["severity"], "ไม่ระบุ")
        (st.error if anomaly["severity"] == "high" else st.warning)(
            f"ความผิดปกติ ({sev}): {anomaly['reason'] or 'ไม่ระบุสาเหตุ'}"
        )

    info_col, todo_col = st.columns(2)
    with info_col:
        st.markdown("**ลูกค้าแจ้งว่า** (จากสายล่าสุด)")
        st.write(brief["summary"] or "ยังไม่มีสรุป — สายอาจยังประมวลผลไม่เสร็จ")
    with todo_col:
        st.markdown("**สิ่งที่ต้องทำต่อ**")
        if brief["next_action_steps"]:
            st.markdown("\n".join(f"- {step}" for step in brief["next_action_steps"]))
            if brief["next_action_owner"]:
                st.caption(f"ผู้รับผิดชอบที่ระบบแนะนำ: {brief['next_action_owner']}")
        else:
            st.write("ระบบไม่ได้ระบุ — ดูจากบทสรุปและสายในเคส")

    if picked.get("customer_id"):
        warranties = db.get_warranties_by_customer(picked["customer_id"])
        if warranties:
            st.markdown("**สินค้า / ประกันของลูกค้า**")
            for w in warranties:
                product = " ".join(
                    str(w.get(k)) for k in ("brand", "model", "size") if w.get(k)
                ) or "ไม่ระบุสินค้า"
                # Older rows were imported without an expiry date —
                # derive it the same way the data-entry page does.
                expiry = w.get("expiry_date") or compute_expiry_date(
                    w.get("date_of_purchase"), w.get("warranty_period_months")
                )
                st.caption(
                    f"{product}  •  ทะเบียน {w.get('registration_no') or '-'}  •  "
                    f"ซื้อ {labels.thai_time(w.get('date_of_purchase'), with_time=False)}  •  "
                    f"หมดประกัน {labels.thai_time(expiry, with_time=False)}"
                )

    st.divider()
    render_case_ownership(picked, key_suffix="dlg")

    with st.expander(f"สายในเคสนี้ ({len(picked_calls)})"):
        for pc in reversed(picked_calls):
            st.markdown(
                f"**{pc['filename']}** — {pc.get('topic') or '-'} "
                f"({sentiment_emoji(pc.get('sentiment'))})"
            )
            if pc.get("summary"):
                st.write(pc["summary"])

case_counts = db.get_case_counts()
case_actor = current_case_actor()

cs_col1, cs_col2, cs_col3, cs_col4, cs_col5 = st.columns(5)
with cs_col1:
    st.markdown(metric_card(case_counts["total"], "เคสทั้งหมด"), unsafe_allow_html=True)
with cs_col2:
    st.markdown(metric_card(case_counts["unassigned"], "ยังไม่มีคนรับ", "#a78bfa"), unsafe_allow_html=True)
with cs_col3:
    st.markdown(metric_card(case_counts["open"], "เปิด", "#22c55e"), unsafe_allow_html=True)
with cs_col4:
    st.markdown(metric_card(case_counts["follow_up"], "ติดตาม", "#eab308"), unsafe_allow_html=True)
with cs_col5:
    st.markdown(metric_card(case_counts["closed"], "ปิดแล้ว", "#ef4444"), unsafe_allow_html=True)

if case_counts["total"] > 0:
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Filter row — push status/search down to SQL ─────────────────────
    _STATUS_OPTIONS = {
        "ทั้งหมด": None,
        "เปิด": "open",
        "ติดตาม": "follow_up",
        "ปิดแล้ว": "closed",
    }
    _OWNER_OPTIONS = ("ทั้งหมด", "เคสของฉัน", "ยังไม่มีคนรับ")
    # Shortcuts on the home page arrive with ?owner=mine / ?owner=unassigned.
    # Apply once, then drop it so the dropdown stays in the user's hands.
    _owner_param = {"mine": "เคสของฉัน", "unassigned": "ยังไม่มีคนรับ"}.get(
        st.query_params.get("owner", "")
    )
    if _owner_param:
        st.session_state["case_owner_filter"] = _owner_param
        st.session_state["case_page"] = 1
        del st.query_params["owner"]
    cf_status_col, cf_owner_col, cf_search_col, cf_size_col = st.columns([1.1, 1.1, 2, 0.9])
    with cf_status_col:
        cs_status_label = st.selectbox(
            "สถานะเคส",
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
            "ค้นหา (หัวข้อ / ชื่อลูกค้า / เบอร์ / ผู้รับเคส)",
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
                "ไม่พบเคสที่ตรงกับเงื่อนไข — ลองล้างคำค้น หรือเปลี่ยนสถานะเคส / ผู้รับเคส</div>",
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
        _case_badge = labels.CASE_STATUS_TH
        # One query for the calls behind every case on this page — that is
        # where "what is this case about" lives (summary, next step, urgency).
        calls_by_case = db.get_calls_for_cases([cs["id"] for cs in all_cases])
        briefs = {
            cs["id"]: case_workflow.case_brief(calls_by_case.get(cs["id"], []))
            for cs in all_cases
        }

        case_rows = []
        for cs in all_cases:
            brief = briefs[cs["id"]]
            customer_name = (
                f"{cs.get('first_name') or ''} {cs.get('last_name') or ''}".strip() or "—"
            )
            case_rows.append({
                "Case ID": cs["id"],
                "ความเร่งด่วน": brief["priority"],
                "เรื่อง": brief["issue"] or cs["subject"],
                "ลูกค้าแจ้งว่า": brief["summary"] or "—",
                "สิ่งที่ต้องทำต่อ": brief["next_action"] or "—",
                "ลูกค้า": f"{customer_name} ({cs.get('phone') or '-'})",
                "สาย": cs.get("call_count", 0),
                "สถานะ": _case_badge.get(cs["status"], cs["status"]),
                "ผู้รับเคส": cs.get("assignee_name") or "ยังไม่มีคนรับ",
                "อัปเดต": labels.thai_time(cs.get("updated_at")),
            })
        cases_df = pd.DataFrame(case_rows)
        # Claiming / closing a case bumps it to the top of the list. A selection
        # is a row *position*, so it would then point at a different case —
        # tie the table's identity to the row order to clear it when that moves.
        _row_order = abs(hash(tuple(cs["id"] for cs in all_cases))) % 10**8
        case_table = st.dataframe(
            cases_df,
            width="stretch",
            hide_index=True,
            on_select="rerun",
            selection_mode=TABLE_CLICK_MODES,
            key=f"case_table_{cs_page}_{_row_order}",
            column_config={
                "Case ID": st.column_config.NumberColumn(width="small"),
                "ความเร่งด่วน": st.column_config.TextColumn(width="small"),
                "เรื่อง": st.column_config.TextColumn(width="medium"),
                "ลูกค้าแจ้งว่า": st.column_config.TextColumn(width="large"),
                "สิ่งที่ต้องทำต่อ": st.column_config.TextColumn(width="large"),
                "ลูกค้า": st.column_config.TextColumn(width="medium"),
                "สาย": st.column_config.NumberColumn(width="small"),
                "ผู้รับเคส": st.column_config.TextColumn(width="medium"),
            },
        )

        # ── Click a case → its details open in a dialog ─────────────────
        row, is_new = picked_row(case_table, "_case_dialog_seen")
        opened_id = st.session_state.get("_case_dialog_case")
        if opened_id and f"_case_flash_{opened_id}" in st.session_state:
            # A claim/close inside the dialog reruns the page: open the SAME case
            # again (by id, not row) so the person sees the result message.
            _case_dialog(opened_id)
        elif row is not None and row < len(all_cases):
            picked_id = all_cases[row]["id"]
            if is_new:
                st.session_state["_case_dialog_case"] = picked_id
                _case_dialog(picked_id)
        else:
            st.info("คลิกที่เคสไหนก็ได้ในตาราง เพื่อเปิดอ่านรายละเอียดและรับเคส")
        if opened_id or (row is not None and row < len(all_cases)):
            reopen_id = all_cases[row]["id"] if row is not None and row < len(all_cases) else opened_id
            if st.button(f"เปิดรายละเอียดเคส #{reopen_id} อีกครั้ง", icon=":material/open_in_new:"):
                st.session_state["_case_dialog_case"] = reopen_id
                _case_dialog(reopen_id)
else:
    st.caption("ยังไม่มีเคสในระบบ — เคสจะถูกสร้างอัตโนมัติหลัง process สาย")
