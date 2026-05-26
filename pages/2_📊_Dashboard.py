import json
import math
from collections import Counter, defaultdict

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="SmartVoice — Dashboard", page_icon="📊", layout="wide")

from smartvoice import db
from smartvoice.file_manager import extract_agent_code_from_filename
from smartvoice.ollama_client import sanitize_evidence, sanitize_next_action
from smartvoice.ui_helpers import init_page, metric_card, sentiment_emoji

init_page()

# Page-scoped CSS — ขยาย caption / small text ให้อ่านง่ายขึ้น (เฉพาะหน้า Dashboard)
st.markdown(
    """
    <style>
      /* caption (st.caption) — ใหญ่และคอนทราสต์สูงขึ้น */
      div[data-testid="stCaptionContainer"],
      div[data-testid="stCaptionContainer"] p,
      div[data-testid="stCaptionContainer"] small {
          font-size: 0.95rem !important;
          font-weight: 500 !important;
          color: #cbd5e1 !important;
          line-height: 1.55 !important;
      }
      /* subheader (st.subheader) — เด่นขึ้นเพื่อแยก section */
      div[data-testid="stHeadingWithActionElements"] h3 {
          font-size: 1.45rem !important;
          font-weight: 700 !important;
      }
      /* expander label (Filters) — อ่านง่ายขึ้น */
      details[data-testid="stExpander"] summary p {
          font-size: 1.05rem !important;
          font-weight: 600 !important;
      }
      /* dataframe header + cell — เพิ่ม readability */
      div[data-testid="stDataFrame"] [role="columnheader"] {
          font-size: 0.95rem !important;
          font-weight: 700 !important;
      }
      div[data-testid="stDataFrame"] [role="gridcell"] {
          font-size: 0.95rem !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────
# PAGE: DASHBOARD — Analytics
# ─────────────────────────────────────────
st.title("📊 Dashboard — Analytics")

# ── Scale-friendly loading: cap rows by user-selected limit ─────────────
# ทางบริษัทมีไฟล์เสียงหลักหมื่น — โหลดทั้งตารางทุกครั้งจะหน่วงระบบ
_LIMIT_OPTIONS = {
    "100 สายล่าสุด": 100,
    "500 สายล่าสุด": 500,
    "1,000 สายล่าสุด": 1000,
    "5,000 สายล่าสุด": 5000,
    "ทั้งหมด (อาจช้าเมื่อข้อมูลเยอะ)": None,
}

total_in_db = db.count_done_calls()

if total_in_db == 0:
    st.info("No completed calls yet. Upload and process audio files from the Admin page.")
    st.stop()

# Default — analytics page needs enough data for chart signal to be meaningful.
# Under 1K rows just load everything; above that, start at 1K latest (chart
# distributions remain accurate while keeping initial paint under ~1s).
_default_limit_label = (
    "ทั้งหมด (อาจช้าเมื่อข้อมูลเยอะ)" if total_in_db <= 1000 else "1,000 สายล่าสุด"
)
if "dashboard_load_limit" not in st.session_state:
    st.session_state["dashboard_load_limit"] = _default_limit_label

_current_limit = _LIMIT_OPTIONS.get(st.session_state["dashboard_load_limit"], 500)
done_calls = db.get_done_calls(limit=_current_limit)

if not done_calls:
    st.info("No completed calls match the selected scope.")
    st.stop()

df = pd.DataFrame(done_calls)
df["created_at"] = pd.to_datetime(df["created_at"])
loaded_count = len(df)

# ── Filters (เปิดโดย default เพื่อให้ผู้ใช้เห็นวิธีลดข้อมูลได้ทันที) ────────────
with st.expander("🔍 Filters", expanded=True):
    f_col1, f_col2, f_col3, f_col4 = st.columns([1, 1, 1, 1.2])
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
    with f_col4:
        st.selectbox(
            "จำนวนสายที่โหลด",
            list(_LIMIT_OPTIONS.keys()),
            key="dashboard_load_limit",
            help=f"ระบบมีทั้งหมด {total_in_db:,} สาย — เลือกจำนวนที่ต้องการโหลดเพื่อวิเคราะห์",
        )

# Info banner — ให้ผู้ใช้รู้ scope ที่กำลังดูอยู่
if _current_limit is not None and loaded_count < total_in_db:
    st.info(
        f"📊 กำลังวิเคราะห์ **{loaded_count:,}** สายล่าสุด จากทั้งหมด "
        f"**{total_in_db:,}** สายในระบบ — ปรับ *'จำนวนสายที่โหลด'* "
        f"ใน Filter เพื่อโหลดเพิ่มหรือลดลง"
    )
else:
    st.success(f"✅ กำลังวิเคราะห์ทั้งหมด **{loaded_count:,}** สายในระบบ")

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
    # ปรับให้ axis ticks, axis titles, legend อ่านง่ายขึ้น (เดิม Plotly default = 12)
    font=dict(color="#e5e7eb", size=15, weight=500),
    showlegend=False,
    bargap=0.45,
)

# เลขบนแท่ง (text labels) — ใหญ่ + หนาให้เห็นชัดบนพื้นมืด
_BAR_TEXTFONT = dict(size=16, color="#f8fafc", weight=700)

# Omazz brand palettes — โทนน้ำเงิน sky/navy บนพื้นดำตาม brand identity
# (แท่งค่าน้อยสีอ่อน, ค่ามากสีเข้ม → สื่อลำดับความสำคัญทันที)
_SCALE_BRAND = [[0, "#bae6fd"], [1, "#0369a1"]]    # sky → ocean (โลโก้ Omazz)
_SCALE_NAVY = [[0, "#93c5fd"], [1, "#1e3a8a"]]     # ฟ้าอ่อน → navy (premium dark)
_SCALE_TEAL = [[0, "#99f6e4"], [1, "#0e7490"]]     # mint → teal/cyan
_SCALE_STEEL = [[0, "#cbd5e1"], [1, "#475569"]]    # slate (เข้ากับพื้นดำ)
_SCALE_RED = [[0, "#fecaca"], [1, "#b91c1c"]]      # warning (เฉพาะ problem/issue)
_BAR_CORNER = 8

with chart_col1:
    st.subheader("Sentiment Distribution")
    sentiment_counts = df["sentiment"].value_counts().reset_index()
    sentiment_counts.columns = ["Sentiment", "Count"]
    # Sentiment: เก็บความหมาย semantic ไว้ แต่ปรับโทนให้เข้ากับพื้น dark + brand
    # — positive=เขียวมิ้นต์ (อ่านง่ายบนพื้นดำ), neutral=สเลทเทาฟ้า (เข้า brand), negative=แดงนวล
    color_map = {"positive": "#34d399", "neutral": "#94a3b8", "negative": "#f87171"}
    fig_sentiment = px.bar(
        sentiment_counts, x="Sentiment", y="Count",
        color="Sentiment", color_discrete_map=color_map, text="Count",
    )
    fig_sentiment.update_traces(
        textposition="outside",
        textfont=_BAR_TEXTFONT,
        marker=dict(cornerradius=_BAR_CORNER, line=dict(width=0)),
        hovertemplate="<b>%{x}</b><br>จำนวน: %{y} สาย<extra></extra>",
    )
    fig_sentiment.update_layout(
        **_CHART_LAYOUT, xaxis_title="", yaxis_title="จำนวนสาย",
        margin=dict(t=30, b=10),
        yaxis=dict(gridcolor="rgba(148,163,184,0.15)", zeroline=False),
        xaxis=dict(showgrid=False),
    )
    st.plotly_chart(fig_sentiment, width="stretch")

with chart_col2:
    st.subheader("Topic / Intent Distribution")
    topic_series = df["topic"].replace("", pd.NA).dropna()
    topic_counts = topic_series.value_counts().reset_index()
    topic_counts.columns = ["Topic", "Count"]
    fig_topic = px.bar(
        topic_counts, x="Count", y="Topic", orientation="h", text="Count",
        color="Count", color_continuous_scale=_SCALE_BRAND,
    )
    fig_topic.update_traces(
        textposition="outside",
        textfont=_BAR_TEXTFONT,
        marker=dict(cornerradius=_BAR_CORNER, line=dict(width=0)),
        hovertemplate="<b>%{y}</b><br>จำนวน: %{x} สาย<extra></extra>",
    )
    fig_topic.update_layout(
        **_CHART_LAYOUT, xaxis_title="จำนวนสาย", yaxis_title="",
        margin=dict(t=20, b=20, r=60), yaxis=dict(autorange="reversed"),
        coloraxis_showscale=False,
        xaxis=dict(gridcolor="rgba(148,163,184,0.15)", zeroline=False),
    )
    st.plotly_chart(fig_topic, width="stretch")

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
            fig_detail = px.bar(
                detail_counts, x="Count", y="Detail", orientation="h", text="Count",
                color="Count", color_continuous_scale=_SCALE_RED,
            )
            fig_detail.update_traces(
                textposition="outside",
                textfont=_BAR_TEXTFONT,
                marker=dict(cornerradius=_BAR_CORNER, line=dict(width=0)),
                hovertemplate="<b>%{y}</b><br>จำนวน: %{x} สาย<extra></extra>",
            )
            fig_detail.update_layout(
                **_CHART_LAYOUT, xaxis_title="จำนวนสาย", yaxis_title="",
                margin=dict(t=10, b=20, r=60), yaxis=dict(autorange="reversed"),
                coloraxis_showscale=False,
                xaxis=dict(gridcolor="rgba(148,163,184,0.15)", zeroline=False),
                height=max(200, 40 * len(detail_counts) + 80),
            )
            st.plotly_chart(fig_detail, width="stretch")

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
            fig_kw = px.bar(
                kw_df, x="Count", y="Keyword", orientation="h", text="Count",
                color="Count", color_continuous_scale=_SCALE_NAVY,
            )
            fig_kw.update_traces(
                textposition="outside",
                textfont=_BAR_TEXTFONT,
                marker=dict(cornerradius=_BAR_CORNER, line=dict(width=0)),
                hovertemplate="<b>%{y}</b><br>พบ: %{x} ครั้ง<extra></extra>",
            )
            fig_kw.update_layout(
                **_CHART_LAYOUT, xaxis_title="จำนวนครั้ง", yaxis_title="",
                margin=dict(t=20, b=20, r=20),
                yaxis=dict(autorange="reversed"),
                xaxis=dict(range=[0, kw_max * 1.25],
                           gridcolor="rgba(148,163,184,0.15)", zeroline=False),
                coloraxis_showscale=False,
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
            brand_max = brand_df["Count"].max()
            fig_brand = px.bar(
                brand_df, x="Count", y="Brand", orientation="h", text="Count",
                color="Count", color_continuous_scale=_SCALE_TEAL,
            )
            fig_brand.update_traces(
                textposition="outside",
                textfont=_BAR_TEXTFONT,
                marker=dict(cornerradius=_BAR_CORNER, line=dict(width=0)),
                hovertemplate="<b>%{y}</b><br>พบ: %{x} ครั้ง<extra></extra>",
            )
            fig_brand.update_layout(
                **_CHART_LAYOUT, xaxis_title="จำนวนครั้ง", yaxis_title="",
                margin=dict(t=20, b=20, r=50),
                yaxis=dict(autorange="reversed"),
                xaxis=dict(range=[0, brand_max * 1.25],
                           gridcolor="rgba(148,163,184,0.15)", zeroline=False),
                coloraxis_showscale=False,
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
    plat_max = plat_df["Count"].max()
    fig_plat = px.bar(
        plat_df, x="Count", y="Platform", orientation="h", text="Count",
        color="Count", color_continuous_scale=_SCALE_STEEL,
    )
    fig_plat.update_traces(
        textposition="outside",
        textfont=_BAR_TEXTFONT,
        marker=dict(cornerradius=_BAR_CORNER, line=dict(width=0)),
        hovertemplate="<b>%{y}</b><br>พบ: %{x} ครั้ง<extra></extra>",
    )
    fig_plat.update_layout(
        **_CHART_LAYOUT, xaxis_title="จำนวนครั้ง", yaxis_title="",
        margin=dict(t=20, b=20, r=50),
        yaxis=dict(autorange="reversed"), height=max(220, 60 + 38 * len(plat_df)),
        xaxis=dict(range=[0, plat_max * 1.25],
                   gridcolor="rgba(148,163,184,0.15)", zeroline=False),
        coloraxis_showscale=False,
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
        issue_max = issue_df["Count"].max()
        fig_issues = px.bar(
            issue_df, x="Count", y="Issue / Topic", orientation="h", text="Count",
            color="Count", color_continuous_scale=_SCALE_RED,
        )
        fig_issues.update_traces(
            textposition="outside",
            textfont=_BAR_TEXTFONT,
            marker=dict(cornerradius=_BAR_CORNER, line=dict(width=0)),
            hovertemplate="<b>%{y}</b><br>จำนวน: %{x} สาย<extra></extra>",
        )
        fig_issues.update_layout(
            **_CHART_LAYOUT, xaxis_title="จำนวนสาย", yaxis_title="",
            margin=dict(t=20, b=20, r=50),
            yaxis=dict(autorange="reversed"), height=max(200, 60 + 50 * len(issue_df)),
            xaxis=dict(range=[0, issue_max * 1.25],
                       gridcolor="rgba(148,163,184,0.15)", zeroline=False),
            coloraxis_showscale=False,
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

def _short_evidence(value: str, transcript: str = "") -> str:
    text = " ".join(str(value or "").split())
    cleaned = sanitize_evidence(text, transcript)
    return cleaned or "—"

def _score_value(value) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0.0
    return max(0.0, min(5.0, score))

# Collect per-call scored entries first, then group by case_id.
scored_calls = []
for call in done_calls:
    raw = call.get("agent_performance") or ""
    try:
        ap = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        ap = {}
    if ap.get("overall_score"):
        next_action, next_action_owner = sanitize_next_action(
            ap.get("next_action") or "—",
            ap.get("next_action_owner") or "ไม่มี",
            call.get("transcript") or "",
        )
        politeness = _score_value(ap.get("politeness", 0))
        problem_solving = _score_value(ap.get("problem_solving", 0))
        scored_calls.append({
            "call_id": call["id"],
            "case_id": call.get("case_id"),
            "filename": call["filename"],
            "phone": call.get("customer_phone") or "",
            "created_at": call.get("created_at") or "",
            "agent_code": extract_agent_code_from_filename(call["filename"]) or "",
            "politeness": politeness,
            "problem_solving": problem_solving,
            "overall_score": politeness + problem_solving,
            "politeness_evidence": _short_evidence(ap.get("politeness_evidence", ""), call.get("transcript") or ""),
            "problem_solving_evidence": _short_evidence(ap.get("problem_solving_evidence", ""), call.get("transcript") or ""),
            "next_action": next_action,
            "next_action_owner": next_action_owner,
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
    evidence_prefix = f"เฉลี่ยจาก {n} สาย; ล่าสุด: " if n > 1 else ""
    case_agent_codes = sorted({e["agent_code"] for e in entries if e["agent_code"]})
    agent_rows.append({
        "Label": label,
        "Agent": ", ".join(case_agent_codes) if case_agent_codes else "—",
        "Politeness": f"{sum(e['politeness'] for e in entries) / n:.1f} / 5.0",
        "Politeness Evidence": f"{evidence_prefix}{latest['politeness_evidence']}",
        "Problem Solving": f"{sum(e['problem_solving'] for e in entries) / n:.1f} / 5.0",
        "Problem Solving Evidence": f"{evidence_prefix}{latest['problem_solving_evidence']}",
        "Next Action": CLOSED_ACTION if is_closed else latest["next_action"],
        "Owner": CLOSED_OWNER if is_closed else latest["next_action_owner"],
        "Score": round(sum(e["overall_score"] for e in entries) / n, 1),
        "_agent_codes": case_agent_codes,
        "_sort": entries_sorted[-1]["created_at"],
    })

for entry in solo_calls:
    agent_rows.append({
        "Label": f"{_phone_prefix(entry['phone'])}{entry['filename']}",
        "Agent": entry["agent_code"] or "—",
        "Politeness": f"{entry['politeness']:.1f} / 5.0",
        "Politeness Evidence": entry["politeness_evidence"],
        "Problem Solving": f"{entry['problem_solving']:.1f} / 5.0",
        "Problem Solving Evidence": entry["problem_solving_evidence"],
        "Next Action": entry["next_action"],
        "Owner": entry["next_action_owner"],
        "Score": entry["overall_score"],
        "_agent_codes": [entry["agent_code"]] if entry["agent_code"] else [],
        "_sort": entry["created_at"],
    })

if agent_rows:
    agent_rows.sort(key=lambda r: r["_sort"], reverse=True)
    for r in agent_rows:
        r.pop("_sort", None)
    ap_df_full = pd.DataFrame(agent_rows)
    avg_score = ap_df_full["Score"].mean()

    ag1, ag2, ag3 = st.columns(3)
    with ag1:
        st.markdown(metric_card(f"{avg_score:.1f}", "Avg Agent Score / 10"), unsafe_allow_html=True)
    with ag2:
        best = ap_df_full.loc[ap_df_full["Score"].idxmax(), "Label"]
        st.markdown(
            f'<div class="metric-card"><div class="metric-value" style="font-size:0.9rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%" title="{best}">{best}</div>'
            f'<div class="metric-label">Best 🏆</div></div>',
            unsafe_allow_html=True,
        )
    with ag3:
        worst = ap_df_full.loc[ap_df_full["Score"].idxmin(), "Label"]
        st.markdown(
            f'<div class="metric-card"><div class="metric-value" style="font-size:0.9rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%" title="{worst}">{worst}</div>'
            f'<div class="metric-label">Needs Improvement 📋</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Collect available agent codes (sorted) for the filter dropdown
    _all_agent_codes = sorted({
        code
        for codes in ap_df_full["_agent_codes"]
        for code in codes
        if code
    })

    # ── Search + pagination — กันแถวเยอะเกินเมื่อโหลดสายจำนวนมาก ────────────
    ap_search_col, ap_agent_col, ap_score_col, ap_size_col = st.columns([2, 1.2, 1.4, 1])
    with ap_search_col:
        ap_search = st.text_input(
            "🔍 ค้นหา (เบอร์ / ชื่อไฟล์ / Subject / Next Action)",
            key="agent_perf_search",
            placeholder="เช่น 081-999-9336, แจ้งปัญหา, ติดตาม",
        )
    with ap_agent_col:
        ap_agent_filter = st.selectbox(
            "Agent",
            ["ทั้งหมด"] + _all_agent_codes,
            key="agent_perf_agent",
            help="กรองตามรหัส Agent (สกัดจาก suffix ของชื่อไฟล์)",
        )
    with ap_score_col:
        ap_score_filter = st.selectbox(
            "กรองตามคะแนน",
            ["ทั้งหมด", "< 6 (ต้องปรับปรุง)", "6–7.9 (พอใช้)", "≥ 8 (ดี)"],
            key="agent_perf_score",
        )
    with ap_size_col:
        ap_page_size = st.selectbox(
            "แถวต่อหน้า",
            [10, 25, 50, 100],
            index=1,
            key="agent_perf_page_size",
        )

    ap_df = ap_df_full.copy()
    if ap_search:
        s = ap_search.strip()
        mask = (
            ap_df["Label"].str.contains(s, case=False, na=False)
            | ap_df["Next Action"].astype(str).str.contains(s, case=False, na=False)
        )
        ap_df = ap_df[mask]
    if ap_agent_filter != "ทั้งหมด":
        # Case rows may aggregate multiple agents — keep if the picked code
        # handled at least one call in the case
        ap_df = ap_df[ap_df["_agent_codes"].apply(lambda codes: ap_agent_filter in codes)]
    if ap_score_filter == "< 6 (ต้องปรับปรุง)":
        ap_df = ap_df[ap_df["Score"] < 6]
    elif ap_score_filter == "6–7.9 (พอใช้)":
        ap_df = ap_df[(ap_df["Score"] >= 6) & (ap_df["Score"] < 8)]
    elif ap_score_filter == "≥ 8 (ดี)":
        ap_df = ap_df[ap_df["Score"] >= 8]

    ap_total = len(ap_df)
    ap_n_pages = max(1, math.ceil(ap_total / ap_page_size)) if ap_total else 1
    if st.session_state.get("agent_perf_page", 1) > ap_n_pages:
        st.session_state["agent_perf_page"] = 1

    pg_col, info_col = st.columns([1, 3])
    with pg_col:
        ap_page = st.number_input(
            f"หน้า (รวม {ap_n_pages:,} หน้า)",
            min_value=1,
            max_value=ap_n_pages,
            step=1,
            key="agent_perf_page",
        )
    ap_start = (ap_page - 1) * ap_page_size
    ap_end = ap_start + ap_page_size
    with info_col:
        if ap_total == 0:
            st.markdown(
                "<div style='padding-top:1.95rem;color:#fbbf24;font-size:0.95rem;font-weight:500'>"
                "ไม่พบแถวที่ตรงกับเงื่อนไข — ลองล้าง search หรือเปลี่ยน 'กรองตามคะแนน'</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<div style='padding-top:1.95rem;color:#cbd5e1;font-size:0.95rem;font-weight:500'>"
                f"แถว <b style='color:#38bdf8'>{ap_start + 1:,}–{min(ap_end, ap_total):,}</b> "
                f"จาก <b style='color:#38bdf8'>{ap_total:,}</b> รายการ "
                f"(ทั้งหมด <b style='color:#38bdf8'>{len(ap_df_full):,}</b>)</div>",
                unsafe_allow_html=True,
            )

    if ap_total > 0:
        # Drop the hidden filter column before rendering — used only for
        # selecting rows by agent code above
        _display_df = ap_df.iloc[ap_start:ap_end].drop(columns=["_agent_codes"], errors="ignore")
        st.dataframe(
            _display_df,
            width="stretch",
            hide_index=True,
            column_config={
                "Label": st.column_config.TextColumn("สาย / เคส", width="large"),
                "Agent": st.column_config.TextColumn("Agent", width="small"),
                "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=10, format="%.1f / 10"),
                "Politeness Evidence": st.column_config.TextColumn("หลักฐาน Politeness", width="large"),
                "Problem Solving Evidence": st.column_config.TextColumn("หลักฐาน Problem Solving", width="large"),
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

cs_col1, cs_col2, cs_col3, cs_col4 = st.columns(4)
with cs_col1:
    st.markdown(metric_card(case_counts["total"], "Total Cases"), unsafe_allow_html=True)
with cs_col2:
    st.markdown(metric_card(case_counts["open"], "🟢 เปิด (Open)", "#22c55e"), unsafe_allow_html=True)
with cs_col3:
    st.markdown(metric_card(case_counts["follow_up"], "🟡 ติดตาม (Follow-up)", "#eab308"), unsafe_allow_html=True)
with cs_col4:
    st.markdown(metric_card(case_counts["closed"], "🔴 ปิด (Closed)", "#ef4444"), unsafe_allow_html=True)

if case_counts["total"] > 0:
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Filter row — push status/search down to SQL ─────────────────────
    _STATUS_OPTIONS = {
        "ทั้งหมด": None,
        "🟢 เปิด (Open)": "open",
        "🟡 ติดตาม (Follow-up)": "follow_up",
        "🔴 ปิด (Closed)": "closed",
    }
    cf_status_col, cf_search_col, cf_size_col = st.columns([1.2, 2.2, 1])
    with cf_status_col:
        cs_status_label = st.selectbox(
            "Status",
            list(_STATUS_OPTIONS.keys()),
            key="case_status_filter",
        )
    with cf_search_col:
        cs_search = st.text_input(
            "🔍 ค้นหา (Subject / ชื่อลูกค้า / เบอร์)",
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
    cs_total_filtered = db.count_cases(status=cs_status, search=cs_search_clean)
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
    )

    if all_cases:
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
