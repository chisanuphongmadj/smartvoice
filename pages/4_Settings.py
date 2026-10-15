"""Friendly runtime settings page."""

import streamlit as st

st.set_page_config(page_title="SmartVoice — ตั้งค่าระบบ", layout="wide")

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
from smartvoice import audit as audit_trail
from smartvoice import discord_notify
from smartvoice.auth import PAGE_SETTINGS
from smartvoice.preflight import run_preflight_checks
from smartvoice.ui_helpers import audit, init_page

# Admin/Supervisor only (see smartvoice.auth.ROLE_PERMISSIONS).
current_user, current_role = init_page(PAGE_SETTINGS)

st.title("ตั้งค่าระบบ")
st.caption(
    "ปรับโหมดการทำงานของ AI และการแจ้งเตือน Discord ได้จากหน้านี้ โดยไม่ต้องแก้ไฟล์ `.env` เอง "
    "— ค่าส่วนใหญ่มีผลหลังเปิดโปรแกรมใหม่ (ปิดแล้วเปิด run.bat อีกครั้ง)"
)


@st.cache_data(ttl=300, show_spinner="กำลังตรวจความพร้อมของระบบ...")
def _cached_preflight_checks():
    """Readiness checks hit Ollama and HuggingFace over the network (~2.6 s).
    Uncached, every click on this page waited for them."""
    return run_preflight_checks()

values = read_env()

mode_col, status_col = st.columns([1.2, 1])

with mode_col:
    st.subheader("เลือกโหมดด่วน")
    st.write("กดปุ่มเดียวเพื่อตั้งค่าทั้งชุด")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("โหมดสาธิต (ไม่ต้องใช้ GPU)", use_container_width=True,
                     help="ใช้บทสนทนาตัวอย่างแทนการถอดเสียงจริง — เหมาะกับโน้ตบุ๊กหรือการนำเสนอ"):
            write_env(DEMO_PRESET)
            audit(
                audit_trail.UPDATE, audit_trail.ENTITY_SETTINGS,
                entity_label="Demo Laptop Mode", changes=dict(DEMO_PRESET),
            )
            st.success("บันทึกโหมดสาธิตแล้ว — ปิดและเปิดโปรแกรมใหม่เพื่อให้มีผล")
            st.rerun()
    with c2:
        if st.button("โหมดใช้งานจริง (AI เต็มรูปแบบ)", use_container_width=True,
                     help="ถอดเสียงจริงด้วย Whisper + แยกผู้พูด — ต้องมี HuggingFace token และเครื่องแรงพอ"):
            write_env(REAL_AI_PRESET)
            audit(
                audit_trail.UPDATE, audit_trail.ENTITY_SETTINGS,
                entity_label="Real AI Mode", changes=dict(REAL_AI_PRESET),
            )
            st.success("บันทึกโหมดใช้งานจริงแล้ว — ใส่ HuggingFace token (ถ้ายังไม่มี) แล้วเปิดโปรแกรมใหม่")
            st.rerun()

with status_col:
    st.subheader("โหมดปัจจุบัน")
    is_demo = env_bool(values, "MOCK_STT", default=False)
    st.metric("การถอดเสียง", "โหมดสาธิต" if is_demo else "ใช้งานจริง")
    token = values.get("HF_TOKEN", "")
    st.caption(f"HuggingFace token: `{mask_secret(token) or 'ยังไม่ได้ตั้งค่า'}`")

st.divider()

st.subheader("ตั้งค่าโดยละเอียด")

# NOTE: This section is intentionally NOT wrapped in `st.form` so the
# Whisper model selector can fire its `on_change` callback immediately —
# inside a form, on_change is deferred until form submit. We use a regular
# `st.button` at the bottom to commit all values to `.env` together.

demo_mode = st.toggle(
    "โหมดสาธิต (ไม่ถอดเสียงจริง ใช้บทสนทนาตัวอย่าง)",
    value=env_bool(values, "MOCK_STT", default=False),
)

st.markdown("#### AI สำหรับการใช้งานจริง")
hf_token = st.text_input(
    "HuggingFace token",
    value="",
    type="password",
    placeholder="เว้นว่างไว้ = ใช้ค่าเดิม",
    help="จำเป็นสำหรับการแยกเสียงพนักงาน/ลูกค้า (pyannote) ในโหมดใช้งานจริง",
    key="_hf_token_input",
)
clear_hf_token = st.checkbox("ลบ HuggingFace token ที่บันทึกไว้")

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

st.markdown("#### โมเดลถอดเสียง (Whisper)")

# GPU availability check — hides cuda from Device dropdown when no GPU
# is present, so the user can't accidentally save a combo that will crash
# later in `model.to('cuda')`.
_has_gpu = gpu_available()
if _has_gpu:
    st.success(f"ตรวจพบ GPU: **{gpu_device_name() or 'CUDA device'}** — เลือก device=cuda ได้")
else:
    st.warning(
        "ไม่พบ GPU บนเครื่องนี้ — option `cuda` ถูกซ่อนจาก Device dropdown "
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
    "หมายเหตุ: เปลี่ยน Whisper model → ระบบจะปรับ Backend / Device / Compute เป็นค่าแนะนำให้อัตโนมัติ "
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

st.markdown("#### แจ้งเตือน Discord")
st.caption(
    "ส่งข้อความเข้าช่อง Discord ทุกครั้งที่มีคนรับเคส คืนเคส ปิดเคส หรือเปิดเคสอีกครั้ง — "
    "สร้าง webhook ได้ที่ Discord: ตั้งค่าช่อง → Integrations → Webhooks → New Webhook → Copy Webhook URL"
)
_saved_webhook = values.get(discord_notify.ENV_KEY, "")
st.caption(f"Webhook ปัจจุบัน: `{mask_secret(_saved_webhook) or 'ยังไม่ได้ตั้งค่า (ไม่ส่งแจ้งเตือน)'}`")
discord_webhook = st.text_input(
    "Discord webhook URL",
    value="",
    type="password",
    placeholder="เว้นว่างไว้ = ใช้ค่าเดิม",
    help="URL นี้เป็นความลับ — ใครมี URL ก็โพสต์เข้าช่องได้ ระบบจึงไม่แสดงเต็มและไม่บันทึกลง Audit log",
    key="_discord_webhook_input",
)
clear_discord_webhook = st.checkbox("ปิดการแจ้งเตือน Discord (ลบ webhook ที่บันทึกไว้)")
if st.button("ส่งข้อความทดสอบ", key="_discord_test_btn",
             help="ใช้ URL ที่พิมพ์ไว้ด้านบน ถ้าเว้นว่างจะใช้ค่าที่บันทึกไว้"):
    _ok, _detail = discord_notify.post(
        discord_notify.build_test_payload(current_user),
        url=discord_webhook.strip() or None,
    )
    (st.success if _ok else st.error)(_detail)

submitted = st.button("บันทึกการตั้งค่า", use_container_width=True, type="primary")

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

    webhook_error = None
    if clear_discord_webhook:
        updates[discord_notify.ENV_KEY] = ""
    elif discord_webhook.strip():
        if discord_notify.is_valid_webhook_url(discord_webhook):
            updates[discord_notify.ENV_KEY] = discord_webhook.strip()
        else:
            webhook_error = (
                "ไม่ได้บันทึก Discord webhook — URL ต้องขึ้นต้นด้วย "
                "`https://discord.com/api/webhooks/` (ค่าอื่นบันทึกแล้วตามปกติ)"
            )

    # HF_TOKEN / DISCORD_WEBHOOK_URL are redacted by smartvoice.audit before they reach the log.
    changed = audit_trail.diff_fields(values, updates)
    write_env(updates)
    if changed:
        audit(
            audit_trail.UPDATE, audit_trail.ENTITY_SETTINGS,
            entity_label="Save Settings", changes=changed,
        )
    st.success("บันทึกแล้ว — ปิดและเปิดโปรแกรมใหม่ด้วย `run.bat` เพื่อให้ค่าใหม่มีผลทุกส่วน")
    if webhook_error:
        st.error(webhook_error)

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

st.subheader("ตรวจความพร้อมของระบบ")
if st.button("ตรวจสอบใหม่", key="_settings_recheck"):
    _cached_preflight_checks.clear()
for check in _cached_preflight_checks():
    if check.ok:
        st.success(f"{check.name}: {check.detail}")
    elif check.severity == "error":
        st.error(f"{check.name}: {check.detail}")
    else:
        st.warning(f"{check.name}: {check.detail}")
