"""Tests for environment readiness helpers."""

from unittest import mock

import httpx

from smartvoice.preflight import recommend_cuda_wheel_tag


def test_recommend_cuda_wheel_tag_prefers_highest_supported_tag():
    assert recommend_cuda_wheel_tag("12.9") == "cu128"
    assert recommend_cuda_wheel_tag("12.8") == "cu128"
    assert recommend_cuda_wheel_tag("12.7") == "cu126"
    assert recommend_cuda_wheel_tag("12.6") == "cu126"
    assert recommend_cuda_wheel_tag("12.5") == "cu118"
    assert recommend_cuda_wheel_tag("11.8") == "cu118"


def test_recommend_cuda_wheel_tag_returns_none_when_unsupported_or_missing():
    assert recommend_cuda_wheel_tag("11.7") is None
    assert recommend_cuda_wheel_tag("") is None
    assert recommend_cuda_wheel_tag(None) is None
    assert recommend_cuda_wheel_tag("unknown") is None


def test_get_ollama_readiness_allows_demo_mode(monkeypatch):
    from smartvoice import preflight

    monkeypatch.setattr(preflight, "MOCK_STT", True)

    assert preflight.get_ollama_readiness() == (True, "demo mode")


def test_get_ollama_readiness_requires_cli(monkeypatch):
    from smartvoice import preflight

    monkeypatch.setattr(preflight, "MOCK_STT", False)
    with mock.patch("smartvoice.preflight.shutil.which", return_value=None):
        assert preflight.get_ollama_readiness() == (False, "Ollama CLI not found in PATH")


def test_get_ollama_readiness_requires_configured_model(monkeypatch):
    from smartvoice import preflight

    monkeypatch.setattr(preflight, "MOCK_STT", False)
    monkeypatch.setattr(preflight, "OLLAMA_MODEL", "required-model")

    response = mock.Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"models": [{"name": "other-model"}]}

    with mock.patch("smartvoice.preflight.shutil.which", return_value="ollama"):
        with mock.patch("smartvoice.preflight.requests.get", return_value=response):
            assert preflight.get_ollama_readiness() == (
                False,
                "model `required-model` not found",
            )


def test_get_ollama_readiness_accepts_configured_model(monkeypatch):
    from smartvoice import preflight

    monkeypatch.setattr(preflight, "MOCK_STT", False)
    monkeypatch.setattr(preflight, "OLLAMA_MODEL", "required-model")

    response = mock.Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"models": [{"name": "required-model"}]}

    with mock.patch("smartvoice.preflight.shutil.which", return_value="ollama"):
        with mock.patch("smartvoice.preflight.requests.get", return_value=response):
            assert preflight.get_ollama_readiness() == (True, "ready")


def test_get_ollama_readiness_accepts_latest_tag_for_untagged_model(monkeypatch):
    from smartvoice import preflight

    monkeypatch.setattr(preflight, "MOCK_STT", False)
    monkeypatch.setattr(preflight, "OLLAMA_MODEL", "required-model")

    response = mock.Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"models": [{"name": "required-model:latest"}]}

    with mock.patch("smartvoice.preflight.shutil.which", return_value="ollama"):
        with mock.patch("smartvoice.preflight.requests.get", return_value=response):
            assert preflight.get_ollama_readiness() == (True, "ready")


def test_get_pyannote_access_readiness_skips_demo_mode(monkeypatch):
    from smartvoice import preflight

    monkeypatch.setattr(preflight, "MOCK_STT", True)
    monkeypatch.setattr(preflight, "HF_TOKEN", "")

    assert preflight.get_pyannote_access_readiness() == (True, "not required in demo mode")


def test_get_pyannote_access_readiness_requires_token(monkeypatch):
    from smartvoice import preflight

    monkeypatch.setattr(preflight, "MOCK_STT", False)
    monkeypatch.setattr(preflight, "HF_TOKEN", "")

    assert preflight.get_pyannote_access_readiness() == (False, "not checked; add HF_TOKEN first")


def test_get_pyannote_access_readiness_requires_gated_model_access(monkeypatch):
    from huggingface_hub.errors import GatedRepoError

    from smartvoice import preflight

    monkeypatch.setattr(preflight, "MOCK_STT", False)
    monkeypatch.setattr(preflight, "HF_TOKEN", "hf_test")
    response = httpx.Response(
        403,
        request=httpx.Request("GET", "https://huggingface.co/pyannote/speaker-diarization-3.1"),
    )

    with mock.patch(
        "smartvoice.preflight.get_hf_file_metadata",
        side_effect=GatedRepoError("gated", response=response),
    ):
        assert preflight.get_pyannote_access_readiness() == (
            False,
            "access not granted for `pyannote/speaker-diarization-3.1`; accept the HuggingFace license first",
        )


def test_get_pyannote_access_readiness_accepts_required_models(monkeypatch):
    from smartvoice import preflight

    monkeypatch.setattr(preflight, "MOCK_STT", False)
    monkeypatch.setattr(preflight, "HF_TOKEN", "hf_test")

    with mock.patch("smartvoice.preflight.get_hf_file_metadata") as metadata:
        assert preflight.get_pyannote_access_readiness() == (
            True,
            "ready for gated pyannote models",
        )

    assert metadata.call_count == 2


def test_get_pyannote_access_readiness_reports_network_failures(monkeypatch):
    from smartvoice import preflight

    monkeypatch.setattr(preflight, "MOCK_STT", False)
    monkeypatch.setattr(preflight, "HF_TOKEN", "hf_test")

    with mock.patch(
        "smartvoice.preflight.get_hf_file_metadata",
        side_effect=httpx.ConnectError("blocked"),
    ):
        assert preflight.get_pyannote_access_readiness() == (
            False,
            "could not reach HuggingFace; check internet, firewall, or proxy settings",
        )


def test_run_preflight_checks_marks_demo_mode(monkeypatch):
    from smartvoice import preflight

    monkeypatch.setattr(preflight, "MOCK_STT", True)
    monkeypatch.setattr(preflight, "HF_TOKEN", "")
    with mock.patch("smartvoice.preflight.shutil.which", return_value="ollama"):
        with mock.patch("smartvoice.preflight.get_ollama_readiness", return_value=(True, "demo mode")):
            checks = {check.name: check for check in preflight.run_preflight_checks()}

    assert checks["Speech-to-text mode"].ok is False
    assert checks["Speech-to-text mode"].detail == "demo mode enabled; real STT and diarization are skipped"
    assert checks["HuggingFace token"].ok is True
    assert checks["Pyannote access"].ok is True
