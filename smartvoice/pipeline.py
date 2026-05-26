import json
import re
import time
import traceback
from datetime import datetime, timedelta, timezone
from smartvoice import db, ollama_client
from smartvoice.config import CASE_RECENCY_HOURS
from smartvoice.logger import get_logger
from smartvoice.stt import transcribe_diarized as _transcribe_diarized

log = get_logger(__name__)

# Phrases that only an Agent (company rep) would say in Thai call centers
_AGENT_MARKERS = [
    "คุณลูกค้า", "ขออนุญาต", "รบกวนทาง", "ทางเราจะ", "ทางบริษัท",
    "ดำเนินการให้", "ตรวจสอบให้", "ขอรับเรื่อง", "ขอเรียนสาย",
    "ต้องขออภัย", "ขอโทษนะครับ", "ขอโทษนะค่ะ", "นำไปปรับปรุง",
    "ขอบคุณที่แจ้ง", "ขอบคุณที่ติดต่อ", "ไม่ทราบว่าคุณลูกค้า", "รับเรื่องไว้",
    "ขอบพระคุณค่ะ", "ขอบพระคุณครับ", "ยินดีให้บริการ", "หากมีข้อสงสัยเพิ่มเติม",
    "ของเราไม่มีบริการทำความสะอาด", "เราไม่ได้มีบริการทำความสะอาด", "ไม่ได้มีบริการทำความสะอาด",
    "เราไม่ได้มีเรื่องบริการทำความสะอาด", "ขออนุญาตแนะนำได้", "ไม่เหมาะกับการเอามาใช้งาน",
    "อยู่นอกเหนือประกัน", "นอกเหนือประกัน", "โปรโมชั่นพิเศษสำหรับลูกค้า", "โปรราคาพิเศษ",
    "ไม่ถูกสุขลักษณะ",
    "ต้องขอแสดงความเสียใจ", "ขอแสดงความเสียใจ", "ไม่มี Trade-in", "ไม่มีเทรดอิน", "ตามนโยบาย",
    # Domain-specific: agent self-references + company speak
    "ทางเจ้าหน้าที่", "เจ้าหน้าที่ให้เขา", "ประสานงาน", "ระบบเรา", "ระบบของเรา",
    "บริษัทเรา", "บริษัทปิด", "เปิดทำการ", "ตรวจสต๊อก", "ตรวจสอบระบบ",
    "ขอตรวจสอบ", "ให้ดูเพิ่มเติม", "ดำเนินการ", "ไปส่งค่ะ", "ไปส่งนะคะ",
    "คอนเฟิร์มวัน", "คอนเฟิร์มโทร", "โทรคอนเฟิร์ม", "แจ้งให้ทราบ",
]

_AGENT_CLOSING_MARKERS = [
    "ขอบพระคุณค่ะ", "ขอบพระคุณครับ", "ขอบคุณที่ติดต่อ", "ยินดีให้บริการ",
    "หากมีข้อสงสัยเพิ่มเติม",
]

_CUSTOMER_ENDING_MARKERS = [
    "ขอบคุณมาก", "ขอบคุณค่ะ", "ขอบคุณครับ", "โอเค", "ตัดใจได้", "วางแผนต่อไป",
]

_OPENING_AGENT_MARKERS = [
    "กลุ่มบริษัทที่นอนโลตัส", "บริษัทที่นอนโลตัส", "ขอบคุณที่ติดต่อ", "ยินดีให้บริการ",
]

_CUSTOMER_MARKERS = [
    "สอบถาม", "อยากทราบ", "พอดี", "ของพี่", "ของผม", "ของหนู",
    "น้ำท่วม", "ทำความสะอาด", "ส่งกลับเข้าบริษัท", "พี่จะได้",
    "พี่พยายาม", "กลิ่นคล้ายเชื้อรา", "ตัดสินใจ", "ตัดใจได้",
    "อยู่ในเครือ", "สอบถามหน่อย", "ปกติที่ร้าน", "ถ้าจะส่งกลับ", "ประกันหรือเปล่า",
    "โครงสร้างใช่ไหม", "ถูกต้องไหม", "วางแผนต่อไป", "Trade-in เหมือนสินค้าชนิดอื่นไหม",
    "ทางบริษัทมี Trade-in",
    # Domain-specific: customer self-reference "พี่" + action verbs
    "พี่ก็สะดวก", "พี่สะดวก", "พี่ก็ได้", "พี่ได้นะ", "พี่เลือก", "พี่ขอ",
    "พี่ให้ไว้", "พี่เซฟไว้", "พี่เมม", "พี่ติด", "พี่นัดไว้", "พี่เลื่อน",
    "พี่เอง", "พี่ก็ไม่", "พี่เหมือน", "พี่จะบอก", "พี่เนี่ย", "พี่ดูปฏิทิน",
    # Customer-direct-request patterns
    "ขอเลื่อน", "ขอเลือกวัน", "ติดตามเรื่อง", "จะขอเลือก", "ไม่สะดวก",
    "ไม่สามารถเข้าไป", "ติดประชุม", "ลางาน", "เปิดบ้าน", "รับสินค้า",
    "ให้ไว้สองเบอร์", "ให้ไว้อีกเบอร์",
    # Customer (elder) addressing agent (younger) by vocatives
    "ได้ไหมลูก", "ได้ไหมหนู", "นะลูก", "ค่ะลูก", "อ่ะลูก", "จ๊ะลูก",
    "ยังไงลูก", "นะน้อง", "อยู่นะคะน้อง", "ค่ะน้อง", "พลอยจ๋า", "พลอยจ้า",
]

# ---------------------------------------------------------------------------
# Strong-cue regex patterns — high-confidence speaker indicators used by
# `_aggressive_relabel_from_strong_cues` to override LLM decisions.
#
# Design rationale
# ----------------
# The LLM `correct_speakers` step is conservative and occasionally preserves
# Pyannote's wrong labels on mega-segments. Rather than trust the LLM alone,
# we apply deterministic domain rules after it runs: if a text chunk contains
# an unambiguous cue (e.g. customer self-refers as "พี่ก็สะดวก" or vocatively
# addresses the agent as "ลูก"), we force the correct label.
# ---------------------------------------------------------------------------

# Word-boundary sensitive: "พี่" must be followed by an action verb (not name).
# Matches "พี่ก็", "พี่จะ", "พี่สะดวก", …
_CUSTOMER_STRONG_RE = re.compile(
    r"(?:"
    r"พี่(?:ก็|จะ|สะดวก|ได้|เลือก|ให้ไว้|เซฟ|เมม|เลื่อน|ติด|ขอ|เอง|นัดไว้|เนี่ย|เหมือน|ดูปฏิทิน|จะบอก)"
    r"|ได้ไหม(?:ลูก|หนู)"
    r"|(?:นะ|ค่ะ|อ่ะ|จ๊ะ|ยังไง)ลูก(?:\s|$)"
    r"|(?:นะ|ค่ะ)น้อง(?:\s|$)"
    r"|อยู่นะคะน้อง"
    r"|พลอยจ๋า|พลอยจ้า"
    r"|ขอเลื่อน(?:วัน|นัด)?"
    r"|ขอเลือกวันรับ"
    r"|ติดตามเรื่อง(?:การ)?ส่ง"
    r"|ติดประชุม|ลางาน|เปิดบ้าน"
    r"|ไม่สามารถเข้า(?:ไป|รับ)"
    r"|ให้ไว้(?:สอง|อีก)เบอร์"
    r")"
)

# Agent self-name "พลอย" or STT variants, plus unambiguous company speak
_AGENT_STRONG_RE = re.compile(
    r"(?:"
    r"พลอย(?:ขอ|ดู|ระบุ|เกรง|ไม่แน่ใจ|จะได้|อาจ|จ๋า)?"
    r"|พอย(?:ขอ|ดู|ระบุ|เกรง|ไม่แน่ใจ|จะได้|อาจ)"
    r"|คุณลูกค้า"
    r"|ทาง(?:บริษัท|เรา|เจ้าหน้าที่)"
    r"|ระบบ(?:เรา|ของเรา)"
    r"|กลุ่มบริษัทที่นอน"
    r"|ขอบคุณที่ติดต่อ"
    r"|ยินดีให้บริการ"
    r"|ขอบพระคุณ(?:ค่ะ|ครับ)"
    r"|คอนเฟิร์ม(?:วัน|โทร)"
    r"|ตรวจ(?:สอบระบบ|สต๊อก|สอบให้)"
    r"|บริษัท(?:เรา|ปิด|เปิดทำการ)"
    r")"
)

_DOMAIN_NORMALIZATIONS = [
    (re.compile(r"เลสเทอร์นิ[กค]ซ์|เลสโทนิ[กค]|เรสโทนิ[กค]|เรสโทนิก|เลสโทรนิก", re.IGNORECASE), "Restonic"),
    (re.compile(r"Restonic(?:ส์|ซ์|ส)?", re.IGNORECASE), "Restonic"),
    (re.compile(r"เทรด\s*-?\s*in|เทรดอิน|เทิร์นอิน|เทรินอิน", re.IGNORECASE), "Trade-in"),
    (re.compile(r"อุปกรณ์ไผ่|อุปกรณ์ภัย|อุปกรณ์ภั[ยย]"), "อุทกภัย"),
    (re.compile(r"เชื้อร้า|เซลลา|เซื้อรา"), "เชื้อรา"),
    (re.compile(r"ผูกสุขลักษณะ"), "ถูกสุขลักษณะ"),
    (re.compile(r"ส่งกับเข้าบริษัท|ส่งกับบริษัท"), "ส่งกลับเข้าบริษัท"),
    (re.compile(r"สุราษ(?:ฎ์|ฎร|ร์)?(?:ธานี)?|สุราษฐม"), "สุราษฎร์ธานี"),
    (re.compile(r"หัดใหญ่"), "หาดใหญ่"),
    (re.compile(r"(น้ำท่วมที่|อยู่ทางทีมที่|ที่)ขนาดใหญ่"), lambda m: f"{m.group(1)}หาดใหญ่"),
    (re.compile(r"ผัดใหญ่"), "หาดใหญ่"),
    (re.compile(r"นำทั่ว|น้ำทั่ว"), "น้ำท่วม"),
    (re.compile(r"ชักยังไง"), "ซักยังไง"),
    (re.compile(r"ผัดอยู่"), "เพาะอยู่"),
    (re.compile(r"จัดโต"), "จัดโปร"),
    (re.compile(r"สเต็ปปลับไป|สเต็ปปับไป"), "สเต็ปต่อไป"),
    (re.compile(r"อยู่ดูแลนอกเหนือประกัน"), "อยู่นอกเหนือประกัน"),
    (re.compile(r"ทางข้าง"), "ทางห้าง"),
    (re.compile(r"(?:มีหน้า|เออไม่ได้)เขาทิ้งกันเยอะ"), "มิน่าเขาทิ้งกันเยอะ"),
    # Common STT confusions from Whisper Thai
    (re.compile(r"โทรศัพท์(?:ความเสียใจ|แสดงความเสียใจ)"), "ขอแสดงความเสียใจ"),
    (re.compile(r"โทรศัพท์โดยการทำ(?:คน|คนสะอาด|ความ)สะอาด"), "บริการทำความสะอาด"),
    (re.compile(r"ทำคนสะอาด"), "ทำความสะอาด"),
    (re.compile(r"เส้นงงาน|เส้นหน้า"), "ใช้งาน"),
    (re.compile(r"โฟนทางใต้"), "โซนภาคใต้"),
    (re.compile(r"โฟนภาค"), "โซนภาค"),
    (re.compile(r"โตที่เฉพาะ"), "โปรที่เฉพาะ"),
    (re.compile(r"ตัวประคัน"), "โปรราคา"),
    (re.compile(r"ตัวประกัน(?=พิเศษ)"), "โปรราคา"),
    (re.compile(r"โปรโมคัน"), "โปรโมชั่น"),
    (re.compile(r"การเทรดการเทรดการคืนการเทรน"), "การเทิร์น การคืน"),
    (re.compile(r"การเทรน(?=นะคะ|ค่ะ|ครับ)"), "การเทิร์น"),
    (re.compile(r"ต่อให้ทางคุณลูกค้าต่างตากไฟถึง"), "ต่อให้ทางคุณลูกค้าตากตากแดด"),
    (re.compile(r"ต่อให้ทางเอ่อคุณลูกค้าตากตากไว้ถึง"), "ต่อให้ทางคุณลูกค้าตากตากแดด"),
    (re.compile(r"(อยู่ใน)\s*\1"), r"\1"),
    (re.compile(r"(น้ำหก)\s*\1"), r"\1"),
    (re.compile(r"ได้ได้"), "ได้"),
    (re.compile(r"นำ้"), "น้ำ"),
    (re.compile(r"ไม๊"), "ไหม"),
    (re.compile(r"ขึ้\s*นมา"), "ขึ้นมา"),
    (re.compile(r"ทำความสาด"), "ทำความสะอาด"),
    (re.compile(r"ส่วนใจ"), "สนใจ"),
    (re.compile(r"ขัดใหญ่"), "หาดใหญ่"),
    (re.compile(r"โทรที่เฉพาะ"), "โปรที่เฉพาะ"),
    (re.compile(r"โทรศัพท์พิเศษ|โตรศัพท์พิเศษ"), "โปรราคาพิเศษ"),
    (re.compile(r"จัดโทร"), "จัดโปร"),
    (re.compile(r"อุทกรรมภัย"), "อุทกภัย"),
    (re.compile(r"ใกล้หน้า(?=เนี่ย|นะ)"), "ใช้งาน"),
    (re.compile(r"กันเทรดกันเทรดกันคืนกันเทรน"), "การเทิร์น การคืน"),
    (re.compile(r"กันเทรน(?=นะคะ|ค่ะ|อะไร)"), "การเทิร์น"),
]

_ANSWER_PATTERN_TEXT = r"(?:อ๋อ\s*)?(?:ใช่ครับ|ใช่ค่ะ|ถูกต้องครับ|ถูกต้องค่ะ|ครับผม)(?:\s*คุณลูกค้า)?"

_QUESTION_PLUS_ANSWER_PATTERNS = [
    re.compile(
        rf"^(?P<question>.+?(?:ไหมคะ|ไหมครับ|ไหมฮะ|ใช่ไหมคะ|ใช่ไหมครับ|ใช่ไหมฮะ|ใช่ไหม|หรือเปล่าคะ|หรือเปล่าครับ|ได้ไหมคะ|ได้ไหมครับ)\??)\s*(?P<answer>{_ANSWER_PATTERN_TEXT})(?P<tail>.+)$"
    ),
    re.compile(
        rf"^(?P<question>.+?(?:ไหมคะ|ไหมครับ|ไหมฮะ|ใช่ไหมคะ|ใช่ไหมครับ|ใช่ไหมฮะ|ใช่ไหม|หรือเปล่าคะ|หรือเปล่าครับ|ได้ไหมคะ|ได้ไหมครับ)\??)\s*(?P<answer>{_ANSWER_PATTERN_TEXT})$"
    ),
]

_QUESTION_TOKENS = ("ไหม", "มั้ย", "ไหมฮะ", "ใช่ไหม", "ใช่ไหมฮะ", "หรือเปล่า", "ได้ไหม", "อะไรไหม", "ถูกต้องไหม", "?")
_SHORT_AGENT_ANSWER_KEYS = {
    "ใช่ครับ", "ใช่ค่ะ", "ถูกต้องครับ", "ถูกต้องค่ะ", "ครับผม",
    "ได้เลยครับ", "ได้เลยค่ะ", "อ๋อใช่ครับ", "อ๋อใช่ค่ะ",
    "ใช่ครับคุณลูกค้า", "ใช่ค่ะคุณลูกค้า", "อ๋อใช่ครับคุณลูกค้า", "อ๋อใช่ค่ะคุณลูกค้า",
}

_ANSWER_PREFIX_RE = re.compile(rf"^(?P<answer>{_ANSWER_PATTERN_TEXT})")

_FOLLOWUP_QUESTION_MARKERS = ("ทีนี้", "ทีเนี้ย", "แล้ว", "งั้น", "โอเค")
_OPENING_CUSTOMER_SPLIT_MARKERS = (
    "พี่สอบถามหน่อย", "สอบถามหน่อย", "ตัวที่นอน", "อยู่ในเครือ", "อยากทราบ", "พอดี",
)
_TRAILING_CUSTOMER_SPLIT_MARKERS = (
    "อ๋อ", "อืม", "เออ", "พี่จะได้", "ปกติไม่เกี่ยวกับประกัน", "โครงสร้างใช่ไหม", "ก็คือมันซักยังไง",
)
_EMBEDDED_CUSTOMER_REACTION_MARKERS = (
    "มิน่าเขาทิ้งกันเยอะ", "มีหน้าเขาทิ้งกันเยอะ", "อ๋อค่ะเหรอ", "อ๋อเหรอ",
)
_LEADING_AGENT_CONTINUATION_MARKERS = (
    "ก็คือ", "คือมัน", "มันจะแห้ง", "ใช่มันจะ", "มันจะเพาะ", "แต่ว่าข้างใน", "ซึ่งถ้าเกิดว่า",
)
_CUSTOMER_RESUME_MARKERS = (
    "แต่ว่าข้างในเนี้ยคือพี่", "แต่ว่าข้างในเนี่ยคือพี่", "พี่พยายาม", "พี่จะถาม",
    "พี่ก็เลยคิดว่า", "เดี๋ยวลองลองถามบริษัท", "เดี๋ยวลองถามบริษัท", "ลองถามบริษัท",
)
_EMBEDDED_AGENT_RESUME_RE = re.compile(
    r"(?P<reaction>.+?)\s*(?P<resume>(?:(?:เออ|อือ|อืม|อ๋อ|ค่ะ|ครับ)\s*)*(?:ใช่ครับ|ใช่ค่ะ|ถูกต้องครับ|ถูกต้องค่ะ|ครับผม).+)$"
)

def _text_key(text: str) -> str:
    text = text.casefold()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[\"'“”‘’?!.,:;()\[\]{}\-–—_/\\]", "", text)
    return text

def _has_question_cue(text: str) -> bool:
    return any(token in text for token in _QUESTION_TOKENS)

def _marker_positions(text: str, markers: tuple[str, ...], min_pos: int = 0, reverse: bool = False) -> list[int]:
    positions = {
        match.start()
        for marker in markers
        for match in re.finditer(re.escape(marker), text)
        if match.start() >= min_pos
    }
    return sorted(positions, reverse=reverse)

def _is_short_agent_answer(text: str) -> bool:
    return _text_key(text) in {_text_key(value) for value in _SHORT_AGENT_ANSWER_KEYS}

_BACKCHANNEL_KEYS = {
    _text_key(value)
    for value in (
        "อ๋อ", "อ๋อค่ะ", "อ๋อครับ", "อืม", "อืมค่ะ", "อืมครับ",
        "อือ", "เออ", "เออค่ะ", "เออครับ", "ค่ะ", "ครับ",
        "โอเค", "โอเคค่ะ", "โอเคครับ", "เหรอ", "อ๋อเหรอ", "ได้ค่ะ", "ได้ครับ",
    )
}

def _is_backchannel(text: str) -> bool:
    return _text_key(text) in _BACKCHANNEL_KEYS

def _apply_domain_normalization(conversation: list[dict]) -> list[dict]:
    if not conversation:
        return conversation

    result: list[dict] = []
    for item in conversation:
        text = item.get("text", "")
        normalized = text
        for pattern, replacement in _DOMAIN_NORMALIZATIONS:
            normalized = pattern.sub(replacement, normalized)
        result.append({**item, "text": normalized})
    return result

def _sort_conversation(conversation: list[dict]) -> list[dict]:
    if not conversation:
        return conversation

    return sorted(
        (dict(item) for item in conversation if item.get("text", "").strip()),
        key=lambda item: (
            float(item.get("start", 0) or 0),
            float(item.get("end", item.get("start", 0)) or item.get("start", 0) or 0),
        ),
    )

def _drop_redundant_opening_segments(conversation: list[dict]) -> list[dict]:
    if len(conversation) < 2:
        return conversation

    opening_window = conversation[:4]
    if not any(_looks_like_agent_opening(item.get("text", "")) for item in opening_window):
        return conversation

    drop_indexes: set[int] = set()
    for idx, item in enumerate(opening_window):
        text = item.get("text", "").strip()
        key = _text_key(text)
        if not text or len(key) < 12 or _looks_like_agent_opening(text):
            continue
        for later_idx, later in enumerate(opening_window[idx + 1 :], start=idx + 1):
            later_key = _text_key(later.get("text", ""))
            if len(later_key) >= len(key) + 8 and key in later_key:
                drop_indexes.add(idx)
                break

    if not drop_indexes:
        return conversation
    return [dict(item) for idx, item in enumerate(conversation) if idx not in drop_indexes]

def _drop_adjacent_duplicate_segments(conversation: list[dict]) -> list[dict]:
    if not conversation:
        return conversation

    result: list[dict] = []
    for item in conversation:
        text = item.get("text", "").strip()
        if not text:
            continue
        if result:
            prev_text = result[-1].get("text", "").strip()
            prev_key = _text_key(prev_text)
            curr_key = _text_key(text)
            if curr_key and (curr_key == prev_key or (len(curr_key) >= 12 and curr_key in prev_key)):
                if len(text) > len(prev_text):
                    result[-1] = dict(item)
                continue
        result.append(dict(item))
    return result

def _merge_adjacent_same_speaker(conversation: list[dict], gap_sec: float = 0.6) -> list[dict]:
    if not conversation:
        return conversation

    merged: list[dict] = []
    for item in _sort_conversation(conversation):
        text = item.get("text", "").strip()
        if not text:
            continue
        if (
            merged
            and merged[-1].get("speaker") == item.get("speaker")
            and (float(item.get("start", 0) or 0) - float(merged[-1].get("end", 0) or 0)) <= gap_sec
        ):
            merged[-1]["text"] += " " + text
            merged[-1]["end"] = max(
                float(merged[-1].get("end", 0) or 0),
                float(item.get("end", item.get("start", 0)) or item.get("start", 0) or 0),
            )
            continue
        merged.append(dict(item))
    return merged

def _split_answer_prefixed_turns(conversation: list[dict]) -> list[dict]:
    if not conversation:
        return conversation

    output: list[dict] = []
    for item in conversation:
        text = item.get("text", "").strip()
        if not text:
            continue

        match = _ANSWER_PREFIX_RE.match(text)
        if not match:
            output.append(item)
            continue

        answer = match.group("answer").strip()
        remainder = text[match.end() :].strip()
        if not answer or not remainder:
            output.append(item)
            continue
        if not (_has_question_cue(remainder) or _customer_score(remainder) >= 2):
            output.append(item)
            continue

        start = item.get("start", 0)
        end = item.get("end", start)
        duration = max(end - start, 0)
        ratio = len(answer) / max(len(text), 1)
        split_time = start + (duration * ratio) if duration > 0 else start

        output.append({
            **item,
            "speaker": "Agent",
            "text": answer,
            "start": start,
            "end": split_time,
        })
        output.append({
            **item,
            "speaker": "Customer",
            "text": remainder,
            "start": split_time,
            "end": end,
        })
    return output

def _split_embedded_customer_reaction_turns(conversation: list[dict]) -> list[dict]:
    if not conversation:
        return conversation

    output: list[dict] = []
    for item in conversation:
        text = item.get("text", "").strip()
        if not text or item.get("speaker") != "Agent":
            output.append(item)
            continue

        positions = _marker_positions(
            text,
            _EMBEDDED_CUSTOMER_REACTION_MARKERS,
            min_pos=max(int(len(text) * 0.2), 18),
        )
        if not positions:
            output.append(item)
            continue

        applied = False
        for split_at in positions:
            prefix = text[:split_at].strip()
            suffix = text[split_at:].strip()
            if not prefix or not suffix or _agent_score(prefix) < 2:
                continue

            resume_match = _EMBEDDED_AGENT_RESUME_RE.match(suffix)
            if not resume_match:
                continue

            reaction = resume_match.group("reaction").strip()
            resume = resume_match.group("resume").strip()
            if not reaction or not resume:
                continue
            if len(reaction) < 8 or len(resume) < 8:
                continue
            if _customer_score(reaction) < 1 and not any(token in reaction for token in ("มิน่า", "มีหน้า", "เหรอ")):
                continue

            start = item.get("start", 0)
            end = item.get("end", start)
            duration = max(end - start, 0)
            first_ratio = len(prefix) / max(len(text), 1)
            second_ratio = (len(prefix) + len(reaction)) / max(len(text), 1)
            first_end = start + (duration * first_ratio) if duration > 0 else start
            second_end = start + (duration * second_ratio) if duration > 0 else end
            second_end = max(first_end, min(second_end, end))

            output.append({
                **item,
                "speaker": "Agent",
                "text": prefix,
                "start": start,
                "end": first_end,
            })
            output.append({
                **item,
                "speaker": "Customer",
                "text": reaction,
                "start": first_end,
                "end": second_end,
            })
            output.append({
                **item,
                "speaker": "Agent",
                "text": resume,
                "start": second_end,
                "end": end,
            })
            applied = True
            break

        if not applied:
            output.append(item)
    return output

def _split_leading_agent_continuation_turns(conversation: list[dict]) -> list[dict]:
    if len(conversation) < 2:
        return conversation

    output: list[dict] = []
    for idx, item in enumerate(conversation):
        text = item.get("text", "").strip()
        if not text or item.get("speaker") != "Customer" or idx == 0:
            output.append(dict(item))
            continue

        prev_item = output[-1] if output else conversation[idx - 1]
        prev_text = prev_item.get("text", "").strip()
        if prev_item.get("speaker") != "Agent":
            output.append(dict(item))
            continue
        if not (_is_short_agent_answer(prev_text) or prev_text.startswith(("ใช่ค่ะ", "ใช่ครับ", "ถูกต้องค่ะ", "ถูกต้องครับ"))):
            output.append(dict(item))
            continue
        if not text.startswith(_LEADING_AGENT_CONTINUATION_MARKERS):
            output.append(dict(item))
            continue

        positions = _marker_positions(text, _CUSTOMER_RESUME_MARKERS, min_pos=max(int(len(text) * 0.2), 12))
        if not positions:
            output.append(dict(item))
            continue

        split_at = positions[0]
        prefix = text[:split_at].strip()
        suffix = text[split_at:].strip()
        if not prefix or not suffix:
            output.append(dict(item))
            continue
        if _customer_score(suffix) < 1:
            output.append(dict(item))
            continue

        start = item.get("start", 0)
        end = item.get("end", start)
        duration = max(end - start, 0)
        ratio = len(prefix) / max(len(text), 1)
        split_time = start + (duration * ratio) if duration > 0 else start

        output.append({
            **item,
            "speaker": "Agent",
            "text": prefix,
            "start": start,
            "end": split_time,
        })
        output.append({
            **item,
            "speaker": "Customer",
            "text": suffix,
            "start": split_time,
            "end": end,
        })
    return output

_EMBEDDED_AGENT_ANSWER_RE = re.compile(
    rf"\s+(?P<answer>{_ANSWER_PATTERN_TEXT})\s+"
)

def _split_embedded_agent_answer_turns(conversation: list[dict]) -> list[dict]:
    """Split Customer turns that contain an embedded Agent answer.

    Pattern: <customer question> อ๋อ ใช่ค่ะ คุณลูกค้า <customer continuation>
    """
    if not conversation:
        return conversation

    output: list[dict] = []
    for item in conversation:
        text = item.get("text", "").strip()
        if not text or item.get("speaker") != "Customer" or len(text) < 30:
            output.append(item)
            continue

        match = _EMBEDDED_AGENT_ANSWER_RE.search(text)
        if not match:
            output.append(item)
            continue

        before = text[:match.start()].strip()
        answer = match.group("answer").strip()
        after = text[match.end():].strip()

        if not before or not after or len(before) < 10 or len(after) < 10:
            output.append(item)
            continue
        if _customer_score(before) < 1 and not _has_question_cue(before):
            output.append(item)
            continue

        start = item.get("start", 0)
        end = item.get("end", start)
        duration = max(end - start, 0)
        r1 = len(before) / max(len(text), 1)
        r2 = (len(before) + len(answer)) / max(len(text), 1)
        t1 = start + duration * r1 if duration > 0 else start
        t2 = start + duration * r2 if duration > 0 else end
        t2 = max(t1, min(t2, end))

        output.append({**item, "speaker": "Customer", "text": before, "start": start, "end": t1})
        output.append({**item, "speaker": "Agent", "text": answer, "start": t1, "end": t2})
        output.append({**item, "speaker": "Customer", "text": after, "start": t2, "end": end})
        continue

    return output


def _split_opening_mixed_turns(conversation: list[dict]) -> list[dict]:
    if not conversation:
        return conversation

    output: list[dict] = []
    for item in conversation:
        text = item.get("text", "").strip()
        if not text or not _looks_like_agent_opening(text):
            output.append(item)
            continue

        positions = [
            text.find(marker)
            for marker in _OPENING_CUSTOMER_SPLIT_MARKERS
            if text.find(marker) > 0
        ]
        if not positions:
            output.append(item)
            continue

        split_at = min(positions)
        opening = text[:split_at].strip()
        remainder = text[split_at:].strip()
        if not opening or not remainder:
            output.append(item)
            continue
        if _agent_score(opening) < 2:
            output.append(item)
            continue
        if not (_has_question_cue(remainder) or _customer_score(remainder) >= 2):
            output.append(item)
            continue

        start = item.get("start", 0)
        end = item.get("end", start)
        duration = max(end - start, 0)
        ratio = len(opening) / max(len(text), 1)
        split_time = start + (duration * ratio) if duration > 0 else start

        output.append({
            **item,
            "speaker": "Agent",
            "text": opening,
            "start": start,
            "end": split_time,
        })
        output.append({
            **item,
            "speaker": "Customer",
            "text": remainder,
            "start": split_time,
            "end": end,
        })
    return output


# Thai sentence-ending particles + English '?' act as boundaries.
# The lookahead `(?=\s)` ensures we only split when STT recorded a pause/space
# after the particle, which is a reliable proxy for an actual prosodic break.
# Pattern order matters — longer particles first so "นะคะ" is not chopped as "นะ" + "คะ".
_SENTENCE_END_RE = re.compile(
    r"(?P<end>นะคะ|นะครับ|ไหมคะ|ไหมครับ|เหรอคะ|เหรอครับ|ใช่ไหม|ใช่มั้ย"
    r"|ค่ะ|คะ|ครับ|คับ|จ๊ะ|จ้ะ|เหรอ|หรอ|นะ|\?)(?=\s)"
)

# Thai turn-initial discourse markers — act as split points when preceded by space.
# Used as a fallback when no polite-particle boundary exists in a long sentence.
# Restricted to high-confidence turn-change interjections/address terms to avoid
# false-splitting on common continuations like "แต่"/"เพราะ" that occur mid-turn.
_SENTENCE_START_RE = re.compile(
    r"\s(?=อ้าว|อ๋อ|เอ๊ะ|โอเค|คุณลูกค้า|พี่ขอ|หนูถ้า|พี่ก็|พี่สะดวก|ได้เลยค่ะ|ได้ค่ะ)"
)

# Only split segments longer than this — shorter ones are probably already
# a single coherent turn and re-splitting would fragment the flow.
_MIN_CHARS_FOR_SPLIT = 160
# If a single sentence after the primary split still exceeds this length,
# apply the turn-initial-marker fallback split inside it. Lowered from 180 to 80
# so that short mixed-speaker clauses ("คุณลูกค้า อ้าวไม่ใช่...") also get split.
_HARD_CHUNK_MAX_CHARS = 80
# Group every N sentences into one sub-segment so we don't fire correct_speakers
# on dozens of trivial chunks like "ค่ะ".
_SENTENCES_PER_CHUNK = 2


def _split_long_segments_by_sentence(conversation: list[dict]) -> list[dict]:
    """Split very long segments at Thai sentence boundaries.

    Rationale
    ---------
    Pyannote occasionally merges multiple speaker turns into a single
    segment (e.g. when two speakers share similar voice characteristics).
    The downstream LLM `correct_speakers` step supports a `parts` split, but
    empirically struggles to find accurate split points in very long
    segments — it tends to rubber-stamp the existing label.

    By pre-splitting long segments at polite-particle boundaries ("ค่ะ ",
    "ครับ ", "นะคะ ", "?", …) we give the LLM a much simpler per-chunk
    classification task. Timestamps are allocated proportionally to
    character length so timeline ordering is preserved.

    Speaker label is kept identical across all sub-chunks (we trust
    `correct_speakers` to re-label them).
    """
    if not conversation:
        return conversation

    output: list[dict] = []
    for item in conversation:
        text = (item.get("text") or "").strip()
        if len(text) < _MIN_CHARS_FOR_SPLIT:
            output.append(item)
            continue

        # Find all sentence-boundary positions (end index, exclusive)
        boundaries = [m.end() for m in _SENTENCE_END_RE.finditer(text)]
        if not boundaries:
            output.append(item)
            continue

        # Slice text into sentences using the boundaries
        raw_sentences: list[str] = []
        prev = 0
        for b in boundaries:
            piece = text[prev:b].strip()
            if piece:
                raw_sentences.append(piece)
            prev = b
        tail = text[prev:].strip()
        if tail:
            raw_sentences.append(tail)

        # Fallback: any sentence still exceeding _HARD_CHUNK_MAX_CHARS is
        # split further at turn-initial discourse markers (อ้าว, อ๋อ, …).
        sentences: list[str] = []
        for s in raw_sentences:
            if len(s) <= _HARD_CHUNK_MAX_CHARS:
                sentences.append(s)
                continue
            split_points = [m.start() for m in _SENTENCE_START_RE.finditer(s)]
            if not split_points:
                sentences.append(s)
                continue
            cursor = 0
            for sp in split_points:
                piece = s[cursor:sp].strip()
                if piece:
                    sentences.append(piece)
                cursor = sp
            trailing = s[cursor:].strip()
            if trailing:
                sentences.append(trailing)

        if len(sentences) <= 1:
            output.append(item)
            continue

        # Group every _SENTENCES_PER_CHUNK sentences into one chunk
        chunks: list[str] = []
        for i in range(0, len(sentences), _SENTENCES_PER_CHUNK):
            chunk = " ".join(sentences[i:i + _SENTENCES_PER_CHUNK]).strip()
            if chunk:
                chunks.append(chunk)

        if len(chunks) <= 1:
            output.append(item)
            continue

        # Allocate time proportionally to character length
        start = float(item.get("start", 0) or 0)
        end = float(item.get("end", start) or start)
        duration = max(end - start, 0.0)
        total_chars = sum(len(c) for c in chunks)

        cursor = start
        for idx, chunk in enumerate(chunks):
            if idx == len(chunks) - 1:
                # Ensure the last chunk lands exactly on the original end
                chunk_end = end
            elif duration > 0 and total_chars > 0:
                chunk_end = cursor + duration * (len(chunk) / total_chars)
            else:
                chunk_end = cursor
            output.append({
                **item,
                "text": chunk,
                "start": cursor,
                "end": chunk_end,
            })
            cursor = chunk_end
    return output


def _aggressive_relabel_from_strong_cues(conversation: list[dict]) -> list[dict]:
    """Force-re-label segments whose text contains an unambiguous domain cue.

    Applied after LLM `correct_speakers` to catch cases where the model was too
    conservative (e.g. kept a whole mega-segment labelled "Agent" even though
    it clearly contains customer self-references like "พี่สะดวก" or vocatives
    like "ได้ไหมลูก").

    Rules
    -----
    1. If text matches _CUSTOMER_STRONG_RE AND does NOT match _AGENT_STRONG_RE
       → force "Customer".
    2. If text matches _AGENT_STRONG_RE AND does NOT match _CUSTOMER_STRONG_RE
       → force "Agent".
    3. If BOTH match → the segment is mixed; leave as-is (another splitter can
       handle it, or we defer to the LLM's original decision).
    4. If NEITHER matches → leave as-is.
    """
    if not conversation:
        return conversation

    result: list[dict] = []
    for item in conversation:
        text = (item.get("text") or "").strip()
        if not text:
            result.append(item)
            continue

        has_customer = bool(_CUSTOMER_STRONG_RE.search(text))
        has_agent = bool(_AGENT_STRONG_RE.search(text))

        new_item = dict(item)
        if has_customer and not has_agent:
            new_item["speaker"] = "Customer"
        elif has_agent and not has_customer:
            new_item["speaker"] = "Agent"
        # else: mixed or no cue — keep existing label

        result.append(new_item)
    return result


def _split_mixed_question_answer_turns(conversation: list[dict]) -> list[dict]:
    if not conversation:
        return conversation

    output: list[dict] = []
    for item in conversation:
        text = item.get("text", "").strip()
        if not text:
            continue

        match = None
        for pattern in _QUESTION_PLUS_ANSWER_PATTERNS:
            match = pattern.match(text)
            if match:
                break
        if not match:
            output.append(item)
            continue

        question = match.group("question").strip()
        answer = match.group("answer").strip()
        tail = (match.groupdict().get("tail") or "").strip()
        if not question or not answer:
            output.append(item)
            continue

        question_agent_score = _agent_score(question)
        question_customer_score = _customer_score(question)
        question_speaker = item.get("speaker")
        if question_speaker == "Agent" and question_customer_score >= question_agent_score + 2:
            question_speaker = "Customer"
        elif question_speaker == "Customer" and question_agent_score >= question_customer_score + 2:
            question_speaker = "Agent"
        elif question_speaker not in ("Agent", "Customer"):
            question_speaker = "Agent" if question_agent_score > question_customer_score else "Customer"
        answer_speaker = "Customer" if question_speaker == "Agent" else "Agent"

        start = item.get("start", 0)
        end = item.get("end", start)
        duration = max(end - start, 0)
        ratio = len(question) / max(len(text), 1)
        split_time = start + (duration * ratio) if duration > 0 else start

        tail_speaker = None
        if tail:
            tail_agent_score = _agent_score(tail)
            tail_customer_score = _customer_score(tail)
            if (_has_question_cue(tail) and tail_customer_score >= tail_agent_score) or tail_customer_score >= tail_agent_score + 2:
                tail_speaker = question_speaker
            else:
                answer = f"{answer} {tail}".strip()

        answer_end = end
        if tail_speaker is not None:
            answer_ratio = (len(question) + len(answer)) / max(len(text), 1)
            answer_end = min(end, start + (duration * answer_ratio)) if duration > 0 else end
            answer_end = max(split_time, answer_end)

        output.append({
            **item,
            "speaker": question_speaker,
            "text": question,
            "start": start,
            "end": split_time,
        })
        output.append({
            **item,
            "speaker": answer_speaker,
            "text": answer,
            "start": split_time,
            "end": answer_end,
        })
        if tail_speaker is not None:
            answer_end = output[-1]["end"]
            output.append({
                **item,
                "speaker": tail_speaker,
                "text": tail,
                "start": answer_end,
                "end": end,
            })
    return output

def _split_followup_question_turns(conversation: list[dict]) -> list[dict]:
    if not conversation:
        return conversation

    output: list[dict] = []
    for item in conversation:
        text = item.get("text", "").strip()
        if not text:
            continue

        positions = _marker_positions(text, _FOLLOWUP_QUESTION_MARKERS, min_pos=1)
        if not positions:
            output.append(item)
            continue

        split_at = min(positions)
        prefix = text[:split_at].strip()
        suffix = text[split_at:].strip()
        if not prefix or not suffix or not _has_question_cue(suffix):
            output.append(item)
            continue

        prefix_agent_score = _agent_score(prefix)
        suffix_agent_score = _agent_score(suffix)
        suffix_customer_score = _customer_score(suffix)
        if prefix_agent_score < 2:
            output.append(item)
            continue
        if suffix_agent_score >= suffix_customer_score + 3 or _looks_like_agent_opening(suffix):
            output.append(item)
            continue

        start = item.get("start", 0)
        end = item.get("end", start)
        duration = max(end - start, 0)
        ratio = len(prefix) / max(len(text), 1)
        split_time = start + (duration * ratio) if duration > 0 else start

        output.append({
            **item,
            "speaker": "Agent",
            "text": prefix,
            "start": start,
            "end": split_time,
        })
        output.append({
            **item,
            "speaker": "Customer",
            "text": suffix,
            "start": split_time,
            "end": end,
        })
    return output

def _split_trailing_customer_question_turns(conversation: list[dict]) -> list[dict]:
    if not conversation:
        return conversation

    output: list[dict] = []
    for item in conversation:
        text = item.get("text", "").strip()
        if not text or item.get("speaker") != "Agent" or not _has_question_cue(text):
            output.append(item)
            continue

        min_pos = max(int(len(text) * 0.35), 24)
        positions = _marker_positions(text, _TRAILING_CUSTOMER_SPLIT_MARKERS, min_pos=min_pos, reverse=True)
        if not positions:
            output.append(item)
            continue

        split_at = None
        prefix = ""
        suffix = ""
        for candidate in positions:
            candidate_prefix = text[:candidate].strip()
            candidate_suffix = text[candidate:].strip()
            if not candidate_prefix or not candidate_suffix:
                continue

            prefix_agent_score = _agent_score(candidate_prefix)
            suffix_agent_score = _agent_score(candidate_suffix)
            suffix_customer_score = _customer_score(candidate_suffix)
            if prefix_agent_score < 2 and len(candidate_prefix) < 40:
                continue
            if suffix_customer_score < 2 and not _has_question_cue(candidate_suffix):
                continue
            if suffix_agent_score >= suffix_customer_score + 2:
                continue

            split_at = candidate
            prefix = candidate_prefix
            suffix = candidate_suffix
            break

        if split_at is None:
            output.append(item)
            continue

        start = item.get("start", 0)
        end = item.get("end", start)
        duration = max(end - start, 0)
        ratio = len(prefix) / max(len(text), 1)
        split_time = start + (duration * ratio) if duration > 0 else start

        output.append({
            **item,
            "speaker": "Agent",
            "text": prefix,
            "start": start,
            "end": split_time,
        })
        output.append({
            **item,
            "speaker": "Customer",
            "text": suffix,
            "start": split_time,
            "end": end,
        })
    return output

def _stabilize_sandwiched_turns(conversation: list[dict]) -> list[dict]:
    if len(conversation) < 3:
        return conversation

    result = [dict(item) for item in conversation]
    for idx in range(1, len(result) - 1):
        prev_item = result[idx - 1]
        item = result[idx]
        next_item = result[idx + 1]
        surrounding_speaker = prev_item.get("speaker")
        text = item.get("text", "").strip()
        if not text:
            continue
        if surrounding_speaker != next_item.get("speaker") or item.get("speaker") == surrounding_speaker:
            continue
        if _is_backchannel(text) or _is_short_agent_answer(text):
            continue

        duration = max(
            float(item.get("end", item.get("start", 0)) or item.get("start", 0) or 0)
            - float(item.get("start", 0) or 0),
            0,
        )
        if duration > 4.0 and len(text) > 40:
            continue

        if any(marker in text for marker in _EMBEDDED_CUSTOMER_REACTION_MARKERS):
            continue

        agent_score = _agent_score(text)
        customer_score = _customer_score(text)
        if surrounding_speaker == "Agent" and customer_score >= agent_score + 3:
            continue
        if surrounding_speaker == "Customer" and agent_score >= customer_score + 3:
            continue
        result[idx]["speaker"] = surrounding_speaker
    return result

def _looks_like_agent_opening(text: str) -> bool:
    text = text.strip()
    if any(marker in text for marker in ("ขอบคุณที่ติดต่อ", "ยินดีให้บริการ")):
        return True
    return text.startswith(("สวัสดีครับ", "สวัสดีค่ะ")) and any(
        marker in text for marker in _OPENING_AGENT_MARKERS
    )

def _agent_score(text: str) -> int:
    score = sum(2 for marker in _AGENT_MARKERS if marker in text)
    score += sum(2 for marker in _AGENT_CLOSING_MARKERS if marker in text)
    if _looks_like_agent_opening(text):
        score += 4
    return score

def _customer_score(text: str) -> int:
    score = sum(1 for marker in _CUSTOMER_MARKERS if marker in text)
    if _has_question_cue(text):
        score += 1
    if any(token in text for token in ["อยู่ในเครือ", "สอบถามหน่อย", "ประกันหรือเปล่า", "โครงสร้างใช่ไหม", "ถูกต้องไหม"]):
        score += 2
    if "Trade-in" in text and _has_question_cue(text):
        score += 2
    if any(token in text for token in ["ขอบคุณมาก", "โอเค", "วางแผนต่อไป"]):
        score += 1
    return score

def _map_raw_speakers_from_opening(conversation: list[dict]) -> list[dict]:
    if not conversation:
        return conversation

    raw_speakers = sorted({
        item.get("speaker")
        for item in conversation
        if item.get("speaker") not in ("Agent", "Customer")
    })
    if len(raw_speakers) != 2:
        return conversation

    agent_raw = None
    for item in conversation[:3]:
        speaker = item.get("speaker")
        text = item.get("text", "")
        if speaker in raw_speakers and (_looks_like_agent_opening(text) or _agent_score(text) >= 3):
            agent_raw = speaker
            break

    if agent_raw is None:
        return conversation

    customer_raw = next((speaker for speaker in raw_speakers if speaker != agent_raw), None)
    mapped: list[dict] = []
    for item in conversation:
        speaker = item.get("speaker")
        if speaker == agent_raw:
            speaker = "Agent"
        elif customer_raw and speaker == customer_raw:
            speaker = "Customer"
        mapped.append({**item, "speaker": speaker})
    return mapped

def _enforce_role_rules(conversation: list[dict]) -> list[dict]:
    if not conversation:
        return conversation

    fixed: list[dict] = []
    for idx, item in enumerate(conversation):
        text = item.get("text", "").strip()
        if not text:
            continue

        agent_score = _agent_score(text)
        customer_score = _customer_score(text)
        new_item = dict(item)

        if idx == 0 and _looks_like_agent_opening(text):
            new_item["speaker"] = "Agent"
        elif idx > 0 and fixed and _is_short_agent_answer(text) and _has_question_cue(fixed[-1].get("text", "")):
            new_item["speaker"] = "Agent"
        elif idx > 0 and fixed and fixed[-1].get("speaker") == "Agent" and customer_score >= 1 and agent_score == 0:
            new_item["speaker"] = "Customer"
        elif agent_score >= 2 and customer_score == 0:
            new_item["speaker"] = "Agent"
        elif customer_score >= 2 and agent_score == 0:
            new_item["speaker"] = "Customer"
        elif item.get("speaker") == "Agent" and agent_score == 0 and _has_question_cue(text) and customer_score >= 3:
            new_item["speaker"] = "Customer"
        elif item.get("speaker") == "Customer" and agent_score >= customer_score + 2:
            new_item["speaker"] = "Agent"
        elif item.get("speaker") == "Agent" and customer_score >= agent_score + 2:
            new_item["speaker"] = "Customer"

        fixed.append(new_item)
    return fixed

def _fix_diarization_swap(conversation: list[dict]) -> tuple[list[dict], str | None]:
    if not conversation:
        return conversation, None

    agent_score: dict[str, int] = {}
    for item in conversation:
        speaker = item["speaker"]
        score = sum(1 for marker in _AGENT_MARKERS if marker in item.get("text", ""))
        agent_score[speaker] = agent_score.get(speaker, 0) + score

    if len(agent_score) < 2:
        return conversation, None

    agent_speaker = max(agent_score, key=agent_score.get)
    scores = sorted(agent_score.values(), reverse=True)
    if scores[0] == 0 or scores[0] == scores[1]:
        return conversation, None

    result: list[dict] = []
    for item in conversation:
        text = item.get("text", "")
        has_agent_marker = any(marker in text for marker in _AGENT_MARKERS)
        if has_agent_marker and item["speaker"] != agent_speaker:
            result.append({**item, "speaker": agent_speaker})
        else:
            result.append(item)
    return result, agent_speaker

def _split_mixed_closing_turns(conversation: list[dict]) -> list[dict]:
    if not conversation:
        return conversation

    output: list[dict] = []
    for item in conversation:
        text = item.get("text", "").strip()
        if not text:
            continue

        positions = [
            (text.find(marker), marker)
            for marker in _AGENT_CLOSING_MARKERS
            if text.find(marker) > 0
        ]
        if not positions:
            output.append(item)
            continue

        split_at, _ = min(positions, key=lambda value: value[0])
        prefix = text[:split_at].strip()
        suffix = text[split_at:].strip()
        if not prefix or not suffix:
            output.append(item)
            continue

        prefix_has_customer_cue = any(marker in prefix for marker in _CUSTOMER_ENDING_MARKERS)
        prefix_has_question = _has_question_cue(prefix) or "ขอบคุณ" in prefix
        if not (item.get("speaker") == "Customer" or prefix_has_customer_cue or prefix_has_question):
            output.append(item)
            continue

        start = item.get("start", 0)
        end = item.get("end", start)
        duration = max(end - start, 0)
        ratio = len(prefix) / max(len(text), 1)
        split_time = start + (duration * ratio) if duration > 0 else start

        first_speaker = "Customer" if (item.get("speaker") == "Customer" or prefix_has_customer_cue) else item.get("speaker", "Customer")
        output.append({
            **item,
            "speaker": first_speaker,
            "text": prefix,
            "start": start,
            "end": split_time,
        })
        output.append({
            **item,
            "speaker": "Agent",
            "text": suffix,
            "start": split_time,
            "end": end,
        })
    return output

def _parse_iso(ts: str | None) -> datetime | None:
    """Parse an ISO timestamp string, tolerating naive timestamps (assumed UTC)."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _call_datetime_from_filename(filename: str | None) -> datetime | None:
    if not filename:
        return None
    match = re.search(r"(?<!\d)(20\d{12})(?!\d)", filename)
    if not match:
        return None
    try:
        dt = datetime.strptime(match.group(1), "%Y%m%d%H%M%S")
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone(timedelta(hours=7))).astimezone(timezone.utc)


def _effective_call_datetime(call: dict | None) -> datetime | None:
    if not call:
        return None
    return _call_datetime_from_filename(call.get("filename")) or _parse_iso(call.get("created_at"))


def _auto_assign_case(call_id: int, analysis: dict) -> None:
    """After analysis, attach this call to an existing case or create a new one.

    Strategy (in order of preference):
      1. **Recency short-circuit** — if the customer has an open case whose
         most-recent call is within CASE_RECENCY_HOURS, attach to that case
         without consulting the LLM. Consecutive calls from the same customer
         (dropped call, follow-up, call-back) are almost always the same case
         even when the topic drifts.
      2. **LLM matching** — for older open cases, ask the LLM to match by
         topic/summary, with recency info included in the prompt.
      3. **New case** — if no match, create a new case.
    """
    try:
        link = db.get_call_customer_link(call_id)
        if not link:
            return  # No customer linked — skip case assignment

        customer_id = link["customer_id"]
        new_topic = analysis.get("topic", "")
        new_summary = analysis.get("summary", "")

        open_cases = db.get_open_cases_by_customer(customer_id)

        # No open cases → create one directly (no LLM needed)
        if not open_cases:
            subject = new_topic or new_summary[:60] or "เรื่องทั่วไป"
            case_id = db.create_case(customer_id, subject)
            db.assign_call_to_case(call_id, case_id)
            return

        # Enrich cases with: (a) call summaries for LLM context
        # (b) latest_call_at for recency short-circuit + LLM context
        call = db.get_call_by_id(call_id)
        call_dt = _effective_call_datetime(call)

        for cs in open_cases:
            case_calls = db.get_calls_by_case(cs["id"])
            summaries = [c.get("summary", "")[:120] for c in case_calls if c.get("summary")]
            cs["call_summaries"] = " | ".join(summaries) if summaries else "-"
            case_datetimes = [
                dt for dt in (_effective_call_datetime(c) for c in case_calls)
                if dt is not None
            ]
            cs["latest_call_at"] = max(case_datetimes).isoformat() if case_datetimes else None

        # (1) Recency short-circuit — attach to the most-recently-updated
        # open case if the time gap is within the configured window.
        if CASE_RECENCY_HOURS > 0 and call_dt is not None:
            window = timedelta(hours=CASE_RECENCY_HOURS)
            for cs in open_cases:
                latest_dt = _parse_iso(cs.get("latest_call_at"))
                if latest_dt is None:
                    continue
                gap = abs((call_dt - latest_dt).total_seconds())
                if gap <= window.total_seconds():
                    log.info(
                        "Auto-merge: call_id=%s → case #%s "
                        "(same customer, %.1f min since last call)",
                        call_id, cs["id"], gap / 60.0,
                    )
                    db.assign_call_to_case(call_id, cs["id"])
                    db.update_case_status(cs["id"], "follow_up")
                    return

        # (2) LLM matching — for cases older than the recency window
        result = ollama_client.match_case(new_topic, new_summary, open_cases)
        matched_id = result.get("match_case_id")
        valid_ids = {cs["id"] for cs in open_cases}
        if matched_id and matched_id in valid_ids:
            db.assign_call_to_case(call_id, matched_id)
            db.update_case_status(matched_id, "follow_up")
            return

        # (3) New case
        subject = result.get("suggested_subject") or new_topic or "เรื่องทั่วไป"
        case_id = db.create_case(customer_id, subject)
        db.assign_call_to_case(call_id, case_id)
    except Exception:
        # Case assignment is non-critical — log but don't break the pipeline
        log.exception("_auto_assign_case failed for call_id=%s", call_id)


def process_call(call_id: int, step_callback=None) -> dict:
    call = db.get_call_by_id(call_id)
    if not call:
        raise ValueError(f"Call ID {call_id} not found")

    if call["status"] != "processing":
        db.update_call_status(call_id, "processing")
    _start = time.time()

    def _step(msg: str):
        db.update_processing_step(call_id, msg)
        if step_callback:
            step_callback(msg)

    try:
        _step("🎙 [1/4] กำลังถอดเสียงและแยกผู้พูด (WhisperX)...")
        raw_segments = _transcribe_diarized(
            call["file_path"], step_callback=step_callback
        )

        MERGE_GAP_SEC = 0.2
        merged: list[dict] = []
        for item in _sort_conversation(raw_segments):
            if not item.get("text"):
                continue
            if (
                merged
                and merged[-1]["speaker"] == item.get("speaker")
                and (item.get("start", 0) - merged[-1].get("end", 0)) <= MERGE_GAP_SEC
            ):
                merged[-1]["text"] += " " + item["text"]
                merged[-1]["end"] = item.get("end", merged[-1].get("end", 0))
            else:
                merged.append({
                    "speaker": item.get("speaker", "Speaker"),
                    "text": item["text"],
                    "start": item.get("start", 0),
                    "end": item.get("end", 0),
                })

        # Absorb isolated short segments into the previous speaker
        # Short = fewer than 4 words AND duration < 2s — likely a diarization flip
        SHORT_CHARS = 15
        SHORT_SEC = 2.0
        stabilized: list[dict] = []
        for item in merged:
            dur = item.get("end", 0) - item.get("start", 0)
            char_count = len(item["text"].strip())
            if (
                stabilized
                and stabilized[-1]["speaker"] != item["speaker"]
                and char_count < SHORT_CHARS
                and dur < SHORT_SEC
                and not (_is_short_agent_answer(item["text"]) and _has_question_cue(stabilized[-1].get("text", "")))
            ):
                stabilized[-1]["text"] += " " + item["text"]
                stabilized[-1]["end"] = item.get("end", stabilized[-1].get("end", 0))
            else:
                stabilized.append(dict(item))
        conversation = _sort_conversation(stabilized)
        conversation = _stabilize_sandwiched_turns(conversation)
        conversation = _merge_adjacent_same_speaker(conversation)
        conversation = _map_raw_speakers_from_opening(conversation)
        conversation = _apply_domain_normalization(conversation)
        conversation = _split_opening_mixed_turns(conversation)
        conversation = _enforce_role_rules(conversation)
        conversation = _split_answer_prefixed_turns(conversation)
        conversation = _split_embedded_agent_answer_turns(conversation)
        conversation = _split_mixed_question_answer_turns(conversation)
        conversation = _split_followup_question_turns(conversation)
        conversation = _split_embedded_customer_reaction_turns(conversation)
        conversation = _split_trailing_customer_question_turns(conversation)
        conversation = _split_leading_agent_continuation_turns(conversation)
        conversation = _stabilize_sandwiched_turns(conversation)
        conversation = _merge_adjacent_same_speaker(conversation)
        conversation = _drop_redundant_opening_segments(conversation)
        conversation = _drop_adjacent_duplicate_segments(conversation)

        _step("🧹 [2/4] กำลังตรวจแก้บทถอดเสียงด้วย AI...")
        conversation = ollama_client.cleanup_transcript(conversation)
        conversation = _sort_conversation(conversation)
        conversation = _split_opening_mixed_turns(conversation)
        conversation = _split_answer_prefixed_turns(conversation)
        conversation = _split_embedded_agent_answer_turns(conversation)
        conversation = _split_mixed_question_answer_turns(conversation)
        conversation = _split_followup_question_turns(conversation)
        conversation = _split_embedded_customer_reaction_turns(conversation)
        conversation = _split_trailing_customer_question_turns(conversation)
        conversation = _split_leading_agent_continuation_turns(conversation)
        conversation = _stabilize_sandwiched_turns(conversation)
        conversation = _merge_adjacent_same_speaker(conversation)
        conversation = _apply_domain_normalization(conversation)
        conversation = _drop_redundant_opening_segments(conversation)
        conversation = _drop_adjacent_duplicate_segments(conversation)

        # Pre-split any remaining long segments at Thai sentence boundaries so
        # correct_speakers only has to classify short, single-turn chunks
        # instead of finding split points inside multi-speaker mega-segments.
        conversation = _split_long_segments_by_sentence(conversation)

        _step("🗣️ [3/4] กำลังแก้ Speaker Turn ที่ปนกันด้วย AI...")
        conversation = ollama_client.correct_speakers(conversation)
        # Aggressive deterministic override — catches cases where the LLM was
        # too conservative and kept Pyannote's wrong label on segments with
        # unambiguous domain cues (e.g. "พี่ก็สะดวก", "ได้ไหมลูก", "พลอยขอ").
        conversation = _aggressive_relabel_from_strong_cues(conversation)
        conversation = _sort_conversation(conversation)
        conversation = _split_opening_mixed_turns(conversation)
        conversation = _split_answer_prefixed_turns(conversation)
        conversation = _split_embedded_agent_answer_turns(conversation)
        conversation = _split_mixed_question_answer_turns(conversation)
        conversation = _split_followup_question_turns(conversation)
        conversation = _split_embedded_customer_reaction_turns(conversation)
        conversation = _split_trailing_customer_question_turns(conversation)
        conversation = _split_leading_agent_continuation_turns(conversation)
        conversation = _split_mixed_closing_turns(conversation)
        conversation = _stabilize_sandwiched_turns(conversation)
        conversation = _aggressive_relabel_from_strong_cues(conversation)
        conversation = _merge_adjacent_same_speaker(conversation)
        conversation = _enforce_role_rules(conversation)
        conversation = ollama_client.cleanup_transcript(conversation)
        conversation = _sort_conversation(conversation)
        # Also pre-split long merged segments before the 2nd splitter pass so
        # the splitters (which rely on pattern matching at segment start/end)
        # can see turn boundaries inside mega-chunks.
        conversation = _split_long_segments_by_sentence(conversation)
        conversation = _aggressive_relabel_from_strong_cues(conversation)
        conversation = _split_opening_mixed_turns(conversation)
        conversation = _split_answer_prefixed_turns(conversation)
        conversation = _split_embedded_agent_answer_turns(conversation)
        conversation = _split_mixed_question_answer_turns(conversation)
        conversation = _split_followup_question_turns(conversation)
        conversation = _split_embedded_customer_reaction_turns(conversation)
        conversation = _split_trailing_customer_question_turns(conversation)
        conversation = _split_leading_agent_continuation_turns(conversation)
        conversation = _split_mixed_closing_turns(conversation)
        conversation = _stabilize_sandwiched_turns(conversation)
        conversation = _aggressive_relabel_from_strong_cues(conversation)
        conversation = _merge_adjacent_same_speaker(conversation)
        conversation = _enforce_role_rules(conversation)
        conversation = _apply_domain_normalization(conversation)
        conversation = _drop_redundant_opening_segments(conversation)
        conversation = _drop_adjacent_duplicate_segments(conversation)
        conversation = _sort_conversation(conversation)
        _step("🤖 [4/4] กำลังวิเคราะห์บทสนทนาด้วย AI...")
        analysis = ollama_client.analyze_transcript(conversation)

        # Apply LLM speaker_mapping (SPEAKER_XX → Agent/Customer) — most accurate
        llm_mapping = analysis.get("speaker_mapping", {})
        if isinstance(llm_mapping, str):
            try:
                llm_mapping = json.loads(llm_mapping)
            except Exception:
                llm_mapping = {}
        if llm_mapping:
            for item in conversation:
                sp = item.get("speaker", "")
                if sp in llm_mapping:
                    item["speaker"] = llm_mapping[sp]

        # Fallback: use heuristic if LLM mapping didn't assign any Agent/Customer
        if not any(item.get("speaker") in ("Agent", "Customer") for item in conversation):
            conversation, agent_speaker = _fix_diarization_swap(conversation)
            if agent_speaker:
                all_speakers = list({item["speaker"] for item in conversation})
                customer_speaker = next((s for s in all_speakers if s != agent_speaker), None)
                for item in conversation:
                    if item["speaker"] == agent_speaker:
                        item["speaker"] = "Agent"
                    elif customer_speaker and item["speaker"] == customer_speaker:
                        item["speaker"] = "Customer"

        # Rule-based correction: segments containing definitive Agent phrases
        for item in conversation:
            text = item.get("text", "")
            if item.get("speaker") != "Agent" and any(p in text for p in _AGENT_MARKERS):
                item["speaker"] = "Agent"
        conversation = _enforce_role_rules(conversation)

        transcript = "\n".join(
            f"{item['speaker']}: {item['text']}"
            for item in conversation
        )

        _step("💾 กำลังบันทึกผล...")
        db.update_call_results(
            call_id=call_id,
            transcript=transcript,
            summary=analysis["summary"],
            sentiment=analysis["sentiment"],
            topic=analysis["topic"],
            speaker_mapping=analysis.get("speaker_mapping", ""),
            agent_performance=analysis.get("agent_performance", ""),
            keywords=analysis.get("keywords", ""),
            brand_mentions=analysis.get("brand_mentions", ""),
            platform_mentions=analysis.get("platform_mentions", ""),
            anomaly_detected=analysis.get("anomaly_detected", False),
            anomaly_reason=analysis.get("anomaly_reason", ""),
            sentiment_reason=analysis.get("sentiment_reason", ""),
            anomaly_severity=analysis.get("anomaly_severity", ""),
            topic_detail=analysis.get("topic_detail", ""),
        )

        # ── Auto Case Assignment ──
        _step("📂 กำลังจัดกลุ่มเคส...")
        _auto_assign_case(call_id, analysis)

        elapsed = time.time() - _start
        elapsed_str = f"{int(elapsed // 60)}m {int(elapsed % 60)}s" if elapsed >= 60 else f"{int(elapsed)}s"
        _step(f"✅ เสร็จสิ้น ใช้เวลา {elapsed_str}")

        return {
            "call_id": call_id,
            "transcript": transcript,
            "conversation": conversation,
            "elapsed_seconds": elapsed,
            "elapsed_str": elapsed_str,
            **analysis,
        }

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        log.exception("process_call failed for call_id=%s", call_id)
        db.update_call_status(call_id, "error", error_msg=error_msg)
        raise
