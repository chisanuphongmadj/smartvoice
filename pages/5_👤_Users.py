"""Admin-only staff account management."""

import pandas as pd
import streamlit as st

st.set_page_config(page_title="SmartVoice — Users", layout="wide")

from smartvoice import audit as audit_trail
from smartvoice import db
from smartvoice.auth import (
    PAGE_LABELS_TH,
    PAGE_USERS,
    ROLE_LABELS_TH,
    ROLES,
    create_user,
    normalize_role,
    role_label,
    visible_pages,
    would_remove_last_admin,
)
from smartvoice.ui_helpers import audit, get_current_user_id, init_page

# Admin only (see smartvoice.auth.ROLE_PERMISSIONS).
current_user, current_role = init_page(PAGE_USERS)

st.title("จัดการผู้ใช้")
st.caption(
    "เพิ่มบัญชี / แก้ไขบทบาท / เปิด-ปิดใช้งาน / ลบบัญชี — "
    "รหัสผ่านเป็นของเจ้าของบัญชีเท่านั้น ผู้ดูแลระบบตั้งหรือรีเซ็ตให้ไม่ได้"
)

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
                    "สถานะ": "ใช้งาน" if u["is_active"] else "ปิดใช้งาน",
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
st.subheader("เพิ่มผู้ใช้ใหม่")

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
    new_user_id, error = create_user(
        username=new_username,
        password=new_password,
        role=new_role,
        display_name=new_display,
        confirm=new_confirm,
    )
    if error:
        st.error(error)
    else:
        audit(
            audit_trail.CREATE,
            audit_trail.ENTITY_USER,
            entity_id=new_user_id,
            entity_label=new_username.strip(),
            changes={
                "role": normalize_role(new_role),
                "display_name": (new_display or "").strip() or new_username.strip(),
            },
        )
        st.success(f"สร้างบัญชี `{new_username.strip()}` เรียบร้อยแล้ว")
        st.rerun()

st.divider()

# ── Edit an existing account ─────────────────────────────────────────────
st.subheader("แก้ไขบัญชี")

if not users:
    st.stop()

selected = st.selectbox(
    "เลือกบัญชี",
    users,
    format_func=lambda u: f"{u['username']} — {u['display_name']} ({u['role']})",
    key="_edit_user_pick",
)
is_self = selected["id"] == _me

edit_col, note_col = st.columns(2)

with edit_col:
    st.markdown("**บทบาทและสถานะ**")
    # Widget keys carry the account id: with a fixed key Streamlit keeps the
    # value from the previously selected account and ignores `value=`, so
    # switching accounts would save the wrong display name / role.
    edit_display = st.text_input(
        "ชื่อที่แสดง", value=selected["display_name"], key=f"_edit_display_{selected['id']}"
    )
    edit_role = st.selectbox(
        "บทบาท",
        ROLES,
        index=ROLES.index(normalize_role(selected["role"])),
        format_func=lambda r: f"{r} ({ROLE_LABELS_TH[r]})",
        key=f"_edit_role_{selected['id']}",
    )
    edit_active = st.toggle(
        "เปิดใช้งานบัญชี",
        value=bool(selected["is_active"]),
        key=f"_edit_active_{selected['id']}",
    )
    if is_self:
        st.caption("นี่คือบัญชีของคุณเอง — ไม่สามารถลดบทบาทหรือปิดใช้งานตัวเองได้")

    if st.button("บันทึกการแก้ไข", use_container_width=True):
        if is_self and (normalize_role(edit_role) != "Admin" or not edit_active):
            st.error("ไม่สามารถลดสิทธิ์หรือปิดใช้งานบัญชีของตัวเองได้")
        elif would_remove_last_admin(selected["id"], new_role=edit_role, new_active=edit_active):
            st.error("ต้องมีบัญชี Admin ที่ใช้งานได้อย่างน้อย 1 บัญชีเสมอ")
        else:
            changes = audit_trail.diff_fields(
                {
                    "display_name": selected["display_name"],
                    "role": normalize_role(selected["role"]),
                    "is_active": bool(selected["is_active"]),
                },
                {
                    "display_name": edit_display.strip(),
                    "role": normalize_role(edit_role),
                    "is_active": bool(edit_active),
                },
            )
            db.update_user(
                selected["id"],
                display_name=edit_display,
                role=normalize_role(edit_role),
                is_active=edit_active,
            )
            if changes:
                audit(
                    audit_trail.UPDATE,
                    audit_trail.ENTITY_USER,
                    entity_id=selected["id"],
                    entity_label=selected["username"],
                    changes=changes,
                )
            st.success("บันทึกเรียบร้อยแล้ว")
            st.rerun()

with note_col:
    # Admins deliberately cannot read, set or reset anyone else's password —
    # only the account owner can change it. The lever an Admin has is the
    # enable/disable toggle on the left.
    st.markdown("**รหัสผ่าน**")
    st.info(
        "ผู้ดูแลระบบ **ไม่มีสิทธิ์** ตั้งหรือรีเซ็ตรหัสผ่านของพนักงาน — "
        "เจ้าของบัญชีเท่านั้นที่เปลี่ยนรหัสผ่านตัวเองได้ ที่กล่องบัญชีใน sidebar "
        "(ต้องกรอกรหัสผ่านเดิมก่อนเสมอ)"
    )
    st.caption(
        "พนักงานลืมรหัสผ่าน: ปิดใช้งานบัญชีเดิมเพื่อกันการเข้าถึง แล้วสร้างบัญชีใหม่ให้ "
        "โดยให้เจ้าตัวตั้งรหัสผ่านเองทันทีที่เข้าใช้งานครั้งแรก"
    )

st.markdown("**เลิกใช้งานบัญชี**")
st.caption(
    "ระบบไม่มีปุ่มลบบัญชีถาวร — บัญชีที่ถูกลบจะทำให้รายการในหน้า “ประวัติการใช้งาน” "
    "ชี้ไปยังผู้ใช้ที่ไม่มีอยู่แล้ว ใช้การปิดใช้งานด้านบนแทน: "
    "บัญชีที่ปิดอยู่จะเข้าสู่ระบบไม่ได้ทันที และเปิดกลับมาได้ภายหลัง"
)
