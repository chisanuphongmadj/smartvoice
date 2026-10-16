"""Dashboard numbers as files: CSV (calls, summary) and a PDF report.

Everything here works on the calls the Dashboard filter bar returned, so a file
always shows what the screen shows. The agent-score maths lives here too and the
Agent Performance page imports it — one formula for screen and report.

The PDF is drawn with fpdf2 (bars are rectangles, not chart images, so no
browser/kaleido is needed) and shaped with HarfBuzz so Thai vowels and tone
marks stack correctly. Lines are wrapped here, not by fpdf2: its character
wrap mode hangs on long Thai runs with no spaces.

No Streamlit import — unit-testable.
"""

from __future__ import annotations

import io
import json
import os
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd
from fpdf import FPDF

from smartvoice import config, labels
from smartvoice.case_workflow import next_action_steps
from smartvoice.file_manager import (
    extract_agent_code_from_filename,
    extract_call_time_from_filename,
    extract_direction_from_filename,
)
from smartvoice.insight_rules import BRAND_ALIASES, PLATFORM_ALIASES, canonical_name
from smartvoice.ollama_client import sanitize_evidence, sanitize_next_action

UNKNOWN_AGENT = "ไม่ทราบรหัส"
_DIRECTION_TH = {"inbound": "สายเข้า", "outbound": "สายออก"}
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


# ── Reading one call ─────────────────────────────────────────────────────

def json_list(raw) -> list[str]:
    try:
        items = json.loads(raw) if raw else []
    except (json.JSONDecodeError, TypeError):
        return []
    return [i.strip() for i in items if isinstance(i, str) and i.strip()] if isinstance(items, list) else []


def call_time(call: dict) -> str:
    """When the call happened (file name), else when it was uploaded."""
    called = extract_call_time_from_filename(call.get("filename") or "")
    return called.strftime("%d/%m/%Y %H:%M น.") if called else labels.thai_time(call.get("created_at"))


def _sort_key(call: dict) -> str:
    called = extract_call_time_from_filename(call.get("filename") or "")
    return called.isoformat() if called else str(call.get("created_at") or "")


def _performance(call: dict) -> dict:
    raw = call.get("agent_performance") or ""
    try:
        ap = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        ap = {}
    return ap if isinstance(ap, dict) else {}


def _score_value(value) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0.0
    return max(0.0, min(5.0, score))


def _evidence(value: str, transcript: str = "") -> str:
    text = " ".join(str(value or "").split())
    return sanitize_evidence(text, transcript) or "ระบบไม่พบหลักฐานที่ชัดเจน"


# ── Agent scores (shared with the Agent Performance page) ────────────────

def scored_calls(calls: list[dict]) -> list[dict]:
    """One entry per call that has a QA score, with its evidence and next steps."""
    entries = []
    for call in calls:
        ap = _performance(call)
        if not ap.get("overall_score"):
            continue
        transcript = call.get("transcript") or ""
        next_action, owner = sanitize_next_action(
            ap.get("next_action") or "", ap.get("next_action_owner") or "", transcript
        )
        politeness = _score_value(ap.get("politeness", 0))
        problem_solving = _score_value(ap.get("problem_solving", 0))
        entries.append({
            "call_id": call["id"],
            "case_id": call.get("case_id"),
            "filename": call["filename"],
            "phone": call.get("customer_phone") or "",
            "topic": call.get("topic_detail") or call.get("topic") or "-",
            "sort_key": _sort_key(call),
            "when": call_time(call),
            "agent": extract_agent_code_from_filename(call["filename"]) or UNKNOWN_AGENT,
            "politeness": politeness,
            "problem_solving": problem_solving,
            "score": politeness + problem_solving,
            "politeness_evidence": _evidence(ap.get("politeness_evidence", ""), transcript),
            "problem_solving_evidence": _evidence(ap.get("problem_solving_evidence", ""), transcript),
            "next_steps": next_action_steps(next_action),
            "owner": "" if owner in {"", "ไม่มี", "—", "-"} else owner,
        })
    return entries


def agent_summary(entries: list[dict]) -> pd.DataFrame:
    """Per-agent averages, best first."""
    by_agent: dict[str, list] = defaultdict(list)
    for entry in entries:
        by_agent[entry["agent"]].append(entry)
    columns = ["รหัสพนักงาน", "จำนวนสาย", "คะแนนเฉลี่ย", "ความสุภาพ", "การแก้ปัญหา", "สายต่ำกว่า 6"]
    if not by_agent:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame([
        {
            "รหัสพนักงาน": agent,
            "จำนวนสาย": len(group),
            "คะแนนเฉลี่ย": round(sum(e["score"] for e in group) / len(group), 1),
            "ความสุภาพ": round(sum(e["politeness"] for e in group) / len(group), 1),
            "การแก้ปัญหา": round(sum(e["problem_solving"] for e in group) / len(group), 1),
            "สายต่ำกว่า 6": sum(1 for e in group if e["score"] < 6),
        }
        for agent, group in by_agent.items()
    ], columns=columns).sort_values(["คะแนนเฉลี่ย", "จำนวนสาย"], ascending=[False, False])


# ── Counting (same rules as the Dashboard pages) ─────────────────────────

_LIST_ALIASES = {"brand_mentions": BRAND_ALIASES, "platform_mentions": PLATFORM_ALIASES}
_LIST_IGNORED = {"platform_mentions": {"โทรศัพท์", "phone"}}


def count_list_field(calls: list[dict], field_name: str, top: int = 15) -> list[tuple[str, int]]:
    """Most common names in a JSON-list column, each counted once per call."""
    aliases = _LIST_ALIASES.get(field_name)
    ignored = _LIST_IGNORED.get(field_name, set())
    counter: Counter = Counter()
    for call in calls:
        names = {
            canonical_name(i, aliases) if aliases else i
            for i in json_list(call.get(field_name))
            if i.lower() not in ignored
        }
        counter.update(names)
    return counter.most_common(top)


def _value_counts(values) -> list[tuple[str, int]]:
    return Counter(v for v in values if v).most_common()


def anomaly_calls(calls: list[dict]) -> list[dict]:
    """Anomalous calls, most severe first, newest first within a level."""
    found = [c for c in calls if c.get("anomaly_detected")]
    found.sort(key=_sort_key, reverse=True)
    found.sort(key=lambda c: SEVERITY_ORDER.get(c.get("anomaly_severity"), 3))
    return found


@dataclass
class Report:
    """Everything the summary CSV and the PDF show, computed once."""
    total: int
    sentiment: list[tuple[str, int]]
    topics: list[tuple[str, int]]
    product_issues: list[tuple[str, int]]
    top_issues: list[tuple[str, int]]
    issue_call_count: int
    keywords: list[tuple[str, int]]
    brands: list[tuple[str, int]]
    platforms: list[tuple[str, int]]
    anomalies: list[dict]
    severity_counts: dict[str, int]
    agents: pd.DataFrame
    team_average: float | None
    low_score_calls: int
    filter_text: str = ""
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def build_report(calls: list[dict], filter_text: str = "", generated_at: datetime | None = None) -> Report:
    issue_calls = [c for c in calls if c.get("sentiment") == "negative" or c.get("anomaly_detected")]
    anomalies = anomaly_calls(calls)
    entries = scored_calls(calls)
    return Report(
        total=len(calls),
        sentiment=[
            (labels.sentiment(code), sum(1 for c in calls if c.get("sentiment") == code))
            for code in ("positive", "neutral", "negative")
        ],
        topics=_value_counts(c.get("topic") for c in calls),
        product_issues=_value_counts(
            c.get("topic_detail") for c in calls if c.get("topic") == "แจ้งปัญหาสินค้า"
        ),
        top_issues=_value_counts(c.get("topic") for c in issue_calls)[:3],
        issue_call_count=len(issue_calls),
        keywords=count_list_field(calls, "keywords", top=15),
        brands=count_list_field(calls, "brand_mentions", top=15),
        platforms=count_list_field(calls, "platform_mentions", top=15),
        anomalies=anomalies,
        severity_counts={s: sum(1 for c in anomalies if c.get("anomaly_severity") == s) for s in SEVERITY_ORDER},
        agents=agent_summary(entries),
        team_average=(sum(e["score"] for e in entries) / len(entries)) if entries else None,
        low_score_calls=sum(1 for e in entries if e["score"] < 6),
        filter_text=filter_text,
        generated_at=generated_at or datetime.now(timezone.utc),
    )


# ── CSV ──────────────────────────────────────────────────────────────────

def _safe_cell(value):
    """Stop Excel reading text from a call (or the LLM) as a formula.

    A lone "-" and negative numbers are left alone.
    """
    if not isinstance(value, str) or not value:
        return value
    risky = value[0] in ("=", "+", "@", "\t", "\r") or (
        value[0] == "-" and len(value) > 1 and not value[1].isdigit()
    )
    return "'" + value if risky else value


def _to_csv(frame: pd.DataFrame) -> bytes:
    # utf-8-sig: Excel on Windows only reads Thai correctly with the BOM.
    return frame.map(_safe_cell).to_csv(index=False).encode("utf-8-sig")


def call_rows(calls: list[dict]) -> pd.DataFrame:
    """One row per call with every analysis field, newest call first."""
    rows = []
    for call in sorted(calls, key=_sort_key, reverse=True):
        ap = _performance(call)
        transcript = call.get("transcript") or ""
        next_action, owner = sanitize_next_action(
            ap.get("next_action") or "", ap.get("next_action_owner") or "", transcript
        )
        scored = bool(ap.get("overall_score"))
        politeness = _score_value(ap.get("politeness", 0))
        problem_solving = _score_value(ap.get("problem_solving", 0))
        anomalous = bool(call.get("anomaly_detected"))
        rows.append({
            "วันที่โทร": call_time(call),
            "ไฟล์เสียง": call.get("filename") or "",
            "เบอร์ลูกค้า": call.get("customer_phone") or "",
            "รหัสพนักงาน": extract_agent_code_from_filename(call.get("filename") or "") or "",
            "ทิศทาง": _DIRECTION_TH.get(extract_direction_from_filename(call.get("filename") or "") or "", ""),
            "หัวข้อ": call.get("topic") or "",
            "ประเภทปัญหาสินค้า": call.get("topic_detail") or "",
            "อารมณ์ลูกค้า": labels.sentiment(call.get("sentiment")) if call.get("sentiment") else "",
            "เหตุผลของอารมณ์": call.get("sentiment_reason") or "",
            "ผิดปกติ": "ใช่" if anomalous else "",
            "ระดับความผิดปกติ": labels.severity(call.get("anomaly_severity")) if anomalous else "",
            "สาเหตุความผิดปกติ": (call.get("anomaly_reason") or "") if anomalous else "",
            "คะแนนพนักงาน (เต็ม 10)": round(politeness + problem_solving, 1) if scored else "",
            "ความสุภาพ (เต็ม 5)": round(politeness, 1) if scored else "",
            "การแก้ปัญหา (เต็ม 5)": round(problem_solving, 1) if scored else "",
            "สิ่งที่ต้องทำต่อ": " / ".join(next_action_steps(next_action)),
            "ผู้รับผิดชอบที่แนะนำ": "" if owner in {"", "ไม่มี", "—", "-"} else owner,
            "คำสำคัญ": ", ".join(json_list(call.get("keywords"))),
            "แบรนด์ที่พูดถึง": ", ".join(
                dict.fromkeys(canonical_name(b, BRAND_ALIASES) for b in json_list(call.get("brand_mentions")))
            ),
            "ช่องทางที่พูดถึง": ", ".join(
                dict.fromkeys(
                    canonical_name(p, PLATFORM_ALIASES) for p in json_list(call.get("platform_mentions"))
                    if p.lower() not in _LIST_IGNORED["platform_mentions"]
                )
            ),
            "เคส": f"#{call['case_id']}" if call.get("case_id") else "",
            "สรุปสาย": call.get("summary") or "",
            "อัปโหลดเมื่อ": labels.thai_time(call.get("created_at")),
        })
    return pd.DataFrame(rows)


def calls_csv(calls: list[dict]) -> bytes:
    return _to_csv(call_rows(calls))


def _share(count: int, total: int) -> str:
    return f"{count * 100 / total:.1f}" if total else ""


def summary_rows(report: Report) -> pd.DataFrame:
    """The Dashboard's numbers as one long table: section, item, count, %, note."""
    rows = []

    def add(section, item, count="", share="", note=""):
        rows.append({"หมวด": section, "รายการ": item, "จำนวน": count, "ร้อยละ": share, "หมายเหตุ": note})

    add("ข้อมูลรายงาน", "ออกรายงานเมื่อ", note=labels.thai_time(report.generated_at))
    add("ข้อมูลรายงาน", "ตัวกรอง", note=report.filter_text or "-")
    add("ภาพรวม", "สายทั้งหมด", report.total)
    add("ภาพรวม", "สายผิดปกติ", len(report.anomalies), _share(len(report.anomalies), report.total))
    if report.team_average is not None:
        add("ภาพรวม", "คะแนนพนักงานเฉลี่ยทั้งทีม", note=f"{report.team_average:.1f} / 10")
        add("ภาพรวม", "สายที่พนักงานได้ต่ำกว่า 6", report.low_score_calls)
    for name, count in report.sentiment:
        add("อารมณ์ลูกค้า", name, count, _share(count, report.total))
    for name, count in report.topics:
        add("ลูกค้าโทรมาเรื่องอะไร", name, count, _share(count, report.total))
    product_total = sum(c for _, c in report.product_issues)
    for name, count in report.product_issues:
        add("ประเภทความเสียหาย (แจ้งปัญหาสินค้า)", name, count, _share(count, product_total))
    for name, count in report.top_issues:
        add("เรื่องที่มีปัญหามากที่สุด", name, count, _share(count, report.issue_call_count),
            f"จาก {report.issue_call_count} สายที่ลูกค้าไม่พอใจหรือผิดปกติ")
    for section, pairs in (
        ("คำที่ลูกค้าพูดถึงบ่อย", report.keywords),
        ("แบรนด์ที่ถูกพูดถึง", report.brands),
        ("ช่องทางซื้อ/ติดต่อที่ถูกพูดถึง", report.platforms),
    ):
        for name, count in pairs:
            add(section, name, count, _share(count, report.total), "นับครั้งเดียวต่อสาย")
    for code, count in report.severity_counts.items():
        add("ความผิดปกติตามระดับ", labels.severity(code), count, _share(count, len(report.anomalies)))
    for _, agent in report.agents.iterrows():
        add(
            "ผลงานพนักงาน", agent["รหัสพนักงาน"], int(agent["จำนวนสาย"]), "",
            f"เฉลี่ย {agent['คะแนนเฉลี่ย']:.1f}/10 (สุภาพ {agent['ความสุภาพ']:.1f}/5, "
            f"แก้ปัญหา {agent['การแก้ปัญหา']:.1f}/5) — ต่ำกว่า 6: {int(agent['สายต่ำกว่า 6'])} สาย",
        )
    return pd.DataFrame(rows)


def summary_csv(report: Report) -> bytes:
    return _to_csv(summary_rows(report))


# ── PDF ──────────────────────────────────────────────────────────────────

class ReportFontMissing(RuntimeError):
    """No Thai-capable TrueType font was found for the PDF."""


def _font_candidates() -> list[tuple[str, str | None]]:
    windows = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    return [
        (os.path.join(windows, "tahoma.ttf"), os.path.join(windows, "tahomabd.ttf")),
        (os.path.join(windows, "LeelawUI.ttf"), os.path.join(windows, "LeelaUIb.ttf")),
        (os.path.join(windows, "leelawad.ttf"), os.path.join(windows, "leelawdb.ttf")),
        ("/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf",
         "/usr/share/fonts/truetype/noto/NotoSansThai-Bold.ttf"),
        ("/usr/share/fonts/truetype/tlwg/Loma.ttf", "/usr/share/fonts/truetype/tlwg/Loma-Bold.ttf"),
        ("/usr/share/fonts/truetype/tlwg/Garuda.ttf", "/usr/share/fonts/truetype/tlwg/Garuda-Bold.ttf"),
    ]


def find_thai_font() -> tuple[str, str | None] | None:
    """(regular, bold-or-None) — REPORT_FONT_PATH wins, then common system fonts."""
    custom = (config.REPORT_FONT_PATH or "").strip()
    if custom:
        return (custom, None) if os.path.isfile(custom) else None
    for regular, bold in _font_candidates():
        if os.path.isfile(regular):
            return regular, bold if bold and os.path.isfile(bold) else None
    return None


# Characters that never start a line: combining marks (Mn) and the vowels that
# follow their consonant; leading vowels (เ แ โ ใ ไ) never end one.
_NO_LINE_START = set("ะาำๆฯ")
_NO_LINE_END = set("เแโใไ")


def _can_break_before(text: str, i: int) -> bool:
    if i <= 0 or i >= len(text):
        return False
    ch, prev = text[i], text[i - 1]
    return (
        unicodedata.category(ch) != "Mn"
        and ch not in _NO_LINE_START
        and prev not in _NO_LINE_END
    )


def wrap_text(text: str, width: float, measure) -> list[str]:
    """Greedy line wrap that prefers spaces and never splits a Thai cell.

    `measure(s)` returns the printed width of `s`. Thai has no spaces between
    words, so a run longer than the line is broken between character clusters
    (never between a consonant and its vowel/tone marks).
    """
    lines: list[str] = []
    for paragraph in str(text or "").splitlines() or [""]:
        first = len(lines)
        line = ""
        for word in paragraph.split(" "):
            candidate = f"{line} {word}" if line else word
            if measure(candidate) <= width:
                line = candidate
                continue
            if line:
                lines.append(line)
                line = ""
            # The word alone may still be too long: cut it at cluster boundaries.
            while word and measure(word) > width:
                cut = 0
                for i in range(1, len(word)):
                    if not _can_break_before(word, i):
                        continue
                    if measure(word[:i]) > width:
                        break
                    cut = i
                if cut == 0:          # one cluster wider than the line: keep it whole
                    cut = next((i for i in range(1, len(word)) if _can_break_before(word, i)), len(word))
                lines.append(word[:cut])
                word = word[cut:]
            line = word
        if line or len(lines) == first:      # no trailing blank line, but keep blank paragraphs
            lines.append(line)
    return lines


_NAVY = (30, 58, 138)
_BRAND = (3, 105, 161)
_RED = (185, 28, 28)
_GREY = (100, 116, 139)
_LIGHT = (241, 245, 249)
_SENTIMENT_RGB = {"เชิงบวก": (52, 211, 153), "เป็นกลาง": (148, 163, 184), "เชิงลบ": (248, 113, 113)}
_SEVERITY_RGB = {"high": (185, 28, 28), "medium": (234, 88, 12), "low": (202, 138, 4)}


class _ReportPDF(FPDF):
    """A4 page with "generated at" and "page x/y" in the footer."""

    generated_text = ""

    def footer(self):
        self.set_y(-12)
        self.set_font("th", "", 8)
        self.set_text_color(*_GREY)
        self.cell(0, 6, f"SmartVoice — {self.generated_text}", align="L")
        self.set_x(self.l_margin)
        self.cell(0, 6, f"หน้า {self.page_no()}/{{nb}}", align="R")


class _Writer:
    """Small layout helpers on top of fpdf2 (A4 portrait, millimetres)."""

    def __init__(self, pdf):
        self.pdf = pdf

    @property
    def width(self) -> float:
        return self.pdf.w - self.pdf.l_margin - self.pdf.r_margin

    def font(self, size: float, bold: bool = False, color=(15, 23, 42)):
        self.pdf.set_font("th", "B" if bold else "", size)
        self.pdf.set_text_color(*color)

    def ensure(self, height: float):
        if self.pdf.get_y() + height > self.pdf.page_break_trigger:
            self.pdf.add_page()

    def lines(self, text: str, width: float) -> list[str]:
        return wrap_text(text, width - 1, self.pdf.get_string_width)

    def paragraph(self, text: str, size: float = 10, color=(15, 23, 42), line_h: float = 5.2):
        self.font(size, color=color)
        for line in self.lines(text, self.width):
            self.ensure(line_h)
            self.pdf.set_x(self.pdf.l_margin)
            self.pdf.cell(self.width, line_h, line, new_x="LMARGIN", new_y="NEXT")

    def heading(self, text: str, note: str = ""):
        self.ensure(24)                       # keep a heading with the start of its block
        self.pdf.ln(3)
        y = self.pdf.get_y()
        self.pdf.set_fill_color(*_NAVY)
        self.pdf.rect(self.pdf.l_margin, y + 1, 1.6, 6, style="F")
        self.pdf.set_x(self.pdf.l_margin + 4)
        self.font(13, bold=True, color=_NAVY)
        self.pdf.cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")
        if note:
            self.paragraph(note, size=8.5, color=_GREY, line_h=4.5)
        self.pdf.ln(1)

    def kpis(self, items: list[tuple[str, str, tuple]]):
        gap = 3
        box_w = (self.width - gap * (len(items) - 1)) / len(items)
        self.ensure(22)
        y = self.pdf.get_y()
        for i, (value, label, color) in enumerate(items):
            x = self.pdf.l_margin + i * (box_w + gap)
            self.pdf.set_fill_color(*_LIGHT)
            self.pdf.rect(x, y, box_w, 19, style="F", round_corners=True, corner_radius=2)
            self.pdf.set_xy(x, y + 2)
            self.font(15, bold=True, color=color)
            self.pdf.cell(box_w, 8, value, align="C")
            self.pdf.set_xy(x, y + 11)
            self.font(8.5, color=_GREY)
            self.pdf.cell(box_w, 5, label, align="C")
        self.pdf.set_xy(self.pdf.l_margin, y + 22)

    def bars(self, pairs: list[tuple[str, int]], color=_BRAND, colors: dict | None = None,
             total: int | None = None, empty: str = "ไม่มีข้อมูล"):
        if not pairs or not any(count for _, count in pairs):
            self.paragraph(empty, size=9, color=_GREY)
            return
        label_w, value_w = 58, 26
        bar_w = self.width - label_w - value_w - 2
        top = max(count for _, count in pairs) or 1
        self.font(9)
        for name, count in pairs:
            label_lines = self.lines(name, label_w - 2)
            row_h = max(6.0, 4.6 * len(label_lines) + 1.4)
            self.ensure(row_h)
            y = self.pdf.get_y()
            self.font(9)
            for n, line in enumerate(label_lines):
                self.pdf.set_xy(self.pdf.l_margin, y + 0.7 + n * 4.6)
                self.pdf.cell(label_w - 2, 4.6, line, align="R")
            length = bar_w * count / top
            if length > 0:
                self.pdf.set_fill_color(*((colors or {}).get(name, color)))
                self.pdf.rect(self.pdf.l_margin + label_w, y + (row_h - 4.4) / 2, max(length, 0.8), 4.4, style="F")
            share = f"  ({count * 100 / total:.0f}%)" if total else ""
            self.pdf.set_xy(self.pdf.l_margin + label_w + length + 1.5, y + (row_h - 4.6) / 2)
            self.font(8.5, bold=True, color=(51, 65, 85))
            self.pdf.cell(value_w, 4.6, f"{count:,}{share}")
            self.pdf.set_xy(self.pdf.l_margin, y + row_h)
        self.pdf.ln(1)

    def table(self, headers: list[str], rows: list[list[str]], widths: list[float], size: float = 8.5):
        line_h = 4.4
        scale = self.width / sum(widths)
        widths = [w * scale for w in widths]

        def header():
            self.ensure(8)
            y = self.pdf.get_y()
            self.pdf.set_fill_color(*_NAVY)
            self.pdf.rect(self.pdf.l_margin, y, self.width, 7, style="F")
            x = self.pdf.l_margin
            self.font(size, bold=True, color=(255, 255, 255))
            for text, w in zip(headers, widths):
                self.pdf.set_xy(x + 1, y + 1.2)
                self.pdf.cell(w - 2, line_h, text)
                x += w
            self.pdf.set_xy(self.pdf.l_margin, y + 7)

        header()
        for index, row in enumerate(rows):
            self.font(size)
            cells = [self.lines(str(value), w - 2) for value, w in zip(row, widths)]
            row_h = max(len(c) for c in cells) * line_h + 2
            if self.pdf.get_y() + row_h > self.pdf.page_break_trigger:
                self.pdf.add_page()
                header()
                self.font(size)
            y = self.pdf.get_y()
            if index % 2:
                self.pdf.set_fill_color(*_LIGHT)
                self.pdf.rect(self.pdf.l_margin, y, self.width, row_h, style="F")
            x = self.pdf.l_margin
            for lines_, w in zip(cells, widths):
                for n, line in enumerate(lines_):
                    self.pdf.set_xy(x + 1, y + 1 + n * line_h)
                    self.pdf.cell(w - 2, line_h, line)
                x += w
            self.pdf.set_xy(self.pdf.l_margin, y + row_h)
        self.pdf.ln(2)


MAX_PDF_ANOMALIES = 40


def pdf_report(report: Report, font: tuple[str, str | None] | None = None) -> bytes:
    """The Dashboard as an A4 report. Raises ReportFontMissing without a Thai font."""
    font = font or find_thai_font()
    if not font:
        raise ReportFontMissing(
            "ไม่พบฟอนต์ภาษาไทยในเครื่อง — ตั้งค่า REPORT_FONT_PATH ใน .env เป็นไฟล์ .ttf ที่มีภาษาไทย"
        )
    regular, bold = font
    pdf = _ReportPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(True, margin=16)
    pdf.add_font("th", "", regular)
    pdf.add_font("th", "B", bold or regular)
    pdf.set_text_shaping(True)
    pdf.generated_text = f"ออกรายงานเมื่อ {labels.thai_time(report.generated_at)}"
    pdf.set_title("SmartVoice — รายงาน Dashboard")
    pdf.add_page()
    w = _Writer(pdf)

    w.font(20, bold=True, color=_NAVY)
    pdf.cell(0, 11, "รายงาน Dashboard — SmartVoice", new_x="LMARGIN", new_y="NEXT")
    w.paragraph(f"ออกรายงานเมื่อ {labels.thai_time(report.generated_at)}", size=9, color=_GREY)
    w.paragraph(f"ตัวกรอง: {report.filter_text or 'ทั้งหมด'}", size=9, color=_GREY)
    pdf.ln(3)

    sentiment = dict(report.sentiment)
    w.kpis([
        (f"{report.total:,}", "สายทั้งหมด", _NAVY),
        (f"{sentiment.get(labels.sentiment('positive'), 0):,}", "ลูกค้าเชิงบวก", (5, 150, 105)),
        (f"{sentiment.get(labels.sentiment('negative'), 0):,}", "ลูกค้าเชิงลบ", _RED),
        (f"{len(report.anomalies):,}", "สายผิดปกติ", (234, 88, 12)),
        (f"{report.team_average:.1f}/10" if report.team_average is not None else "-",
         "คะแนนพนักงานเฉลี่ย", _BRAND),
    ])

    w.heading("อารมณ์ลูกค้า")
    w.bars(report.sentiment, colors=_SENTIMENT_RGB, total=report.total)

    w.heading("ลูกค้าโทรมาเรื่องอะไร")
    w.bars(report.topics, total=report.total)
    if report.product_issues:
        w.heading("ประเภทความเสียหาย ภายใน \"แจ้งปัญหาสินค้า\"")
        w.bars(report.product_issues, color=_RED, total=sum(c for _, c in report.product_issues))

    w.heading(
        "3 เรื่องที่มีปัญหามากที่สุด",
        f"นับจาก {report.issue_call_count:,} สายที่ลูกค้าไม่พอใจหรือผิดปกติ" if report.issue_call_count else "",
    )
    w.bars(report.top_issues, color=_RED, empty="ไม่พบสายที่ลูกค้าไม่พอใจหรือผิดปกติ")

    w.heading("คำที่ลูกค้าพูดถึงบ่อย", "นับครั้งเดียวต่อสาย")
    w.bars(report.keywords[:12], color=_NAVY, empty="ยังไม่มีคำสำคัญ")
    w.heading("แบรนด์ที่ถูกพูดถึง")
    w.bars(report.brands[:12], color=(14, 116, 144), empty="ไม่มีการพูดถึงแบรนด์")
    w.heading("ช่องทางซื้อ / ติดต่อที่ถูกพูดถึง")
    w.bars(report.platforms[:12], color=(71, 85, 105), empty="ไม่มีการพูดถึงช่องทาง")

    w.heading(
        "ผลงานพนักงาน",
        "คะแนนเต็ม 10 = ความสุภาพ (5) + การแก้ปัญหา (5) — ทุกคะแนนอ้างอิงคำพูดของพนักงานในสาย",
    )
    if report.agents.empty:
        w.paragraph("ยังไม่มีคะแนนพนักงานในสายที่เลือก", size=9, color=_GREY)
    else:
        w.table(
            ["รหัสพนักงาน", "จำนวนสาย", "คะแนนเฉลี่ย", "ความสุภาพ", "การแก้ปัญหา", "สายต่ำกว่า 6"],
            [
                [a["รหัสพนักงาน"], f"{int(a['จำนวนสาย']):,}", f"{a['คะแนนเฉลี่ย']:.1f} / 10",
                 f"{a['ความสุภาพ']:.1f} / 5", f"{a['การแก้ปัญหา']:.1f} / 5", f"{int(a['สายต่ำกว่า 6']):,}"]
                for _, a in report.agents.iterrows()
            ],
            [30, 18, 22, 20, 22, 20],
        )

    severity_note = "  •  ".join(
        f"{labels.severity(code)} {count:,}" for code, count in report.severity_counts.items()
    )
    w.heading(
        f"สายที่ผิดปกติ ({len(report.anomalies):,} สาย)",
        f"{severity_note} — สายที่ควรส่งต่อหัวหน้า เช่น ขู่ฟ้อง ขู่ร้องเรียน ขอคุยหัวหน้า คำหยาบ",
    )
    if not report.anomalies:
        w.paragraph("ไม่พบความผิดปกติในสายที่เลือก", size=9, color=_GREY)
    else:
        shown = report.anomalies[:MAX_PDF_ANOMALIES]
        w.table(
            ["วันที่โทร", "ลูกค้า", "พนักงาน", "ระดับ", "สาเหตุ"],
            [
                [call_time(c), c.get("customer_phone") or "-",
                 extract_agent_code_from_filename(c.get("filename") or "") or "-",
                 labels.severity(c.get("anomaly_severity")), c.get("anomaly_reason") or "ไม่ระบุสาเหตุ"]
                for c in shown
            ],
            [31, 22, 15, 15, 77],
        )
        if len(report.anomalies) > len(shown):
            w.paragraph(
                f"แสดง {len(shown)} สายแรกจาก {len(report.anomalies):,} สาย — ดูทั้งหมดได้ในไฟล์ CSV รายการสาย",
                size=8.5, color=_GREY,
            )

    buffer = io.BytesIO()
    pdf.output(buffer)
    return buffer.getvalue()
