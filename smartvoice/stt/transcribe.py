"""Transcription backends — HuggingFace transformers & faster-whisper.

Note: torchaudio suppression is handled in smartvoice/__init__.py
(runs before any module in the package).
"""

import os
import re as _re

from smartvoice.config import (
    WHISPER_MODEL,
    WHISPER_DEVICE,
    WHISPER_COMPUTE,
    WHISPER_BEAM_SIZE,
    WHISPER_HOTWORDS,
    WHISPER_VAD_FILTER,
    WHISPER_CONDITION_ON_PREVIOUS_TEXT,
    WHISPER_NO_SPEECH_THRESHOLD,
    WHISPER_LOG_PROB_THRESHOLD,
    WHISPER_COMPRESSION_RATIO_THRESHOLD,
    WHISPER_PATIENCE,
    HF_TOKEN,
)
from smartvoice.stt.audio import has_thai

# Standard model names that faster-whisper can download directly (no conversion)
_STANDARD_MODELS = {
    "tiny", "tiny.en", "base", "base.en", "small", "small.en",
    "medium", "medium.en", "large-v1", "large-v2", "large-v3",
    "large", "distil-large-v2", "distil-large-v3",
    "large-v3-turbo", "turbo",
}

_CT2_MODELS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "models")
)

# Thai call-center context prompt — helps Whisper stay in Thai and reduces hallucination.
_BASE_INITIAL_PROMPT = (
    "บทสนทนาภาษาไทยระหว่างเจ้าหน้าที่กลุ่มบริษัทที่นอนโลตัสกับลูกค้าทางโทรศัพท์ "
    "สวัสดีค่ะ สวัสดีครับ ขอบคุณที่ติดต่อกลุ่มบริษัทที่นอนโลตัส ยินดีให้บริการค่ะ "
    "ที่นอน โลตัส กลุ่มบริษัทที่นอนโลตัส Restonic เรสโทนิค Omazz โอมัซซ์ "
    "ประกัน ประกันโครงสร้าง วัสดุ ฟองน้ำ รูพรุน เชื้อรา "
    "อุทกภัย น้ำท่วม ทำความสะอาด เทรดอิน Trade-in เทิร์น คืนสินค้า โปรโมชั่น โปรราคาพิเศษ "
    "สุราษฎร์ธานี หาดใหญ่ ภาคใต้ ลูกค้า คุณลูกค้า เจ้าหน้าที่ พนักงาน ฝ่ายขาย Shop สาขา "
    "ตัวที่นอน Restonic อยู่ในเครือไหมคะ รับทำความสะอาด ส่งกลับเข้าบริษัท "
    "น้ำท่วมที่หาดใหญ่ ไม่ถูกสุขลักษณะ อยู่นอกเหนือประกัน โปรโมชั่นพิเศษ โปรราคาพิเศษ "
    "เป็นรูพรุน พูดง่าย ๆ คือฟองน้ำ ซักยังไงก็ไม่ได้อยู่แล้ว มิน่าเขาทิ้งกันเยอะ สเต็ปต่อไป "
    "ตากแดดไว้ข้างนอก แห้งแค่ข้างนอก ทางห้าง โซนภาคใต้ จัดโปร ไม่มี Trade-in ตามนโยบาย "
    "ขอโทษค่ะ เสียใจด้วยค่ะ ขออนุญาตแนะนำได้ไหมคะ ขอบพระคุณค่ะ สวัสดีค่ะ"
)
_HF_INITIAL_PROMPT = (
    "บทสนทนาภาษาไทยทางโทรศัพท์ระหว่างพนักงานกับลูกค้า "
    "กลุ่มบริษัทที่นอนโลตัส Restonic Omazz หาดใหญ่ สุราษฎร์ธานี อุทกภัย "
    "รับทำความสะอาด ส่งกลับเข้าบริษัท ประกันโครงสร้าง Trade-in โปรโมชั่นพิเศษ โปรราคาพิเศษ "
    "ฟองน้ำ รูพรุน เชื้อรา แห้งแค่ข้างนอก มิน่าเขาทิ้งกันเยอะ"
)

_DEFAULT_HOTWORDS = [
    "Restonic",
    "Omazz",
    "Trade-in",
    "หาดใหญ่",
    "สุราษฎร์ธานี",
    "อุทกภัย",
    "รับทำความสะอาด",
    "ส่งกลับเข้าบริษัท",
    "ประกันโครงสร้าง",
    "รูพรุน",
    "ฟองน้ำ",
    "เชื้อรา",
    "ถูกสุขลักษณะ",
    "โปรโมชั่นพิเศษ",
    "โปรราคาพิเศษ",
    "กลุ่มบริษัทที่นอนโลตัส",
    "ภาคใต้",
    "ทางห้าง",
    "จัดโปร",
    "แห้งแค่ข้างนอก",
    "มิน่า",
]


def _hotwords_text() -> str:
    words: list[str] = []
    seen: set[str] = set()
    extra_words = [part.strip() for part in WHISPER_HOTWORDS.split(",") if part.strip()]
    for word in [*_DEFAULT_HOTWORDS, *extra_words]:
        key = word.casefold()
        if key in seen:
            continue
        seen.add(key)
        words.append(word)
    return " ".join(words)


def _initial_prompt() -> str:
    return _BASE_INITIAL_PROMPT


def _hf_initial_prompt() -> str:
    return _HF_INITIAL_PROMPT


def _hf_prompt_ids(tokenizer, device=None, max_prompt_tokens=96):
    try:
        import torch

        get_prompt_ids = getattr(tokenizer, "get_prompt_ids", None)
        if get_prompt_ids is None:
            return None
        try:
            prompt_ids = get_prompt_ids(_hf_initial_prompt(), return_tensors="pt")
        except TypeError:
            prompt_ids = get_prompt_ids(_hf_initial_prompt())
        if prompt_ids is None:
            return None
        if not torch.is_tensor(prompt_ids):
            prompt_ids = torch.as_tensor(prompt_ids, dtype=torch.long)
        else:
            prompt_ids = prompt_ids.to(dtype=torch.long)
        prompt_ids = prompt_ids.reshape(-1)
        if max_prompt_tokens and prompt_ids.numel() > max_prompt_tokens:
            prompt_ids = prompt_ids[:max_prompt_tokens]
        if device is not None:
            prompt_ids = prompt_ids.to(device)
        return prompt_ids
    except Exception:
        return None


# Singleton model references
_whisper_model = None


def unload_model():
    """Delete the cached Whisper model and free GPU memory."""
    global _whisper_model
    if _whisper_model is not None:
        del _whisper_model
        _whisper_model = None
        try:
            import torch, gc
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass


# ── Helpers ──────────────────────────────────────────────────────────────

def resolve_device_compute() -> tuple[str, str]:
    """Auto-detect best device and compute type."""
    device = WHISPER_DEVICE
    compute = WHISPER_COMPUTE
    if device == "auto":
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            device = "cpu"
    if compute == "auto":
        compute = "float16" if device == "cuda" else "int8"
    return device, compute


def is_standard_model() -> bool:
    return WHISPER_MODEL in _STANDARD_MODELS


def _ct2_model_path() -> str:
    safe_name = WHISPER_MODEL.replace("/", "--")
    return os.path.join(_CT2_MODELS_DIR, safe_name)


def _ensure_ct2_support_files(log_fn, ct2_dir: str) -> None:
    from huggingface_hub import hf_hub_download

    required_files = ["preprocessor_config.json", "tokenizer.json"]
    optional_files = ["tokenizer_config.json", "generation_config.json"]

    missing_required = [f for f in required_files if not os.path.exists(os.path.join(ct2_dir, f))]
    missing_optional = [f for f in optional_files if not os.path.exists(os.path.join(ct2_dir, f))]
    if not missing_required and not missing_optional:
        return

    log_fn("→ ดึง tokenizer/config support files ของโมเดล...")
    for filename in missing_required + missing_optional:
        try:
            src_path = hf_hub_download(repo_id=WHISPER_MODEL, filename=filename)
        except Exception:
            continue
        dst_path = os.path.join(ct2_dir, filename)
        with open(src_path, "rb") as src, open(dst_path, "wb") as dst:
            dst.write(src.read())
    log_fn("← เตรียม tokenizer/config support files เสร็จแล้ว")


def _ensure_ct2_model(log_fn) -> str:
    ct2_dir = _ct2_model_path()
    if os.path.exists(os.path.join(ct2_dir, "model.bin")):
        _ensure_ct2_support_files(log_fn, ct2_dir)
        return ct2_dir

    device, _ = resolve_device_compute()
    quantization = "float16" if device == "cuda" else "int8"
    log_fn(f"→ แปลงโมเดล {WHISPER_MODEL} → CTranslate2 (quantization={quantization}, ครั้งเดียว ใช้เวลา ~5-10 นาที)...")
    os.makedirs(ct2_dir, exist_ok=True)

    from ctranslate2.converters import TransformersConverter
    converter = TransformersConverter(WHISPER_MODEL, low_cpu_mem_usage=True)
    converter.convert(ct2_dir, quantization=quantization, force=True)
    _ensure_ct2_support_files(log_fn, ct2_dir)
    log_fn("← แปลงโมเดลเสร็จแล้ว")
    return ct2_dir


def _resolve_model_path(log_fn) -> str:
    if is_standard_model():
        return WHISPER_MODEL
    return _ensure_ct2_model(log_fn)


# ── Hallucination filter ─────────────────────────────────────────────────

_HALLUCINATION_RE = [
    _re.compile(r'(https?://|www\.|\.com|\.co\.th)', _re.IGNORECASE),
    _re.compile(r'(ADDLINE|ADD\s*LINE|subscribe|like\s*and\s*share)', _re.IGNORECASE),
    _re.compile(r'(ฟุตบอล|บอลสเต็ป|พนัน|เดิมพัน|สล็อต|คาสิโน)', _re.IGNORECASE),
    _re.compile(r'(หลักสูตร.*ฟรี|คอร์สออนไลน์|สมัครสมาชิก)', _re.IGNORECASE),
    _re.compile(r'(ซับสไครบ์|กดไลค์|กดกระดิ่ง|กดติดตาม)', _re.IGNORECASE),
]


def _is_hallucination(text: str) -> bool:
    """Detect likely hallucinated content from Whisper."""
    for pat in _HALLUCINATION_RE:
        if pat.search(text):
            return True
    # Detect repetitive loops: same 4+ char substring repeated 6+ times
    # (raised thresholds to avoid false positives on natural Thai repetitions)
    if _re.search(r'(.{4,})\1{5,}', text):
        return True
    return False


def _filter_hallucinations(words: list[dict]) -> list[dict]:
    """Remove words/phrases that are likely hallucinations.
    Also merges adjacent words into windows to catch multi-word hallucinations.
    """
    if not words:
        return words

    # Pass 1: flag individual hallucinated words
    keep = [not _is_hallucination(w["word"]) for w in words]

    # Pass 2: sliding window (5 words) — if merged text is hallucination, drop all
    # Skip this pass when items are segment-level (avg > 30 chars) to avoid
    # merging entire segments into huge strings that trigger false positives.
    avg_chars = sum(len(w.get("word", "")) for w in words) / max(len(words), 1)
    if avg_chars <= 30:
        window = 5
        for i in range(len(words) - window + 1):
            merged = "".join(words[j]["word"] for j in range(i, i + window))
            if _is_hallucination(merged):
                for j in range(i, i + window):
                    keep[j] = False

    return [w for w, k in zip(words, keep) if k]


_THAI_SPLIT_RE = _re.compile(
    r'(?<=ค่ะ)|(?<=ครับ)|(?<=คะ)|(?<=นะคะ)|(?<=นะครับ)|(?<=ไหมคะ)|(?<=ไหมครับ)'
    r'|(?<=มั้ยคะ)|(?<=มั้ยครับ)|(?<=เลยค่ะ)|(?<=เลยครับ)|(?<=แล้วค่ะ)|(?<=แล้วครับ)'
    r'|(?<=อื้อ)|(?<=อ๋อ)|(?<=เหรอ)|(?<=ใช่ไหม)|(?<=ใช่มั้ย)'
)

_MAX_PSEUDO_WORD_CHARS = 12


def _split_thai_text(text: str) -> list[str]:
    """Split Thai text into pseudo-word chunks for timestamp interpolation.

    Strategy: first split on spaces (preserving space as prefix on subsequent
    parts so that ``"".join(parts)`` reconstructs the original text), then on
    Thai sentence-ending particles, then break remaining long pieces into
    ~12-char chunks.
    """
    # Step 1: split on spaces, keeping space prefix for later re-joining
    raw_parts = text.split(" ")
    space_parts: list[str] = []
    for idx, part in enumerate(raw_parts):
        if not part:
            continue
        space_parts.append((" " + part) if (idx > 0 and space_parts) else part)
    # Step 2: further split on Thai particles (within each space-part)
    finer: list[str] = []
    for part in space_parts:
        prefix = " " if part.startswith(" ") else ""
        core = part.lstrip(" ")
        pieces = _THAI_SPLIT_RE.split(core)
        for j, p in enumerate(pieces):
            if not p:
                continue
            finer.append((prefix + p) if j == 0 else p)
    # Step 3: break remaining long pieces into fixed-size chunks
    result: list[str] = []
    for piece in finer:
        stripped = piece.lstrip(" ")
        prefix = piece[:len(piece) - len(stripped)]  # preserve leading space
        if len(stripped) <= _MAX_PSEUDO_WORD_CHARS:
            result.append(piece)
        else:
            for i in range(0, len(stripped), _MAX_PSEUDO_WORD_CHARS):
                chunk = stripped[i:i + _MAX_PSEUDO_WORD_CHARS]
                if chunk:
                    result.append((prefix + chunk) if i == 0 else chunk)
    return result


def _split_segments_to_words(items: list[dict]) -> list[dict]:
    """Split segment-level items into pseudo-word items with interpolated timestamps.

    When HF generate() returns one text blob per ~30s chunk, diarization cannot
    assign speakers within the chunk.  This helper splits each item's text into
    fine-grained pseudo-words and linearly distributes timestamps so that
    Pyannote word-level speaker assignment works correctly.

    Items that are already word-level (<=30 chars) are kept as-is.
    """
    if not items:
        return items
    avg_chars = sum(len(w.get("word", "")) for w in items) / max(len(items), 1)
    if avg_chars <= 30:
        return items  # already word-level

    out: list[dict] = []
    for item in items:
        text = (item.get("word") or "").strip()
        if not text:
            continue
        start = float(item.get("start", 0.0) or 0.0)
        end = float(item.get("end", start) or start)
        parts = _split_thai_text(text)
        if len(parts) <= 1:
            out.append(item)
            continue
        duration = end - start
        step = duration / len(parts)
        for i, part in enumerate(parts):
            w_start = round(start + i * step, 3)
            w_end = round(start + (i + 1) * step, 3)
            out.append({"word": part, "start": w_start, "end": w_end})
    return out


def _decoded_span_seconds(words: list[dict]) -> float:
    if not words:
        return 0.0
    starts = [float(word.get("start", 0.0) or 0.0) for word in words]
    ends = [float(word.get("end", word.get("start", 0.0)) or 0.0) for word in words]
    return max(ends) - min(starts)


def _transcript_text_chars(words: list[dict]) -> int:
    return sum(len((word.get("word") or "").strip()) for word in words)


def _hf_quality_summary(words: list[dict], audio_duration_s: float) -> str:
    span_s = _decoded_span_seconds(words)
    coverage = span_s / max(audio_duration_s, 1.0)
    text_chars = _transcript_text_chars(words)
    chars_per_sec = text_chars / max(audio_duration_s, 1.0)
    return (
        f"items={len(words)}, chars={text_chars}, decoded_span={span_s:.1f}s/{audio_duration_s:.1f}s, "
        f"coverage={coverage:.2f}, chars_per_sec={chars_per_sec:.2f}"
    )


def _hf_quality_key(words: list[dict], audio_duration_s: float) -> tuple[float, float, int, int]:
    span_s = _decoded_span_seconds(words)
    coverage = span_s / max(audio_duration_s, 1.0)
    text_chars = _transcript_text_chars(words)
    chars_per_sec = text_chars / max(audio_duration_s, 1.0)
    return (coverage, chars_per_sec, text_chars, len(words))


def _looks_sparse_hf_result(words: list[dict], audio_duration_s: float) -> bool:
    if not words:
        return True
    if audio_duration_s <= 0:
        return False
    span_s = _decoded_span_seconds(words)
    if audio_duration_s >= 45 and span_s < max(20.0, audio_duration_s * 0.75):
        return True
    text_chars = _transcript_text_chars(words)
    if audio_duration_s >= 120 and text_chars < max(1600, int(audio_duration_s * 9.0)):
        return True
    return False


def _extract_hf_generated_items(generation_output: dict, tokenizer, audio_duration_s: float) -> list[dict]:
    items: list[dict] = []
    segments = generation_output.get("segments") or []
    if segments and isinstance(segments[0], list):
        segments = segments[0]
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        start = segment.get("start")
        if start is None:
            start = items[-1]["end"] if items else 0.0
        end = segment.get("end")
        if end is None:
            end = start + 0.1
        start = float(start)
        end = max(float(end), start)

        text = ""
        tokens = segment.get("tokens")
        if tokens is not None:
            try:
                if hasattr(tokens, "detach"):
                    tokens = tokens.detach().cpu()
                if hasattr(tokens, "tolist"):
                    tokens = tokens.tolist()
                text = tokenizer.decode(tokens, skip_special_tokens=True)
            except Exception:
                text = ""
        text = text.strip()
        if text:
            items.append({"word": text, "start": start, "end": end})

    if items:
        return items

    sequences = generation_output.get("sequences")
    if sequences is not None:
        try:
            if hasattr(sequences, "detach"):
                sequences = sequences.detach().cpu()
            if getattr(sequences, "ndim", 0) > 1:
                sequences = sequences[0]
            if hasattr(sequences, "tolist"):
                sequences = sequences.tolist()
            text = tokenizer.decode(sequences, skip_special_tokens=True).strip()
            if text:
                return [{"word": text, "start": 0.0, "end": max(audio_duration_s, 0.1)}]
        except Exception:
            pass
    return []


# ── Backends ─────────────────────────────────────────────────────────────

def transcribe_hf(audio, sr: int, log_fn) -> list[dict]:
    """Transcribe using HuggingFace transformers pipeline.
    Returns list of {"word", "start", "end"}.
    """
    global _whisper_model
    import torch

    # Prevent transformers from importing torchaudio (triggers libtorchcodec crash)
    try:
        import transformers.utils.import_utils as _tfi
        _tfi._torchaudio_available = False
    except Exception:
        pass

    from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

    device, _ = resolve_device_compute()
    torch_dtype = torch.float16 if device == "cuda" else torch.float32
    audio_duration_s = len(audio) / float(sr) if sr else 0.0

    if _whisper_model is None:
        dtype_name = "float16" if torch_dtype == torch.float16 else "float32"
        log_fn(f"→ โหลดโมเดล {WHISPER_MODEL} (transformers, {device}, {dtype_name})")
        processor = AutoProcessor.from_pretrained(WHISPER_MODEL)
        model = AutoModelForSpeechSeq2Seq.from_pretrained(
            WHISPER_MODEL,
            dtype=torch_dtype,
            low_cpu_mem_usage=True,
        )
        model = model.to(device)
        model.eval()
        _whisper_model = {
            "processor": processor,
            "model": model,
        }
    else:
        log_fn(f"→ ใช้โมเดล {WHISPER_MODEL} ที่โหลดไว้แล้ว")

    processor = _whisper_model["processor"]
    model = _whisper_model["model"]
    model_config = getattr(model, "config", None)
    max_target_positions = int(getattr(model_config, "max_target_positions", 448) or 448)
    default_prompt_tokens = max(24, min(48, max_target_positions // 8))

    # ── Chunked generation for finer timestamps ──────────────────────────
    # Whisper internally uses 30s mel windows.  By manually chunking the
    # audio into ~15s pieces we get one segment per chunk, giving diarization
    # ~15s resolution instead of ~30s before pseudo-word splitting.
    _HF_CHUNK_SECONDS = 15
    chunk_samples = int(_HF_CHUNK_SECONDS * sr)
    n_chunks = max(1, -(-len(audio) // chunk_samples))  # ceil division
    log_fn(f"→ chunked audio: {n_chunks} chunks × {_HF_CHUNK_SECONDS}s")

    prompt_ids = _hf_prompt_ids(
        processor.tokenizer,
        getattr(model, "device", None),
        max_prompt_tokens=default_prompt_tokens,
    )

    generate_kwargs_base = {
        "language": "th",
        "task": "transcribe",
        "num_beams": max(1, WHISPER_BEAM_SIZE),
        "temperature": (0.0, 0.2, 0.4),
        "compression_ratio_threshold": WHISPER_COMPRESSION_RATIO_THRESHOLD,
        "logprob_threshold": WHISPER_LOG_PROB_THRESHOLD,
        "no_speech_threshold": WHISPER_NO_SPEECH_THRESHOLD,
        "return_timestamps": True,
        "return_segments": True,
        "return_dict_in_generate": True,
    }
    if prompt_ids is not None:
        generate_kwargs_base["prompt_ids"] = prompt_ids
        generate_kwargs_base["prompt_condition_type"] = "first-segment"

    all_words: list[dict] = []
    for ci in range(n_chunks):
        chunk_start_s = ci * _HF_CHUNK_SECONDS
        start_sample = ci * chunk_samples
        end_sample = min(start_sample + chunk_samples, len(audio))
        chunk_audio = audio[start_sample:end_sample]
        chunk_duration = len(chunk_audio) / float(sr)

        inputs = processor(
            chunk_audio,
            sampling_rate=sr,
            return_tensors="pt",
            truncation=False,
            padding="longest",
            return_attention_mask=True,
        )
        input_features = inputs.input_features.to(device=device, dtype=torch_dtype)
        attention_mask = getattr(inputs, "attention_mask", None)
        if attention_mask is not None:
            attention_mask = attention_mask.to(device)

        result = model.generate(
            input_features=input_features,
            attention_mask=attention_mask,
            **generate_kwargs_base,
        )

        items = _extract_hf_generated_items(result, processor.tokenizer, chunk_duration)
        # Offset timestamps to absolute position
        for item in items:
            item["start"] = round(float(item.get("start", 0)) + chunk_start_s, 3)
            item["end"] = round(float(item.get("end", 0)) + chunk_start_s, 3)
        all_words.extend(items)

    before = len(all_words)
    all_words = _filter_hallucinations(all_words)
    if before != len(all_words):
        log_fn(f"⚠ กรอง hallucination ออก {before - len(all_words)} items")
    all_words.sort(key=lambda w: (float(w.get("start", 0) or 0), float(w.get("end", w.get("start", 0)) or 0)))

    stats = _hf_quality_summary(all_words, audio_duration_s)
    log_fn(f"→ transformers chunked stats: {stats}")

    # Split segment-level items into pseudo-words for diarization
    before_split = len(all_words)
    all_words = _split_segments_to_words(all_words)
    if len(all_words) != before_split:
        log_fn(f"→ split segments → {len(all_words)} pseudo-words (was {before_split} segments)")

    log_fn(f"← ถอดเสียงเสร็จ {len(all_words)} items (transformers)")
    return all_words


def transcribe_fw(audio, log_fn) -> list[dict]:
    """Transcribe using faster-whisper.
    Returns list of {"word", "start", "end"}.
    """
    global _whisper_model
    from faster_whisper import WhisperModel

    device, compute = resolve_device_compute()
    model_path = _resolve_model_path(log_fn)
    hotwords = _hotwords_text() or None

    if _whisper_model is None:
        log_fn(f"→ โหลดโมเดล {WHISPER_MODEL} (faster-whisper, {device}, {compute})")
        log_fn("→ กำลังโหลด weights ของ faster-whisper เข้า GPU/หน่วยความจำ...")
        _whisper_model = WhisperModel(model_path, device=device, compute_type=compute)
        log_fn("← โหลด faster-whisper model เสร็จแล้ว")
    else:
        log_fn(f"→ ใช้โมเดล {WHISPER_MODEL} ที่โหลดไว้แล้ว")

    log_fn("→ เริ่มถอดเสียงด้วย faster-whisper...")
    segments_iter, _ = _whisper_model.transcribe(
        audio,
        language="th",
        initial_prompt=_initial_prompt(),
        beam_size=max(1, WHISPER_BEAM_SIZE),
        best_of=max(5, WHISPER_BEAM_SIZE),
        patience=max(1.0, WHISPER_PATIENCE),
        word_timestamps=True,
        vad_filter=WHISPER_VAD_FILTER,
        vad_parameters={
            "min_silence_duration_ms": 500,
            "speech_pad_ms": 200,
            "threshold": 0.45,
        },
        temperature=0.0,
        condition_on_previous_text=WHISPER_CONDITION_ON_PREVIOUS_TEXT,
        no_speech_threshold=WHISPER_NO_SPEECH_THRESHOLD,
        compression_ratio_threshold=WHISPER_COMPRESSION_RATIO_THRESHOLD,
        log_prob_threshold=WHISPER_LOG_PROB_THRESHOLD,
        repetition_penalty=1.5,
        hallucination_silence_threshold=1.0,
        hotwords=hotwords,
    )

    words = []
    seg_count = 0
    low_conf_segments = 0
    non_thai_segments = 0
    suspicious_segments = 0
    fallback_segments = 0
    for seg in segments_iter:
        text = seg.text.strip()
        if not text:
            continue
        seg_count += 1
        if seg.no_speech_prob is not None and seg.no_speech_prob >= WHISPER_NO_SPEECH_THRESHOLD:
            low_conf_segments += 1
        if not has_thai(text):
            non_thai_segments += 1
        if _is_hallucination(text):
            suspicious_segments += 1
        if seg.words:
            for w in seg.words:
                word_text = (w.word or "").strip()
                if not word_text:
                    continue
                words.append({"word": word_text, "start": w.start, "end": w.end})
        else:
            fallback_segments += 1
            start = float(getattr(seg, "start", 0.0) or 0.0)
            end = float(getattr(seg, "end", start + 0.1) or (start + 0.1))
            words.append({"word": text, "start": start, "end": end})

    if low_conf_segments or non_thai_segments or suspicious_segments or fallback_segments:
        log_fn(
            "⚠ faster-whisper quality stats: "
            f"low_conf={low_conf_segments}, non_thai={non_thai_segments}, "
            f"suspicious={suspicious_segments}, fallback_no_words={fallback_segments}"
        )

    # Post-process: remove hallucinated words
    before = len(words)
    words = _filter_hallucinations(words)
    if before != len(words):
        log_fn(f"⚠ กรอง hallucination ออก {before - len(words)} words")
    words.sort(key=lambda word: (float(word.get("start", 0) or 0), float(word.get("end", word.get("start", 0)) or 0)))

    log_fn(f"← ถอดเสียงเสร็จ {seg_count} segments, {len(words)} words (faster-whisper)")
    return words
