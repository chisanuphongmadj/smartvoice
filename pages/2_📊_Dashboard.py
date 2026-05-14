import json
from collections import Counter, defaultdict

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="SmartVoice — Dashboard", page_icon="📊", layout="wide")

from smartvoice import db
from smartvoice.ui_helpers import init_page, metric_card, sentiment_emoji

init_page()

# ─────────────────────────────────────────
# PAGE: DASHBOARD — Analytics
# ─────────────────────────────────────────
st.title("📊 Dashboard — Analytics")

done_calls = db.get_done_calls()

if not done_calls:
    st.info("No completed calls yet. Upload and process audio files from the Admin page.")
    st.stop()

df = pd.DataFrame(done_calls)
df["created_at"] = pd.to_datetime(df["created_at"])

# ── Filters ──────────────────────────────────────────────────────────────
with st.expander("🔍 Filters", expanded=False):
    f_col1, f_col2, f_col3 = st.columns([1, 1, 1])
    with f_col1:
        min_date = df["created_at"].dt.date.min()
        max_date = df["created_at"].dt.date.max()
        date_range = st.date_input(
            "Date range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )
    with f_col2:
        intent_options = ["All"] + sorted(df["topic"].dropna().unique().tolist())
        selected_intent = st.selectbox("Intent / Topic", intent_options)
    with f_col3:
        sentiment_options = ["All", "positive", "neutral", "negative"]
        selected_sentiment = st.selectbox("Sentiment", sentiment_options)

if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    start_date, end_date = date_range
    df = df[
        (df["created_at"].dt.date >= start_date)
        & (df["created_at"].dt.date <= end_date)
    ]
if selected_intent != "All":
    df = df[df["topic"] == selected_intent]
if selected_sentiment != "All":
    df = df[df["sentiment"] == selected_sentiment]

done_calls = df.to_dict("records")

if df.empty:
    st.warning("ไม่พบข้อมูลที่ตรงกับ filter ที่เลือก")
    st.stop()

# ── KPI row ──────────────────────────────────────────────────────────────
total = len(df)
pos = (df["sentiment"] == "positive").sum()
neg = (df["sentiment"] == "negative").sum()
neu = (df["sentiment"] == "neutral").sum()

col1, col2, col3, col4 = st.columns(4)
for col, val, label in [
    (col1, total, "Total Calls"),
    (col2, pos, "Positive 😊"),
    (col3, neu, "Neutral 😐"),
    (col4, neg, "Negative 😠"),
]:
    with col:
        st.markdown(metric_card(val, label), unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Charts row ───────────────────────────────────────────────────────────
chart_col1, chart_col2 = st.columns(2)

_CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font_color="#e5e7eb",
    showlegend=False,
)

with chart_col1:
    st.subheader("Sentiment Distribution")
    sentiment_counts = df["sentiment"].value_counts().reset_index()
    sentiment_counts.columns = ["Sentiment", "Count"]
    color_map = {"positive": "#22c55e", "neutral": "#eab308", "negative": "#ef4444"}
    fig_sentiment = px.bar(
        sentiment_counts, x="Sentiment", y="Count",
        color="Sentiment", color_discrete_map=color_map, text="Count",
    )
    fig_sentiment.update_traces(
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>จำนวน: %{y} สาย<extra></extra>",
    )
    fig_sentiment.update_layout(
        **_CHART_LAYOUT, xaxis_title="", yaxis_title="จำนวนสาย",
        margin=dict(t=30, b=10),
    )
    st.plotly_chart(fig_sentiment, width="stretch")

with chart_col2:
    st.subheader("Topic / Intent Distribution")
    topic_series = df["topic"].replace("", pd.NA).dropna()
    topic_counts = topic_series.value_counts().reset_index()
    topic_counts.columns = ["Topic", "Count"]
    fig_topic = px.bar(topic_counts, x="Count", y="Topic", orientation="h", text="Count")
    fig_topic.update_traces(
        marker_color="#3b82f6", textposition="outside",
        hovertemplate="<b>%{y}</b><br>จำนวน: %{x} สาย<extra></extra>",
    )
    fig_topic.update_layout(
        **_CHART_LAYOUT, xaxis_title="จำนวนสาย", yaxis_title="",
        margin=dict(t=20, b=20, r=60), yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig_topic, width="stretch")

st.divider()

# ── Keyword/Brand Trends + Anomaly row ───────────────────────────────────
kw_col, anom_col = st.columns(2)

with kw_col:
    kw_left, kw_right = st.columns(2)

    with kw_left:
        st.subheader("🏷 หัวข้อปัญหา (Issue Keywords)")
        all_keywords = []
        for call in done_calls:
            raw = call.get("keywords") or ""
            try:
                kws = json.loads(raw) if raw else []
                if isinstance(kws, list):
                    all_keywords.extend([k for k in kws if isinstance(k, str) and k.strip()])
            except (json.JSONDecodeError, TypeError):
                pass

        if all_keywords:
            kw_counts = Counter(all_keywords).most_common(15)
            kw_df = pd.DataFrame(kw_counts, columns=["Keyword", "Count"])
            kw_max = kw_df["Count"].max()
            fig_kw = px.bar(kw_df, x="Count", y="Keyword", orientation="h", text="Count")
            fig_kw.update_traces(
                marker_color="#3b82f6", textposition="outside",
                hovertemplate="<b>%{y}</b><br>พบ: %{x} ครั้ง<extra></extra>",
            )
            fig_kw.update_layout(
                **_CHART_LAYOUT, xaxis_title="จำนวนครั้ง", yaxis_title="",
                margin=dict(t=20, b=20, r=20),
                yaxis=dict(autorange="reversed"),
                xaxis=dict(range=[0, kw_max * 1.25]),
            )
            st.plotly_chart(fig_kw, width="stretch")
        else:
            st.caption("ยังไม่มีข้อมูล keyword")

    with kw_right:
        st.subheader("🔖 Brand Mentions")
        all_brands = []
        for call in done_calls:
            raw = call.get("brand_mentions") or ""
            try:
                brands = json.loads(raw) if raw else []
                if isinstance(brands, list):
                    all_brands.extend([b for b in brands if isinstance(b, str) and b.strip()])
            except (json.JSONDecodeError, TypeError):
                pass

        if all_brands:
            brand_counts = Counter(all_brands).most_common(15)
            brand_df = pd.DataFrame(brand_counts, columns=["Brand", "Count"])
            fig_brand = px.bar(brand_df, x="Count", y="Brand", orientation="h", text="Count")
            fig_brand.update_traces(
                marker_color="#10b981", textposition="outside",
                hovertemplate="<b>%{y}</b><br>พบ: %{x} ครั้ง<extra></extra>",
            )
            fig_brand.update_layout(
                **_CHART_LAYOUT, xaxis_title="จำนวนครั้ง", yaxis_title="",
                margin=dict(t=20, b=20, r=50),
                yaxis=dict(autorange="reversed"),
            )
            st.plotly_chart(fig_brand, width="stretch")
        else:
            st.caption("ยังไม่มีข้อมูล brand mentions")

st.divider()

# ── Platform Mentions ────────────────────────────────────────────────────
st.subheader("🛒 Platform / Channel Mentions")
all_platforms = []
for call in done_calls:
    raw = call.get("platform_mentions") or ""
    try:
        platforms = json.loads(raw) if raw else []
        if isinstance(platforms, list):
            all_platforms.extend([p for p in platforms if isinstance(p, str) and p.strip()])
    except (json.JSONDecodeError, TypeError):
        pass

if all_platforms:
    plat_counts = Counter(all_platforms).most_common(15)
    plat_df = pd.DataFrame(plat_counts, columns=["Platform", "Count"])
    fig_plat = px.bar(plat_df, x="Count", y="Platform", orientation="h", text="Count")
    fig_plat.update_traces(
        marker_color="#f59e0b", textposition="outside",
        hovertemplate="<b>%{y}</b><br>พบ: %{x} ครั้ง<extra></extra>",
    )
    fig_plat.update_layout(
        **_CHART_LAYOUT, xaxis_title="จำนวนครั้ง", yaxis_title="",
        margin=dict(t=20, b=20, r=50),
        yaxis=dict(autorange="reversed"), height=300,
    )
    st.plotly_chart(fig_plat, width="stretch")
else:
    st.caption("ยังไม่มีข้อมูล platform mentions — re-process ไฟล์เสียงเพื่อดูผล")

with anom_col:
    st.subheader("⚠️ Anomaly Detection")
    anom_calls = [c for c in done_calls if c.get("anomaly_detected")]
    normal_count = total - len(anom_calls)

    a1, a2 = st.columns(2)
    with a1:
        st.markdown(metric_card(len(anom_calls), "Anomaly Calls ⚠️", "#ef4444"), unsafe_allow_html=True)
    with a2:
        st.markdown(metric_card(normal_count, "Normal Calls ✅", "#22c55e"), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    if anom_calls:
        for c in anom_calls:
            reason = c.get("anomaly_reason") or "ไม่ระบุสาเหตุ"
            severity = c.get("anomaly_severity") or ""
            sev_badge = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(severity, "⚠️")
            st.warning(f"{sev_badge} **{c['filename']}**  \n{reason}")
    else:
        st.success("ไม่พบความผิดปกติในการสนทนา")

st.divider()

# ── Top Issues ───────────────────────────────────────────────────────────
st.subheader("🔥 Top 3 Issues")
issue_calls = [c for c in done_calls if c.get("sentiment") == "negative" or c.get("anomaly_detected")]
if issue_calls:
    issue_topic_counts = Counter(
        c["topic"] for c in issue_calls if c.get("topic")
    ).most_common(3)
    if issue_topic_counts:
        issue_df = pd.DataFrame(issue_topic_counts, columns=["Issue / Topic", "Count"])
        fig_issues = px.bar(issue_df, x="Count", y="Issue / Topic", orientation="h", text="Count")
        fig_issues.update_traces(
            marker_color="#ef4444", textposition="outside",
            hovertemplate="<b>%{y}</b><br>จำนวน: %{x} สาย<extra></extra>",
        )
        fig_issues.update_layout(
            **_CHART_LAYOUT, xaxis_title="จำนวนสาย", yaxis_title="",
            margin=dict(t=20, b=20, r=50),
            yaxis=dict(autorange="reversed"), height=220,
        )
        st.plotly_chart(fig_issues, width="stretch")
        st.caption(f"จาก {len(issue_calls)} สาย (Negative sentiment + Anomaly)")
    else:
        st.caption("ไม่พบ topic ใน calls ที่มีปัญหา")
else:
    st.success("ไม่พบสายที่มีปัญหา (Negative/Anomaly) ในช่วงเวลาที่เลือก")

st.divider()

# ── Agent Performance ────────────────────────────────────────────────────
st.subheader("👤 Agent Performance")
st.caption(
    "🔗 สายในเคสเดียวกันถูกรวมเป็นแถวเดียว "
    "(คะแนน = ค่าเฉลี่ย, Next Action = จากสายล่าสุด) "
    "— เคสที่ปิดแล้วจะไม่แสดง Next Action"
)

# Collect per-call scored entries first, then group by case_id.
scored_calls = []
for call in done_calls:
    raw = call.get("agent_performance") or ""
    try:
        ap = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        ap = {}
    if ap.get("overall_score"):
        scored_calls.append({
            "call_id": call["id"],
            "case_id": call.get("case_id"),
            "filename": call["filename"],
            "phone": call.get("customer_phone") or "",
            "created_at": call.get("created_at") or "",
            "politeness": float(ap.get("politeness", 0)),
            "problem_solving": float(ap.get("problem_solving", 0)),
            "overall_score": float(ap.get("overall_score", 0)),
            "next_action": ap.get("next_action") or "—",
            "next_action_owner": ap.get("next_action_owner") or "ไม่มี",
        })

# Group calls that share a case_id; standalone calls (no case_id) stay solo.
case_groups: dict = defaultdict(list)
solo_calls: list = []
for entry in scored_calls:
    if entry["case_id"]:
        case_groups[entry["case_id"]].append(entry)
    else:
        solo_calls.append(entry)

# Cache case records (subject + status) to avoid repeated DB lookups
_case_cache: dict = {}

def _get_case(case_id: int) -> dict:
    if case_id not in _case_cache:
        cs = db.get_case_by_id(case_id)
        _case_cache[case_id] = cs or {"subject": f"เคส #{case_id}", "status": "open"}
    return _case_cache[case_id]

def _phone_prefix(phone: str) -> str:
    return f"\U0001F4DE {phone} · " if phone else ""  # \U0001F4DE = 📞

CLOSED_ACTION = "— เคสปิดแล้ว (ไม่มีเรื่องค้าง)"
CLOSED_OWNER = "—"

agent_rows = []
for case_id, entries in case_groups.items():
    # Latest call within case drives the "next action" (current outstanding step)
    entries_sorted = sorted(entries, key=lambda e: e["created_at"])
    latest = entries_sorted[-1]
    n = len(entries)
    # All calls in a case share the customer → pick the first non-empty phone
    phone = next((e["phone"] for e in entries if e["phone"]), "")
    case = _get_case(case_id)
    is_closed = case.get("status") == "closed"
    if n == 1:
        # Single-call case — filename + phone prefix
        label = f"{_phone_prefix(phone)}{latest['filename']}"
    else:
        label = f"{_phone_prefix(phone)}📂 เคส #{case_id} — {case['subject']} ({n} สาย)"
    agent_rows.append({
        "Label": label,
        "Politeness": f"{sum(e['politeness'] for e in entries) / n:.1f} / 5.0",
        "Problem Solving": f"{sum(e['problem_solving'] for e in entries) / n:.1f} / 5.0",
        "Next Action": CLOSED_ACTION if is_closed else latest["next_action"],
        "Owner": CLOSED_OWNER if is_closed else latest["next_action_owner"],
        "Score": round(sum(e["overall_score"] for e in entries) / n, 1),
        "_sort": entries_sorted[-1]["created_at"],
    })

for entry in solo_calls:
    agent_rows.append({
        "Label": f"{_phone_prefix(entry['phone'])}{entry['filename']}",
        "Politeness": f"{entry['politeness']:.1f} / 5.0",
        "Problem Solving": f"{entry['problem_solving']:.1f} / 5.0",
        "Next Action": entry["next_action"],
        "Owner": entry["next_action_owner"],
        "Score": entry["overall_score"],
        "_sort": entry["created_at"],
    })

if agent_rows:
    agent_rows.sort(key=lambda r: r["_sort"], reverse=True)
    for r in agent_rows:
        r.pop("_sort", None)
    ap_df = pd.DataFrame(agent_rows)
    avg_score = ap_df["Score"].mean()

    ag1, ag2, ag3 = st.columns(3)
    with ag1:
        st.markdown(metric_card(f"{avg_score:.1f}", "Avg Agent Score / 10"), unsafe_allow_html=True)
    with ag2:
        best = ap_df.loc[ap_df["Score"].idxmax(), "Label"]
        st.markdown(
            f'<div class="metric-card"><div class="metric-value" style="font-size:0.9rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%" title="{best}">{best}</div>'
            f'<div class="metric-label">Best 🏆</div></div>',
            unsafe_allow_html=True,
        )
    with ag3:
        worst = ap_df.loc[ap_df["Score"].idxmin(), "Label"]
        st.markdown(
            f'<div class="metric-card"><div class="metric-value" style="font-size:0.9rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%" title="{worst}">{worst}</div>'
            f'<div class="metric-label">Needs Improvement 📋</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    st.dataframe(
        ap_df,
        width="stretch",
        hide_index=True,
        column_config={
            "Label": st.column_config.TextColumn("สาย / เคส", width="large"),
            "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=10, format="%.1f / 10"),
            "Next Action": st.column_config.TextColumn("Next Action 📌", width="large"),
            "Owner": st.column_config.TextColumn("ผู้รับผิดชอบ 👤", width="medium"),
        },
    )
else:
    st.caption("ยังไม่มีข้อมูล Agent Performance — re-process ไฟล์เสียงเพื่อดูผล")

st.divider()

# ── Case Stats ───────────────────────────────────────────────────────────
st.subheader("📂 Case Management")

case_counts = db.get_case_counts()
all_cases = db.get_all_cases()

cs_col1, cs_col2, cs_col3, cs_col4 = st.columns(4)
with cs_col1:
    st.markdown(metric_card(case_counts["total"], "Total Cases"), unsafe_allow_html=True)
with cs_col2:
    st.markdown(metric_card(case_counts["open"], "🟢 เปิด (Open)", "#22c55e"), unsafe_allow_html=True)
with cs_col3:
    st.markdown(metric_card(case_counts["follow_up"], "🟡 ติดตาม (Follow-up)", "#eab308"), unsafe_allow_html=True)
with cs_col4:
    st.markdown(metric_card(case_counts["closed"], "🔴 ปิด (Closed)", "#ef4444"), unsafe_allow_html=True)

if all_cases:
    st.markdown("<br>", unsafe_allow_html=True)
    case_rows = []
    _case_badge = {"open": "🟢 เปิด", "follow_up": "🟡 ติดตาม", "closed": "🔴 ปิด"}
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
            "Updated": cs.get("updated_at", "")[:10],
        })
    cases_df = pd.DataFrame(case_rows)
    st.dataframe(
        cases_df,
        width="stretch",
        hide_index=True,
        column_config={
            "Subject": st.column_config.TextColumn(width="large"),
            "Customer": st.column_config.TextColumn(width="medium"),
        },
    )
else:
    st.caption("ยังไม่มีเคสในระบบ — เคสจะถูกสร้างอัตโนมัติหลัง process สาย")

st.divider()

# ── Call summaries table ─────────────────────────────────────────────────
st.subheader("Call Summaries")

search_term = st.text_input("🔍 Filter by filename or topic", "")
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
display_df["anomaly_detected"] = display_df["anomaly_detected"].map(lambda v: "⚠️ Yes" if v else "✅ No")
display_df["created_at"] = pd.to_datetime(display_df["created_at"]).dt.strftime("%Y-%m-%d %H:%M:%S")
display_df.columns = ["Filename", "Sentiment", "Topic", "Keywords", "Anomaly", "Summary", "Created (UTC)"]

st.dataframe(
    display_df,
    width="stretch",
    hide_index=True,
    column_config={
        "Summary": st.column_config.TextColumn(width="large"),
        "Filename": st.column_config.TextColumn(width="medium"),
        "Keywords": st.column_config.TextColumn(width="medium"),
    },
)

st.markdown(f"<br><small style='color:#6b7280'>Showing {len(filtered_df)} of {total} calls</small>", unsafe_allow_html=True)
