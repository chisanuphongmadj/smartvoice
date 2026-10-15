"""Dashboard → ความผิดปกติ: calls flagged as escalation-worthy, most severe first."""

import streamlit as st

st.set_page_config(page_title="SmartVoice — สายที่ผิดปกติ", layout="wide")

from smartvoice.auth import PAGE_ANOMALY
from smartvoice.dashboard_common import inject_dashboard_css, load_filtered_calls
from smartvoice.ui_helpers import init_page, metric_card

init_page(PAGE_ANOMALY)
inject_dashboard_css()

st.title("Dashboard — สายที่ผิดปกติ")
st.caption(
    "สายที่ควรส่งต่อหัวหน้า เช่น ขู่ฟ้อง ขู่ร้องเรียน ขอคุยหัวหน้า คำหยาบ หรือพนักงานทำผิด "
    "— ลูกค้าไม่พอใจแต่จบเรื่องได้ ไม่นับเป็นความผิดปกติ"
)

df, _ = load_filtered_calls()
done_calls = df.to_dict("records")

_SEVERITY_LABELS = {"high": "รุนแรง", "medium": "ปานกลาง", "low": "เล็กน้อย"}
_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

anom_calls = [c for c in done_calls if c.get("anomaly_detected")]
by_severity = {
    sev: sum(1 for c in anom_calls if c.get("anomaly_severity") == sev) for sev in _SEVERITY_LABELS
}

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

severity_pick = st.selectbox(
    "ระดับความรุนแรง",
    ["ทั้งหมด", *_SEVERITY_LABELS],
    format_func=lambda s: _SEVERITY_LABELS.get(s, s),
    key="anomaly_severity_filter",
)
shown = [
    c for c in anom_calls
    if severity_pick == "ทั้งหมด" or c.get("anomaly_severity") == severity_pick
]
shown.sort(key=lambda c: (_SEVERITY_ORDER.get(c.get("anomaly_severity"), 3), -c["created_at"].timestamp()))

if not shown:
    st.caption("ไม่มีสายในระดับนี้")
for c in shown:
    sev = _SEVERITY_LABELS.get(c.get("anomaly_severity") or "", "ไม่ระบุ")
    reason = c.get("anomaly_reason") or "ไม่ระบุสาเหตุ"
    (st.error if c.get("anomaly_severity") == "high" else st.warning)(
        f"**{sev}** — {c['filename']}  \n{reason}"
    )
