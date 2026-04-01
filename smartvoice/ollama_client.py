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


def chat(system_prompt: str, user_prompt: str) -> str:
    url = f"{_base_url()}/api/chat"
    payload = {
        "model": _model(),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"temperature": 0},
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


def analyze_transcript(conversation) -> dict:
    from smartvoice.prompts import build_analysis_prompt

    if isinstance(conversation, list):
        segs = [item for item in conversation if item.get("text")][:MAX_SEGMENTS]
        conversation_text = "\n".join(
            f"{item.get('speaker', 'Unknown')}: {item.get('text', '')}"
            for item in segs
        )
    else:
        conversation_text = str(conversation)

    # Hard cap on characters to avoid token overload
    if len(conversation_text) > MAX_CHARS:
        conversation_text = conversation_text[:MAX_CHARS] + "\n...(ตัดบทสนทนาที่เกินมา)"

    system, user = build_analysis_prompt(conversation_text)
    raw = chat(system, user)
    result = extract_json(raw)

    sentiment = result.get("customer_sentiment", result.get("sentiment", "neutral")).lower()
    if sentiment not in ("positive", "neutral", "negative"):
        sentiment = "neutral"

    import json as _json
    agent_perf = result.get("agent_performance", {})
    keywords = result.get("keywords", [])
    brand_mentions = result.get("brand_mentions", [])
    platform_mentions = result.get("platform_mentions", [])

    return {
        "summary": result.get("summary", ""),
        "sentiment": sentiment,
        "topic": result.get("topic", ""),
        "speaker_mapping": _json.dumps(result.get("speaker_mapping", {}), ensure_ascii=False),
        "agent_performance": _json.dumps(agent_perf, ensure_ascii=False),
        "keywords": _json.dumps(keywords, ensure_ascii=False),
        "brand_mentions": _json.dumps(brand_mentions, ensure_ascii=False),
        "platform_mentions": _json.dumps(platform_mentions, ensure_ascii=False),
        "anomaly_detected": bool(result.get("anomaly_detected", False)),
        "anomaly_reason": result.get("anomaly_reason") or "",
    }
