import json
import os

import streamlit as st

st.set_page_config(page_title="SmartVoice — Admin", page_icon="📤", layout="wide")

from smartvoice import db, file_manager
from smartvoice.preflight import get_ollama_readiness, ollama_setup_lines
from smartvoice.ui_helpers import (
    get_current_user,
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

# Require login before allowing uploads — captured for audit trail on each call.
_current_user, _current_role = get_current_user()
if not _current_user:
    st.warning("🔒 กรุณาเข้าสู่ระบบที่ Sidebar ก่อนอัพโหลดไฟล์ (ระบบจะบันทึกว่าใครเป็นผู้อัพโหลดแต่ละไฟล์)")
    st.stop()

st.caption(f"กำลังเข้าสู่ระบบในชื่อ **{_current_user}** (_{_current_role}_) — ไฟล์ที่อัพโหลดจะถูกบันทึกชื่อผู้อัพโหลด")

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
            safe_name = file_manager.sanitize_filename(uf.name)

            is_valid, err_msg = file_manager.validate_upload(file_bytes, safe_name)
            if not is_valid:
                st.warning(f"⚠️ `{safe_name}` — {err_msg}")
                continue

            file_hash = file_manager.compute_file_hash(file_bytes)

            existing = db.get_call_by_hash(file_hash)
            if existing:
                if existing["status"] == "error":
                    db.update_call_status(existing["id"], "uploaded", error_msg=None)
                    db.update_processing_step(existing["id"], None)
                    st.warning(f"⚠️ `{safe_name}` มีอยู่แล้ว (status: error) — reset เป็น Pending แล้ว")
                else:
                    st.info(f"ℹ️ `{safe_name}` already exists (duplicate), skipped.")
                continue

            saved_path = file_manager.save_audio_file(file_bytes, safe_name, file_hash)
            call_id = db.insert_call(
                safe_name, file_hash, saved_path,
                uploaded_by=_current_user,
                uploaded_by_role=_current_role,
            )

            # Auto-link by phone number in filename
            phone = file_manager.extract_phone_from_filename(safe_name)
            if phone:
                db.update_call_customer_phone(call_id, phone)
                link_info = db.auto_link_call_by_phone(call_id, phone)
                if link_info:
                    st.success(
                        f"✅ `{safe_name}` uploaded — 🔗 เชื่อมอัตโนมัติกับ "
                        f"**{link_info['customer_name']}** (📞 {phone})"
                        + (f" + Warranty #{link_info['warranty_id']}" if link_info['warranty_id'] else "")
                    )
                else:
                    st.success(f"✅ `{safe_name}` uploaded — 📞 เบอร์ `{phone}` (ไม่พบลูกค้าในระบบ)")
            else:
                st.success(f"✅ `{safe_name}` uploaded and registered.")

st.divider()

# Processing section
st.subheader("2. Process Calls")

calls = db.get_all_calls()
ollama_ready, ollama_detail = get_ollama_readiness()
processing_blocked = not ollama_ready

if processing_blocked:
    st.error(
        "ยังประมวลผลไม่ได้ใน Real AI mode เพราะ Ollama ยังไม่พร้อม "
        f"({ollama_detail})"
    )
    st.markdown("**วิธีติดตั้ง Ollama และโมเดลที่โปรเจกต์ใช้**")
    for line in ollama_setup_lines():
        st.markdown(line)

# Clean up `just_launched` — remove ids whose DB status has moved past 'processing'.
# (Without this, a call keeps showing PROCESSING forever because the session-state
# override stays even after the pipeline finishes.)
if "just_launched" in st.session_state:
    _active_db_statuses = {c["id"]: c["status"] for c in calls}
    st.session_state.just_launched = {
        cid for cid in st.session_state.just_launched
        if _active_db_statuses.get(cid) in ("uploaded", "processing")
    }

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
        disabled=len(pending) == 0 or processing_blocked,
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

# ── Orphan case cleanup ──
_orphan_count = db.count_orphan_cases()
if _orphan_count > 0:
    orph_col1, orph_col2 = st.columns([1, 3])
    with orph_col1:
        if st.button(
            f"🧹 ล้างเคสค้าง ({_orphan_count})",
            use_container_width=True,
            help="ลบเคสที่ไม่มีสายชี้มา (เกิดจากการลบไฟล์เสียงก่อนหน้า)",
        ):
            removed = db.delete_orphan_cases()
            st.success(f"ลบ {removed} เคสที่ค้างเรียบร้อยแล้ว")
            st.rerun()
    with orph_col2:
        st.caption(f"⚠️ พบ {_orphan_count} เคสที่ไม่มีสายอ้างอิง (orphan) — กดปุ่มซ้ายเพื่อล้าง")

st.divider()

# Individual call actions
st.subheader("3. Individual Call Actions")
if not calls:
    st.caption("No calls uploaded yet.")
else:
    refresh_calls = calls

    if "selected_calls" not in st.session_state:
        st.session_state.selected_calls = set()

    # ── Toolbar: search + status filter + sort ────────────────────────────
    tbar_search, tbar_status, tbar_sort = st.columns([2, 2, 1])
    with tbar_search:
        q = st.text_input(
            "🔍 ค้นหา",
            key="_call_search",
            placeholder="ชื่อไฟล์ / เบอร์ / ผู้อัพโหลด",
            label_visibility="collapsed",
        ).strip().lower()
    with tbar_status:
        status_filter = st.radio(
            "สถานะ",
            ["ทั้งหมด", "Pending", "Processing", "Done", "Error"],
            horizontal=True,
            key="_call_status_filter",
            label_visibility="collapsed",
        )
    with tbar_sort:
        sort_mode = st.selectbox(
            "เรียง",
            ["ใหม่ → เก่า", "เก่า → ใหม่", "ตามสถานะ"],
            key="_call_sort_mode",
            label_visibility="collapsed",
        )

    # Apply filter
    _status_map = {
        "Pending": "uploaded", "Processing": "processing",
        "Done": "done", "Error": "error",
    }
    filtered_calls = refresh_calls
    if status_filter != "ทั้งหมด":
        want = _status_map[status_filter]
        filtered_calls = [c for c in filtered_calls if c["status"] == want]
    if q:
        def _match(c):
            hay = " ".join([
                c.get("filename", "") or "",
                c.get("customer_phone", "") or "",
                c.get("uploaded_by", "") or "",
            ]).lower()
            return q in hay
        filtered_calls = [c for c in filtered_calls if _match(c)]

    # Apply sort
    if sort_mode == "ใหม่ → เก่า":
        filtered_calls = sorted(filtered_calls, key=lambda c: c.get("created_at") or "", reverse=True)
    elif sort_mode == "เก่า → ใหม่":
        filtered_calls = sorted(filtered_calls, key=lambda c: c.get("created_at") or "")
    else:  # ตามสถานะ
        _status_order = {"error": 0, "processing": 1, "uploaded": 2, "done": 3}
        filtered_calls = sorted(
            filtered_calls,
            key=lambda c: (_status_order.get(c["status"], 9), c.get("created_at") or ""),
        )

    # Keep selected_calls in sync with checkbox state (scoped to filtered view)
    st.session_state.selected_calls = {
        c["id"] for c in filtered_calls
        if st.session_state.get(f"chk_{c['id']}", False)
    }

    # Result summary
    st.caption(
        f"พบ **{len(filtered_calls)}** / {len(refresh_calls)} ไฟล์"
        + (f"  •  🔍 `{q}`" if q else "")
        + (f"  •  สถานะ: **{status_filter}**" if status_filter != "ทั้งหมด" else "")
    )

    # ── Bulk actions ──────────────────────────────────────────────────────
    bulk_col1, bulk_col2, bulk_col3 = st.columns([1, 1, 2])
    with bulk_col1:
        if st.button("☑ Select All (ที่กรองอยู่)", use_container_width=True):
            st.session_state.selected_calls = {c["id"] for c in filtered_calls}
            for c in filtered_calls:
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

    # ── Pagination ────────────────────────────────────────────────────────
    PAGE_SIZE = 20
    # Reset page size when search/filter/sort changes, so users aren't stuck
    # seeing a stale "Load more" count after narrowing the list.
    _filter_key = (q, status_filter, sort_mode)
    if st.session_state.get("_call_filter_key") != _filter_key:
        st.session_state._call_filter_key = _filter_key
        st.session_state._call_page_size = PAGE_SIZE
    if "_call_page_size" not in st.session_state:
        st.session_state._call_page_size = PAGE_SIZE
    visible_calls = filtered_calls[: st.session_state._call_page_size]

    # Helper: shrink long filenames with middle ellipsis (keeps head + tail)
    def _shrink_name(name: str, head: int = 22, tail: int = 18) -> str:
        if len(name) <= head + tail + 1:
            return name
        return f"{name[:head]}…{name[-tail:]}"

    # Status → emoji badge for expander title
    _st_icon = {
        "uploaded": "🟣 PENDING", "processing": "🔵 PROCESSING",
        "done": "🟢 DONE", "error": "🔴 ERROR",
    }

    for call in visible_calls:
        _eff_st = call["status"]
        if call["id"] in st.session_state.get("just_launched", set()):
            _eff_st = "processing"
        _phone = call.get("customer_phone") or ""
        _phone_tag = f"  📞 {_phone}" if _phone else ""
        _date_short = (call.get("created_at") or "")[:10]
        _uploader_short = call.get("uploaded_by") or "—"
        _hdr_name = _shrink_name(call["filename"])
        _hdr = (
            f"🎵 {_hdr_name}  —  {_st_icon.get(_eff_st, _eff_st.upper())}"
            f"{_phone_tag}  •  📅 {_date_short}  •  👤 {_uploader_short}"
        )
        with st.expander(_hdr):
            chk_col, info_col, action_col = st.columns([0.3, 2, 1])
            with chk_col:
                st.checkbox(
                    "เลือก",
                    key=f"chk_{call['id']}",
                    label_visibility="collapsed",
                )

            with info_col:
                st.markdown(f"**File:** `{call['file_path']}`")
                if _phone:
                    st.markdown(f"**เบอร์ลูกค้า (จากชื่อไฟล์):** `{_phone}`")
                _uploaded_ts = call['created_at'][:19].replace('T', ' ')
                _uploader = call.get('uploaded_by') or "—"
                _uploader_role = call.get('uploaded_by_role') or ""
                _uploader_label = f"{_uploader} ({_uploader_role})" if _uploader_role else _uploader
                st.markdown(
                    f"**📤 Uploaded:** {_uploaded_ts} UTC &nbsp;•&nbsp; "
                    f"**โดย:** {_uploader_label}"
                )
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
                    _match_badge = "🤖 Auto" if cust_link.get("matched_by") == "auto_phone" else "✋ Manual"
                    with st.expander(f"👤 ข้อมูลลูกค้า & รับประกัน ({_match_badge})"):
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

                # Case info
                if call.get("case_id"):
                    case = db.get_case_by_id(call["case_id"])
                    if case:
                        _case_status_map = {"open": "🟢 เปิด", "follow_up": "🟡 ติดตาม", "closed": "🔴 ปิด"}
                        _cs = _case_status_map.get(case["status"], case["status"])
                        sibling_calls = db.get_calls_by_case(case["id"])
                        with st.expander(f"📂 เคส #{case['id']}: {case['subject']}  —  {_cs}  ({len(sibling_calls)} สาย)"):
                            if len(sibling_calls) > 1:
                                for oc in sibling_calls:
                                    _mark = "👉" if oc["id"] == call["id"] else "  ↳"
                                    st.caption(f"{_mark} 🎵 {oc['filename']}  ({oc['status']})")
                            cs_col1, cs_col2 = st.columns(2)
                            with cs_col1:
                                _status_options = ["open", "follow_up", "closed"]
                                _cur_idx = _status_options.index(case["status"]) if case["status"] in _status_options else 0
                                new_status = st.selectbox(
                                    "เปลี่ยนสถานะเคส",
                                    _status_options,
                                    index=_cur_idx,
                                    format_func=lambda s: {"open": "🟢 เปิด", "follow_up": "🟡 ติดตาม", "closed": "🔴 ปิด"}.get(s, s),
                                    key=f"case_status_{call['id']}",
                                )
                                if new_status != case["status"]:
                                    if st.button("💾 อัปเดทสถานะ", key=f"case_upd_{call['id']}"):
                                        db.update_case_status(case["id"], new_status)
                                        st.success(f"อัปเดทเคส #{case['id']} → {new_status}")
                                        st.rerun()
                            with cs_col2:
                                new_subject = st.text_input(
                                    "แก้ไขหัวข้อเคส",
                                    value=case["subject"],
                                    key=f"case_subj_{call['id']}",
                                )
                                if new_subject != case["subject"]:
                                    if st.button("💾 อัปเดทหัวข้อ", key=f"case_subj_btn_{call['id']}"):
                                        db.update_case_subject(case["id"], new_subject)
                                        st.success("อัปเดทหัวข้อเคสเรียบร้อย")
                                        st.rerun()

                            # Merge with another case (same customer only)
                            link_info = db.get_call_customer_link(call["id"])
                            if link_info:
                                other_cases = [
                                    cs for cs in db.get_cases_by_customer(link_info["customer_id"])
                                    if cs["id"] != case["id"]
                                ]
                                if other_cases:
                                    st.markdown("---")
                                    st.caption("🔗 **รวมเข้ากับเคสอื่น** (ย้ายสายทั้งหมดจากเคสนี้ไปอีกเคส)")
                                    merge_opts = {
                                        f"เคส #{cs['id']}: {cs['subject']} ({cs['status']})": cs["id"]
                                        for cs in other_cases
                                    }
                                    m_col1, m_col2 = st.columns([3, 1])
                                    with m_col1:
                                        picked = st.selectbox(
                                            "เลือกเคสปลายทาง",
                                            list(merge_opts.keys()),
                                            key=f"merge_pick_{call['id']}",
                                            label_visibility="collapsed",
                                        )
                                    with m_col2:
                                        if st.button("🔗 รวม", key=f"merge_btn_{call['id']}"):
                                            dst_id = merge_opts[picked]
                                            moved = db.merge_cases(case["id"], dst_id)
                                            st.success(f"ย้าย {moved} สาย → เคส #{dst_id} และลบเคส #{case['id']}")
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
                        disabled=processing_blocked,
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
                        disabled=processing_blocked,
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

    # ── "Load more" pagination footer ─────────────────────────────────────
    _remaining = len(filtered_calls) - len(visible_calls)
    if _remaining > 0:
        lm_col1, lm_col2 = st.columns([3, 1])
        with lm_col1:
            st.caption(f"แสดง {len(visible_calls)} / {len(filtered_calls)} ไฟล์ (เหลืออีก {_remaining})")
        with lm_col2:
            if st.button(f"⬇ แสดงเพิ่ม ({min(PAGE_SIZE, _remaining)})", use_container_width=True):
                st.session_state._call_page_size += PAGE_SIZE
                st.rerun()
    elif len(filtered_calls) > PAGE_SIZE:
        lm_col1, lm_col2 = st.columns([3, 1])
        with lm_col1:
            st.caption(f"แสดงครบ {len(filtered_calls)} ไฟล์แล้ว")
        with lm_col2:
            if st.button("⬆ ย่อกลับ", use_container_width=True):
                st.session_state._call_page_size = PAGE_SIZE
                st.rerun()


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
