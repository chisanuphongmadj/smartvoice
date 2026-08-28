"""Friendly runtime settings page."""

import streamlit as st

st.set_page_config(page_title="SmartVoice - Settings", page_icon="⚙️", layout="wide")

from smartvoice.env_settings import (
    DEMO_PRESET,
    REAL_AI_PRESET,
    env_bool,
    gpu_available,
    gpu_device_name,
    mask_secret,
    read_env,
    recommended_combo_for_model,
    validate_whisper_combo,
    write_env,
)
from smartvoice.auth import PAGE_SETTINGS
from smartvoice.preflight import run_preflight_checks
from smartvoice.ui_helpers import init_page

# Admin/Supervisor only (see smartvoice.auth.ROLE_PERMISSIONS).
current_user, current_role = init_page(PAGE_SETTINGS)

st.title("⚙️ Settings")
st.caption("ปรับโหมด demo และ AI ได้จากหน้านี้ โดยไม่ต้องเปิดไฟล์ `.env` เอง")

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

# NOTE: This section is intentionally NOT wrapped in `st.form` so the
# Whisper model selector can fire its `on_change` callback immediately —
# inside a form, on_change is deferred until form submit. We use a regular
# `st.button` at the bottom to commit all values to `.env` together.

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
    key="_hf_token_input",
)
clear_hf_token = st.checkbox("Clear saved HuggingFace token")

ollama_base_url = st.text_input(
    "Ollama base URL",
    value=values.get("OLLAMA_BASE_URL", "http://localhost:11434"),
    key="_ollama_base_url_input",
)
ollama_model = st.text_input(
    "Ollama model",
    value=values.get("OLLAMA_MODEL", "scb10x/llama3.1-typhoon2-8b-instruct"),
    key="_ollama_model_input",
)

st.markdown("#### Speech model")

# GPU availability check — hides cuda from Device dropdown when no GPU
# is present, so the user can't accidentally save a combo that will crash
# later in `model.to('cuda')`.
_has_gpu = gpu_available()
if _has_gpu:
    st.success(f"🚀 ตรวจพบ GPU: **{gpu_device_name() or 'CUDA device'}** — เลือก device=cuda ได้")
else:
    st.warning(
        "⚠️ ไม่พบ GPU บนเครื่องนี้ — option `cuda` ถูกซ่อนจาก Device dropdown "
        "เพื่อกัน pipeline crash ตอน process. แนะนำ device=cpu + compute=int8"
    )

# ── Option lists + session_state seeding ────────────────────────────────────
# Seed session_state from .env once per session so widgets render with the
# user's last-saved values. After that, the model selector's on_change
# callback can rewrite backend/device/compute keys to apply the recommended
# combo for the newly-picked model.
_WHISPER_MODELS = [
    "biodatlab/distill-whisper-th-large-v3",
    "large-v3",
    "large-v3-turbo",
]
_BACKEND_OPTIONS = ["auto", "transformers", "faster-whisper"]
_COMPUTE_OPTIONS = ["auto", "float16", "int8"]
_DEVICE_OPTIONS = ["auto", "cpu"] + (["cuda"] if _has_gpu else [])


def _seed_state(state_key: str, env_key: str, default: str, allowed) -> None:
    if state_key not in st.session_state:
        saved = values.get(env_key, default)
        if saved not in allowed:
            saved = default
        st.session_state[state_key] = saved


_seed_state("_whisper_model_select",   "WHISPER_MODEL",   _WHISPER_MODELS[0], _WHISPER_MODELS)
_seed_state("_whisper_backend_select", "WHISPER_BACKEND", "transformers",     _BACKEND_OPTIONS)
_seed_state("_whisper_device_select",  "WHISPER_DEVICE",  "auto",             _DEVICE_OPTIONS)
_seed_state("_whisper_compute_select", "WHISPER_COMPUTE", "auto",             _COMPUTE_OPTIONS)


def _apply_model_recommendations() -> None:
    """Snap Backend / Device / Compute to the recommended combo for the
    currently-picked model. Fires as the Whisper model selectbox's on_change."""
    selected = st.session_state.get("_whisper_model_select")
    combo = recommended_combo_for_model(selected, has_gpu=_has_gpu)
    if combo is None:
        return
    backend, device, compute = combo
    # Stay within the dropdown choices presented by this UI render
    if device not in _DEVICE_OPTIONS:
        device = "auto"
    st.session_state["_whisper_backend_select"] = backend
    st.session_state["_whisper_device_select"] = device
    st.session_state["_whisper_compute_select"] = compute


st.caption(
    "💡 เปลี่ยน Whisper model → ระบบจะปรับ Backend / Device / Compute เป็นค่าแนะนำให้อัตโนมัติ "
    "(หลังจากนั้นปรับเองได้)"
)
whisper_model = st.selectbox(
    "Whisper model",
    _WHISPER_MODELS,
    key="_whisper_model_select",
    on_change=_apply_model_recommendations,
    help=(
        "biodatlab/distill-whisper-th-large-v3 → แม่นยำสำหรับภาษาไทย (แนะนำ backend=transformers)  •  "
        "large-v3 / large-v3-turbo → เร็วกว่า (แนะนำ backend=faster-whisper)"
    ),
)
whisper_backend = st.selectbox(
    "Backend",
    _BACKEND_OPTIONS,
    key="_whisper_backend_select",
    help=(
        "transformers → ใช้ได้กับทุก HF model ทันที  •  "
        "faster-whisper → เร็วกว่า แต่ถ้าโมเดลไม่ใช่ standard name "
        "(large-v3, large-v3-turbo, ฯลฯ) ระบบจะแปลง CT2 ก่อนใช้งานครั้งแรก (~5-10 นาที)"
    ),
)
whisper_device = st.selectbox(
    "Device",
    _DEVICE_OPTIONS,
    key="_whisper_device_select",
    help="auto = ตรวจ GPU เอง (cuda ถ้ามี, ไม่งั้น cpu)",
)
whisper_compute = st.selectbox(
    "Compute",
    _COMPUTE_OPTIONS,
    key="_whisper_compute_select",
    help=(
        "auto → จับคู่กับ device อัตโนมัติ (cuda→float16, cpu→int8)  •  "
        "float16 → เร็วบน GPU เท่านั้น  •  int8 → quantized, ดีสำหรับ CPU"
    ),
)

submitted = st.button("Save Settings", use_container_width=True, type="primary")

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

    # Run combo validation after save so the user sees actionable feedback
    # before the next `process_call()` would otherwise crash.
    _issues = validate_whisper_combo(
        model=whisper_model,
        backend=whisper_backend,
        device=whisper_device,
        compute=whisper_compute,
        has_gpu=_has_gpu,
    )
    for severity, message in _issues:
        if severity == "error":
            st.error(message)
        elif severity == "warning":
            st.warning(message)
        else:
            st.info(message)

st.divider()

st.subheader("Readiness Checks")
for check in run_preflight_checks():
    if check.ok:
        st.success(f"{check.name}: {check.detail}")
    elif check.severity == "error":
        st.error(f"{check.name}: {check.detail}")
    else:
        st.warning(f"{check.name}: {check.detail}")
