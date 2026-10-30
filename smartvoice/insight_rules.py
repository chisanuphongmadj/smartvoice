"""Deterministic checks applied to the LLM's analysis before it is saved.

An 8B model asked for a score, a brand list or an anomaly flag tends to copy
what the prompt shows and to tick every box (every call used to score 10/10,
and the group's five brand names showed up on calls that never said them).
So the prompts ask for *parts* — per-item yes/no with a verbatim quote, a
category plus the sentence that triggered it — and this module decides:

- a checklist item counts only if its quote really occurs in the Agent's lines;
- scores are computed here from the verified items, not taken from the model;
- an anomaly counts only if its quote occurs in the call and contains a
  keyword of its category; severity comes from the category, not the model;
- brands/platforms are kept only if their name (or a known spelling) occurs in
  the call, and are mapped to one canonical name so the dashboard groups them;
- topic / topic_detail are clamped to the fixed vocabulary.

No Streamlit or network imports — everything here is unit-tested.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

# ── Quote verification ───────────────────────────────────────────────────

_SQUASH_RE = re.compile(r"[\s'\"“”‘’.,!?…:;()\[\]\-–—/]+")
MIN_QUOTE_CHARS = 4          # shorter than this ("ค่ะ") proves nothing
QUOTE_MATCH_RATIO = 0.8      # Thai STT text + model copying: allow small drift


def _squash(text: str) -> str:
    return _SQUASH_RE.sub("", str(text or "")).lower()


def quote_in_text(quote: str, text: str) -> bool:
    """True when `quote` (ignoring spaces/punctuation) occurs in `text`.

    A small drift is tolerated — the longest common run must cover 80% of
    the quote — because the model often drops a particle or a repeated word
    when it copies a line of speech-to-text output.
    """
    q, t = _squash(quote), _squash(text)
    if len(q) < MIN_QUOTE_CHARS or not t:
        return False
    if q in t:
        return True
    match = SequenceMatcher(None, q, t, autojunk=False).find_longest_match(0, len(q), 0, len(t))
    return match.size >= max(MIN_QUOTE_CHARS, int(len(q) * QUOTE_MATCH_RATIO))


SPLIT_MAX_ADDED = 0.1        # a split may fix a particle, not write new speech
SPLIT_MIN_KEPT = 0.8         # ... nor drop a fifth of what was said


def split_keeps_text(parts: list[str], segment: str) -> bool:
    """True when the texts the model gave for a split segment are that segment's
    own words, in order (ignoring spaces/punctuation).

    The speaker-correction model once filled a split part with lines of its own
    prompt ("สวัสดีครับ/ค่ะ [ชื่อบริษัท] ... เรียกอีกฝ่ายว่า "คุณลูกค้า"") in place
    of what the customer said.
    """
    joined, source = _squash("".join(parts)), _squash(segment)
    if not joined or not source:
        return False
    matched = sum(b.size for b in SequenceMatcher(None, joined, source, autojunk=False).get_matching_blocks())
    return (len(joined) - matched) <= len(joined) * SPLIT_MAX_ADDED and matched >= len(source) * SPLIT_MIN_KEPT


def speaker_text(conversation_text: str, speaker: str) -> str:
    """Only the lines spoken by `speaker` ("Agent" / "Customer").

    Falls back to the whole text when no line carries that label (an older
    transcript, or diarization that never assigned roles).
    """
    prefix = f"{speaker.lower()}:"
    lines = [
        line.split(":", 1)[1]
        for line in (conversation_text or "").splitlines()
        if line.strip().lower().startswith(prefix)
    ]
    return "\n".join(lines) if lines else (conversation_text or "")


# ── Agent QA ─────────────────────────────────────────────────────────────

POLITENESS_ITEMS = {
    "P1": "ทักทายเปิดสาย",
    "P2": "ใช้คำสุภาพสม่ำเสมอ",
    "P3": "แสดงความเห็นใจ/ขอโทษเมื่อลูกค้ามีปัญหา",
    "P4": "ขออนุญาต/ขอบคุณก่อนให้รอหรือขอข้อมูล",
    "P5": "กล่าวปิดสาย",
}
PROBLEM_SOLVING_ITEMS = {
    "S1": "ถาม/ทวนเพื่อเข้าใจปัญหา",
    "S2": "ตอบตรงประเด็น",
    "S3": "อธิบายเหตุผล/เงื่อนไขประกอบ",
    "S4": "บอกขั้นตอนถัดไป",
    "S5": "สรุปสิ่งที่ตกลง/ถามว่ามีอะไรให้ช่วยเพิ่ม",
}
# Only these items may be marked "not applicable" by the model.
_MAY_BE_NOT_APPLICABLE = {"P3"}


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    return str(value or "").strip().lower() in {"true", "yes", "1", "ใช่"}


# Phrases only the company side says. Diarization often files the agent's
# words under "Customer:", so a quote found outside the Agent lines still
# counts when it plainly sounds like the agent.
_AGENT_VOICE = (
    "ลูกค้า", "ขออนุญาต", "ทางบริษัท", "ทางเรา", "บริษัทที่นอน", "รบกวน", "ยินดีให้บริการ",
    "ขอบคุณที่", "ขออภัย", "สักครู่", "เรียนสาย", "แจ้งกลับ",
)


def not_customer_text(conversation_text: str) -> str:
    """Every line except those labelled Customer.

    Diarization leaves many turns as "Speaker 0" / "Speaker 1"; those are as
    likely the agent as anyone, so only lines clearly marked Customer are
    excluded from agent evidence.
    """
    return "\n".join(
        line for line in (conversation_text or "").splitlines()
        if not line.strip().lower().startswith("customer:")
    )


def agent_said(quote: str, conversation_text: str) -> bool:
    """The quote is the agent's: outside the Customer lines, or in agent voice anywhere."""
    if quote_in_text(quote, not_customer_text(conversation_text)):
        return True
    return any(v in (quote or "") for v in _AGENT_VOICE) and quote_in_text(quote, conversation_text)


_POLITE_PARTICLE_RE = re.compile(r"(ค่ะ|คะ|ค่า|ครับ|คับ)")


def polite_particles_check(conversation_text: str) -> dict:
    """P2 (polite particles throughout) measured directly, not quoted.

    The model can only quote "ค่ะ" for it, which is too short to verify. Counts
    the agent-side lines (see not_customer_text) that carry a polite particle;
    60% or more counts as done.
    """
    lines = [
        line.split(":", 1)[-1] for line in not_customer_text(conversation_text).splitlines()
        if len(line.split(":", 1)[-1].strip()) >= 8
    ]
    if not lines:
        return {"done": False, "quote": ""}
    polite = sum(1 for line in lines if _POLITE_PARTICLE_RE.search(line))
    return {
        "done": polite / len(lines) >= 0.6,
        "quote": f"ลงท้ายสุภาพ {polite} จาก {len(lines)} ประโยคของพนักงาน",
        "measured": True,
    }


# The prompt names each item in plain Thai (codes like "P1" were too abstract
# for the model: it repeated two of them and never reached the rest).
ITEM_KEYS_TH = {
    "ทักทายเปิดสาย": "P1", "ใช้คำสุภาพ": "P2", "เห็นใจหรือขอโทษ": "P3", "ขออนุญาตหรือขอบคุณ": "P4",
    "กล่าวปิดสาย": "P5", "ถามหรือทวนปัญหา": "S1", "ตอบตรงคำถาม": "S2", "อธิบายเหตุผลหรือเงื่อนไข": "S3",
    "บอกขั้นตอนถัดไป": "S4", "สรุปหรือถามว่าช่วยอะไรเพิ่ม": "S5",
}


def has_itemised_qa(result: dict) -> bool:
    """True for the per-item answer formats; False for the old totals-only one."""
    if not isinstance(result, dict):
        return False
    return (
        any(k in result for k in ITEM_KEYS_TH)
        or isinstance(result.get("found"), list)
        or any(isinstance(result.get(k), dict) for k in ("P1", "S1"))
    )


def items_from_answer(result: dict) -> dict:
    """{"P1": {"done", "quote"}, ...} from either answer format.

    Current format: "found": [{"item": "P1", "quote": "..."}] lists only the
    items with evidence — the earlier per-item template with "done": false
    pre-filled was copied as-is, leaving whole sections unscored.
    """
    if not isinstance(result, dict):
        return {}
    if any(k in result for k in ITEM_KEYS_TH):
        items = {
            code: {"done": bool(str(result.get(name) or "").strip()), "quote": str(result.get(name) or "")}
            for name, code in ITEM_KEYS_TH.items()
        }
        if "ลูกค้ามีปัญหา" in result:
            items["P3"]["applicable"] = _truthy(result.get("ลูกค้ามีปัญหา"))
        return items
    if not isinstance(result.get("found"), list):
        return result
    items: dict = {}
    for entry in result["found"]:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("item") or "").strip().upper()[:2]
        if key in POLITENESS_ITEMS or key in PROBLEM_SOLVING_ITEMS:
            items.setdefault(key, {"done": True, "quote": entry.get("quote") or ""})
    if "customer_had_problem" in result:
        items.setdefault("P3", {"done": False, "quote": ""})
        items["P3"]["applicable"] = _truthy(result.get("customer_had_problem"))
    return items


def score_items(result: dict, items: dict[str, str], conversation_text: str) -> tuple[int, str]:
    """(score 1-5, evidence text) from verified checklist items.

    Score = share of applicable items done, on a 1-5 scale. An item counts
    only when the model says it was done AND its quote is something the agent
    actually said (see agent_said).
    """
    done: list[str] = []
    missed: list[str] = []
    applicable = 0
    for key, name in items.items():
        entry = result.get(key)
        if not isinstance(entry, dict):
            entry = {"done": entry}
        if key in _MAY_BE_NOT_APPLICABLE and entry.get("applicable") is not None and not _truthy(entry.get("applicable")):
            continue
        applicable += 1
        quote = " ".join(str(entry.get("quote") or "").split())
        if key == "P2":
            entry = polite_particles_check(conversation_text)
            quote = entry["quote"]
        if entry.get("measured"):
            (done if entry["done"] else missed).append(f"{name} ({quote})")
            continue
        if _truthy(entry.get("done")) and agent_said(quote, conversation_text):
            done.append(f"{name} ('{quote}')")
        elif _truthy(entry.get("done")) and quote:
            missed.append(f"{name} (คำพูดที่อ้างไม่พบในสาย)")
        else:
            missed.append(f"{name} (ไม่พบหลักฐาน)")
    score = max(1, round(5 * len(done) / applicable)) if applicable else 3
    evidence = f"ทำได้: {', '.join(done) or 'ไม่มี'} / ไม่ได้: {', '.join(missed) or 'ไม่มี'}"
    return score, evidence


# ── Sentiment ────────────────────────────────────────────────────────────

_PRAISE_WORDS = (
    "ประทับใจ", "พอใจ", "ชอบ", "สุดยอด", "เยี่ยม", "บริการดี", "ดีมาก", "ดีเลย", "ช่วยได้มาก",
    "ดีใจ", "โล่งใจ", "ชื่นชม", "เก่งมาก", "สบายใจ",
)
_STRONG_NEGATIVE = (
    "แม่ง", "เหี้ย", "ห่วย", "ไม่พอใจ", "ผิดหวัง", "โมโห", "หงุดหงิด", "เซ็ง", "แย่มาก", "ไม่ไหว",
    "กู", "มึง", "เสียความรู้สึก",
)


def check_sentiment(sentiment: str, quote: str, customer_text: str) -> str:
    """Hold the label to what the customer actually said.

    - "positive" needs a praise word in the customer's quoted words: the model
      labelled calls positive because the customer said "ขอบคุณครับ".
    - a customer who swears or says outright that they are displeased is not
      positive or neutral (a real call with "แม่ง ... กูเสียเงินไปแล้ว" came
      back positive).
    """
    talk = (customer_text or "").lower()
    if sentiment != "negative" and any(w in talk for w in _STRONG_NEGATIVE):
        return "negative"
    if sentiment == "positive" and not any(w in (quote or "") for w in _PRAISE_WORDS):
        return "neutral"
    return sentiment


# ── Next action ──────────────────────────────────────────────────────────

CLOSED_NEXT_ACTION = "ไม่มี — เคสปิดสมบูรณ์"
OWNERS = ("Agent คนเดิม", "หัวหน้าทีม", "ฝ่าย QC", "ฝ่ายจัดส่ง", "ฝ่ายคลังสินค้า", "ฝ่ายบัญชี")
_SUGGESTED_DEADLINE = {
    "ฝ่ายบัญชี": "ภายใน 7 วันทำการ",
    "ฝ่าย QC": "ภายใน 3-5 วัน",
    "ฝ่ายจัดส่ง": "ภายใน 3-7 วัน",
}
_INLINE_PLACEHOLDER_RE = re.compile(r"(?:ที่\s*)?<[^<>]*>|\[[^\[\]]*\]")
_SEGMENT_LABEL_RE = re.compile(r"^\s*(?:\[[^\]]*\]|สิ่งที่ต้องทำ|บริบท(?:/รายละเอียด)?|รายละเอียด|กำหนดเวลา|วิธีปิดงาน)\s*:\s*")

_MONEY_ACTION_WORDS = ("คืนเงิน", "โอนเงิน", "โอนคืน", "เงินคืน", "รีฟันด์", "refund")
_MONEY_TALK_WORDS = ("เงิน", "โอน", "บาท", "ยอด", "refund", "รีฟันด์")


def clean_next_action_text(text: str) -> str:
    """Drop template leftovers: "<เบอร์ที่ลูกค้าให้ไว้>", "[บริบท]", "บริบท: " labels."""
    parts = []
    for part in str(text or "").split("|"):
        part = _SEGMENT_LABEL_RE.sub("", part)
        part = _INLINE_PLACEHOLDER_RE.sub("", part)
        part = " ".join(part.split()).strip(" -:")
        if part:
            parts.append(part)
    return " | ".join(parts)


def money_action_is_ungrounded(next_action: str, conversation_text: str) -> bool:
    """A refund/transfer task on a call where nobody talked about money.

    The old prompt's example action was "ติดตามการโอนเงินคืน", and the model
    put it on calls about delivery dates and mattress weight.
    """
    action = (next_action or "").lower()
    if not any(w in action for w in _MONEY_ACTION_WORDS):
        return False
    talk = (conversation_text or "").lower()
    return not any(w in talk for w in _MONEY_TALK_WORDS)


# A department named outright in the task decides the owner.
_OWNER_NAMED_IN_TODO = (
    ("ฝ่ายบัญชี", ("บัญชี",)),
    ("ฝ่าย QC", ("qc", "ตรวจสอบคุณภาพ")),
    ("ฝ่ายจัดส่ง", ("ฝ่ายจัดส่ง", "ขนส่ง")),
    ("ฝ่ายคลังสินค้า", ("คลังสินค้า", "สต็อก")),
    ("หัวหน้าทีม", ("หัวหน้า", "ขออนุมัติ")),
)


def build_next_action(raw, conversation_text: str) -> tuple[str, str] | None:
    """(next_action, owner) from the structured answer, or None if not structured.

    No "todo" (or "pending": false) means nothing is left to do.
    """
    if not isinstance(raw, dict) or not ({"todo", "pending"} & set(raw)):
        return None
    todo = clean_next_action_text(raw.get("todo") or "")
    if ("pending" in raw and not _truthy(raw.get("pending"))) or not todo:
        return CLOSED_NEXT_ACTION, "ไม่มี"
    owner = str(raw.get("owner") or "").strip()
    if owner not in OWNERS:
        owner = ""
    lowered = todo.lower()
    for department, words in _OWNER_NAMED_IN_TODO:
        if any(w in lowered for w in words):
            owner = department
            break
    deadline = clean_next_action_text(raw.get("deadline") or "")
    if not deadline or "ไม่ระบุ" in deadline:
        deadline = f"ไม่ระบุในสาย (แนะนำ: {_SUGGESTED_DEADLINE.get(owner, 'ภายใน 2-3 วัน')})"
    parts = [
        todo,
        clean_next_action_text(raw.get("detail") or ""),
        deadline,
        clean_next_action_text(raw.get("follow_up") or ""),
    ]
    return " | ".join(p for p in parts if p), owner or "ไม่มี"


# ── Anomaly ──────────────────────────────────────────────────────────────

SEVERITY_BY_CATEGORY = {
    "A1": "high", "A2": "high", "A3": "medium", "A4": "low",
    "B1": "high", "B2": "high", "B3": "high",
    "C1": "medium", "C2": "medium", "C3": "low",
    "D1": "medium",
}
# Categories whose evidence must contain one of these words. B has its own
# check (misconduct_is_grounded); D only needs a verified quote. Thai has no word
# breaks, so some words carry an exclusion: "แจ้งความต้องการ" (state one's
# needs) is not "แจ้งความ" (file a police report) — a real call was flagged
# as a legal threat for it.
_KEYWORD_EXCLUSIONS = {
    "แจ้งความ": re.compile(r"แจ้งความ(?!ต้องการ|ประสงค์|คืบหน้า|จำนง)"),
    "ศาล": re.compile(r"ศาล(?!า)"),
    "คัน": re.compile(r"(?<!รถ)คัน(?!ละ|นี้|นั้น|ไหน|ที่)"),
    "กู": re.compile(r"กู(?![้๊๋])"),
    "สื่อ": re.compile(r"สื่อ(?!สาร)"),
}


def has_keyword(text: str, keywords) -> str | None:
    """The first keyword that really occurs in `text` (exclusions applied)."""
    lowered = (text or "").lower()
    for word in keywords:
        pattern = _KEYWORD_EXCLUSIONS.get(word)
        if (pattern.search(lowered) if pattern else word in lowered):
            return word
    return None


CATEGORY_KEYWORDS = {
    "A1": ("ฟ้อง", "ทนาย", "ดำเนินคดี", "ศาล", "แจ้งความ"),
    "A2": ("สคบ", "ร้องเรียน", "กระทรวง", "พาณิชย์", "คุ้มครองผู้บริโภค", "เพจ", "เฟซบุ๊ก", "เฟสบุ๊ค",
           "facebook", "สื่อ", "ข่าว", "โพสต์", "ประจาน"),
    "A3": ("หัวหน้า", "ผู้จัดการ", "supervisor", "ผู้บริหาร"),
    "A4": ("แม่ง", "เหี้ย", "ควย", "สัส", "มึง", "กู"),
    "C1": ("แพ้", "ผื่น", "คัน", "แสบ", "ระคายเคือง", "หายใจ", "เชื้อรา", "สารเคมี", "บาดเจ็บ"),
    "C2": ("น้ำท่วม", "ไฟไหม้", "อุทกภัย"),
    "C3": ("ค่าเสียหาย", "ชดเชย", "เยียวยา"),
}
# Agent misconduct is high severity, so a quote that merely exists is not
# enough: on a real call the 12B model raised B2 for an agent and customer
# sorting out an item name ("ไม่เห็นพ็อปเปอร์" — "เป็นผ้าปู ไม่ใช่พ็อปเปอร์").
# B1/B3 need the rude or refusing words in the agent's quote; B2 needs the
# customer to say they were told wrong — a plain "ไม่ใช่" is ordinary clarifying.
_MISCONDUCT_WORDS = {
    "B1": CATEGORY_KEYWORDS["A4"] + ("เรื่องของคุณ", "ช่างคุณ", "ฟังไม่รู้เรื่อง", "พูดไม่รู้เรื่อง", "โง่"),
    "B3": ("ช่วยไม่ได้", "ไม่ใช่หน้าที่", "ไม่เกี่ยวกับเรา", "ไม่เกี่ยวกับทางเรา", "ไปติดต่อเอง",
           "ไม่รับผิดชอบ", "วางสาย"),
}
_TOLD_WRONG_WORDS = (
    "บอกผิด", "แจ้งผิด", "ให้ข้อมูลผิด", "ข้อมูลผิด", "บอกไม่ตรง", "แจ้งไม่ตรง", "พูดไม่ตรง",
    "ไม่ตรงกับที่บอก", "ไม่ตรงกับที่แจ้ง", "ไม่เหมือนที่บอก", "ตอนแรกบอกว่า", "เมื่อกี้บอกว่า", "โกหก",
)
# Words strong enough to flag on their own when a CUSTOMER says them — the
# model missed a rash/allergy complaint and a swearing customer on real calls.
_BACKSTOP_KEYWORDS = {
    "A1": ("ฟ้อง", "ทนาย", "ดำเนินคดี", "แจ้งความ"),
    "A2": ("สคบ", "คุ้มครองผู้บริโภค"),
    "C1": ("แพ้", "ผื่น", "แสบจมูก", "แสบตา", "ระคายเคือง", "หายใจไม่", "เชื้อรา", "สารเคมี", "บาดเจ็บ"),
    "A4": ("แม่ง", "เหี้ย", "ควย", "สัส", "มึง"),
}
_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}
CATEGORY_LABELS_TH = {
    "A1": "ลูกค้าขู่ดำเนินคดี", "A2": "ลูกค้าขู่ร้องเรียนหน่วยงาน/สื่อ", "A3": "ลูกค้าขอคุยกับหัวหน้า",
    "A4": "ลูกค้าใช้คำหยาบ", "B1": "พนักงานพูดไม่สุภาพ", "B2": "พนักงานให้ข้อมูลผิด",
    "B3": "พนักงานปฏิเสธไม่ช่วย", "C1": "ลูกค้าได้รับผลกระทบต่อสุขภาพจากสินค้า",
    "C2": "สินค้าเสียหายจากภัยพิบัติ", "C3": "ลูกค้าเรียกค่าเสียหาย", "D1": "สายขัดข้อง",
}


def _snippet(line: str, keyword: str, width: int = 45) -> str:
    """The words around `keyword`, cut on spaces so Thai words stay whole."""
    at = max(0, line.lower().find(keyword))
    start, end = max(0, at - width), min(len(line), at + len(keyword) + width)
    while start > 0 and line[start - 1] != " ":
        start -= 1
    while end < len(line) and line[end] != " ":
        end += 1
    return line[start:end].strip()


def keyword_anomaly(conversation_text: str) -> dict | None:
    """Most severe backstop hit in the customer's lines, or None.

    Only labelled Customer lines are scanned, so the agent repeating the
    customer's words ("ลูกค้าแจ้งว่าแพ้") cannot trigger it.
    """
    lines = [
        line.split(":", 1)[1]
        for line in (conversation_text or "").splitlines()
        if line.strip().lower().startswith("customer:")
    ]
    hits = []
    for category, words in _BACKSTOP_KEYWORDS.items():
        for line in lines:
            word = has_keyword(line, words)
            if word:
                hits.append((category, _snippet(line, word)))
                break
    if not hits:
        return None
    category, quote = min(hits, key=lambda h: _SEVERITY_RANK[SEVERITY_BY_CATEGORY[h[0]]])
    return {
        "anomaly_detected": True,
        "anomaly_reason": f"[{category}] {CATEGORY_LABELS_TH[category]} — evidence: \"{quote}\"",
        "anomaly_severity": SEVERITY_BY_CATEGORY[category],
    }


_CATEGORY_RE = re.compile(r"\b([ABCD][1-4])\b")
_LEGACY_EVIDENCE_RE = re.compile(r"evidence\s*:\s*[\"“']?(.+?)[\"”']?\s*$", re.IGNORECASE | re.DOTALL)


def _infer_category(quote: str) -> str:
    for category in ("A1", "A2", "A3", "C1", "C2", "C3", "A4"):
        if has_keyword(quote, CATEGORY_KEYWORDS[category]):
            return category
    return ""


def misconduct_is_grounded(category: str, quote: str, conversation_text: str) -> bool:
    """A B-category flag is backed by what the agent said (and, for B2, the customer's objection)."""
    if not agent_said(quote, conversation_text):
        return False
    if category == "B2":
        return has_keyword(speaker_text(conversation_text, "Customer"), _TOLD_WRONG_WORDS) is not None
    return has_keyword(quote, _MISCONDUCT_WORDS[category]) is not None


def verify_anomaly(result: dict, conversation_text: str) -> dict:
    """{anomaly_detected, anomaly_reason, anomaly_severity} after checking the evidence."""
    nothing = keyword_anomaly(conversation_text) or {
        "anomaly_detected": False, "anomaly_reason": "", "anomaly_severity": "",
    }
    if not isinstance(result, dict) or not _truthy(result.get("anomaly_detected")):
        return nothing

    reason = " ".join(str(result.get("reason") or result.get("anomaly_reason") or "").split())
    quote = " ".join(str(result.get("evidence_quote") or "").split())
    if not quote:
        legacy = _LEGACY_EVIDENCE_RE.search(reason)
        quote = legacy.group(1).strip() if legacy else ""
    if not quote_in_text(quote, conversation_text):
        return nothing

    found = _CATEGORY_RE.search(str(result.get("category") or "")) or _CATEGORY_RE.search(reason)
    category = found.group(1) if found and found.group(1) in SEVERITY_BY_CATEGORY else ""
    if category in CATEGORY_KEYWORDS and not has_keyword(quote, CATEGORY_KEYWORDS[category]):
        category = _infer_category(quote)   # wrong code, but the quote may fit another
    if category.startswith("B") and not misconduct_is_grounded(category, quote, conversation_text):
        category = _infer_category(quote)
    if not category:
        category = _infer_category(quote)
    if not category:
        return nothing

    explanation = re.sub(r"^\[[^\]]*\]\s*", "", reason.split(" — evidence")[0]).strip() or CATEGORY_LABELS_TH[category]
    return {
        "anomaly_detected": True,
        "anomaly_reason": f"[{category}] {explanation} — evidence: \"{quote}\"",
        "anomaly_severity": SEVERITY_BY_CATEGORY[category],
    }


# ── Topics ───────────────────────────────────────────────────────────────

TOPICS = (
    "แจ้งปัญหาสินค้า",
    "สอบถามข้อมูลสินค้า",
    "สอบถามการจัดส่ง",
    "ร้องเรียนบริการ",
    "สอบถามประกัน/Warranty",
    "คืน/เปลี่ยน/Trade-in",
    "สอบถามโปรโมชั่น",
    "ติดตามเคส",
    "อื่นๆ",
)
_TOPIC_STEMS = (
    ("แจ้งปัญหาสินค้า", ("ปัญหาสินค้า", "แจ้งปัญหา", "ชำรุด")),
    ("สอบถามการจัดส่ง", ("จัดส่ง",)),
    ("สอบถามประกัน/Warranty", ("ประกัน", "warranty", "เคลม")),
    ("คืน/เปลี่ยน/Trade-in", ("คืน", "เปลี่ยน", "trade")),
    ("ร้องเรียนบริการ", ("ร้องเรียน",)),
    ("สอบถามโปรโมชั่น", ("โปรโมชั่น", "โปร", "ส่วนลด")),
    ("ติดตามเคส", ("ติดตาม",)),
    ("สอบถามข้อมูลสินค้า", ("ข้อมูลสินค้า", "สอบถามสินค้า")),
)


def normalize_topic(raw) -> str:
    """Clamp the model's topic to the fixed list ("อื่นๆ: ..." → "อื่นๆ")."""
    text = " ".join(str(raw or "").split())
    if text in TOPICS:
        return text
    lowered = text.lower()
    for topic, stems in _TOPIC_STEMS:
        if any(stem in lowered for stem in stems):
            return topic
    return "อื่นๆ"


# ── Brands and platforms ─────────────────────────────────────────────────

# canonical name → spellings that count as a mention (lower-case). Thai STT
# often mangles brand names, so the common misspellings are listed too.
BRAND_ALIASES: dict[str, tuple[str, ...]] = {
    "Lotus (โลตัส)": ("lotus", "โลตัส"),
    "Omazz": ("omazz", "โอมาซ", "โอแมซ", "โอมาส", "โอมาสนา"),
    "Restonic": ("restonic", "เรสโทนิค", "เรสโตนิค", "เรสโทนิก", "เรสโตนิก"),
    "Slumberland": ("slumberland", "สลัมเบอร์แลนด์", "สลัมเบอแลนด์", "สลัมเบอร์แลน"),
    "Dunlopillo": ("dunlopillo", "ดันล็อปพิลโล", "ดันลอปพิลโล", "ดันลอปปิลโล", "ดันล็อป"),
    "Sealy": ("sealy", "ซีลี่", "ซีลี"),
    "Simmons": ("simmons", "ซิมมอนส์"),
    "Serta": ("serta", "เซอร์ต้า"),
    "King Koil": ("king koil", "คิงคอยล์"),
    "Therapedic": ("therapedic", "เทอราพีดิค"),
    "Synda": ("synda", "ซินดา"),
    "Satin": ("satin", "ซาติน"),
}
# The agent's greeting names the company, not a product brand.
_COMPANY_GREETING_RE = re.compile(r"(?:กลุ่ม)?บริษัท\s*ที่นอน\s*(?:ใน\s*)?(?:เครือ\s*)?โลตัส")

PLATFORM_ALIASES: dict[str, tuple[str, ...]] = {
    "Shopee": ("shopee", "ช้อปปี้", "ช็อปปี้", "ชอปปี้", "ช๊อปปี้"),
    "Lazada": ("lazada", "ลาซาด้า", "ลาซาดา"),
    "TikTok Shop": ("tiktok", "ติ๊กต็อก", "ติ๊กต๊อก", "ติกตอก"),
    "LINE": ("line", "ไลน์"),
    "Facebook": ("facebook", "เฟซบุ๊ก", "เฟสบุ๊ค", "เฟซบุ๊ค", "เพจ"),
    "เว็บไซต์": ("website", "เว็บไซต์", "เว็บ"),
    "หน้าร้าน/ห้าง": ("หน้าร้าน", "ห้าง", "สาขา", "โชว์รูม"),
}


def _canonical(name: str, aliases: dict[str, tuple[str, ...]]) -> str | None:
    lowered = " ".join(str(name or "").split()).lower()
    if not lowered:
        return None
    for canonical, spellings in aliases.items():
        if lowered == canonical.lower() or any(s in lowered for s in spellings):
            return canonical
    return None


def _mentioned(spellings: tuple[str, ...], text: str) -> bool:
    for s in spellings:
        if re.fullmatch(r"[a-z ]+", s):
            if re.search(rf"(?<![a-z]){re.escape(s)}(?![a-z])", text):
                return True
        elif s in text:
            return True
    return False


def canonical_mentions(raw, conversation_text: str, aliases: dict[str, tuple[str, ...]]) -> list[str]:
    """Keep only names actually said in the call, under one canonical spelling."""
    if not isinstance(raw, list):
        return []
    text = _COMPANY_GREETING_RE.sub(" ", (conversation_text or "")).lower()
    kept: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            continue
        canonical = _canonical(item, aliases)
        if canonical is None:
            # A name we don't know: keep it only if it literally occurs.
            name = " ".join(item.split())
            if name.lower() in text and name not in kept:
                kept.append(name)
            continue
        if canonical not in kept and _mentioned(aliases[canonical], text):
            kept.append(canonical)
    return kept


def canonical_name(name: str, aliases: dict[str, tuple[str, ...]]) -> str:
    """Display-time grouping for rows saved before canonicalisation."""
    return _canonical(name, aliases) or " ".join(str(name or "").split())
