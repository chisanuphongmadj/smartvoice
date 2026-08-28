"""Admin-only staff account management."""

import pandas as pd
import streamlit as st

st.set_page_config(page_title="SmartVoice — Users", page_icon="👤", layout="wide")

from smartvoice import db
from smartvoice.auth import (
    PAGE_LABELS_TH,
    PAGE_USERS,
    ROLE_LABELS_TH,
    ROLES,
    create_user,
    normalize_role,
    reset_password,
    role_label,
    visible_pages,
    would_remove_last_admin,
)
from smartvoice.ui_helpers import get_current_user_id, init_page

# Admin only (see smartvoice.auth.ROLE_PERMISSIONS).
current_user, current_role = init_page(PAGE_USERS)

st.title("👤 จัดการผู้ใช้")
st.caption("เพิ่ม / แก้ไขบทบาท / รีเซ็ตรหัสผ่าน / ปิดการใช้งานบัญชีพนักงาน")

_me = get_current_user_id()
users = db.get_all_users()

# ── Existing accounts ────────────────────────────────────────────────────
st.subheader("บัญชีทั้งหมด")

if not users:
    st.info("ยังไม่มีบัญชีในฐานข้อมูล — บัญชีที่ใช้อยู่มาจาก `SMARTVOICE_USERS` ใน `.env`")
else:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Username": u["username"],
                    "ชื่อที่แสดง": u["display_name"],
                    "บทบาท": role_label(u["role"]),
                    "สถานะ": "✅ ใช้งาน" if u["is_active"] else "🚫 ปิดใช้งาน",
                    "เข้าระบบล่าสุด": (u["last_login_at"] or "—")[:19].replace("T", " "),
                    "สร้างเมื่อ": u["created_at"][:19].replace("T", " "),
                }
                for u in users
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )

st.divider()

# ── Add a new account ────────────────────────────────────────────────────
st.subheader("➕ เพิ่มผู้ใช้ใหม่")

with st.form("_add_user_form"):
    c1, c2 = st.columns(2)
    with c1:
        new_username = st.text_input("Username", placeholder="เช่น somchai.p")
        new_display = st.text_input("ชื่อที่แสดง", placeholder="เช่น สมชาย ประเสริฐ")
    with c2:
        new_role = st.selectbox(
            "บทบาท",
            ROLES,
            index=ROLES.index("Agent"),
            format_func=lambda r: f"{r} ({ROLE_LABELS_TH[r]})",
        )
        new_password = st.text_input("รหัสผ่าน", type="password")
        new_confirm = st.text_input("ยืนยันรหัสผ่าน", type="password")

    st.caption(
        "สิทธิ์ของบทบาทที่เลือก: "
        + " · ".join(PAGE_LABELS_TH[page] for page in visible_pages(new_role))
    )
    add_submitted = st.form_submit_button("สร้างบัญชี")

if add_submitted:
    _, error = create_user(
        username=new_username,
        password=new_password,
        role=new_role,
        display_name=new_display,
        confirm=new_confirm,
    )
    if error:
        st.error(error)
    else:
        st.success(f"สร้างบัญชี `{new_username.strip()}` เรียบร้อยแล้ว")
        st.rerun()

st.divider()

# ── Edit an existing account ─────────────────────────────────────────────
st.subheader("✏️ แก้ไขบัญชี")

if not users:
    st.stop()

selected = st.selectbox(
    "เลือกบัญชี",
    users,
    format_func=lambda u: f"{u['username']} — {u['display_name']} ({u['role']})",
    key="_edit_user_pick",
)
is_self = selected["id"] == _me

edit_col, password_col = st.columns(2)

with edit_col:
    st.markdown("**บทบาทและสถานะ**")
    edit_display = st.text_input("ชื่อที่แสดง", value=selected["display_name"], key="_edit_display")
    edit_role = st.selectbox(
        "บทบาท",
        ROLES,
        index=ROLES.index(normalize_role(selected["role"])),
        format_func=lambda r: f"{r} ({ROLE_LABELS_TH[r]})",
        key="_edit_role",
    )
    edit_active = st.toggle(
        "เปิดใช้งานบัญชี", value=bool(selected["is_active"]), key="_edit_active"
    )
    if is_self:
        st.caption("นี่คือบัญชีของคุณเอง — ไม่สามารถลดบทบาทหรือปิดใช้งานตัวเองได้")

    if st.button("บันทึกการแก้ไข", use_container_width=True):
        if is_self and (normalize_role(edit_role) != "Admin" or not edit_active):
            st.error("ไม่สามารถลดสิทธิ์หรือปิดใช้งานบัญชีของตัวเองได้")
        elif would_remove_last_admin(selected["id"], new_role=edit_role, new_active=edit_active):
            st.error("ต้องมีบัญชี Admin ที่ใช้งานได้อย่างน้อย 1 บัญชีเสมอ")
        else:
            db.update_user(
                selected["id"],
                display_name=edit_display,
                role=normalize_role(edit_role),
                is_active=edit_active,
            )
            st.success("บันทึกเรียบร้อยแล้ว")
            st.rerun()

with password_col:
    st.markdown("**รีเซ็ตรหัสผ่าน**")
    with st.form("_reset_password_form"):
        reset_pw = st.text_input("รหัสผ่านใหม่", type="password")
        reset_confirm = st.text_input("ยืนยันรหัสผ่านใหม่", type="password")
        reset_submitted = st.form_submit_button("รีเซ็ตรหัสผ่าน", use_container_width=True)

    if reset_submitted:
        error = reset_password(selected["id"], reset_pw, reset_confirm)
        if error:
            st.error(error)
        else:
            st.success(f"รีเซ็ตรหัสผ่านของ `{selected['username']}` เรียบร้อยแล้ว")

st.markdown("**ลบบัญชี**")
if is_self:
    st.caption("ไม่สามารถลบบัญชีของตัวเองได้")
else:
    confirm_delete = st.checkbox(
        f"ยืนยันการลบบัญชี `{selected['username']}` อย่างถาวร", key="_confirm_delete_user"
    )
    if st.button("🗑 ลบบัญชี", disabled=not confirm_delete):
        if would_remove_last_admin(selected["id"], new_active=False):
            st.error("ต้องมีบัญชี Admin ที่ใช้งานได้อย่างน้อย 1 บัญชีเสมอ")
        else:
            db.delete_user(selected["id"])
            st.success(f"ลบบัญชี `{selected['username']}` แล้ว")
            st.rerun()
