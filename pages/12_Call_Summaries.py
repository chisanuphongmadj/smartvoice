"""Dashboard → รายการสาย: every analysed call in the current filter, paged.

The table keeps short columns; clicking any cell opens the whole call —
summary, follow-up, scores and the transcript — in a dialog.
"""

import json
import math

import pandas as pd
import streamlit as st

st.set_page_config(page_title="SmartVoice — รายการสาย", layout="wide")

from smartvoice import case_workflow, db, labels
from smartvoice.auth import PAGE_CALLS
from smartvoice.dashboard_common import inject_dashboard_css, load_filtered_calls
from smartvoice.file_manager import (
    extract_agent_code_from_filename,
    extract_call_time_from_filename,
    extract_direction_from_filename,
)
from smartvoice.ollama_client import sanitize_evidence, sanitize_next_action
from smartvoice.ui_helpers import (
    TABLE_CLICK_MODES,
    init_page,
    metric_card,
    picked_row,
    render_transcript,
    sentiment_emoji,
)

init_page(PAGE_CALLS)
inject_dashboard_css()

st.title("Dashboard — รายการสาย")
st.caption("คลิกที่สายไหนก็ได้ในตาราง เพื่อเปิดอ่านสรุป สิ่งที่ต้องทำต่อ คะแนนพนักงาน และบทสนทนาเต็ม")

_DIRECTION_TH = {"inbound": "สายเข้า", "outbound": "สายออก"}


def _json_list(raw) -> list[str]:
    try:
        items = json.loads(raw) if raw else []
    except (json.JSONDecodeError, TypeError):
        return []
    return [i for i in items if isinstance(i, str) and i.strip()] if isinstance(items, list) else []


def _call_time(call: dict) -> str:
    called = extract_call_time_from_filename(call.get("filename") or "")
    return called.strftime("%d/%m/%Y %H:%M น.") if called else labels.thai_time(call.get("created_at"))


@st.dialog("รายละเอียดสาย", width="large")
def _call_dialog(call_id: int) -> None:
    call = db.get_call_by_id(call_id)
    if not call:
        st.warning("ไม่พบสายนี้แล้ว — อาจถูกลบไป")
        return
    filename = call.get("filename") or ""
    direction = _DIRECTION_TH.get(extract_direction_from_filename(filename) or "", "-")
    st.markdown(f"#### {call.get('topic_detail') or call.get('topic') or 'สาย'} — ลูกค้า {call.get('customer_phone') or '-'}")
    meta = [
        f"วันที่โทร {_call_time(call)}",
        direction,
        f"พนักงาน {extract_agent_code_from_filename(filename) or '-'}",
        f"อารมณ์ลูกค้า: {sentiment_emoji(call.get('sentiment'))}",
    ]
    if call.get("case_id"):
        case = db.get_case_by_id(call["case_id"])
        if case:
            owner = case.get("assignee_name") or "ยังไม่มีคนรับ"
            meta.append(f"เคส #{case['id']} ({labels.case_status(case['status'])}, ผู้รับเคส: {owner})")
    st.caption("  •  ".join(meta))

    if call.get("anomaly_detected"):
        (st.error if call.get("anomaly_severity") == "high" else st.warning)(
            f"ความผิดปกติ ({labels.severity(call.get('anomaly_severity'))}): "
            f"{call.get('anomaly_reason') or 'ไม่ระบุสาเหตุ'}"
        )

    st.markdown("**สรุปสาย**")
    st.write(call.get("summary") or "ยังไม่มีสรุป")
    if call.get("sentiment_reason"):
        st.caption(f"เหตุผลที่ประเมินอารมณ์ลูกค้า: {call['sentiment_reason']}")

    try:
        perf = json.loads(call.get("agent_performance") or "{}")
    except (json.JSONDecodeError, TypeError):
        perf = {}
    perf = perf if isinstance(perf, dict) else {}
    transcript = call.get("transcript") or ""

    todo_col, words_col = st.columns(2)
    with todo_col:
        st.markdown("**สิ่งที่ต้องทำต่อ**")
        action, owner = sanitize_next_action(
            perf.get("next_action") or "", perf.get("next_action_owner") or "", transcript
        )
        steps = case_workflow.next_action_steps(action)
        if steps:
            st.markdown("\n".join(f"- {step}" for step in steps))
            if owner and owner not in {"ไม่มี", "—", "-"}:
                st.caption(f"ผู้รับผิดชอบที่ระบบแนะนำ: {owner}")
        else:
            st.write("ระบบไม่ได้ระบุ")
    with words_col:
        st.markdown("**คำสำคัญ / แบรนด์ / ช่องทาง**")
        for title, field in (("คำสำคัญ", "keywords"), ("แบรนด์", "brand_mentions"), ("ช่องทาง", "platform_mentions")):
            items = _json_list(call.get(field))
            st.caption(f"{title}: {', '.join(items) if items else '-'}")

    if perf.get("overall_score"):
        st.markdown("**คะแนนพนักงาน**")
        s1, s2, s3 = st.columns(3)
        with s1:
            st.markdown(metric_card(f"{float(perf.get('politeness') or 0) + float(perf.get('problem_solving') or 0):.1f} / 10", "คะแนนรวม"), unsafe_allow_html=True)
        with s2:
            st.markdown(metric_card(f"{float(perf.get('politeness') or 0):.1f} / 5", "ความสุภาพ"), unsafe_allow_html=True)
        with s3:
            st.markdown(metric_card(f"{float(perf.get('problem_solving') or 0):.1f} / 5", "การแก้ปัญหา"), unsafe_allow_html=True)
        e1, e2 = st.columns(2)
        with e1:
            st.caption("หลักฐานความสุภาพ")
            st.write(sanitize_evidence(" ".join(str(perf.get("politeness_evidence") or "").split()), transcript) or "-")
        with e2:
            st.caption("หลักฐานการแก้ปัญหา")
            st.write(sanitize_evidence(" ".join(str(perf.get("problem_solving_evidence") or "").split()), transcript) or "-")

    with st.expander("บทสนทนาเต็ม (แยกผู้พูด)"):
        render_transcript(call)
    st.caption(f"ไฟล์: {filename}")


df, total_in_db = load_filtered_calls()
total = len(df)

search_term = st.text_input(
    "ค้นหา (เบอร์ / ชื่อไฟล์ / หัวข้อ / สรุป)",
    key="calls_search",
    placeholder="เช่น 0819979336, แจ้งปัญหา, ที่นอน",
)
filtered_df = df.copy()
if search_term:
    mask = (
        filtered_df["filename"].str.contains(search_term, case=False, na=False, regex=False)
        | filtered_df["topic"].str.contains(search_term, case=False, na=False, regex=False)
        | filtered_df["summary"].str.contains(search_term, case=False, na=False, regex=False)
    )
    filtered_df = filtered_df[mask]

# Newest call first, by when it happened (file name) rather than upload time.
calls = sorted(
    filtered_df.to_dict("records"),
    key=lambda c: (extract_call_time_from_filename(c.get("filename") or "") is not None,
                   str(extract_call_time_from_filename(c.get("filename") or "") or c.get("created_at"))),
    reverse=True,
)

# ── Pagination — กันตาราง render แถวเป็นพัน ทำให้หน้าช้า ────────────────
_PAGE_SIZE_OPTIONS = [25, 50, 100, 200]
total_rows = len(calls)

ps_col, pg_col, info_col = st.columns([1, 1, 2], vertical_alignment="bottom")
with ps_col:
    page_size = st.selectbox("แถวต่อหน้า", _PAGE_SIZE_OPTIONS, index=1, key="dashboard_page_size")
n_pages = max(1, math.ceil(total_rows / page_size)) if total_rows else 1
# clamp ค่า page ถ้า filter ทำให้แถวลด/หรือ page_size เปลี่ยน
if st.session_state.get("dashboard_page", 1) > n_pages:
    st.session_state["dashboard_page"] = 1
with pg_col:
    page = st.number_input(f"หน้า (รวม {n_pages:,} หน้า)", min_value=1, max_value=n_pages, step=1, key="dashboard_page")

start = (page - 1) * page_size
page_calls = calls[start:start + page_size]
with info_col:
    if total_rows:
        st.caption(
            f"แสดง {start + 1:,}–{start + len(page_calls):,} จาก {total_rows:,} สายที่ตรงตัวกรอง "
            f"(ระบบมีทั้งหมด {total_in_db:,} สาย)"
        )

if not page_calls:
    st.warning("ไม่พบสายที่ตรงกับคำค้น — ลองพิมพ์คำอื่น หรือล้างตัวกรองด้านบน")
    st.stop()

table = st.dataframe(
    pd.DataFrame([
        {
            "วันที่โทร": _call_time(c),
            "ลูกค้า": c.get("customer_phone") or "-",
            "พนักงาน": extract_agent_code_from_filename(c.get("filename") or "") or "-",
            "ทิศทาง": _DIRECTION_TH.get(extract_direction_from_filename(c.get("filename") or "") or "", "-"),
            "หัวข้อ": c.get("topic_detail") or c.get("topic") or "-",
            "อารมณ์ลูกค้า": sentiment_emoji(c.get("sentiment")),
            "ผิดปกติ": labels.severity(c.get("anomaly_severity")) if c.get("anomaly_detected") else "-",
            "สรุปสาย": c.get("summary") or "-",
        }
        for c in page_calls
    ]),
    width="stretch",
    hide_index=True,
    on_select="rerun",
    selection_mode=TABLE_CLICK_MODES,
    key=f"calls_table_{page}",
    column_config={
        "วันที่โทร": st.column_config.TextColumn(width="medium"),
        "ลูกค้า": st.column_config.TextColumn(width=110),
        "พนักงาน": st.column_config.TextColumn(width="small"),
        "ทิศทาง": st.column_config.TextColumn(width="small"),
        "หัวข้อ": st.column_config.TextColumn(width="medium"),
        "อารมณ์ลูกค้า": st.column_config.TextColumn(width="small"),
        "ผิดปกติ": st.column_config.TextColumn(width="small"),
        "สรุปสาย": st.column_config.TextColumn(width="large"),
    },
)

row, is_new = picked_row(table, "_call_dialog_seen")
if row is None or row >= len(page_calls):
    st.info("คลิกที่สายไหนก็ได้ในตาราง เพื่อเปิดอ่านรายละเอียดเต็ม")
else:
    picked_id = page_calls[row]["id"]
    if is_new:
        _call_dialog(picked_id)
    if st.button("เปิดรายละเอียดสายนี้อีกครั้ง", icon=":material/open_in_new:"):
        _call_dialog(picked_id)
