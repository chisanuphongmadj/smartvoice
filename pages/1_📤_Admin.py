import json
import os

import streamlit as st

st.set_page_config(page_title="SmartVoice — Admin", page_icon="📤", layout="wide")

from smartvoice import db, file_manager
from smartvoice.ui_helpers import (
    init_page,
    launch_processing,
    launch_processing_queue,
    metric_card,
    status_badge,
)

init_page()

# ─────────────────────────────────────────
# PAGE: ADMIN — Upload & Process
# ─────────────────────────────────────────
st.title("📤 Admin — Upload & Process")

# Upload section
st.subheader("1. Upload Audio Files")
uploaded_files = st.file_uploader(
    "Drop .wav or .mp3 files here",
    type=["wav", "mp3"],
    accept_multiple_files=True,
)

if uploaded_files:
    upload_key = tuple(sorted(uf.name for uf in uploaded_files))
    if st.session_state.get("_last_upload_key") != upload_key:
        st.session_state["_last_upload_key"] = upload_key
        for uf in uploaded_files:
            file_bytes = uf.read()

            if not file_manager.is_allowed_extension(uf.name):
                st.warning(f"⚠️ `{uf.name}` — unsupported format, skipped.")
                continue

            file_hash = file_manager.compute_file_hash(file_bytes)

            existing = db.get_call_by_hash(file_hash)
            if existing:
                if existing["status"] == "error":
                    db.update_call_status(existing["id"], "uploaded", error_msg=None)
                    db.update_processing_step(existing["id"], None)
                    st.warning(f"⚠️ `{uf.name}` มีอยู่แล้ว (status: error) — reset เป็น Pending แล้ว")
                else:
                    st.info(f"ℹ️ `{uf.name}` already exists (duplicate), skipped.")
                continue

            saved_path = file_manager.save_audio_file(file_bytes, uf.name, file_hash)
            db.insert_call(uf.name, file_hash, saved_path)
            st.success(f"✅ `{uf.name}` uploaded and registered.")

st.divider()

# Processing section
st.subheader("2. Process Calls")

calls = db.get_all_calls()
pending    = [c for c in calls if c["status"] == "uploaded"]
processing = [c for c in calls if c["status"] == "processing"]
done       = [c for c in calls if c["status"] == "done"]
errored    = [c for c in calls if c["status"] == "error"]

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown(metric_card(len(pending), "Pending"), unsafe_allow_html=True)
with col2:
    st.markdown(metric_card(len(processing), "Processing"), unsafe_allow_html=True)
with col3:
    st.markdown(metric_card(len(done), "Done"), unsafe_allow_html=True)
with col4:
    st.markdown(metric_card(len(errored), "Errors"), unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

col_a, col_b = st.columns([1, 3])
with col_a:
    process_all_btn = st.button(
        "▶ Process All Pending",
        disabled=len(pending) == 0,
        use_container_width=True,
        type="primary",
    )
with col_b:
    if len(pending) == 0:
        st.info("No pending calls to process.")

if process_all_btn and pending:
    queued = launch_processing_queue([c["id"] for c in pending])
    if "just_launched" not in st.session_state:
        st.session_state.just_launched = set()
    st.session_state.just_launched.update(queued or [])
    st.rerun()

st.divider()

# Individual call actions
st.subheader("3. Individual Call Actions")
if not calls:
    st.caption("No calls uploaded yet.")
else:
    refresh_calls = calls

    if "selected_calls" not in st.session_state:
        st.session_state.selected_calls = set()

    st.session_state.selected_calls = {
        c["id"] for c in refresh_calls
        if st.session_state.get(f"chk_{c['id']}", False)
    }

    bulk_col1, bulk_col2, bulk_col3 = st.columns([1, 1, 2])
    with bulk_col1:
        if st.button("☑ Select All", use_container_width=True):
            st.session_state.selected_calls = {c["id"] for c in refresh_calls}
            for c in refresh_calls:
                st.session_state[f"chk_{c['id']}"] = True
            st.rerun()
    with bulk_col2:
        if st.button("☐ Deselect All", use_container_width=True):
            st.session_state.selected_calls = set()
            for c in refresh_calls:
                st.session_state[f"chk_{c['id']}"] = False
            st.rerun()
    with bulk_col3:
        selected_count = len(st.session_state.selected_calls)
        delete_selected_btn = st.button(
            f"🗑 Delete Selected ({selected_count})",
            disabled=selected_count == 0,
            use_container_width=True,
            type="secondary",
        )

    if delete_selected_btn and st.session_state.selected_calls:
        ids_to_delete = list(st.session_state.selected_calls)
        calls_to_delete = [c for c in refresh_calls if c["id"] in ids_to_delete]
        for call in calls_to_delete:
            if call["file_path"] and os.path.exists(call["file_path"]):
                os.remove(call["file_path"])
        db.delete_calls_bulk(ids_to_delete)
        st.session_state.selected_calls = set()
        st.success(f"ลบ {len(ids_to_delete)} ไฟล์เรียบร้อยแล้ว")
        st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    for call in refresh_calls:
        _eff_st = call["status"]
        if call["id"] in st.session_state.get("just_launched", set()):
            _eff_st = "processing"
        with st.expander(f"🎵 {call['filename']}  —  {_eff_st.upper()}"):
            chk_col, info_col, action_col = st.columns([0.3, 2, 1])
            with chk_col:
                st.checkbox(
                    "เลือก",
                    key=f"chk_{call['id']}",
                    label_visibility="collapsed",
                )

            with info_col:
                st.markdown(f"**File:** `{call['file_path']}`")
                st.markdown(f"**Uploaded:** {call['created_at'][:19].replace('T', ' ')} UTC")
                st.markdown(
                    f"**Status:** {status_badge(_eff_st)}",
                    unsafe_allow_html=True,
                )
                if _eff_st == "processing":
                    step = call.get("processing_step") or "กำลังเริ่มต้น..."
                    updated = call.get("updated_at", "")[:19].replace("T", " ")
                    st.markdown(
                        f'<div style="color:#93c5fd;font-size:0.85rem;margin-top:4px">⏳ {step}</div>'
                        f'<div style="color:#6b7280;font-size:0.75rem">อัปเดตล่าสุด: {updated} UTC</div>',
                        unsafe_allow_html=True,
                    )
                if call["error_msg"]:
                    st.error(f"Error: {call['error_msg'][:300]}")

                # Customer & Warranty context
                cust_link = db.get_call_customer_link(call["id"])
                if cust_link:
                    with st.expander("👤 ข้อมูลลูกค้า & รับประกัน"):
                        cc1, cc2 = st.columns(2)
                        with cc1:
                            st.markdown("**ลูกค้า**")
                            st.markdown(f"ชื่อ: {cust_link['first_name']} {cust_link['last_name']}")
                            st.markdown(f"เบอร์: `{cust_link['phone'] or '-'}`")
                            st.markdown(f"อีเมล: {cust_link['email'] or '-'}")
                        with cc2:
                            if cust_link.get("registration_no"):
                                st.markdown("**ทะเบียนรับประกัน**")
                                st.markdown(f"เลขที่: `{cust_link['registration_no']}`")
                                st.markdown(f"สินค้า: {cust_link.get('brand','')} {cust_link.get('model','')}")
                                st.markdown(f"ขนาด: {cust_link.get('size','')}")
                                st.markdown(f"ช่องทาง: {cust_link.get('purchase_channel','')}")
                                st.markdown(f"วันซื้อ: {cust_link.get('date_of_purchase','')}")
                                months = cust_link.get("warranty_period_months", 0)
                                st.markdown(f"ระยะประกัน: {months} เดือน ({months//12} ปี)")
                else:
                    with st.expander("👤 เชื่อมข้อมูลลูกค้า"):
                        all_custs = db.get_all_customers()
                        if all_custs:
                            cust_options = {f"{c['first_name']} {c['last_name']} ({c['phone'] or '-'})": c["id"] for c in all_custs}
                            sel = st.selectbox("เลือกลูกค้า", ["— เลือก —"] + list(cust_options.keys()), key=f"cust_sel_{call['id']}")
                            if sel != "— เลือก —":
                                cid = cust_options[sel]
                                warrs = db.get_warranties_by_customer(cid)
                                warr_options = {f"{w['registration_no']} — {w['brand']} {w['model']}": w["id"] for w in warrs}
                                wsel = st.selectbox("เลือก Warranty (ถ้ามี)", ["— ไม่ระบุ —"] + list(warr_options.keys()), key=f"warr_sel_{call['id']}")
                                if st.button("🔗 เชื่อม", key=f"link_btn_{call['id']}"):
                                    wid = warr_options.get(wsel) if wsel != "— ไม่ระบุ —" else None
                                    db.link_call_customer(call["id"], cid, wid, matched_by="manual")
                                    st.success("เชื่อมข้อมูลเรียบร้อย")
                                    st.rerun()

                if call["status"] == "done" and call.get("transcript"):
                    with st.expander("🗣 Tagged Transcript"):
                        try:
                            mapping = json.loads(call.get("speaker_mapping") or "{}")
                        except (json.JSONDecodeError, TypeError):
                            mapping = {}

                        def _resolve_role(spk: str, m: dict) -> str:
                            if spk in m:
                                return m[spk]
                            spk_l = spk.lower()
                            for k, v in m.items():
                                if k.lower() == spk_l:
                                    return v
                            import re as _re
                            nums = _re.findall(r"\d+", spk)
                            if nums:
                                n = int(nums[-1])
                                for cand in [f"SPEAKER_{n:02d}", f"Speaker {n}", f"speaker_{n}"]:
                                    if cand in m:
                                        return m[cand]
                                for k, v in m.items():
                                    kn = _re.findall(r"\d+", k)
                                    if kn and int(kn[-1]) == n:
                                        return v
                            return spk

                        if mapping:
                            for raw_line in call["transcript"].splitlines():
                                if ": " in raw_line:
                                    spk, txt = raw_line.split(": ", 1)
                                    role = _resolve_role(spk.strip(), mapping)
                                    color = "#93c5fd" if role == "Agent" else "#86efac"
                                    st.markdown(
                                        f'<span style="color:{color};font-weight:600">[{role}]</span> {txt}',
                                        unsafe_allow_html=True,
                                    )
                                else:
                                    st.markdown(raw_line)
                        else:
                            st.text(call["transcript"])

            with action_col:
                effective_status = call["status"]
                if call["id"] in st.session_state.get("just_launched", set()):
                    effective_status = "processing"

                if effective_status in ("uploaded", "error"):
                    if st.button(
                        "▶ Process",
                        key=f"proc_{call['id']}",
                        use_container_width=True,
                    ):
                        if "just_launched" not in st.session_state:
                            st.session_state.just_launched = set()
                        st.session_state.just_launched.add(call["id"])
                        launch_processing(call["id"])
                        st.rerun()

                if effective_status == "done":
                    if st.button(
                        "🔄 Re-process",
                        key=f"reproc_{call['id']}",
                        use_container_width=True,
                    ):
                        db.update_call_status(call["id"], "uploaded")
                        if "just_launched" not in st.session_state:
                            st.session_state.just_launched = set()
                        st.session_state.just_launched.add(call["id"])
                        launch_processing(call["id"])
                        st.rerun()

                if st.button(
                    "🗑 Delete",
                    key=f"del_{call['id']}",
                    use_container_width=True,
                    type="secondary",
                ):
                    try:
                        if call["file_path"] and os.path.exists(call["file_path"]):
                            os.remove(call["file_path"])
                        db.delete_call(call["id"])
                        st.session_state.selected_calls.discard(call["id"])
                        st.success(f"ลบ `{call['filename']}` เรียบร้อยแล้ว")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"ลบไม่สำเร็จ: {exc}")


@st.fragment(run_every=3)
def _auto_refresh_status():
    fresh_calls = db.get_all_calls()
    active = [c for c in fresh_calls if c["status"] == "processing"]

    has_processing = bool(active)
    if has_processing:
        current = active[0]
        step = current.get("processing_step") or "กำลังเริ่มต้น..."
        remaining = len(active)
        queue_info = f" (เหลือ {remaining} ไฟล์)" if remaining > 1 else ""
        st.info(f"⏳ กำลังประมวลผล `{current['filename'][:40]}`{queue_info}\n\n**ขั้นตอนปัจจุบัน:** {step}")
    else:
        if st.session_state.get("_was_processing", False):
            st.session_state["_was_processing"] = False
            st.rerun()

    st.session_state["_was_processing"] = has_processing

_auto_refresh_status()
