"""Shared pieces of the Dashboard pages — CSS, chart styling and the call filters.

The Dashboard used to be one 1,000-line page; it is split into one page per
topic (ภาพรวม, คีย์เวิร์ด, ความผิดปกติ, ผลงาน Agent, รายการสาย). Every page
calls `load_filtered_calls()`, so they all show the same filter bar and the
filters picked on one page carry over to the next.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pandas as pd
import plotly.express as px
import streamlit as st

from smartvoice import audit, dashboard_report, db, labels
from smartvoice.dashboard_report import count_list_field  # noqa: F401 — used by the Insights page
from smartvoice.ui_helpers import get_current_user

# ── Page CSS ─────────────────────────────────────────────────────────────

_DASHBOARD_CSS = """
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
  /* expander label (ตัวกรอง) — อ่านง่ายขึ้น */
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
"""


def inject_dashboard_css() -> None:
    st.markdown(_DASHBOARD_CSS, unsafe_allow_html=True)


# ── Chart styling ────────────────────────────────────────────────────────

CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    # ปรับให้ axis ticks, axis titles, legend อ่านง่ายขึ้น (เดิม Plotly default = 12)
    font=dict(color="#e5e7eb", size=15, weight=500),
    showlegend=False,
    bargap=0.45,
)
# เลขบนแท่ง (text labels) — ใหญ่ + หนาให้เห็นชัดบนพื้นมืด
BAR_TEXTFONT = dict(size=16, color="#f8fafc", weight=700)
BAR_CORNER = 8
GRID_COLOR = "rgba(148,163,184,0.15)"

# Omazz brand palettes — โทนน้ำเงิน sky/navy บนพื้นดำตาม brand identity
# (แท่งค่าน้อยสีอ่อน, ค่ามากสีเข้ม → สื่อลำดับความสำคัญทันที)
SCALE_BRAND = [[0, "#bae6fd"], [1, "#0369a1"]]    # sky → ocean (โลโก้ Omazz)
SCALE_NAVY = [[0, "#93c5fd"], [1, "#1e3a8a"]]     # ฟ้าอ่อน → navy (premium dark)
SCALE_TEAL = [[0, "#99f6e4"], [1, "#0e7490"]]     # mint → teal/cyan
SCALE_STEEL = [[0, "#cbd5e1"], [1, "#475569"]]    # slate (เข้ากับพื้นดำ)
SCALE_RED = [[0, "#fecaca"], [1, "#b91c1c"]]      # warning (เฉพาะ problem/issue)

# Sentiment keeps its meaning: เขียวมิ้นต์ / สเลทเทาฟ้า / แดงนวล
SENTIMENT_COLORS = {"positive": "#34d399", "neutral": "#94a3b8", "negative": "#f87171"}


def hbar(
    data: pd.DataFrame,
    label: str,
    scale: list,
    hover_unit: str = "จำนวน: %{x} สาย",
    xaxis_title: str = "จำนวนสาย",
    margin: dict | None = None,
    height: int | None = None,
    headroom: bool = True,
):
    """Horizontal bar chart of `data[label]` vs `data["Count"]` in the house style.

    `headroom` widens the x-axis by 25% so the value printed outside the
    longest bar is not clipped.
    """
    fig = px.bar(
        data, x="Count", y=label, orientation="h", text="Count",
        color="Count", color_continuous_scale=scale,
    )
    fig.update_traces(
        textposition="outside",
        textfont=BAR_TEXTFONT,
        marker=dict(cornerradius=BAR_CORNER, line=dict(width=0)),
        hovertemplate=f"<b>%{{y}}</b><br>{hover_unit}<extra></extra>",
    )
    xaxis = dict(gridcolor=GRID_COLOR, zeroline=False)
    if not data.empty and data["Count"].max() <= 10:
        xaxis["dtick"] = 1  # counts are whole numbers — no "0.5 สาย" ticks
    if headroom and not data.empty:
        xaxis["range"] = [0, data["Count"].max() * 1.25]
    layout = dict(
        **CHART_LAYOUT,
        xaxis_title=xaxis_title,
        yaxis_title="",
        margin=margin or dict(t=20, b=20, r=50),
        yaxis=dict(autorange="reversed"),
        xaxis=xaxis,
        coloraxis_showscale=False,
    )
    if height:
        layout["height"] = height
    fig.update_layout(**layout)
    return fig


# Names saved by older prompts are grouped under today's canonical spelling,
# so "Lotus", "โลตัส" and "Lotus/โลตัส" are one bar, not three.
# ── Shared filters ───────────────────────────────────────────────────────

# ทางบริษัทมีไฟล์เสียงหลักหมื่น — โหลดทั้งตารางทุกครั้งจะหน่วงระบบ
LIMIT_OPTIONS = {
    "100 สายล่าสุด": 100,
    "500 สายล่าสุด": 500,
    "1,000 สายล่าสุด": 1000,
    "5,000 สายล่าสุด": 5000,
    "ทั้งหมด (อาจช้าเมื่อข้อมูลเยอะ)": None,
}
_ALL_LIMIT = "ทั้งหมด (อาจช้าเมื่อข้อมูลเยอะ)"
ALL = "All"
SENTIMENT_OPTIONS = [ALL, "positive", "neutral", "negative"]

KEY_LIMIT = "dashboard_load_limit"
KEY_DATES = "dash_date_range"
KEY_INTENT = "dash_intent"
KEY_SENTIMENT = "dash_sentiment"
FILTER_KEYS = (KEY_LIMIT, KEY_DATES, KEY_INTENT, KEY_SENTIMENT)


def _kept(key: str) -> str:
    return f"_keep_{key}"


def restore_filters() -> None:
    """Bring back the filters picked on another Dashboard page.

    Each page draws its own copy of the filter widgets, and Streamlit treats
    them as different widgets: the value left in session state by the previous
    page is *not* picked up by the new one, which silently falls back to its
    first option ("100 สายล่าสุด"). So the real value lives in a plain
    `_keep_*` key and is written back — every run, not only when missing —
    before the widgets are drawn. `remember_filters` runs as each widget's
    on_change, so a change is saved before this restore sees it.
    """
    for key in FILTER_KEYS:
        if _kept(key) in st.session_state:
            st.session_state[key] = st.session_state[_kept(key)]


def remember_filters() -> None:
    for key in FILTER_KEYS:
        if key in st.session_state:
            st.session_state[_kept(key)] = st.session_state[key]


def clamp_date_range(value, min_date: date, max_date: date) -> tuple:
    """Keep a saved (start, end) inside the dates of the loaded calls.

    `st.date_input` raises when its value falls outside min/max, which happens
    when the load limit shrinks after a range was picked. A one-date tuple
    (the user has clicked only the start so far) is kept as-is if it fits.
    """
    if isinstance(value, (list, tuple)) and 1 <= len(value) <= 2:
        picked = [d for d in value if isinstance(d, date)]
        if len(picked) == len(value) and all(min_date <= d <= max_date for d in picked):
            return tuple(picked)
    return (min_date, max_date)


def default_limit_label(total_in_db: int) -> str:
    # Under 1K rows just load everything; above that, start at 1K latest
    # (chart distributions remain accurate while keeping first paint ~1s).
    return _ALL_LIMIT if total_in_db <= 1000 else "1,000 สายล่าสุด"


def _filter_summary() -> str:
    parts = [st.session_state.get(KEY_LIMIT, "")]
    dates = st.session_state.get(KEY_DATES)
    if isinstance(dates, (list, tuple)) and len(dates) == 2:
        parts.append(f"{dates[0]:%d/%m/%Y} – {dates[1]:%d/%m/%Y}")
    intent = st.session_state.get(KEY_INTENT, ALL)
    parts.append("ทุกหัวข้อ" if intent == ALL else intent)
    sentiment = st.session_state.get(KEY_SENTIMENT, ALL)
    parts.append("ทุกอารมณ์ลูกค้า" if sentiment == ALL else f"ลูกค้า{labels.sentiment(sentiment)}")
    return "  •  ".join(p for p in parts if p)


def _option_label(value: str) -> str:
    return "ทั้งหมด" if value == ALL else value


def _sentiment_option(value: str) -> str:
    return "ทั้งหมด" if value == ALL else labels.sentiment(value)


def load_filtered_calls() -> tuple[pd.DataFrame, int]:
    """Draw the filter bar and return (filtered calls, calls in the database).

    Stops the page with a message when there is nothing to show.
    """
    restore_filters()

    total_in_db = db.count_done_calls()
    if total_in_db == 0:
        st.info("ยังไม่มีสายที่ประมวลผลเสร็จ — อัปโหลดและประมวลผลไฟล์เสียงที่เมนู อัปโหลดและประมวลผลเสียง ก่อน")
        st.stop()

    if st.session_state.get(KEY_LIMIT) not in LIMIT_OPTIONS:
        st.session_state[KEY_LIMIT] = default_limit_label(total_in_db)
    limit = LIMIT_OPTIONS[st.session_state[KEY_LIMIT]]

    done_calls = db.get_done_calls(limit=limit)
    if not done_calls:
        st.info("ไม่พบสายในขอบเขตที่เลือก")
        st.stop()

    df = pd.DataFrame(done_calls)
    df["created_at"] = pd.to_datetime(df["created_at"])
    loaded_count = len(df)

    min_date = df["created_at"].dt.date.min()
    max_date = df["created_at"].dt.date.max()
    st.session_state[KEY_DATES] = clamp_date_range(
        st.session_state.get(KEY_DATES), min_date, max_date
    )
    intent_options = [ALL] + sorted(df["topic"].dropna().unique().tolist())
    if st.session_state.get(KEY_INTENT) not in intent_options:
        st.session_state[KEY_INTENT] = ALL
    if st.session_state.get(KEY_SENTIMENT) not in SENTIMENT_OPTIONS:
        st.session_state[KEY_SENTIMENT] = ALL

    filter_col, export_col = st.columns([3, 1])
    with filter_col, st.expander(f"ตัวกรอง: {_filter_summary()}", expanded=False):
        f_col1, f_col2, f_col3, f_col4 = st.columns([1, 1, 1, 1.2])
        with f_col1:
            st.date_input(
                "ช่วงวันที่", min_value=min_date, max_value=max_date, key=KEY_DATES,
                on_change=remember_filters,
            )
        with f_col2:
            st.selectbox(
                "หัวข้อที่ลูกค้าโทรมา", intent_options, key=KEY_INTENT, format_func=_option_label,
                on_change=remember_filters,
            )
        with f_col3:
            st.selectbox(
                "อารมณ์ลูกค้า (Sentiment)", SENTIMENT_OPTIONS, key=KEY_SENTIMENT,
                format_func=_sentiment_option, on_change=remember_filters,
            )
        with f_col4:
            st.selectbox(
                "จำนวนสายที่โหลด",
                list(LIMIT_OPTIONS.keys()),
                key=KEY_LIMIT,
                on_change=remember_filters,
                help=f"ระบบมีทั้งหมด {total_in_db:,} สาย — เลือกจำนวนที่ต้องการโหลดเพื่อวิเคราะห์",
            )
        st.caption("ตัวกรองนี้ใช้ร่วมกันทุกหน้าในหมวด Dashboard")
    remember_filters()

    if limit is not None and loaded_count < total_in_db:
        st.caption(
            f"กำลังวิเคราะห์ {loaded_count:,} สายล่าสุด จากทั้งหมด {total_in_db:,} สาย "
            "— เปลี่ยนได้ที่ 'จำนวนสายที่โหลด' ในตัวกรอง"
        )

    date_range = st.session_state[KEY_DATES]
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start_date, end_date = date_range
        df = df[(df["created_at"].dt.date >= start_date) & (df["created_at"].dt.date <= end_date)]
    if st.session_state[KEY_INTENT] != ALL:
        df = df[df["topic"] == st.session_state[KEY_INTENT]]
    if st.session_state[KEY_SENTIMENT] != ALL:
        df = df[df["sentiment"] == st.session_state[KEY_SENTIMENT]]

    if df.empty:
        st.warning("ไม่พบข้อมูลที่ตรงกับตัวกรองที่เลือก")
        st.stop()
    with export_col:
        render_export_menu(df)
    return df, total_in_db


# ── Export ───────────────────────────────────────────────────────────────

def _logged_export(kind: str, build, calls: int, filter_text: str):
    """Wrap a file builder so the download is written to the audit trail.

    The builder runs only when the button is clicked (Streamlit's deferred
    download data), so pages don't pay for a PDF nobody asked for. The user is
    captured now because the click is served outside the page run.
    """
    user, role = get_current_user()

    def run():
        data = build()
        audit.record(
            action=audit.EXPORT, entity=audit.ENTITY_REPORT, entity_label=kind,
            actor=user, actor_role=role,
            changes={"format": kind, "calls": calls, "filter": filter_text},
        )
        return data

    return run


def render_export_menu(df: pd.DataFrame) -> None:
    """"ส่งออกรายงาน" — PDF report, summary CSV and call-list CSV of the current filter."""
    calls = df.to_dict("records")
    filter_text = _filter_summary()
    stamp = datetime.now(timezone(timedelta(hours=7))).strftime("%Y%m%d_%H%M")
    has_font = dashboard_report.find_thai_font() is not None

    def report():
        return dashboard_report.build_report(calls, filter_text)

    with st.popover("ส่งออกรายงาน", icon=":material/download:", width="stretch"):
        st.caption(f"ใช้ข้อมูลตามตัวกรองตอนนี้ — {len(calls):,} สาย")
        st.download_button(
            "รายงาน PDF",
            data=_logged_export("PDF", lambda: dashboard_report.pdf_report(report()), len(calls), filter_text),
            file_name=f"smartvoice_dashboard_{stamp}.pdf",
            mime="application/pdf",
            on_click="ignore",
            icon=":material/picture_as_pdf:",
            width="stretch",
            key="export_pdf",
            disabled=not has_font,
            help=None if has_font else "ไม่พบฟอนต์ภาษาไทยในเครื่อง — ตั้งค่า REPORT_FONT_PATH ใน .env",
        )
        st.download_button(
            "สรุปตัวเลข (CSV)",
            data=_logged_export("CSV สรุป", lambda: dashboard_report.summary_csv(report()), len(calls), filter_text),
            file_name=f"smartvoice_summary_{stamp}.csv",
            mime="text/csv",
            on_click="ignore",
            icon=":material/table_chart:",
            width="stretch",
            key="export_summary_csv",
        )
        st.download_button(
            "รายการสาย (CSV)",
            data=_logged_export("CSV รายการสาย", lambda: dashboard_report.calls_csv(calls), len(calls), filter_text),
            file_name=f"smartvoice_calls_{stamp}.csv",
            mime="text/csv",
            on_click="ignore",
            icon=":material/list_alt:",
            width="stretch",
            key="export_calls_csv",
        )
        st.caption("PDF = กราฟและตารางทุกหน้า Dashboard · CSV เปิดใน Excel ได้ (ภาษาไทยไม่เพี้ยน)")
