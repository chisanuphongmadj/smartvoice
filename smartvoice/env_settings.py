"""Read and update local `.env` settings from the Streamlit UI."""

from __future__ import annotations

import os
import shutil
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
    for key, value in updates.items():
        safe_value = "" if value is None else str(value)
        set_key(str(path), key, safe_value, quote_mode="auto")
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
