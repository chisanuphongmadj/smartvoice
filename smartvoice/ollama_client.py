import json
import os
import re
import requests

from smartvoice import insight_rules
from smartvoice.logger import get_logger

log = get_logger(__name__)

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "scb10x/llama3.1-typhoon2-8b-instruct"


def _base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _model() -> str:
    return os.getenv("OLLAMA_MODEL", DEFAULT_MODEL)


def _normalize_llm_output(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json|text)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def _num_ctx() -> int:
    """Context window sent with every request.

    Ollama silently drops the *start* of a prompt that exceeds its context
    window, and its default differs between installs (2048-8192). The QA
    prompt plus a long call needs ~8k tokens, so it is set explicitly.
    """
    try:
        return max(4096, int(os.getenv("OLLAMA_NUM_CTX", "12288")))
    except ValueError:
        return 12288


def chat(
    system_prompt: str, user_prompt: str, *, temperature: float = 0, json_mode: bool = False
) -> str:
    url = f"{_base_url()}/api/chat"
    payload = {
        "model": _model(),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": _num_ctx()},
    }
    if json_mode:
        # Constrains decoding to a JSON object — no prose around it to strip.
        payload["format"] = "json"
        # Cap the answer: in JSON mode the model sometimes repeats list items
        # until the 600 s timeout (one real QA request hung for 10 minutes).
        # Every analysis answer fits well inside this.
        payload["options"]["num_predict"] = 1500
    response = requests.post(url, json=payload, timeout=600)
    response.raise_for_status()
    data = response.json()
    return data["message"]["content"]


def extract_json(raw: str) -> dict:
    raw = _normalize_llm_output(raw)
    decoder = json.JSONDecoder()
    for idx, char in enumerate(raw):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(raw[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError(f"No JSON object found in LLM response: {raw[:300]}")


def _extract_json_array(raw: str) -> list | None:
    raw = _normalize_llm_output(raw)
    decoder = json.JSONDecoder()
    for idx, char in enumerate(raw):
        if char != "[":
            continue
        try:
            value, _ = decoder.raw_decode(raw[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, list):
            return value
    return None


def correct_speakers(conversation: list[dict]) -> list[dict]:
    """Use LLM to verify and correct speaker assignments per segment."""
    from smartvoice.prompts import build_speaker_correction_prompt

    conversation_text = "\n".join(
        f"[{i}] {item.get('speaker', 'Unknown')}: {item.get('text', '')}"
        for i, item in enumerate(conversation)
        if item.get("text")
    )
    system, user = build_speaker_correction_prompt(conversation_text)
    try:
        raw = chat(system, user)
        corrections = _extract_json_array(raw)
        if not isinstance(corrections, list) or not corrections:
            log.warning(
                "correct_speakers: LLM response yielded no JSON array — skipping.\n"
                "  raw preview: %r",
                (raw or "")[:400],
            )
            return conversation
        # Defensive: LLM sometimes returns bare indices like [0, 3, 5] instead of
        # [{"idx": 0, "speaker": "Agent"}, ...]. Filter out non-dict entries so
        # .get() never crashes.
        non_dict_sample = [c for c in corrections if not isinstance(c, dict)][:3]
        corrections = [c for c in corrections if isinstance(c, dict)]
        if not corrections:
            log.warning(
                "correct_speakers: LLM returned array of non-dict entries — skipping.\n"
                "  sample non-dict items: %r\n"
                "  raw preview: %r",
                non_dict_sample,
                (raw or "")[:400],
            )
            return conversation
        # Build output — handle both simple speaker swap and segment split (parts)
        result: list[dict] = []
        correction_map = {c.get("idx"): c for c in corrections if c.get("idx") is not None}
        for i, item in enumerate(conversation):
            c = correction_map.get(i)
            if c is None:
                result.append(dict(item))
            elif "parts" in c:
                # Split segment into multiple sub-segments
                for part in c["parts"]:
                    speaker = part.get("speaker")
                    text = part.get("text", "").strip()
                    if speaker in ("Agent", "Customer") and text:
                        result.append({**item, "speaker": speaker, "text": text})
            else:
                speaker = c.get("speaker")
                new_item = dict(item)
                if speaker in ("Agent", "Customer"):
                    new_item["speaker"] = speaker
                result.append(new_item)
        return result
    except Exception:
        log.exception("correct_speakers failed — returning original conversation")
        return conversation


def cleanup_transcript(conversation: list[dict]) -> list[dict]:
    """Use LLM to fix garbled/hallucinated text from STT."""
    from smartvoice.prompts import build_transcript_cleanup_prompt

    if not conversation:
        return conversation

    # Build indexed text for the LLM
    conversation_text = "\n".join(
        f"[{i}] {item.get('speaker', 'Unknown')}: {item.get('text', '')}"
        for i, item in enumerate(conversation)
        if item.get("text")
    )

    system, user = build_transcript_cleanup_prompt(conversation_text)
    try:
        raw = _normalize_llm_output(chat(system, user))
        cleaned_map: dict[int, str | None] = {}
        for line in raw.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(r"\[(\d+)\]\s*[^:]+:\s*(.*)", line)
            if m:
                idx = int(m.group(1))
                text = m.group(2).strip()
                if text in ("<REMOVE>", "[REMOVE]", "REMOVE"):
                    cleaned_map[idx] = None
                else:
                    cleaned_map[idx] = text

        if not cleaned_map:
            return conversation

        result = []
        for i, item in enumerate(conversation):
            if i in cleaned_map and cleaned_map[i] is None:
                continue
            new_item = dict(item)
            if i in cleaned_map and cleaned_map[i]:
                new_item["text"] = cleaned_map[i]
            result.append(new_item)
        return result
    except Exception:
        log.exception("cleanup_transcript failed — returning original conversation")
        return conversation


# ~7k tokens of Thai; with the longest prompt this stays inside _num_ctx().
MAX_CHARS = 14000
# When a call is longer, keep its opening and its ending (greeting, problem,
# and what was agreed at the close) and drop the middle.
HEAD_SHARE = 0.4
_ELLIPSIS_LINE = "...(ตัดช่วงกลางของบทสนทนาออกเพราะยาวเกิน)..."


def _normalize_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1")
    return False


def _coerce_score(value, default: int = 3, minimum: int = 1, maximum: int = 5) -> int:
    if isinstance(value, bool):
        return default
    try:
        score = int(float(value))
    except (TypeError, ValueError):
        score = default
    return max(minimum, min(maximum, score))


_PROMPT_EXAMPLE_NEXT_ACTION_TOKENS = (
    "15,000",
    "REG0012",
    "081-987-9336",
    "Restonic Queen",
    "Slumberland King",
    "Dunlopillo Queen",
)


def _looks_like_copied_next_action_example(next_action: str, conversation_text: str) -> bool:
    return any(
        token in next_action and token not in conversation_text
        for token in _PROMPT_EXAMPLE_NEXT_ACTION_TOKENS
    )


def _fallback_next_action_from_conversation(conversation_text: str) -> tuple[str, str]:
    text = conversation_text.lower()
    if any(k in text for k in ("คืนเงิน", "โอนเงิน", "รีฟันด์", "refund")):
        return (
            "ติดตามการคืนเงินลูกค้า | รายละเอียดตามบทสนทนา | ไม่ระบุในสาย (แนะนำ: ภายใน 7 วันทำการ) | โทรแจ้งลูกค้าและบันทึกผลใน CRM",
            "ฝ่ายบัญชี",
        )
    if any(k in text for k in ("qc", "ตรวจสอบคุณภาพ", "ตรวจสินค้า", "ตรวจที่นอน", "เชื้อรา", "ชำรุด", "เสียหาย", "น้ำท่วม")):
        return (
            "ส่งตรวจสอบปัญหาสินค้า | รายละเอียดตามบทสนทนา | ไม่ระบุในสาย (แนะนำ: ภายใน 3-5 วัน) | บันทึกผลตรวจและแจ้งลูกค้า",
            "ฝ่าย QC",
        )
    if any(k in text for k in ("จัดส่ง", "ส่งสินค้า", "รับสินค้า", "รับคืน", "เปลี่ยนสินค้า", "เลื่อนวัน", "วันรับ")):
        return (
            "ติดตามและยืนยันการจัดส่งหรือวันรับสินค้า | รายละเอียดตามบทสนทนา | ไม่ระบุในสาย (แนะนำ: ภายใน 2-3 วัน) | โทรแจ้งลูกค้าและบันทึกผลใน CRM",
            "ฝ่ายจัดส่ง",
        )
    if any(k in text for k in ("ประกัน", "warranty", "เคลม")):
        return (
            "ติดตามข้อมูลประกันหรือเคลมให้ลูกค้า | รายละเอียดตามบทสนทนา | ไม่ระบุในสาย (แนะนำ: ภายใน 2-3 วัน) | โทรแจ้งลูกค้าและบันทึกผลใน CRM",
            "Agent คนเดิม",
        )
    return (
        "ติดตามผลตามประเด็นที่ลูกค้าสอบถาม | รายละเอียดตามบทสนทนา | ไม่ระบุในสาย (แนะนำ: ภายใน 2-3 วัน) | โทรแจ้งลูกค้าและบันทึกผลใน CRM",
        "Agent คนเดิม",
    )


def sanitize_next_action(
    next_action: str, next_action_owner: str, conversation_text: str
) -> tuple[str, str]:
    """Also used at display time, so rows saved by older prompts get cleaned too."""
    if _looks_like_copied_next_action_example(next_action or "", conversation_text or ""):
        return _fallback_next_action_from_conversation(conversation_text or "")
    if insight_rules.money_action_is_ungrounded(next_action or "", conversation_text or ""):
        log.warning("next_action mentions a refund on a call with no money talk — replacing")
        return _fallback_next_action_from_conversation(conversation_text or "")
    if (next_action or "").startswith("ไม่มี"):
        return next_action, next_action_owner
    return insight_rules.clean_next_action_text(next_action) or next_action, next_action_owner


# Placeholder fragments that Typhoon-8B has been observed copying verbatim from
# the agent-QA prompt schema into politeness_evidence / problem_solving_evidence.
# Match against the *stripped* evidence — see _strip_brackets below.
_EVIDENCE_LEAKAGE_FRAGMENTS = (
    "ข้อ + quote สั้น",
    "ข้อ + quote",
    "ทุกข้อ + quote",
    "quote สั้นจาก transcript",
    "เหตุผลหรือไม่พบหลักฐาน",
    "ชื่อข้อจริง",
    "<quote",
    "quote Agent",
)

# Vague summary phrases the LLM emits when it summarises rather than quoting —
# if any appears AND no quote is present, treat as "no evidence".
_EVIDENCE_VAGUE_PHRASES = (
    "ทุกข้อ",
    "ไม่มีข้อที่ไม่ทำ",
    "ไม่มีข้อที่ทำไม่ได้",
)

_BRACKET_RE = re.compile(r"[\[\]<>]")


def _evidence_is_leaked(evidence: str) -> bool:
    """Detect template/placeholder leakage in evidence strings."""
    if not evidence:
        return False
    text = evidence.strip()
    if _BRACKET_RE.search(text):
        return True
    lowered = text.lower()
    if any(frag.lower() in lowered for frag in _EVIDENCE_LEAKAGE_FRAGMENTS):
        return True
    return False


def _evidence_is_vague(evidence: str) -> bool:
    """Detect evidence that summarises instead of quoting.

    Rule: if the LLM uses a known vague phrase ("ทุกข้อ", "ไม่มีข้อที่ไม่ทำ")
    and provides no quoted Agent line, it never actually inspected the
    transcript — fall back to "ไม่พบหลักฐาน".
    """
    if not evidence:
        return True
    text = evidence.strip()
    has_quote = ("'" in text) or ('"' in text) or ("ไม่พบหลักฐาน" in text)
    if has_quote:
        return False
    bare = " ".join(text.split())
    return any(phrase in bare for phrase in _EVIDENCE_VAGUE_PHRASES)


_EVIDENCE_FALLBACK = "ไม่พบหลักฐานที่ชัดเจนใน transcript — โปรด re-process หรือฟังสายเพื่อตรวจสอบ"

# Concrete fake values previously used in the Agent QA prompt's "รูปแบบที่ถูก"
# example. Typhoon-8B copied them verbatim into evidence on most calls, so any
# row that still references them — without the same string actually appearing
# in the real transcript — is template leakage and must be scrubbed.
_EVIDENCE_PROMPT_EXAMPLE_TOKENS = ("ร้านที่นอนพลอย", "พลอยค่ะ")


def _evidence_has_prompt_example_leak(evidence: str, conversation_text: str) -> bool:
    if not evidence:
        return False
    convo = conversation_text or ""
    return any(tok in evidence and tok not in convo for tok in _EVIDENCE_PROMPT_EXAMPLE_TOKENS)


def sanitize_evidence(evidence: str, conversation_text: str = "") -> str:
    """Clean LLM evidence strings before display.

    Why: Typhoon-8B sometimes copies the JSON-schema placeholder
    (e.g. "[ข้อ + quote สั้น]") straight into politeness_evidence /
    problem_solving_evidence, leaving users staring at template syntax instead
    of real findings. Also drops vague summaries like "ทำได้: ทุกข้อ" that
    carry no quotes or item names, and prompt-example tokens (e.g.
    "ร้านที่นอนพลอย") that the model lifted from the QA prompt even though the
    real conversation never said them.
    """
    if not evidence:
        return ""
    text = str(evidence).strip()
    if _evidence_is_leaked(text) or _evidence_is_vague(text):
        log.warning("sanitize_evidence: detected leaked/vague evidence %r", text[:120])
        return _EVIDENCE_FALLBACK
    if _evidence_has_prompt_example_leak(text, conversation_text):
        log.warning(
            "sanitize_evidence: evidence quotes prompt-example token absent from transcript %r",
            text[:120],
        )
        return _EVIDENCE_FALLBACK
    return text


def _prepare_conversation_text(conversation) -> str:
    """Conversation list/str → "Speaker: text" lines within MAX_CHARS.

    Over budget, the middle is dropped on line boundaries — the old cut kept
    only the first 6,000 characters, losing the close of 4 in 11 real calls
    (the closing greeting and what was agreed are scored from the end).
    """
    if isinstance(conversation, list):
        lines = [
            f"{item.get('speaker', 'Unknown')}: {item.get('text', '')}"
            for item in conversation
            if item.get("text")
        ]
    else:
        lines = str(conversation).splitlines()
    text = "\n".join(lines)
    if len(text) <= MAX_CHARS:
        return text

    head_budget = int(MAX_CHARS * HEAD_SHARE)
    tail_budget = MAX_CHARS - head_budget
    head, used = [], 0
    for line in lines:
        if used + len(line) + 1 > head_budget:
            break
        head.append(line)
        used += len(line) + 1
    tail, used = [], 0
    for line in reversed(lines[len(head):]):
        if used + len(line) + 1 > tail_budget:
            break
        tail.append(line)
        used += len(line) + 1
    if not head and not tail:  # one enormous line
        return text[:head_budget] + "\n" + _ELLIPSIS_LINE + "\n" + text[-tail_budget:]
    return "\n".join(head + [_ELLIPSIS_LINE] + list(reversed(tail)))


# Allowed topic_detail values when topic = "แจ้งปัญหาสินค้า". Kept in sync with
# the controlled vocabulary in prompts.py so the LLM cannot drift the labels.
PRODUCT_ISSUE_TOPIC = "แจ้งปัญหาสินค้า"
TOPIC_DETAIL_CHOICES = (
    "ผ้าขาด/ผ้าหุ้มชำรุด",
    "เตียง/โครงหัก",
    "สปริง/ฟองน้ำยุบ",
    "เปื้อน/รอยขีดข่วน",
    "ความชื้น/น้ำท่วม",
    "ขนาด/สเปคผิด",
    "กลิ่น/แพ้/ระคายเคือง",
    "อื่นๆ",
)
_TOPIC_DETAIL_FALLBACK = "อื่นๆ"
# Stem keywords used to snap LLM rewordings back to the canonical label.
# Order matters: first hit wins, so put more specific stems before generic ones.
# Stems are whole words on purpose: the old bare "รา" matched "รายละเอียด"
# and "ผ้า" matched "ผ้าห่ม", snapping unrelated answers onto those labels.
_TOPIC_DETAIL_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("กลิ่น/แพ้/ระคายเคือง", ("แพ้", "ผื่น", "คัน", "แสบ", "ระคายเคือง", "กลิ่น", "สารเคมี")),
    ("เปื้อน/รอยขีดข่วน",   ("เปื้อน", "คราบ", "รอยขีด", "ขีดข่วน", "รอยถลอก")),
    ("ความชื้น/น้ำท่วม",    ("เชื้อรา", "ราขึ้น", "ความชื้น", "อับชื้น", "น้ำท่วม", "น้ำหก")),
    ("สปริง/ฟองน้ำยุบ",     ("สปริง", "ฟองน้ำ", "ยุบ", "เป็นแอ่ง")),
    ("เตียง/โครงหัก",       ("เตียงหัก", "โครงเตียง", "โครงหัก", "ขาเตียง", "หัวเตียง")),
    ("ผ้าขาด/ผ้าหุ้มชำรุด", ("ผ้าขาด", "ผ้าหุ้ม", "ปลอก", "ผ้าฉีก", "ผ้ารอง")),
    ("ขนาด/สเปคผิด",        ("ขนาดไม่ตรง", "ผิดรุ่น", "สเปคผิด", "สีผิด", "ผิดสเปค", "ไม่ตรงปก", "ไม่ครบ", "ไม่ตรงที่สั่ง", "สีไม่ตรง", "รุ่นไม่ตรง", "ขนาดผิด")),
)


def normalize_topic_detail(topic: str, raw_detail) -> str:
    """Clamp LLM-produced topic_detail to the allowed vocabulary.

    Why: Typhoon-8B occasionally rewords labels ("ผ้าขาด/ผ้าหุ้มชำรุด" →
    "ผ้าหุ้มขาด") or fills the field even when topic isn't a product-issue
    call. Keeping the DB on a fixed vocabulary lets the dashboard group cleanly.
    """
    if topic != PRODUCT_ISSUE_TOPIC:
        return ""
    if not isinstance(raw_detail, str):
        return _TOPIC_DETAIL_FALLBACK
    cleaned = raw_detail.strip()
    if not cleaned:
        return _TOPIC_DETAIL_FALLBACK
    if cleaned in TOPIC_DETAIL_CHOICES:
        return cleaned
    for label, stems in _TOPIC_DETAIL_KEYWORDS:
        for stem in stems:
            if stem in cleaned:
                return label
    return _TOPIC_DETAIL_FALLBACK


def extract_summary_and_topics(conversation) -> dict:
    """Call 1: Summary, Topic, Keywords, Brands, Platforms."""
    from smartvoice.prompts import build_extraction_prompt

    text = _prepare_conversation_text(conversation)
    system, user = build_extraction_prompt(text)
    try:
        result = extract_json(chat(system, user, json_mode=True))
    except Exception:
        log.exception("extract_summary_and_topics: LLM call/parse failed — using empty defaults")
        result = {}

    keywords = result.get("keywords", [])
    keywords = [k.strip() for k in keywords if isinstance(k, str) and k.strip()][:8] if isinstance(keywords, list) else []
    # Only names actually said in the call, one spelling each (the model used
    # to list the group's five brands from the prompt on calls that never
    # mentioned them, and "Lotus", "โลตัส", "Lotus/โลตัส" split the chart).
    brand_mentions = insight_rules.canonical_mentions(
        result.get("brand_mentions", []), text, insight_rules.BRAND_ALIASES
    )
    platform_mentions = insight_rules.canonical_mentions(
        result.get("platform_mentions", []), text, insight_rules.PLATFORM_ALIASES
    )
    topic = insight_rules.normalize_topic(result.get("topic", "")) if result.get("topic") else ""
    topic_detail = normalize_topic_detail(topic, result.get("topic_detail", ""))

    return {
        "summary": result.get("summary", ""),
        "topic": topic,
        "topic_detail": topic_detail,
        "keywords": json.dumps(keywords if isinstance(keywords, list) else [], ensure_ascii=False),
        "brand_mentions": json.dumps(brand_mentions if isinstance(brand_mentions, list) else [], ensure_ascii=False),
        "platform_mentions": json.dumps(platform_mentions if isinstance(platform_mentions, list) else [], ensure_ascii=False),
    }


def analyze_sentiment(conversation) -> dict:
    """Call 2: Overall customer sentiment (3-class polarity) — see prompts.py."""
    from smartvoice.prompts import build_sentiment_prompt

    text = _prepare_conversation_text(conversation)
    system, user = build_sentiment_prompt(text)
    try:
        result = extract_json(chat(system, user, json_mode=True))
    except Exception:
        log.exception("analyze_sentiment: LLM call/parse failed — defaulting to neutral")
        result = {}

    sentiment = str(result.get("sentiment") or "neutral").strip().lower()
    if sentiment not in ("positive", "neutral", "negative"):
        sentiment = "neutral"

    reason = " ".join(str(result.get("sentiment_reason") or "").split())
    quote = " ".join(str(result.get("customer_quote") or "").split())
    customer_text = insight_rules.speaker_text(text, "Customer")
    if not insight_rules.quote_in_text(quote, customer_text):
        quote = ""
    sentiment = insight_rules.check_sentiment(sentiment, quote, customer_text)
    if quote:
        # Show the customer's own words next to the label — only when they
        # really occur in what the customer said.
        reason = f"{reason} — ลูกค้าพูดว่า: \"{quote}\"" if reason else f"ลูกค้าพูดว่า: \"{quote}\""

    return {
        "sentiment": sentiment,
        "sentiment_reason": reason,
    }


_PROMPT_EXAMPLE_TOKENS = ("15,000", "15000", "REG0012", "081-987-9336", "0819879336")


def _scrub_prompt_example_leakage(next_action: str, conversation_text: str) -> str:
    """Strip example values from prompts.py that the LLM copied verbatim.

    Why: Typhoon-8B sometimes lifts the in-prompt next_action example
    ("จำนวน 15,000 บาท ... รหัส #REG0012 ... 081-987-9336") even when the
    real conversation never mentioned those numbers. Detect tokens that exist
    in the example but NOT in the actual transcript and excise the leaked
    sub-clause.
    """
    if not next_action:
        return next_action
    convo = conversation_text or ""
    cleaned = next_action
    for tok in _PROMPT_EXAMPLE_TOKENS:
        if tok in cleaned and tok not in convo:
            log.warning(
                "evaluate_agent_qa: next_action contained prompt example token %r "
                "not present in conversation — scrubbing", tok
            )
            # Drop the " | "-separated segment that carries the leaked token,
            # keeping the rest of the action so we don't lose the verb/timing.
            parts = [p for p in cleaned.split("|") if tok not in p]
            cleaned = " | ".join(p.strip() for p in parts) if parts else ""
    return cleaned.strip() or "ติดตามผลและแจ้งลูกค้า | ตามที่ตกลงในสาย | ภายใน 3 วันทำการ | บันทึกผลใน CRM"


def evaluate_agent_qa(conversation) -> dict:
    """Call 3: Two-factor agent QA (Politeness + Problem Solving) — see prompts.py."""
    from smartvoice.prompts import build_agent_qa_prompt

    text = _prepare_conversation_text(conversation)
    system, user = build_agent_qa_prompt(text)
    try:
        # temperature 0: the same call must get the same score when re-processed.
        result = extract_json(chat(system, user, json_mode=True))
    except Exception:
        log.exception("evaluate_agent_qa: LLM call/parse failed — defaulting to mid scores")
        result = {}

    if insight_rules.has_itemised_qa(result):
        # Scores computed here from items whose quotes the agent really said —
        # the model's own totals came out 5/5 on every call.
        items = insight_rules.items_from_answer(result)
        politeness, politeness_evidence = insight_rules.score_items(
            items, insight_rules.POLITENESS_ITEMS, text
        )
        problem_solving, problem_solving_evidence = insight_rules.score_items(
            items, insight_rules.PROBLEM_SOLVING_ITEMS, text
        )
    else:  # older answer format: {"politeness": n, "politeness_evidence": "..."}
        politeness = _coerce_score(result.get("politeness"), default=3)
        problem_solving = _coerce_score(result.get("problem_solving"), default=3)
        politeness_evidence = sanitize_evidence(result.get("politeness_evidence", ""), text)
        problem_solving_evidence = sanitize_evidence(result.get("problem_solving_evidence", ""), text)
    overall_score = politeness + problem_solving

    # The next step is its own request (see prompts.NEXT_ACTION_USER): asked
    # alongside the checklist, the model marked plainly open calls as closed.
    from smartvoice.prompts import build_next_action_prompt

    try:
        na_system, na_user = build_next_action_prompt(text)
        next_answer = extract_json(chat(na_system, na_user, json_mode=True))
    except Exception:
        log.exception("evaluate_agent_qa: next-action call failed — using the QA answer")
        next_answer = {}
    structured = insight_rules.build_next_action(next_answer, text) or insight_rules.build_next_action(
        result.get("next_action"), text
    )
    if structured:
        next_action, next_action_owner = structured
    else:
        next_action_owner = result.get("next_action_owner") or "ไม่มี"
        next_action = result.get("next_action") or insight_rules.CLOSED_NEXT_ACTION
    if _looks_like_copied_next_action_example(next_action, text):
        next_action, next_action_owner = _fallback_next_action_from_conversation(text)
    else:
        next_action = _scrub_prompt_example_leakage(next_action, text)
        next_action, next_action_owner = sanitize_next_action(next_action, next_action_owner, text)

    # Fallback: if next_action exists (not closed) but owner is "ไม่มี",
    # infer owner from keywords in next_action text
    _is_closed = "ไม่มี" in next_action and "เคสปิด" in next_action
    if not _is_closed and next_action_owner == "ไม่มี":
        _txt = next_action.lower()
        if any(k in _txt for k in ("คืนเงิน", "โอนเงิน", "คืนค่าสินค้า", "ฝ่ายบัญชี", "บัญชี")):
            next_action_owner = "ฝ่ายบัญชี"
        elif any(k in _txt for k in ("qc", "ตรวจสอบคุณภาพ", "ตรวจสินค้า", "ตรวจที่นอน", "ฝ่ายตรวจสอบ")):
            next_action_owner = "ฝ่าย QC"
        elif any(k in _txt for k in ("จัดส่ง", "รับคืนสินค้า", "เปลี่ยนสินค้า", "ส่งสินค้าใหม่", "ขนส่ง")):
            next_action_owner = "ฝ่ายจัดส่ง"
        elif any(k in _txt for k in ("สต็อก", "ของหมด", "สินค้าในคลัง", "คลังสินค้า")):
            next_action_owner = "ฝ่ายคลังสินค้า"
        elif any(k in _txt for k in ("หัวหน้า", "ผู้จัดการ", "ขออนุมัติ", "ผู้มีอำนาจ")):
            next_action_owner = "หัวหน้าทีม"
        else:
            next_action_owner = "Agent คนเดิม"

    agent_perf = {
        "politeness": politeness,
        "politeness_evidence": politeness_evidence,
        "problem_solving": problem_solving,
        "problem_solving_evidence": problem_solving_evidence,
        "overall_score": overall_score,
        "next_action": next_action,
        "next_action_owner": next_action_owner,
        "strengths": result.get("strengths", []),
        "improvements": result.get("improvements", []),
    }
    return {
        "agent_performance": json.dumps(agent_perf, ensure_ascii=False),
    }


def detect_anomaly(conversation) -> dict:
    """Call 4: Criteria-based anomaly detection."""
    from smartvoice.prompts import build_anomaly_prompt

    text = _prepare_conversation_text(conversation)
    system, user = build_anomaly_prompt(text)
    try:
        result = extract_json(chat(system, user, json_mode=True))
    except Exception:
        log.exception("detect_anomaly: LLM call/parse failed — defaulting to no anomaly")
        result = {}

    # Flag only with a quote that occurs in the call and carries a keyword of
    # its category; severity follows the category (insight_rules).
    return insight_rules.verify_anomaly(result, text)


def analyze_transcript(conversation) -> dict:
    """Run all 4 analysis calls and merge results."""
    extraction = extract_summary_and_topics(conversation)
    sentiment = analyze_sentiment(conversation)
    agent_qa = evaluate_agent_qa(conversation)
    anomaly = detect_anomaly(conversation)

    return {
        **extraction,
        **sentiment,
        **agent_qa,
        **anomaly,
        "speaker_mapping": json.dumps({}, ensure_ascii=False),
    }


def match_case(
    new_topic: str, new_summary: str, existing_cases: list[dict], new_call_at: str | None = None
) -> dict:
    """Call LLM to decide if a new call belongs to an existing case or needs a new one."""
    from smartvoice.prompts import build_case_match_prompt

    system, user = build_case_match_prompt(new_topic, new_summary, existing_cases, new_call_at)
    try:
        result = extract_json(chat(system, user, json_mode=True))
    except Exception:
        log.exception("match_case: LLM call/parse failed — creating new case instead")
        result = {}

    return {
        "match_case_id": result.get("match_case_id"),
        "reason": result.get("reason", ""),
        "suggested_subject": result.get("suggested_subject", new_topic or "เรื่องทั่วไป"),
    }
