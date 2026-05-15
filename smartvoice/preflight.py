"""Environment readiness checks for local demo/deployment handoff."""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass

import requests

from smartvoice.auth import is_auth_configured
from smartvoice.config import HF_TOKEN, MOCK_STT, OLLAMA_BASE_URL, OLLAMA_MODEL


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str
    severity: str = "warning"


def recommend_cuda_wheel_tag(cuda_version: str | None) -> str | None:
    if not cuda_version:
        return None
    try:
        major_text, minor_text, *_ = cuda_version.strip().split(".")
        version = (int(major_text), int(minor_text))
    except (TypeError, ValueError):
        return None
    if version >= (12, 8):
        return "cu128"
    if version >= (12, 6):
        return "cu126"
    if version >= (11, 8):
        return "cu118"
    return None


def _canonical_ollama_model_name(model_name: str) -> str:
    final_segment = model_name.rsplit("/", 1)[-1]
    return model_name if ":" in final_segment else f"{model_name}:latest"


def get_ollama_readiness() -> tuple[bool, str]:
    if MOCK_STT:
        return True, "demo mode"

    ollama_binary = shutil.which("ollama")
    if not ollama_binary:
        return False, "Ollama CLI not found in PATH"

    try:
        response = requests.get(f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags", timeout=2)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        return False, f"Ollama server not reachable: {exc.__class__.__name__}"

    models = {
        _canonical_ollama_model_name(model["name"])
        for model in data.get("models", [])
        if isinstance(model, dict) and model.get("name")
    }
    if _canonical_ollama_model_name(OLLAMA_MODEL) not in models:
        return False, f"model `{OLLAMA_MODEL}` not found"
    return True, "ready"


def ollama_setup_lines() -> list[str]:
    return [
        "1. ติดตั้ง Ollama จาก https://ollama.com",
        "2. เปิด terminal แล้วรัน `ollama serve`",
        f"3. เปิด terminal อีกหน้าต่างแล้วรัน `ollama pull {OLLAMA_MODEL}`",
        "4. กลับมาหน้านี้แล้วรีเฟรชอีกครั้ง",
    ]


def run_preflight_checks() -> list[CheckResult]:
    """Return high-signal setup checks shown on the home page."""
    checks: list[CheckResult] = []

    py_ok = (3, 10) <= sys.version_info[:2] <= (3, 11)
    checks.append(CheckResult(
        "Python",
        py_ok,
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} "
        "(recommended: 3.10 or 3.11)",
        "error",
    ))

    checks.append(CheckResult(
        "Authentication",
        is_auth_configured(),
        "SMARTVOICE_USERS is configured" if is_auth_configured()
        else "SMARTVOICE_USERS is empty; sidebar login is demo/audit-only",
        "warning",
    ))

    checks.append(CheckResult(
        "HuggingFace token",
        bool(HF_TOKEN) or MOCK_STT,
        "ready" if HF_TOKEN else "missing; diarization is skipped unless MOCK_STT=true",
        "warning",
    ))

    ollama_binary = shutil.which("ollama")
    checks.append(CheckResult(
        "Ollama CLI",
        bool(ollama_binary),
        ollama_binary or "not found in PATH",
        "warning",
    ))

    ollama_ready, detail = get_ollama_readiness()
    checks.append(CheckResult("Ollama", ollama_ready, detail, "warning"))

    data_dir = os.path.abspath("data")
    checks.append(CheckResult(
        "Local data directory",
        os.path.isdir(data_dir),
        data_dir,
        "warning",
    ))

    return checks
