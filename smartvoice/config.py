"""Centralized configuration — all environment variables in one place."""

import os

def _get_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _get_int(name: str, default: str) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return int(default)


def _get_float(name: str, default: str) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return float(default)

# ── STT ──────────────────────────────────────────────────────────────────
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "biodatlab/distill-whisper-th-large-v3")
WHISPER_BACKEND = os.getenv("WHISPER_BACKEND", "transformers")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "auto")
WHISPER_COMPUTE = os.getenv("WHISPER_COMPUTE", "auto")
WHISPER_BEAM_SIZE = _get_int("WHISPER_BEAM_SIZE", "5")
WHISPER_HOTWORDS = os.getenv("WHISPER_HOTWORDS", "")
WHISPER_VAD_FILTER = _get_bool("WHISPER_VAD_FILTER", "false")
WHISPER_CONDITION_ON_PREVIOUS_TEXT = _get_bool("WHISPER_CONDITION_ON_PREVIOUS_TEXT", "false")
WHISPER_NO_SPEECH_THRESHOLD = _get_float("WHISPER_NO_SPEECH_THRESHOLD", "0.6")
WHISPER_LOG_PROB_THRESHOLD = _get_float("WHISPER_LOG_PROB_THRESHOLD", "-1.0")
WHISPER_COMPRESSION_RATIO_THRESHOLD = _get_float("WHISPER_COMPRESSION_RATIO_THRESHOLD", "2.4")
WHISPER_PATIENCE = _get_float("WHISPER_PATIENCE", "1.2")
DENOISE_ENABLED = _get_bool("DENOISE_ENABLED", "true")
DENOISE_PROP_DECREASE = _get_float("DENOISE_PROP_DECREASE", "0.35")
HF_TOKEN = os.getenv("HF_TOKEN", "")
MOCK_STT = _get_bool("MOCK_STT", "false")

# ── LLM ──────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "scb10x/llama3.1-typhoon2-8b-instruct")

# ── Reports ──────────────────────────────────────────────────────────────
# Thai TrueType font for the Dashboard PDF. Blank = use the first one found
# among the usual system fonts (Tahoma / Leelawadee on Windows, Noto Sans Thai
# or TLWG fonts on Linux).
REPORT_FONT_PATH = os.getenv("REPORT_FONT_PATH", "")

# ── Database ─────────────────────────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "data/smartvoice.db")

# ── Case Auto-Assignment ─────────────────────────────────────────────────
# When a new call arrives from a customer who has an open case with a recent
# sibling call (within this many hours), auto-attach WITHOUT asking the LLM.
# This handles the common "customer called back 5 min later" / "dropped call
# resumed" pattern, which LLM topic-matching misses when topics drift.
# Set to 0 to disable the short-circuit and always use LLM matching.
CASE_RECENCY_HOURS = _get_float("CASE_RECENCY_HOURS", "4.0")

# Reset calls that were left in `processing` after the app/process was killed.
# Set to 0 to disable automatic recovery.
PROCESSING_STALE_MINUTES = _get_int("PROCESSING_STALE_MINUTES", "180")
