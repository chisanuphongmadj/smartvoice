"""Dashboard → รายการสาย: every analysed call in the current filter, paged."""

import json
import math

import pandas as pd
import streamlit as st

st.set_page_config(page_title="SmartVoice — รายการสาย", layout="wide")

from smartvoice.auth import PAGE_CALLS
from smartvoice.dashboard_common import inject_dashboard_css, load_filtered_calls
from smartvoice.ui_helpers import init_page, sentiment_emoji

init_page(PAGE_CALLS)
inject_dashboard_css()

st.title("Dashboard — รายการสาย")

df, total_in_db = load_filtered_calls()
total = len(df)

search_term = st.text_input(
    "ค้นหา (ชื่อไฟล์ / หัวข้อ / สรุป)",
    key="calls_search",
    placeholder="เช่น 0819979336, แจ้งปัญหา, ที่นอน",
)
filtered_df = df.copy()
if search_term:
    mask = (
        filtered_df["filename"].str.contains(search_term, case=False, na=False)
        | filtered_df["topic"].str.contains(search_term, case=False, na=False)
        | filtered_df["summary"].str.contains(search_term, case=False, na=False)
    )
    filtered_df = filtered_df[mask]


def _fmt_keywords(raw):
    try:
        kws = json.loads(raw) if raw else []
        return ", ".join(kws[:5]) if isinstance(kws, list) else ""
    except (json.JSONDecodeError, TypeError):
        return ""


display_df = filtered_df[["filename", "sentiment", "topic", "keywords", "anomaly_detected", "summary", "created_at"]].copy()
display_df["sentiment"] = display_df["sentiment"].map(lambda s: sentiment_emoji(s))
display_df["keywords"] = display_df["keywords"].map(_fmt_keywords)
display_df["anomaly_detected"] = display_df["anomaly_detected"].map(lambda v: "พบ" if v else "ปกติ")
display_df["created_at"] = pd.to_datetime(display_df["created_at"]).dt.strftime("%Y-%m-%d %H:%M:%S")
display_df.columns = ["Filename", "Sentiment", "Topic", "Keywords", "Anomaly", "Summary", "Created (UTC)"]

# ── Pagination — กันตาราง render แถวเป็นพัน ทำให้หน้าช้า ────────────────
_PAGE_SIZE_OPTIONS = [25, 50, 100, 200]
total_rows = len(display_df)
n_pages = max(1, math.ceil(total_rows / _PAGE_SIZE_OPTIONS[1])) if total_rows else 1

ps_col, pg_col, info_col = st.columns([1, 1, 2])
with ps_col:
    page_size = st.selectbox(
        "แถวต่อหน้า",
        _PAGE_SIZE_OPTIONS,
        index=1,  # default 50
        key="dashboard_page_size",
    )
n_pages = max(1, math.ceil(total_rows / page_size)) if total_rows else 1
# clamp ค่า page ถ้า filter ทำให้แถวลด/หรือ page_size เปลี่ยน
_saved_page = st.session_state.get("dashboard_page", 1)
if _saved_page > n_pages:
    st.session_state["dashboard_page"] = 1
with pg_col:
    page = st.number_input(
        f"หน้า (รวม {n_pages:,} หน้า)",
        min_value=1,
        max_value=n_pages,
        step=1,
        key="dashboard_page",
    )

start = (page - 1) * page_size
end = start + page_size
page_df = display_df.iloc[start:end]

with info_col:
    st.markdown(
        f"<div style='padding-top:1.95rem;color:#cbd5e1;font-size:0.95rem;font-weight:500'>"
        f"แถว <b style='color:#38bdf8'>{start + 1:,}–{min(end, total_rows):,}</b> "
        f"จากทั้งหมด <b style='color:#38bdf8'>{total_rows:,}</b> สาย "
        f"(ตามผล filter)</div>",
        unsafe_allow_html=True,
    )

st.dataframe(
    page_df,
    width="stretch",
    hide_index=True,
    column_config={
        "Summary": st.column_config.TextColumn(width="large"),
        "Filename": st.column_config.TextColumn(width="medium"),
        "Keywords": st.column_config.TextColumn(width="medium"),
    },
)

st.markdown(
    f"<br><span style='color:#cbd5e1;font-size:1rem;font-weight:500'>"
    f"แสดง <b style='color:#38bdf8'>{len(filtered_df):,}</b> จากที่โหลด "
    f"<b style='color:#38bdf8'>{total:,}</b> สาย "
    f"(ระบบมีทั้งหมด <b style='color:#38bdf8'>{total_in_db:,}</b> สาย)</span>",
    unsafe_allow_html=True,
)
