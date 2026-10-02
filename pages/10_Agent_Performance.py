"""Dashboard → ผลงาน Agent: QA scores with the quotes that back them up."""

import json
import math
from collections import defaultdict

import pandas as pd
import streamlit as st

st.set_page_config(page_title="SmartVoice — ผลงาน Agent", layout="wide")

from smartvoice import db
from smartvoice.auth import PAGE_AGENT_PERFORMANCE
from smartvoice.dashboard_common import inject_dashboard_css, load_filtered_calls
from smartvoice.file_manager import extract_agent_code_from_filename
from smartvoice.ollama_client import sanitize_evidence, sanitize_next_action
from smartvoice.ui_helpers import init_page, metric_card

init_page(PAGE_AGENT_PERFORMANCE)
inject_dashboard_css()

st.title("Dashboard — ผลงาน Agent")

df, _ = load_filtered_calls()
done_calls = df.to_dict("records")

st.caption(
    "สายในเคสเดียวกันถูกรวมเป็นแถวเดียว "
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
    return f"เบอร์ {phone} · " if phone else ""

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
        label = f"{_phone_prefix(phone)}เคส #{case_id} — {case['subject']} ({n} สาย)"
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
            f'<div class="metric-label">Best</div></div>',
            unsafe_allow_html=True,
        )
    with ag3:
        worst = ap_df_full.loc[ap_df_full["Score"].idxmin(), "Label"]
        st.markdown(
            f'<div class="metric-card"><div class="metric-value" style="font-size:0.9rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%" title="{worst}">{worst}</div>'
            f'<div class="metric-label">Needs Improvement</div></div>',
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
            "ค้นหา (เบอร์ / ชื่อไฟล์ / Subject / Next Action)",
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
                "Next Action": st.column_config.TextColumn("Next Action", width="large"),
                "Owner": st.column_config.TextColumn("ผู้รับผิดชอบ", width="medium"),
            },
        )
else:
    st.caption("ยังไม่มีข้อมูล Agent Performance — re-process ไฟล์เสียงเพื่อดูผล")
