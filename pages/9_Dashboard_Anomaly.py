"""Dashboard → ความผิดปกติ: calls flagged as escalation-worthy, most severe first.

A paged table (short columns) instead of one box per call — hundreds of
anomalies used to make the page endless; clicking any cell opens the whole
call: the quoted evidence, summary and transcript.
"""

import math

import pandas as pd
import streamlit as st

st.set_page_config(page_title="SmartVoice — สายที่ผิดปกติ", layout="wide")

from smartvoice import labels
from smartvoice.auth import PAGE_ANOMALY
from smartvoice.dashboard_common import inject_dashboard_css, load_filtered_calls
from smartvoice.dashboard_report import anomaly_calls, call_time
from smartvoice.file_manager import extract_agent_code_from_filename
from smartvoice.ui_helpers import TABLE_CLICK_MODES, init_page, metric_card, picked_row, render_transcript

init_page(PAGE_ANOMALY)
inject_dashboard_css()

st.title("Dashboard — สายที่ผิดปกติ")
st.caption(
    "สายที่ควรส่งต่อหัวหน้า เช่น ขู่ฟ้อง ขู่ร้องเรียน ขอคุยหัวหน้า คำหยาบ หรือพนักงานทำผิด "
    "— ลูกค้าไม่พอใจแต่จบเรื่องได้ ไม่นับเป็นความผิดปกติ"
)

df, _ = load_filtered_calls()
done_calls = df.to_dict("records")

_SEVERITIES = ("high", "medium", "low")
_SEVERITY_COLOR = {"รุนแรง": "#ef4444", "ปานกลาง": "#f97316", "เล็กน้อย": "#eab308"}

anom_calls = anomaly_calls(done_calls)
by_severity = {sev: sum(1 for c in anom_calls if c.get("anomaly_severity") == sev) for sev in _SEVERITIES}

a1, a2, a3, a4, a5 = st.columns(5)
with a1:
    st.markdown(metric_card(len(anom_calls), "สายผิดปกติ", "#ef4444"), unsafe_allow_html=True)
with a2:
    st.markdown(metric_card(by_severity["high"], "รุนแรง", "#ef4444"), unsafe_allow_html=True)
with a3:
    st.markdown(metric_card(by_severity["medium"], "ปานกลาง", "#f97316"), unsafe_allow_html=True)
with a4:
    st.markdown(metric_card(by_severity["low"], "เล็กน้อย", "#eab308"), unsafe_allow_html=True)
with a5:
    st.markdown(metric_card(len(done_calls) - len(anom_calls), "สายปกติ", "#22c55e"), unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

if not anom_calls:
    st.success("ไม่พบความผิดปกติในการสนทนา")
    st.stop()


@st.dialog("รายละเอียดสายที่ผิดปกติ", width="large")
def _anomaly_dialog(call: dict) -> None:
    severity = labels.severity(call.get("anomaly_severity"))
    st.markdown(f"#### ความผิดปกติระดับ{severity}")
    st.caption(
        f"วันที่โทร {call_time(call)}  •  ลูกค้า {call.get('customer_phone') or '-'}  •  "
        f"พนักงาน {extract_agent_code_from_filename(call.get('filename') or '') or '-'}  •  "
        f"หัวข้อ {call.get('topic_detail') or call.get('topic') or '-'}"
        + (f"  •  เคส #{call['case_id']}" if call.get("case_id") else "")
    )
    (st.error if call.get("anomaly_severity") == "high" else st.warning)(
        call.get("anomaly_reason") or "ไม่ระบุสาเหตุ"
    )
    st.markdown("**สรุปสาย**")
    st.write(call.get("summary") or "ไม่มีสรุป")
    if call.get("case_id"):
        st.page_link(
            "pages/11_Cases.py", label="ไปหน้าจัดการเคส", icon=":material/assignment:",
        )
    with st.expander("บทสนทนาเต็ม"):
        render_transcript(call)
    st.caption(f"ไฟล์เสียง: {call.get('filename') or '-'}")


f_sev, f_size, f_page = st.columns([2, 1, 1], vertical_alignment="bottom")
with f_sev:
    severity_pick = st.selectbox(
        "ระดับความรุนแรง",
        ["ทั้งหมด", *_SEVERITIES],
        format_func=lambda s: s if s == "ทั้งหมด" else labels.severity(s),
        key="anomaly_severity_filter",
    )
shown = [c for c in anom_calls if severity_pick == "ทั้งหมด" or c.get("anomaly_severity") == severity_pick]
with f_size:
    page_size = st.selectbox("แถวต่อหน้า", [25, 50, 100], key="anomaly_page_size")
n_pages = max(1, math.ceil(len(shown) / page_size))
if st.session_state.get("anomaly_page", 1) > n_pages:
    st.session_state["anomaly_page"] = 1
with f_page:
    page = st.number_input(f"หน้า (รวม {n_pages:,} หน้า)", min_value=1, max_value=n_pages, step=1, key="anomaly_page")

if not shown:
    st.caption("ไม่มีสายในระดับนี้")
    st.stop()

start = (page - 1) * page_size
page_calls = shown[start:start + page_size]
st.caption(
    f"แสดง {start + 1:,}–{start + len(page_calls):,} จาก {len(shown):,} สาย เรียงจากรุนแรงสุด "
    "— คลิกแถวไหนก็ได้เพื่ออ่านหลักฐานเต็มและบทสนทนา"
)

table = pd.DataFrame([
    {
        "ระดับ": labels.severity(c.get("anomaly_severity")),
        "วันที่โทร": call_time(c),
        "ลูกค้า": c.get("customer_phone") or "-",
        "พนักงาน": extract_agent_code_from_filename(c.get("filename") or "") or "-",
        "สาเหตุ": c.get("anomaly_reason") or "ไม่ระบุสาเหตุ",
    }
    for c in page_calls
])
event = st.dataframe(
    table.style.map(lambda v: f"color: {_SEVERITY_COLOR.get(v, 'inherit')}; font-weight: 700", subset=["ระดับ"]),
    width="stretch",
    hide_index=True,
    on_select="rerun",
    selection_mode=TABLE_CLICK_MODES,
    # Filter and page in the key: a new view must not keep the old row position.
    key=f"anomaly_table_{severity_pick}_{page}_{page_size}",
    column_config={
        "ระดับ": st.column_config.TextColumn(width="small"),
        "วันที่โทร": st.column_config.TextColumn(width="medium"),
        "ลูกค้า": st.column_config.TextColumn(width=110),
        "พนักงาน": st.column_config.TextColumn(width="small"),
        "สาเหตุ": st.column_config.TextColumn(width="large"),
    },
)

row, is_new = picked_row(event, "_anomaly_dialog_seen")
if row is not None and row < len(page_calls):
    if is_new:
        _anomaly_dialog(page_calls[row])
    if st.button("เปิดรายละเอียดสายนี้อีกครั้ง", icon=":material/open_in_new:"):
        _anomaly_dialog(page_calls[row])
