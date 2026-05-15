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
