"""Read and update local `.env` settings from the Streamlit UI."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from dotenv import dotenv_values, set_key


ENV_PATH = Path(".env")
ENV_EXAMPLE_PATH = Path(".env.example")


def ensure_env_file(path: Path = ENV_PATH) -> Path:
    """Create `.env` from `.env.example` if it does not exist."""
    if path.exists():
        return path
    if ENV_EXAMPLE_PATH.exists():
        shutil.copyfile(ENV_EXAMPLE_PATH, path)
    else:
        path.write_text("", encoding="utf-8")
    return path


def read_env(path: Path = ENV_PATH) -> dict[str, str]:
    ensure_env_file(path)
    values = dotenv_values(path)
    return {key: value or "" for key, value in values.items()}


def write_env(updates: dict[str, str], path: Path = ENV_PATH) -> None:
    ensure_env_file(path)
    safe_updates = {
        key: "" if value is None else str(value) for key, value in updates.items()
    }

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / ".env"
        shutil.copyfile(path, temp_path)
        for key, safe_value in safe_updates.items():
            set_key(str(temp_path), key, safe_value, quote_mode="auto")
        path.write_text(temp_path.read_text(encoding="utf-8"), encoding="utf-8")

    for key, safe_value in safe_updates.items():
        os.environ[key] = safe_value


def env_bool(values: dict[str, str], key: str, default: bool = False) -> bool:
    raw = values.get(key)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def mask_secret(value: str, visible: int = 6) -> str:
    if not value:
        return ""
    if len(value) <= visible:
        return "*" * len(value)
    return f"{value[:visible]}...{value[-4:]}"


DEMO_PRESET = {
    "MOCK_STT": "true",
    "WHISPER_DEVICE": "cpu",
    "WHISPER_COMPUTE": "int8",
}

REAL_AI_PRESET = {
    "MOCK_STT": "false",
    "WHISPER_BACKEND": "transformers",
    "WHISPER_MODEL": "biodatlab/distill-whisper-th-large-v3",
    "WHISPER_DEVICE": "auto",
    "WHISPER_COMPUTE": "auto",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "scb10x/llama3.1-typhoon2-8b-instruct",
}


# Whisper models that faster-whisper can load natively (no CT2 conversion).
# Must stay in sync with `smartvoice/stt/transcribe.py:_STANDARD_MODELS`.
_FW_STANDARD_MODELS: frozenset[str] = frozenset({
    "tiny", "tiny.en", "base", "base.en", "small", "small.en",
    "medium", "medium.en", "large-v1", "large-v2", "large-v3",
    "large", "distil-large-v2", "distil-large-v3",
    "large-v3-turbo", "turbo",
})


# Per-model recommended (backend, device, compute) combo. The Settings page
# auto-applies these defaults when the user picks a model so the user never
# has to know that biodatlab needs `transformers` while large-v3 prefers
# `faster-whisper`. Picking `auto` for device/compute lets resolve_device_compute()
# adapt at runtime to whatever hardware is present.
_MODEL_RECOMMENDED_COMBO: dict[str, tuple[str, str, str]] = {
    # Thai-tuned HF model — best on transformers (no CT2 conversion needed)
    "biodatlab/distill-whisper-th-large-v3": ("transformers", "auto", "auto"),
    # Standard Whisper checkpoints — faster-whisper is meaningfully quicker
    "large-v3":       ("faster-whisper", "auto", "auto"),
    "large-v3-turbo": ("faster-whisper", "auto", "auto"),
}


def recommended_combo_for_model(
    model: str,
    has_gpu: bool | None = None,
) -> tuple[str, str, str] | None:
    """Return the (backend, device, compute) combo recommended for `model`.

    When `has_gpu` is False and the recommendation includes `cuda`, the device
    is downgraded to `auto` so the host's lack of GPU doesn't cause a crash.
    Returns ``None`` for unknown models so the Settings page can keep current
    user values instead of overriding them.
    """
    combo = _MODEL_RECOMMENDED_COMBO.get(model)
    if combo is None:
        return None
    backend, device, compute = combo
    if device == "cuda" and has_gpu is False:
        device = "auto"
    return backend, device, compute


def gpu_available() -> bool:
    """Return True if a CUDA-capable GPU is reachable from this process.

    Safe to call when torch is not importable (e.g. demo-only deploys); falls
    back to False instead of raising.
    """
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def gpu_device_name() -> str | None:
    """Return the first CUDA device's marketing name, or None if no GPU."""
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.get_device_name(0)
    except Exception:
        pass
    return None


def validate_whisper_combo(
    model: str,
    backend: str,
    device: str,
    compute: str,
    has_gpu: bool,
) -> list[tuple[str, str]]:
    """Validate the Whisper model / backend / device / compute combination.

    Returns a list of ``(severity, message)`` tuples where ``severity`` is one
    of ``"error"`` / ``"warning"`` / ``"info"``. An empty list means the combo
    is clean. The Settings page calls this after save so the user sees
    actionable feedback before the next `process_call()` would otherwise crash.
    """
    issues: list[tuple[str, str]] = []

    # device=cuda requires a real GPU — pipeline would crash on .to('cuda')
    if device == "cuda" and not has_gpu:
        issues.append((
            "error",
            "เลือก device=cuda แต่ไม่พบ GPU บนเครื่องนี้ — pipeline จะ crash ตอน "
            "process call ครั้งถัดไป (เปลี่ยนเป็น device=auto หรือ cpu)",
        ))

    # compute=float16 is GPU-only in practice — CPU inference must use int8/auto
    if device == "cpu" and compute == "float16":
        issues.append((
            "warning",
            "compute=float16 ออกแบบมาสำหรับ GPU — บน CPU แนะนำ compute=int8 หรือ auto "
            "เพื่อให้ inference เสถียรและเร็วกว่า",
        ))

    # device=auto + no GPU resolves to cpu → float16 still mismatched
    if device == "auto" and not has_gpu and compute == "float16":
        issues.append((
            "warning",
            "เครื่องนี้ไม่มี GPU → device=auto จะตกเป็น cpu — แนะนำเปลี่ยน compute "
            "เป็น int8 หรือ auto",
        ))

    # faster-whisper + non-standard HF model triggers a one-time CT2 conversion
    if backend == "faster-whisper" and model and model not in _FW_STANDARD_MODELS:
        issues.append((
            "info",
            f"backend=faster-whisper + model={model} → ระบบจะแปลงโมเดลเป็น CT2 "
            "ก่อนใช้งานครั้งแรก (~5-10 นาที, ทำครั้งเดียวเก็บแคชไว้) — "
            "หรือเปลี่ยน backend เป็น transformers เพื่อข้ามขั้นตอนนี้",
        ))

    return issues
