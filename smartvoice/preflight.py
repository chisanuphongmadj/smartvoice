"""Environment readiness checks for local demo/deployment handoff."""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass

import requests

from smartvoice.auth import is_auth_configured
from smartvoice.config import HF_TOKEN, MOCK_STT, OLLAMA_BASE_URL


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str
    severity: str = "warning"


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

    try:
        response = requests.get(f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags", timeout=2)
        ollama_ok = response.ok
        detail = "server reachable" if ollama_ok else f"server returned HTTP {response.status_code}"
    except requests.RequestException as exc:
        ollama_ok = False
        detail = f"server not reachable: {exc.__class__.__name__}"
    checks.append(CheckResult("Ollama server", ollama_ok, detail, "warning"))

    data_dir = os.path.abspath("data")
    checks.append(CheckResult(
        "Local data directory",
        os.path.isdir(data_dir),
        data_dir,
        "warning",
    ))

    return checks
