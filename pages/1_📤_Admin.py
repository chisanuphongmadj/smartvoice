import json
import os

import streamlit as st

st.set_page_config(page_title="SmartVoice — Admin", layout="wide")

from smartvoice import audit as audit_trail
from smartvoice import case_workflow, db, file_manager
from smartvoice.auth import PAGE_ADMIN, role_label
from smartvoice.file_manager import extract_direction_from_filename
from smartvoice.preflight import get_ollama_readiness, ollama_setup_lines
from smartvoice.ui_helpers import (
    audit,
    current_case_actor,
    init_page,
    launch_processing,
    launch_processing_queue,
    metric_card,
    render_case_ownership,
    status_badge,
)

# Admin/Supervisor only — Agent and QA never see this page in the sidebar, and
# this guard also blocks a hand-typed /admin URL.
_current_user, _current_role = init_page(PAGE_ADMIN)

# ─────────────────────────────────────────
# PAGE: ADMIN — Upload & Process
# ─────────────────────────────────────────
st.title("Admin — อัปโหลดและประมวลผล")

st.caption(f"กำลังเข้าสู่ระบบในชื่อ **{_current_user}** — _{role_label(_current_role)}_ — ไฟล์ที่อัพโหลดจะถูกบันทึกชื่อผู้อัพโหลด")

# Upload section
st.subheader("1. อัปโหลดไฟล์เสียง")
uploaded_files = st.file_uploader(
    "ลากไฟล์ .wav หรือ .mp3 มาวางที่นี่",
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
                st.warning(f"`{safe_name}` — {err_msg}")
                continue

            file_hash = file_manager.compute_file_hash(file_bytes)

            existing = db.get_call_by_hash(file_hash)
            if existing:
                if existing["status"] == "error":
                    db.update_call_status(existing["id"], "uploaded", error_msg=None)
                    db.update_processing_step(existing["id"], None)
                    st.warning(f"`{safe_name}` มีอยู่แล้ว (สถานะ: ผิดพลาด) — ตั้งกลับเป็นรอประมวลผลแล้ว")
                else:
                    st.info(f"`{safe_name}` มีอยู่แล้ว (ไฟล์ซ้ำ) — ข้ามไฟล์นี้")
                continue

            saved_path = file_manager.save_audio_file(file_bytes, safe_name, file_hash)
            call_id = db.insert_call(
                safe_name, file_hash, saved_path,
                uploaded_by=_current_user,
                uploaded_by_role=_current_role,
            )
            audit(
                audit_trail.CREATE,
                audit_trail.ENTITY_CALL,
                entity_id=call_id,
                entity_label=safe_name,
                changes={"file_hash": file_hash, "size_mb": round(len(file_bytes) / 1048576, 2)},
            )

            # Auto-link by phone number in filename
            phone = file_manager.extract_phone_from_filename(safe_name)
            if phone:
                db.update_call_customer_phone(call_id, phone)
                link_info = db.auto_link_call_by_phone(call_id, phone)
                if link_info:
                    st.success(
                        f"อัปโหลด `{safe_name}` แล้ว — เชื่อมอัตโนมัติกับ "
                        f"**{link_info['customer_name']}** (เบอร์ {phone})"
                        + (f" + ทะเบียนรับประกัน #{link_info['warranty_id']}" if link_info['warranty_id'] else "")
                    )
                else:
                    st.success(f"อัปโหลด `{safe_name}` แล้ว — เบอร์ `{phone}` (ไม่พบลูกค้าในระบบ)")
            else:
                st.success(f"อัปโหลด `{safe_name}` และบันทึกเข้าระบบแล้ว")

st.divider()

# Processing section
st.subheader("2. ประมวลผลสาย")

# ── Scale-friendly counts: SQL aggregate so it stays fast at 10K+ rows ─────
# (the Admin list below is capped to "latest N" via a user picker — these
#  counts always reflect the WHOLE table, not the capped subset)
_counts = db.count_calls_by_status()
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

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown(metric_card(_counts["uploaded"], "รอประมวลผล"), unsafe_allow_html=True)
with col2:
    st.markdown(metric_card(_counts["processing"], "กำลังประมวลผล"), unsafe_allow_html=True)
with col3:
    st.markdown(metric_card(_counts["done"], "เสร็จแล้ว"), unsafe_allow_html=True)
with col4:
    st.markdown(metric_card(_counts["error"], "ผิดพลาด"), unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

col_a, col_b = st.columns([1, 3])
with col_a:
    process_all_btn = st.button(
        "ประมวลผลทั้งหมดที่รออยู่",
        disabled=_counts["uploaded"] == 0 or processing_blocked,
        use_container_width=True,
        type="primary",
    )
with col_b:
    if _counts["uploaded"] == 0:
        st.info("ไม่มีสายที่รอประมวลผล")

if process_all_btn and _counts["uploaded"] > 0:
    # Lazy fetch — only the IDs we need, and only when the button is clicked
    pending_ids = db.get_pending_call_ids()
    queued = launch_processing_queue(pending_ids)
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
            f"ล้างเคสค้าง ({_orphan_count})",
            use_container_width=True,
            help="ลบเคสที่ไม่มีสายชี้มา (เกิดจากการลบไฟล์เสียงก่อนหน้า)",
        ):
            removed = db.delete_orphan_cases()
            st.success(f"ลบ {removed} เคสที่ค้างเรียบร้อยแล้ว")
            st.rerun()
    with orph_col2:
        st.caption(f"พบ {_orphan_count} เคสที่ไม่มีสายอ้างอิง (orphan) — กดปุ่มซ้ายเพื่อล้าง")

st.divider()

# Individual call actions
st.subheader("3. จัดการสายรายไฟล์")
if _counts["total"] == 0:
    st.caption("ยังไม่มีสายที่อัปโหลดเข้ามา")
else:
    # ── Load-limit picker (ops-focused: usually browsing recent uploads) ──
    # บริษัทมีไฟล์เสียงเป็นหมื่นๆ ไฟล์ — โหลดทั้งหมดทุกครั้งจะหน่วงระบบ
    _ADMIN_LIMIT_OPTIONS = {
        "100 สายล่าสุด": 100,
        "200 สายล่าสุด": 200,
        "500 สายล่าสุด": 500,
        "1,000 สายล่าสุด": 1000,
        "5,000 สายล่าสุด": 5000,
        "ทั้งหมด (อาจช้าเมื่อข้อมูลเยอะ)": None,
    }
    # Default — ops users mostly look at recent uploads, so a tighter default
    # keeps the page snappy. 200 latest ≈ 10 pages of pagination (PAGE_SIZE=20),
    # enough for a normal browsing session.
    _default_admin_limit = (
        "ทั้งหมด (อาจช้าเมื่อข้อมูลเยอะ)" if _counts["total"] <= 200 else "200 สายล่าสุด"
    )
    if "_admin_load_limit" not in st.session_state:
        st.session_state["_admin_load_limit"] = _default_admin_limit

    lim_col1, lim_col2 = st.columns([1, 3])
    with lim_col1:
        st.selectbox(
            "ขอบเขตการโหลด",
            list(_ADMIN_LIMIT_OPTIONS.keys()),
            key="_admin_load_limit",
            help="จำกัดจำนวนสายที่โหลดเข้ามาแสดง เพื่อให้หน้านี้เปิดเร็วเมื่อมีไฟล์เยอะมาก",
        )
    _admin_limit = _ADMIN_LIMIT_OPTIONS.get(st.session_state["_admin_load_limit"])
    with lim_col2:
        if _admin_limit is not None and _counts["total"] > _admin_limit:
            st.caption(
                f"โหลด {_admin_limit:,} สายล่าสุดจากทั้งหมด {_counts['total']:,} สาย"
                "  •  ถ้าต้องค้นสายเก่ากว่านี้ ให้ขยายขอบเขตด้านซ้าย"
            )

    refresh_calls = db.get_all_calls(limit=_admin_limit)

    # Clean up `just_launched` — remove ids whose status has moved past
    # 'processing'. Use the same loaded subset (newest calls are the most
    # likely candidates; older just_launched ids are rare and will self-clear
    # on the next refresh when their status changes).
    if "just_launched" in st.session_state:
        _active_db_statuses = {c["id"]: c["status"] for c in refresh_calls}
        st.session_state.just_launched = {
            cid for cid in st.session_state.just_launched
            if _active_db_statuses.get(cid) in ("uploaded", "processing")
        }

    if "selected_calls" not in st.session_state:
        st.session_state.selected_calls = set()

    # ── Toolbar: search + status filter + sort ────────────────────────────
    tbar_search, tbar_status, tbar_sort = st.columns([2, 2, 1])
    with tbar_search:
        q = st.text_input(
            "ค้นหา",
            key="_call_search",
            placeholder="ชื่อไฟล์ / เบอร์ / ผู้อัพโหลด",
            label_visibility="collapsed",
        ).strip().lower()
    with tbar_status:
        status_filter = st.radio(
            "สถานะ",
            ["ทั้งหมด", "รอประมวลผล", "กำลังประมวลผล", "เสร็จแล้ว", "ผิดพลาด"],
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

    # Direction filter — derived from filename suffix (-Inbound.wav / -Outbound.wav).
    # Omazz CDR system tags every file this way; no DB column needed.
    direction_filter = st.radio(
        "ทิศทางสาย",
        ["ทั้งหมด", "สายเข้า (Inbound)", "สายออก (Outbound)"],
        horizontal=True,
        key="_call_direction_filter",
        label_visibility="collapsed",
    )

    # Apply filter
    _status_map = {
        "รอประมวลผล": "uploaded", "กำลังประมวลผล": "processing",
        "เสร็จแล้ว": "done", "ผิดพลาด": "error",
    }
    _direction_map = {
        "สายเข้า (Inbound)": "inbound",
        "สายออก (Outbound)": "outbound",
    }
    filtered_calls = refresh_calls
    if status_filter != "ทั้งหมด":
        want = _status_map[status_filter]
        filtered_calls = [c for c in filtered_calls if c["status"] == want]
    if direction_filter != "ทั้งหมด":
        want_dir = _direction_map[direction_filter]
        filtered_calls = [
            c for c in filtered_calls
            if extract_direction_from_filename(c.get("filename", "")) == want_dir
        ]
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
        + (f"  •  `{q}`" if q else "")
        + (f"  •  สถานะ: **{status_filter}**" if status_filter != "ทั้งหมด" else "")
        + (f"  •  ทิศทาง: **{direction_filter}**" if direction_filter != "ทั้งหมด" else "")
    )

    # ── Bulk actions ──────────────────────────────────────────────────────
    bulk_col1, bulk_col2, bulk_col3 = st.columns([1, 1, 2])
    with bulk_col1:
        if st.button("เลือกทั้งหมด (ที่กรองอยู่)", use_container_width=True):
            st.session_state.selected_calls = {c["id"] for c in filtered_calls}
            for c in filtered_calls:
                st.session_state[f"chk_{c['id']}"] = True
            st.rerun()
    with bulk_col2:
        if st.button("ยกเลิกการเลือกทั้งหมด", use_container_width=True):
            st.session_state.selected_calls = set()
            for c in refresh_calls:
                st.session_state[f"chk_{c['id']}"] = False
            st.rerun()
    with bulk_col3:
        selected_count = len(st.session_state.selected_calls)
        delete_selected_btn = st.button(
            f"ลบที่เลือกไว้ ({selected_count})",
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
        for call in calls_to_delete:
            audit(
                audit_trail.DELETE,
                audit_trail.ENTITY_CALL,
                entity_id=call["id"],
                entity_label=call["filename"],
                changes={"status": call["status"], "bulk": True},
            )
        st.session_state.selected_calls = set()
        st.success(f"ลบ {len(ids_to_delete)} ไฟล์เรียบร้อยแล้ว")
        st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Pagination ────────────────────────────────────────────────────────
    PAGE_SIZE = 20
    # Reset page size when search/filter/sort changes, so users aren't stuck
    # seeing a stale "Load more" count after narrowing the list.
    _filter_key = (q, status_filter, direction_filter, sort_mode)
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

    # Status word for the expander title — no icons: the label has to read the
    # same as the status filter above it.
    _st_label = {
        "uploaded": "รอประมวลผล", "processing": "กำลังประมวลผล",
        "done": "เสร็จแล้ว", "error": "ผิดพลาด",
    }

    for call in visible_calls:
        _eff_st = call["status"]
        if call["id"] in st.session_state.get("just_launched", set()):
            _eff_st = "processing"
        _phone = call.get("customer_phone") or ""
        _phone_tag = f"  •  เบอร์: {_phone}" if _phone else ""
        _date_short = (call.get("created_at") or "")[:10]
        _uploader_short = call.get("uploaded_by") or "—"
        _hdr_name = _shrink_name(call["filename"])
        _hdr = (
            f"ไฟล์: {_hdr_name}  —  สถานะ: {_st_label.get(_eff_st, _eff_st)}"
            f"{_phone_tag}  •  วันที่: {_date_short}  •  ผู้อัปโหลด: {_uploader_short}"
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
                    f"**อัปโหลดเมื่อ:** {_uploaded_ts} UTC &nbsp;•&nbsp; "
                    f"**โดย:** {_uploader_label}"
                )
                st.markdown(
                    f"**สถานะ:** {status_badge(_eff_st)}",
                    unsafe_allow_html=True,
                )
                if _eff_st == "processing":
                    step = call.get("processing_step") or "กำลังเริ่มต้น..."
                    updated = call.get("updated_at", "")[:19].replace("T", " ")
                    st.markdown(
                        f'<div style="color:#93c5fd;font-size:0.85rem;margin-top:4px">{step}</div>'
                        f'<div style="color:#6b7280;font-size:0.75rem">อัปเดตล่าสุด: {updated} UTC</div>',
                        unsafe_allow_html=True,
                    )
                if call["error_msg"]:
                    st.error(f"Error: {call['error_msg'][:300]}")

                # Customer & Warranty context
                cust_link = db.get_call_customer_link(call["id"])
                if cust_link:
                    _match_badge = "จับคู่อัตโนมัติ" if cust_link.get("matched_by") == "auto_phone" else "จับคู่เอง"
                    with st.expander(f"ข้อมูลลูกค้า & รับประกัน ({_match_badge})"):
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
                    with st.expander("เชื่อมข้อมูลลูกค้า"):
                        all_custs = db.get_all_customers()
                        if all_custs:
                            cust_options = {f"{c['first_name']} {c['last_name']} ({c['phone'] or '-'})": c["id"] for c in all_custs}
                            sel = st.selectbox("เลือกลูกค้า", ["— เลือก —"] + list(cust_options.keys()), key=f"cust_sel_{call['id']}")
                            if sel != "— เลือก —":
                                cid = cust_options[sel]
                                warrs = db.get_warranties_by_customer(cid)
                                warr_options = {f"{w['registration_no']} — {w['brand']} {w['model']}": w["id"] for w in warrs}
                                wsel = st.selectbox("เลือก Warranty (ถ้ามี)", ["— ไม่ระบุ —"] + list(warr_options.keys()), key=f"warr_sel_{call['id']}")
                                if st.button("เชื่อมข้อมูล", key=f"link_btn_{call['id']}"):
                                    wid = warr_options.get(wsel) if wsel != "— ไม่ระบุ —" else None
                                    db.link_call_customer(call["id"], cid, wid, matched_by="manual")
                                    audit(
                                        audit_trail.UPDATE,
                                        audit_trail.ENTITY_CALL,
                                        entity_id=call["id"],
                                        entity_label=call["filename"],
                                        changes={"linked_customer_id": cid, "linked_warranty_id": wid},
                                    )
                                    st.success("เชื่อมข้อมูลเรียบร้อย")
                                    st.rerun()

                # Case info
                if call.get("case_id"):
                    case = db.get_case_detail(call["case_id"])
                    if case:
                        _case_status_map = {"open": "เปิด", "follow_up": "ติดตาม", "closed": "ปิด"}
                        _cs = _case_status_map.get(case["status"], case["status"])
                        _owner = case.get("assignee_name") or "ยังไม่มีคนรับ"
                        sibling_calls = db.get_calls_by_case(case["id"])
                        with st.expander(f"เคส #{case['id']}: {case['subject']}  —  สถานะ: {_cs}  •  ผู้รับเคส: {_owner}  ({len(sibling_calls)} สาย)"):
                            if len(sibling_calls) > 1:
                                for oc in sibling_calls:
                                    _mark = "สายนี้:" if oc["id"] == call["id"] else "  ↳"
                                    st.caption(f"{_mark} {oc['filename']}  ({_st_label.get(oc['status'], oc['status'])})")
                            cs_col1, cs_col2 = st.columns(2)
                            with cs_col1:
                                # Claim / status / release — status changes only by
                                # whoever claimed the case (smartvoice.case_workflow).
                                render_case_ownership(case, key_suffix=f"call{call['id']}")
                            with cs_col2:
                                new_subject = st.text_input(
                                    "แก้ไขหัวข้อเคส",
                                    value=case["subject"],
                                    key=f"case_subj_{call['id']}_{case['id']}",
                                )
                                if new_subject != case["subject"]:
                                    if st.button("บันทึกหัวข้อ", key=f"case_subj_btn_{call['id']}"):
                                        db.update_case_subject(case["id"], new_subject)
                                        audit(
                                            audit_trail.UPDATE,
                                            audit_trail.ENTITY_CASE,
                                            entity_id=case["id"],
                                            entity_label=new_subject,
                                            changes={"subject": [case["subject"], new_subject]},
                                        )
                                        st.success("อัปเดทหัวข้อเคสเรียบร้อย")
                                        st.rerun()

                            # Merge with another case (same customer only)
                            link_info = db.get_call_customer_link(call["id"])
                            if link_info:
                                other_cases = [
                                    cs for cs in db.get_cases_by_customer(link_info["customer_id"])
                                    if cs["id"] != case["id"]
                                ]
                                _held_by_other = case.get("assignee_username") and not case_workflow.is_owner(
                                    case, current_case_actor()
                                )
                                if other_cases and _held_by_other:
                                    st.markdown("---")
                                    st.caption(
                                        f"รวมเคสไม่ได้ — เคสนี้ {case['assignee_name']} รับไว้อยู่ "
                                        "ต้องคืนเคสหรือปลดผู้รับเคสก่อน"
                                    )
                                elif other_cases:
                                    st.markdown("---")
                                    st.caption("**รวมเข้ากับเคสอื่น** (ย้ายสายทั้งหมดจากเคสนี้ไปอีกเคส)")
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
                                        if st.button("รวมเคส", key=f"merge_btn_{call['id']}"):
                                            dst_id = merge_opts[picked]
                                            moved = db.merge_cases(case["id"], dst_id)
                                            audit(
                                                audit_trail.DELETE,
                                                audit_trail.ENTITY_CASE,
                                                entity_id=case["id"],
                                                entity_label=case["subject"],
                                                changes={"merged_into_case_id": dst_id, "moved_calls": moved},
                                            )
                                            st.success(f"ย้าย {moved} สาย → เคส #{dst_id} และลบเคส #{case['id']}")
                                            st.rerun()

                if call["status"] == "done" and call.get("transcript"):
                    with st.expander("บทสนทนาแยกผู้พูด"):
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
                        "ประมวลผล",
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
                        "ประมวลผลใหม่",
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
                    "ลบไฟล์นี้",
                    key=f"del_{call['id']}",
                    use_container_width=True,
                    type="secondary",
                ):
                    try:
                        if call["file_path"] and os.path.exists(call["file_path"]):
                            os.remove(call["file_path"])
                        db.delete_call(call["id"])
                        audit(
                            audit_trail.DELETE,
                            audit_trail.ENTITY_CALL,
                            entity_id=call["id"],
                            entity_label=call["filename"],
                            changes={"status": call["status"]},
                        )
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
            if st.button(f"แสดงเพิ่ม ({min(PAGE_SIZE, _remaining)})", use_container_width=True):
                st.session_state._call_page_size += PAGE_SIZE
                st.rerun()
    elif len(filtered_calls) > PAGE_SIZE:
        lm_col1, lm_col2 = st.columns([3, 1])
        with lm_col1:
            st.caption(f"แสดงครบ {len(filtered_calls)} ไฟล์แล้ว")
        with lm_col2:
            if st.button("ย่อกลับ", use_container_width=True):
                st.session_state._call_page_size = PAGE_SIZE
                st.rerun()


@st.fragment(run_every=3)
def _auto_refresh_status():
    # Scope to processing-only rows — this fragment runs every 3 seconds,
    # so scanning the full calls table here is wasteful at 10K+ uploads.
    active = db.get_processing_calls()

    has_processing = bool(active)
    if has_processing:
        current = active[0]
        step = current.get("processing_step") or "กำลังเริ่มต้น..."
        remaining = len(active)
        queue_info = f" (เหลือ {remaining} ไฟล์)" if remaining > 1 else ""
        st.info(f"กำลังประมวลผล `{current['filename'][:40]}`{queue_info}\n\n**ขั้นตอนปัจจุบัน:** {step}")
    else:
        if st.session_state.get("_was_processing", False):
            st.session_state["_was_processing"] = False
            st.rerun()

    st.session_state["_was_processing"] = has_processing

_auto_refresh_status()
