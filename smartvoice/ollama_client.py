import json
import os
import re
import requests

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


def chat(system_prompt: str, user_prompt: str, *, temperature: float = 0) -> str:
    url = f"{_base_url()}/api/chat"
    payload = {
        "model": _model(),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"temperature": temperature},
    }
    response = requests.post(url, json=payload, timeout=600)
    response.raise_for_status()
    data = response.json()
    return data["message"]["content"]


def extract_json(raw: str) -> dict:
    raw = _normalize_llm_output(raw)
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in LLM response: {raw[:300]}")
    return json.loads(match.group())


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
        return conversation


MAX_SEGMENTS = 60
MAX_CHARS = 6000


def _prepare_conversation_text(conversation) -> str:
    """Convert conversation list/str to capped text for LLM prompts."""
    if isinstance(conversation, list):
        segs = [item for item in conversation if item.get("text")][:MAX_SEGMENTS]
        text = "\n".join(
            f"{item.get('speaker', 'Unknown')}: {item.get('text', '')}"
            for item in segs
        )
    else:
        text = str(conversation)
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n...(ตัดบทสนทนาที่เกินมา)"
    return text


def extract_summary_and_topics(conversation) -> dict:
    """Call 1: Summary, Topic, Keywords, Brands, Platforms."""
    from smartvoice.prompts import build_extraction_prompt

    text = _prepare_conversation_text(conversation)
    system, user = build_extraction_prompt(text)
    try:
        result = extract_json(chat(system, user))
    except Exception:
        result = {}

    keywords = result.get("keywords", [])
    brand_mentions = result.get("brand_mentions", [])
    platform_mentions = result.get("platform_mentions", [])

    return {
        "summary": result.get("summary", ""),
        "topic": result.get("topic", ""),
        "keywords": json.dumps(keywords if isinstance(keywords, list) else [], ensure_ascii=False),
        "brand_mentions": json.dumps(brand_mentions if isinstance(brand_mentions, list) else [], ensure_ascii=False),
        "platform_mentions": json.dumps(platform_mentions if isinstance(platform_mentions, list) else [], ensure_ascii=False),
    }


def analyze_sentiment(conversation) -> dict:
    """Call 2: Aspect-based sentiment analysis."""
    from smartvoice.prompts import build_sentiment_prompt

    text = _prepare_conversation_text(conversation)
    system, user = build_sentiment_prompt(text)
    try:
        result = extract_json(chat(system, user))
    except Exception:
        result = {}

    sentiment = result.get("sentiment", "neutral").lower()
    if sentiment not in ("positive", "neutral", "negative"):
        sentiment = "neutral"

    return {
        "sentiment": sentiment,
        "sentiment_reason": result.get("sentiment_reason", ""),
    }


def evaluate_agent_qa(conversation) -> dict:
    """Call 3: SERVQUAL-inspired agent performance evaluation."""
    from smartvoice.prompts import build_agent_qa_prompt

    text = _prepare_conversation_text(conversation)
    system, user = build_agent_qa_prompt(text)
    try:
        result = extract_json(chat(system, user, temperature=0.3))
    except Exception:
        result = {}

    politeness = result.get("politeness", 3)
    problem_solving = result.get("problem_solving", 3)
    overall_score = result.get("overall_score", 0)
    if not isinstance(politeness, (int, float)):
        politeness = 3
    if not isinstance(problem_solving, (int, float)):
        problem_solving = 3
    if not isinstance(overall_score, (int, float)):
        overall_score = int(politeness) + int(problem_solving)

    agent_perf = {
        "politeness": int(politeness),
        "problem_solving": int(problem_solving),
        "overall_score": int(overall_score),
        "next_action": result.get("next_action") or "ไม่มี — เคสปิดสมบูรณ์",
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
        result = extract_json(chat(system, user))
    except Exception:
        result = {}

    return {
        "anomaly_detected": bool(result.get("anomaly_detected", False)),
        "anomaly_reason": result.get("anomaly_reason") or "",
        "anomaly_severity": result.get("anomaly_severity") or "",
    }


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
