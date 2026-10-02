"""Dashboard → ภาพรวม: headline numbers, sentiment, topics and the top issues.

The other Dashboard pages (keywords, anomalies, agent performance, call list)
sit next to this one under the "Dashboard" heading in the sidebar.
"""

from collections import Counter

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="SmartVoice — Dashboard", layout="wide")

from smartvoice import db
from smartvoice.auth import PAGE_DASHBOARD
from smartvoice.dashboard_common import (
    BAR_CORNER,
    BAR_TEXTFONT,
    CHART_LAYOUT,
    GRID_COLOR,
    SCALE_BRAND,
    SCALE_RED,
    SENTIMENT_COLORS,
    hbar,
    inject_dashboard_css,
    load_filtered_calls,
)
from smartvoice.ui_helpers import init_page, metric_card

init_page(PAGE_DASHBOARD)
inject_dashboard_css()

st.title("Dashboard — ภาพรวม")
st.caption("ดูรายละเอียดแต่ละเรื่องได้จากเมนู Dashboard ใน sidebar")

df, total_in_db = load_filtered_calls()
done_calls = df.to_dict("records")

# ── KPI row ──────────────────────────────────────────────────────────────
total = len(df)
col1, col2, col3, col4 = st.columns(4)
for col, val, label in [
    (col1, total, "Total Calls"),
    (col2, (df["sentiment"] == "positive").sum(), "Positive"),
    (col3, (df["sentiment"] == "neutral").sum(), "Neutral"),
    (col4, (df["sentiment"] == "negative").sum(), "Negative"),
]:
    with col:
        st.markdown(metric_card(val, label), unsafe_allow_html=True)

# ── Shortcuts to the pages that need someone to act ─────────────────────
anomaly_count = int(df["anomaly_detected"].fillna(0).astype(bool).sum())
unassigned_cases = db.get_case_counts()["unassigned"]
link_col1, link_col2 = st.columns(2)
with link_col1:
    st.page_link(
        "pages/9_Dashboard_Anomaly.py",
        label=f"สายผิดปกติ {anomaly_count:,} สาย",
    )
with link_col2:
    st.page_link(
        "pages/11_Cases.py",
        label=f"เคสรอคนรับ {unassigned_cases:,} เคส",
    )

st.divider()

# ── Charts row ───────────────────────────────────────────────────────────
chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    st.subheader("Sentiment Distribution")
    sentiment_counts = df["sentiment"].value_counts().reset_index()
    sentiment_counts.columns = ["Sentiment", "Count"]
    fig_sentiment = px.bar(
        sentiment_counts, x="Sentiment", y="Count",
        color="Sentiment", color_discrete_map=SENTIMENT_COLORS, text="Count",
    )
    fig_sentiment.update_traces(
        textposition="outside",
        textfont=BAR_TEXTFONT,
        marker=dict(cornerradius=BAR_CORNER, line=dict(width=0)),
        hovertemplate="<b>%{x}</b><br>จำนวน: %{y} สาย<extra></extra>",
    )
    fig_sentiment.update_layout(
        **CHART_LAYOUT, xaxis_title="", yaxis_title="จำนวนสาย",
        margin=dict(t=30, b=10),
        yaxis=dict(gridcolor=GRID_COLOR, zeroline=False),
        xaxis=dict(showgrid=False),
    )
    st.plotly_chart(fig_sentiment, width="stretch")

with chart_col2:
    st.subheader("Topic / Intent Distribution")
    topic_counts = df["topic"].replace("", pd.NA).dropna().value_counts().reset_index()
    topic_counts.columns = ["Topic", "Count"]
    st.plotly_chart(
        hbar(topic_counts, "Topic", SCALE_BRAND, margin=dict(t=20, b=20, r=60), headroom=False),
        width="stretch",
    )

    # ── Drill-down: "แจ้งปัญหาสินค้า" ละเอียดตามประเภทความเสียหาย ──
    # Omazz ขอให้แสดงประเภทความเสียหายแบบเจาะจง (ผ้าขาด/เตียงหัก/...) แทน
    # หมวดกว้าง — pipeline เก็บไว้ใน column topic_detail (ดู prompts.py)
    if "topic_detail" in df.columns:
        detail_series = df.loc[
            df["topic"] == "แจ้งปัญหาสินค้า", "topic_detail"
        ].replace("", pd.NA).dropna()
        if not detail_series.empty:
            detail_counts = detail_series.value_counts().reset_index()
            detail_counts.columns = ["Detail", "Count"]
            st.caption("เจาะลึก: ประเภทความเสียหายภายใน \"แจ้งปัญหาสินค้า\"")
            st.plotly_chart(
                hbar(
                    detail_counts, "Detail", SCALE_RED,
                    margin=dict(t=10, b=20, r=60),
                    height=max(200, 40 * len(detail_counts) + 80),
                    headroom=False,
                ),
                width="stretch",
            )

st.divider()

# ── Top Issues ───────────────────────────────────────────────────────────
st.subheader("Top 3 Issues")
issue_calls = [c for c in done_calls if c.get("sentiment") == "negative" or c.get("anomaly_detected")]
if issue_calls:
    issue_topic_counts = Counter(c["topic"] for c in issue_calls if c.get("topic")).most_common(3)
    if issue_topic_counts:
        issue_df = pd.DataFrame(issue_topic_counts, columns=["Issue / Topic", "Count"])
        st.plotly_chart(
            hbar(issue_df, "Issue / Topic", SCALE_RED, height=max(200, 60 + 50 * len(issue_df))),
            width="stretch",
        )
        st.caption(f"จาก {len(issue_calls)} สาย (Negative sentiment + Anomaly)")
    else:
        st.caption("ไม่พบ topic ใน calls ที่มีปัญหา")
else:
    st.success("ไม่พบสายที่มีปัญหา (Negative/Anomaly) ในช่วงเวลาที่เลือก")
