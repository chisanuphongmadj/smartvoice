"""Dashboard → ผลงานพนักงาน: QA scores with the quotes that back them up.

Laid out for reading, not scrolling sideways: a per-agent summary first, then a
compact list of calls/cases (short columns only); clicking any cell opens the
full evidence for that row in a dialog — long quotes in table cells had to be
clicked open one by one.
"""

import json
import math
from collections import defaultdict

import pandas as pd
import streamlit as st

st.set_page_config(page_title="SmartVoice — ผลงานพนักงาน", layout="wide")

from smartvoice import db, labels
from smartvoice.auth import PAGE_AGENT_PERFORMANCE
from smartvoice.case_workflow import next_action_steps
from smartvoice.dashboard_common import inject_dashboard_css, load_filtered_calls
from smartvoice.file_manager import extract_agent_code_from_filename, extract_call_time_from_filename
from smartvoice.ollama_client import sanitize_evidence, sanitize_next_action
from smartvoice.ui_helpers import TABLE_CLICK_MODES, init_page, metric_card, picked_row

init_page(PAGE_AGENT_PERFORMANCE)
inject_dashboard_css()

st.title("Dashboard — ผลงานพนักงาน")

df, _ = load_filtered_calls()
done_calls = df.to_dict("records")

st.caption(
    "คะแนนเต็ม 10 = ความสุภาพ (5) + การแก้ปัญหา (5) — ทุกคะแนนอ้างอิงคำพูดของพนักงานในสาย  •  "
    "ต่ำกว่า 6 = ควรช่วยดู, 6–7.9 = พอใช้, 8 ขึ้นไป = ดี"
)

UNKNOWN_AGENT = "ไม่ทราบรหัส"


def _evidence(value: str, transcript: str = "") -> str:
    text = " ".join(str(value or "").split())
    return sanitize_evidence(text, transcript) or "ระบบไม่พบหลักฐานที่ชัดเจน"


def _score_value(value) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0.0
    return max(0.0, min(5.0, score))


def _when(filename: str, created_at) -> str:
    """Call time from the file name (when the call happened); upload time otherwise."""
    called = extract_call_time_from_filename(filename)
    if called:
        return called.strftime("%d/%m/%Y %H:%M น.")
    return labels.thai_time(created_at)


# ── One entry per scored call ────────────────────────────────────────────
scored_calls = []
for call in done_calls:
    raw = call.get("agent_performance") or ""
    try:
        ap = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        ap = {}
    if not isinstance(ap, dict) or not ap.get("overall_score"):
        continue
    transcript = call.get("transcript") or ""
    next_action, owner = sanitize_next_action(
        ap.get("next_action") or "", ap.get("next_action_owner") or "", transcript
    )
    politeness = _score_value(ap.get("politeness", 0))
    problem_solving = _score_value(ap.get("problem_solving", 0))
    called = extract_call_time_from_filename(call["filename"])
    scored_calls.append({
        "call_id": call["id"],
        "case_id": call.get("case_id"),
        "filename": call["filename"],
        "phone": call.get("customer_phone") or "",
        "topic": call.get("topic_detail") or call.get("topic") or "-",
        "sort_key": called.isoformat() if called else str(call.get("created_at") or ""),
        "when": _when(call["filename"], call.get("created_at")),
        "agent": extract_agent_code_from_filename(call["filename"]) or UNKNOWN_AGENT,
        "politeness": politeness,
        "problem_solving": problem_solving,
        "score": politeness + problem_solving,
        "politeness_evidence": _evidence(ap.get("politeness_evidence", ""), transcript),
        "problem_solving_evidence": _evidence(ap.get("problem_solving_evidence", ""), transcript),
        "next_steps": next_action_steps(next_action),
        "owner": "" if owner in {"", "ไม่มี", "—", "-"} else owner,
    })

if not scored_calls:
    st.info("ยังไม่มีคะแนนพนักงานในสายที่เลือก — สายที่ประมวลผลแล้วจะมีคะแนนอัตโนมัติ")
    st.stop()


# ── 1. สรุปรายพนักงาน ─────────────────────────────────────────────────────
by_agent: dict[str, list] = defaultdict(list)
for entry in scored_calls:
    by_agent[entry["agent"]].append(entry)

agent_summary = pd.DataFrame([
    {
        "รหัสพนักงาน": agent,
        "จำนวนสาย": len(entries),
        "คะแนนเฉลี่ย": round(sum(e["score"] for e in entries) / len(entries), 1),
        "ความสุภาพ": round(sum(e["politeness"] for e in entries) / len(entries), 1),
        "การแก้ปัญหา": round(sum(e["problem_solving"] for e in entries) / len(entries), 1),
        "สายต่ำกว่า 6": sum(1 for e in entries if e["score"] < 6),
    }
    for agent, entries in by_agent.items()
]).sort_values(["คะแนนเฉลี่ย", "จำนวนสาย"], ascending=[False, False])

team_avg = sum(e["score"] for e in scored_calls) / len(scored_calls)
low_calls = sum(1 for e in scored_calls if e["score"] < 6)
known = agent_summary[agent_summary["รหัสพนักงาน"] != UNKNOWN_AGENT]
ranked = known if not known.empty else agent_summary

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(metric_card(f"{team_avg:.1f} / 10", "คะแนนเฉลี่ยทั้งทีม"), unsafe_allow_html=True)
with k2:
    top = ranked.iloc[0]
    st.markdown(
        metric_card(top["รหัสพนักงาน"], f"คะแนนสูงสุด ({top['คะแนนเฉลี่ย']:.1f})", "#22c55e"),
        unsafe_allow_html=True,
    )
with k3:
    bottom = ranked.iloc[-1]
    if len(ranked) < 2 or bottom["คะแนนเฉลี่ย"] == top["คะแนนเฉลี่ย"]:
        st.markdown(metric_card("—", "ทุกคนคะแนนเท่ากัน"), unsafe_allow_html=True)
    else:
        st.markdown(
            metric_card(bottom["รหัสพนักงาน"], f"ควรช่วยดู ({bottom['คะแนนเฉลี่ย']:.1f})", "#eab308"),
            unsafe_allow_html=True,
        )
with k4:
    st.markdown(
        metric_card(low_calls, "สายที่ได้ต่ำกว่า 6", "#ef4444" if low_calls else "#22c55e"),
        unsafe_allow_html=True,
    )

st.subheader("สรุปรายพนักงาน")
st.dataframe(
    agent_summary,
    width="stretch",
    hide_index=True,
    column_config={
        "รหัสพนักงาน": st.column_config.TextColumn(help="เบอร์ภายในของพนักงาน อ่านจากชื่อไฟล์เสียง"),
        "คะแนนเฉลี่ย": st.column_config.ProgressColumn(min_value=0, max_value=10, format="%.1f / 10"),
        "ความสุภาพ": st.column_config.ProgressColumn(min_value=0, max_value=5, format="%.1f / 5"),
        "การแก้ปัญหา": st.column_config.ProgressColumn(min_value=0, max_value=5, format="%.1f / 5"),
    },
)


@st.dialog("รายละเอียดคะแนน", width="large")
def _row_dialog(r: dict) -> None:
    """Full evidence and follow-up for one call/case row."""
    latest = r["latest"]
    st.markdown(f"#### {r['topic']} — ลูกค้า {r['phone'] or '-'}")
    meta = [f"วันที่โทร {r['when']}", f"พนักงาน {', '.join(r['agents'])}"]
    if r["case"]:
        meta.append(f"เคส #{r['case']['id']} ({labels.case_status(r['case'].get('status'))})")
    if len(r["calls"]) > 1:
        meta.append(f"{len(r['calls'])} สาย — คะแนนเป็นค่าเฉลี่ย, หลักฐานมาจากสายล่าสุด")
    st.caption("  •  ".join(meta))

    s1, s2, s3 = st.columns(3)
    with s1:
        st.markdown(metric_card(f"{r['score']:.1f} / 10", "คะแนนรวม"), unsafe_allow_html=True)
    with s2:
        st.markdown(metric_card(f"{r['politeness']:.1f} / 5", "ความสุภาพ"), unsafe_allow_html=True)
    with s3:
        st.markdown(metric_card(f"{r['problem_solving']:.1f} / 5", "การแก้ปัญหา"), unsafe_allow_html=True)

    e1, e2 = st.columns(2)
    with e1:
        st.markdown("**หลักฐานความสุภาพ**")
        st.write(latest["politeness_evidence"])
    with e2:
        st.markdown("**หลักฐานการแก้ปัญหา**")
        st.write(latest["problem_solving_evidence"])

    st.markdown("**สิ่งที่ต้องทำต่อ**")
    if r["closed"]:
        st.write("เคสนี้ปิดแล้ว — ไม่มีเรื่องค้าง")
    elif latest["next_steps"]:
        st.markdown("\n".join(f"- {step}" for step in latest["next_steps"]))
        if latest["owner"]:
            st.caption(f"ผู้รับผิดชอบที่ระบบแนะนำ: {latest['owner']}")
    else:
        st.write("ระบบไม่ได้ระบุ")

    if len(r["calls"]) > 1:
        with st.expander(f"คะแนนแต่ละสายในเคสนี้ ({len(r['calls'])} สาย)"):
            for c in reversed(r["calls"]):
                st.markdown(
                    f"- {c['when']} — พนักงาน {c['agent']} — **{c['score']:.1f} / 10** "
                    f"(สุภาพ {c['politeness']:.1f}, แก้ปัญหา {c['problem_solving']:.1f})"
                )


# ── 2. รายการสาย — calls of one case become one row ─────────────────────
case_groups: dict = defaultdict(list)
rows: list[dict] = []
for entry in scored_calls:
    if entry["case_id"]:
        case_groups[entry["case_id"]].append(entry)
    else:
        rows.append({"calls": [entry], "case": None})
for case_id, entries in case_groups.items():
    rows.append({
        "calls": sorted(entries, key=lambda e: e["sort_key"]),
        "case": db.get_case_by_id(case_id) or {"id": case_id, "subject": f"เคส #{case_id}", "status": "open"},
    })

for row in rows:
    calls = row["calls"]
    latest = calls[-1]
    n = len(calls)
    row.update({
        "latest": latest,
        "when": latest["when"],
        "sort_key": latest["sort_key"],
        "phone": next((c["phone"] for c in calls if c["phone"]), ""),
        "topic": latest["topic"],
        "agents": sorted({c["agent"] for c in calls}),
        "score": round(sum(c["score"] for c in calls) / n, 1),
        "politeness": round(sum(c["politeness"] for c in calls) / n, 1),
        "problem_solving": round(sum(c["problem_solving"] for c in calls) / n, 1),
        "closed": bool(row["case"]) and row["case"].get("status") == "closed",
    })
rows.sort(key=lambda r: r["sort_key"], reverse=True)

st.subheader("รายละเอียดรายสาย")
f_search, f_agent, f_score, f_size = st.columns([2, 1.2, 1.4, 1])
with f_search:
    search = st.text_input(
        "ค้นหา (เบอร์ / เรื่อง / สิ่งที่ต้องทำต่อ)",
        key="agent_perf_search",
        placeholder="เช่น 0819979336, คืนเงิน, ติดตาม",
    )
with f_agent:
    agent_pick = st.selectbox(
        "รหัสพนักงาน", ["ทั้งหมด"] + sorted(by_agent), key="agent_perf_agent",
    )
with f_score:
    score_pick = st.selectbox(
        "กรองตามคะแนน",
        ["ทั้งหมด", "ต่ำกว่า 6 (ควรช่วยดู)", "6–7.9 (พอใช้)", "8 ขึ้นไป (ดี)"],
        key="agent_perf_score",
    )
with f_size:
    page_size = st.selectbox("แถวต่อหน้า", [10, 25, 50, 100], index=1, key="agent_perf_page_size")

shown = rows
if search.strip():
    q = search.strip().lower()
    shown = [
        r for r in shown
        if q in " ".join([
            r["phone"], r["topic"], " ".join(r["latest"]["next_steps"]),
            (r["case"] or {}).get("subject", ""), *[c["filename"] for c in r["calls"]],
        ]).lower()
    ]
if agent_pick != "ทั้งหมด":
    shown = [r for r in shown if agent_pick in r["agents"]]
if score_pick.startswith("ต่ำกว่า 6"):
    shown = [r for r in shown if r["score"] < 6]
elif score_pick.startswith("6–7.9"):
    shown = [r for r in shown if 6 <= r["score"] < 8]
elif score_pick.startswith("8 ขึ้นไป"):
    shown = [r for r in shown if r["score"] >= 8]

n_pages = max(1, math.ceil(len(shown) / page_size))
if st.session_state.get("agent_perf_page", 1) > n_pages:
    st.session_state["agent_perf_page"] = 1
pg_col, info_col = st.columns([1, 3], vertical_alignment="bottom")
with pg_col:
    page = st.number_input(
        f"หน้า (รวม {n_pages:,} หน้า)", min_value=1, max_value=n_pages, step=1, key="agent_perf_page",
    )
start = (page - 1) * page_size
page_rows = shown[start:start + page_size]
with info_col:
    if shown:
        st.caption(f"แสดง {start + 1:,}–{start + len(page_rows):,} จาก {len(shown):,} รายการ — คลิกแถวไหนก็ได้เพื่ออ่านหลักฐานเต็ม")
    else:
        st.warning("ไม่พบรายการที่ตรงกับเงื่อนไข — ลองล้างคำค้น หรือเปลี่ยนตัวกรอง")

if page_rows:
    table = st.dataframe(
        pd.DataFrame([
            {
                "วันที่โทร": r["when"],
                "ลูกค้า": r["phone"] or "-",
                "เรื่อง": (f"เคส #{r['case']['id']} · " if r["case"] and len(r["calls"]) > 1 else "") + r["topic"],
                "สาย": len(r["calls"]),
                "พนักงาน": ", ".join(r["agents"]),
                "คะแนน": r["score"],
                "สิ่งที่ต้องทำต่อ": "เคสปิดแล้ว" if r["closed"] else (r["latest"]["next_steps"] or ["-"])[0],
            }
            for r in page_rows
        ]),
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode=TABLE_CLICK_MODES,
        key=f"agent_perf_table_{page}",
        column_config={
            "วันที่โทร": st.column_config.TextColumn(width="medium"),
            "ลูกค้า": st.column_config.TextColumn(width=110),
            "เรื่อง": st.column_config.TextColumn(width="medium"),
            "สาย": st.column_config.NumberColumn(width="small"),
            "พนักงาน": st.column_config.TextColumn(width="small"),
            "คะแนน": st.column_config.ProgressColumn(min_value=0, max_value=10, format="%.1f / 10", width="small"),
            "สิ่งที่ต้องทำต่อ": st.column_config.TextColumn(width="large"),
        },
    )

    row, is_new = picked_row(table, "_agent_dialog_seen")
    if row is None or row >= len(page_rows):
        st.info("คลิกที่แถวไหนก็ได้ในตาราง เพื่ออ่านคำพูดที่ใช้ให้คะแนน และสิ่งที่ต้องทำต่อ")
    else:
        if is_new:
            _row_dialog(page_rows[row])
        if st.button("เปิดรายละเอียดแถวนี้อีกครั้ง", icon=":material/open_in_new:"):
            _row_dialog(page_rows[row])
