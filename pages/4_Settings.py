"""Friendly runtime settings page."""

import streamlit as st

st.set_page_config(page_title="SmartVoice - Settings", page_icon="⚙️", layout="wide")

from smartvoice.env_settings import (
    DEMO_PRESET,
    REAL_AI_PRESET,
    env_bool,
    mask_secret,
    read_env,
    write_env,
)
from smartvoice.preflight import run_preflight_checks
from smartvoice.ui_helpers import get_current_user, init_page

init_page()

st.title("⚙️ Settings")
st.caption("ปรับโหมด demo และ AI ได้จากหน้านี้ โดยไม่ต้องเปิดไฟล์ `.env` เอง")

current_user, current_role = get_current_user()
if not current_user:
    st.warning("กรุณา login ที่ sidebar ก่อนปรับ settings")
    st.stop()

if current_role not in {"Admin", "Supervisor"}:
    st.error("เฉพาะ Admin หรือ Supervisor เท่านั้นที่ปรับ settings ได้")
    st.stop()

values = read_env()

mode_col, status_col = st.columns([1.2, 1])

with mode_col:
    st.subheader("Quick Mode")
    st.write("เลือก preset แล้วกด Apply เพื่อบันทึกลง `.env`")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Use Demo Laptop Mode", use_container_width=True):
            write_env(DEMO_PRESET)
            st.success("Saved demo mode. Restart the app to apply all settings.")
            st.rerun()
    with c2:
        if st.button("Use Real AI Mode", use_container_width=True):
            write_env(REAL_AI_PRESET)
            st.success("Saved real AI mode. Add HF token if needed, then restart.")
            st.rerun()

with status_col:
    st.subheader("Current Mode")
    is_demo = env_bool(values, "MOCK_STT", default=False)
    st.metric("STT", "Demo / Mock" if is_demo else "Real AI")
    token = values.get("HF_TOKEN", "")
    st.caption(f"HF token: `{mask_secret(token) or 'not set'}`")

st.divider()

st.subheader("Demo & AI Settings")

with st.form("settings_form"):
    demo_mode = st.toggle(
        "Demo mode (skip real STT and use mock transcripts)",
        value=env_bool(values, "MOCK_STT", default=False),
    )

    st.markdown("#### Real AI")
    hf_token = st.text_input(
        "HuggingFace token",
        value="",
        type="password",
        placeholder="Leave blank to keep current token",
        help="Required for pyannote speaker diarization in real AI mode.",
    )
    clear_hf_token = st.checkbox("Clear saved HuggingFace token")

    ollama_base_url = st.text_input(
        "Ollama base URL",
        value=values.get("OLLAMA_BASE_URL", "http://localhost:11434"),
    )
    ollama_model = st.text_input(
        "Ollama model",
        value=values.get("OLLAMA_MODEL", "scb10x/llama3.1-typhoon2-8b-instruct"),
    )

    st.markdown("#### Speech model")
    whisper_model = st.selectbox(
        "Whisper model",
        [
            "biodatlab/distill-whisper-th-large-v3",
            "large-v3",
            "large-v3-turbo",
        ],
        index=[
            "biodatlab/distill-whisper-th-large-v3",
            "large-v3",
            "large-v3-turbo",
        ].index(values.get("WHISPER_MODEL", "biodatlab/distill-whisper-th-large-v3"))
        if values.get("WHISPER_MODEL", "biodatlab/distill-whisper-th-large-v3")
        in {"biodatlab/distill-whisper-th-large-v3", "large-v3", "large-v3-turbo"}
        else 0,
    )
    whisper_backend = st.selectbox(
        "Backend",
        ["auto", "transformers", "faster-whisper"],
        index=["auto", "transformers", "faster-whisper"].index(
            values.get("WHISPER_BACKEND", "transformers")
            if values.get("WHISPER_BACKEND", "transformers") in {"auto", "transformers", "faster-whisper"}
            else "transformers"
        ),
    )
    whisper_device = st.selectbox(
        "Device",
        ["auto", "cpu", "cuda"],
        index=["auto", "cpu", "cuda"].index(
            values.get("WHISPER_DEVICE", "auto")
            if values.get("WHISPER_DEVICE", "auto") in {"auto", "cpu", "cuda"}
            else "auto"
        ),
    )
    whisper_compute = st.selectbox(
        "Compute",
        ["auto", "float16", "int8"],
        index=["auto", "float16", "int8"].index(
            values.get("WHISPER_COMPUTE", "auto")
            if values.get("WHISPER_COMPUTE", "auto") in {"auto", "float16", "int8"}
            else "auto"
        ),
    )

    submitted = st.form_submit_button("Save Settings", use_container_width=True)

if submitted:
    updates = {
        "MOCK_STT": "true" if demo_mode else "false",
        "OLLAMA_BASE_URL": ollama_base_url.strip() or "http://localhost:11434",
        "OLLAMA_MODEL": ollama_model.strip(),
        "WHISPER_MODEL": whisper_model,
        "WHISPER_BACKEND": whisper_backend,
        "WHISPER_DEVICE": whisper_device,
        "WHISPER_COMPUTE": whisper_compute,
    }
    if clear_hf_token:
        updates["HF_TOKEN"] = ""
    elif hf_token.strip():
        updates["HF_TOKEN"] = hf_token.strip()

    write_env(updates)
    st.success("Saved to `.env`. Restart the app with `run.bat` so every module uses the new settings.")

st.divider()

st.subheader("Readiness Checks")
for check in run_preflight_checks():
    if check.ok:
        st.success(f"{check.name}: {check.detail}")
    elif check.severity == "error":
        st.error(f"{check.name}: {check.detail}")
    else:
        st.warning(f"{check.name}: {check.detail}")
