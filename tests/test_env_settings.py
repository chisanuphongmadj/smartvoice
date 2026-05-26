"""Tests for UI-managed .env settings."""

from pathlib import Path

from smartvoice import env_settings


def test_mask_secret():
    assert env_settings.mask_secret("") == ""
    assert env_settings.mask_secret("abc") == "***"
    assert env_settings.mask_secret("hf_1234567890") == "hf_123...7890"


def test_env_bool():
    assert env_settings.env_bool({"MOCK_STT": "true"}, "MOCK_STT")
    assert env_settings.env_bool({"MOCK_STT": "1"}, "MOCK_STT")
    assert not env_settings.env_bool({"MOCK_STT": "false"}, "MOCK_STT")
    assert env_settings.env_bool({}, "MISSING", default=True)


def test_write_and_read_env(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    monkeypatch.setattr(env_settings, "ENV_EXAMPLE_PATH", Path("__missing__"))

    env_settings.write_env({"MOCK_STT": "true", "OLLAMA_MODEL": "demo"}, env_file)
    values = env_settings.read_env(env_file)

    assert values["MOCK_STT"] == "true"
    assert values["OLLAMA_MODEL"] == "demo"


def test_write_env_updates_existing_file_without_replacing_destination(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("# keep me\nMOCK_STT=false\n", encoding="utf-8")
    monkeypatch.setattr(env_settings, "ENV_EXAMPLE_PATH", Path("__missing__"))

    env_settings.write_env({"MOCK_STT": "true", "OLLAMA_MODEL": "demo"}, env_file)

    assert env_file.read_text(encoding="utf-8") == (
        "# keep me\nMOCK_STT=true\nOLLAMA_MODEL=demo\n"
    )


# ── Whisper combo validator ─────────────────────────────────────────────────
# These checks make sure the Settings page can flag incompatible
# device / compute / backend combos *before* the next process_call would
# crash. The Settings UI also hides `cuda` from the Device dropdown when
# no GPU is present (defence in depth).

def _severities(issues):
    return {sev for sev, _ in issues}


def test_validate_combo_cuda_without_gpu_is_error():
    issues = env_settings.validate_whisper_combo(
        model="biodatlab/distill-whisper-th-large-v3",
        backend="transformers",
        device="cuda",
        compute="float16",
        has_gpu=False,
    )
    assert "error" in _severities(issues)


def test_validate_combo_cpu_float16_is_warning():
    issues = env_settings.validate_whisper_combo(
        model="large-v3",
        backend="faster-whisper",
        device="cpu",
        compute="float16",
        has_gpu=True,
    )
    assert "warning" in _severities(issues)
    assert "error" not in _severities(issues)


def test_validate_combo_auto_no_gpu_float16_is_warning():
    # device=auto + no GPU resolves to cpu — float16 is still mismatched
    issues = env_settings.validate_whisper_combo(
        model="large-v3",
        backend="faster-whisper",
        device="auto",
        compute="float16",
        has_gpu=False,
    )
    assert "warning" in _severities(issues)


def test_validate_combo_fw_nonstandard_model_is_info():
    issues = env_settings.validate_whisper_combo(
        model="biodatlab/distill-whisper-th-large-v3",
        backend="faster-whisper",
        device="cpu",
        compute="int8",
        has_gpu=False,
    )
    assert "info" in _severities(issues)
    assert "error" not in _severities(issues)


def test_validate_combo_clean_gpu_setup():
    issues = env_settings.validate_whisper_combo(
        model="biodatlab/distill-whisper-th-large-v3",
        backend="transformers",
        device="cuda",
        compute="float16",
        has_gpu=True,
    )
    assert issues == []


def test_validate_combo_clean_cpu_setup():
    issues = env_settings.validate_whisper_combo(
        model="large-v3",
        backend="faster-whisper",
        device="cpu",
        compute="int8",
        has_gpu=False,
    )
    # large-v3 is a standard FW model → no CT2 info, no warnings
    assert issues == []


def test_validate_combo_clean_auto_setup():
    # auto + auto on a GPU host → no warnings of any kind
    issues = env_settings.validate_whisper_combo(
        model="biodatlab/distill-whisper-th-large-v3",
        backend="transformers",
        device="auto",
        compute="auto",
        has_gpu=True,
    )
    assert issues == []


def test_gpu_available_is_boolean():
    # gpu_available must never raise — runs on hosts without torch installed too
    assert isinstance(env_settings.gpu_available(), bool)


def test_gpu_device_name_returns_none_or_string():
    name = env_settings.gpu_device_name()
    assert name is None or isinstance(name, str)


# ── Per-model recommended combo ─────────────────────────────────────────────
# The Settings page auto-applies these when the user picks a model so users
# don't have to remember the backend/device/compute pairing for each model.

def test_recommended_combo_thai_model_uses_transformers():
    # biodatlab is the Thai-tuned HF model — transformers backend avoids the
    # 5-10 min CT2 conversion that faster-whisper would otherwise trigger
    combo = env_settings.recommended_combo_for_model(
        "biodatlab/distill-whisper-th-large-v3", has_gpu=True
    )
    assert combo == ("transformers", "auto", "auto")


def test_recommended_combo_standard_models_use_faster_whisper():
    # Standard Whisper checkpoints are faster on faster-whisper
    assert env_settings.recommended_combo_for_model("large-v3", has_gpu=True) == (
        "faster-whisper", "auto", "auto",
    )
    assert env_settings.recommended_combo_for_model("large-v3-turbo", has_gpu=True) == (
        "faster-whisper", "auto", "auto",
    )


def test_recommended_combo_unknown_model_returns_none():
    # Unknown model → caller should keep current user values
    assert env_settings.recommended_combo_for_model("some/random-model", has_gpu=True) is None


def test_recommended_combo_downgrades_cuda_when_no_gpu(monkeypatch):
    # Simulate a hypothetical future entry whose recommended device is "cuda"
    monkeypatch.setitem(
        env_settings._MODEL_RECOMMENDED_COMBO,
        "gpu-only-model",
        ("faster-whisper", "cuda", "float16"),
    )
    combo = env_settings.recommended_combo_for_model("gpu-only-model", has_gpu=False)
    # device must be downgraded so the recommendation doesn't crash on CPU-only hosts
    assert combo is not None and combo[1] == "auto"


def test_recommended_combo_keeps_cuda_when_gpu_present(monkeypatch):
    monkeypatch.setitem(
        env_settings._MODEL_RECOMMENDED_COMBO,
        "gpu-only-model",
        ("faster-whisper", "cuda", "float16"),
    )
    combo = env_settings.recommended_combo_for_model("gpu-only-model", has_gpu=True)
    assert combo == ("faster-whisper", "cuda", "float16")


def test_recommended_combo_has_gpu_none_keeps_recommendation():
    # Default has_gpu=None should not trigger downgrade logic
    combo = env_settings.recommended_combo_for_model(
        "biodatlab/distill-whisper-th-large-v3"
    )
    assert combo == ("transformers", "auto", "auto")
