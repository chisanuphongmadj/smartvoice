"""Admin-only manual data management for customers and warranty registrations."""

import pandas as pd
import streamlit as st

st.set_page_config(page_title="SmartVoice — เพิ่ม/แก้ไขข้อมูลลูกค้า", layout="wide")

from datetime import date

from smartvoice import customer_entry, db, labels
from smartvoice.auth import PAGE_DATA_ENTRY
from smartvoice.ui_helpers import init_page

# Admin only (see smartvoice.auth.ROLE_PERMISSIONS).
current_user, current_role = init_page(PAGE_DATA_ENTRY)

st.title("ข้อมูลลูกค้า & ทะเบียนรับประกัน")
st.caption("เพิ่ม / แก้ไข / ลบ ข้อมูลลูกค้าและทะเบียนรับประกัน — ค้นหาและดูภาพรวมได้ที่เมนู ลูกค้าและการรับประกัน")

_OTHER = "อื่นๆ"
_NONE = "—"
_FLASH_KEY = "_data_entry_flash"

# Saving reruns the page so the pickers and tables pick up the change, which
# would otherwise wipe the success message before anyone reads it.
_flash = st.session_state.pop(_FLASH_KEY, None)
if _flash:
    st.success(_flash)


def _flash_and_rerun(message: str):
    st.session_state[_FLASH_KEY] = message
    st.rerun()


def _as_date(value) -> date | None:
    """Parse an ISO date string from the DB into a date for st.date_input."""
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _pick_with_other(label: str, options, key: str, current: str | None = None):
    """Selectbox with an 'อื่นๆ' escape hatch that reveals a free-text input."""
    choices = (_NONE, *options)
    if current in options:
        index = choices.index(current)
    elif current:
        index = choices.index(_OTHER) if _OTHER in choices else 0
    else:
        index = 0

    choice = st.selectbox(label, choices, index=index, key=key)
    if choice == _OTHER:
        typed = st.text_input(
            f"{label} (ระบุเอง)",
            value="" if current in options else (current or ""),
            key=f"{key}_other",
        )
        return typed.strip() or None
    return None if choice == _NONE else choice


def _customer_label(c: dict) -> str:
    return f"{c['first_name']} {c['last_name']} ({c['phone'] or '-'}) · id={c['id']}"


def _recent_table(rows: list[dict], columns: dict, empty_message: str):
    if not rows:
        st.info(empty_message)
        return
    st.dataframe(
        pd.DataFrame([{label: fn(r) for label, fn in columns.items()} for r in rows]),
        width="stretch",
        hide_index=True,
    )


tab_customer, tab_warranty, tab_hidden = st.tabs(
    ["ลูกค้า", "ทะเบียนรับประกัน", "รายการที่ซ่อนไว้"]
)

# ─────────────────────────────────────────
# TAB 1 — CUSTOMERS
# ─────────────────────────────────────────
with tab_customer:
    customers = db.get_all_customers()

    with st.expander("เพิ่มลูกค้าใหม่", expanded=not customers):
        with st.form("_add_customer_form"):
            c1, c2 = st.columns(2)
            with c1:
                first_name = st.text_input("ชื่อ *", placeholder="สมชาย")
                last_name = st.text_input("นามสกุล *", placeholder="ใจดี")
                phone = st.text_input("เบอร์โทร", placeholder="0812345678")
                email = st.text_input("อีเมล", placeholder="somchai@email.com")
                gender = st.selectbox("เพศ", (_NONE, *customer_entry.GENDERS))
                dob = st.date_input(
                    "วันเกิด",
                    value=None,
                    min_value=date(1920, 1, 1),
                    max_value=date.today(),
                    format="YYYY-MM-DD",
                )
            with c2:
                address = st.text_area("ที่อยู่", placeholder="123/45 หมู่บ้าน ...", height=100)
                a1, a2 = st.columns(2)
                with a1:
                    subdistrict = st.text_input("แขวง/ตำบล")
                    city_province = st.text_input("จังหวัด")
                with a2:
                    district = st.text_input("เขต/อำเภอ")
                    postcode = st.text_input("รหัสไปรษณีย์")
                country = st.text_input("ประเทศ", value="Thailand")

            st.caption("* จำเป็นต้องกรอก — เบอร์โทรต้องไม่ซ้ำกับลูกค้ารายอื่น (ใช้เชื่อมสายเข้าอัตโนมัติ)")
            customer_submitted = st.form_submit_button("บันทึกลูกค้า", use_container_width=True)

        if customer_submitted:
            new_id, error = customer_entry.create_customer(
                actor=current_user,
                actor_role=current_role,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                email=email,
                gender=None if gender == _NONE else gender,
                date_of_birth=dob,
                address=address,
                subdistrict=subdistrict,
                district=district,
                city_province=city_province,
                country=country,
                postcode=postcode,
            )
            if error:
                st.error(error)
            else:
                _flash_and_rerun(
                    f"บันทึกลูกค้า **{first_name.strip()} {last_name.strip()}** เรียบร้อยแล้ว (id={new_id})"
                )

    st.divider()
    st.subheader("แก้ไข / ลบ ลูกค้า")

    if not customers:
        st.info("ยังไม่มีข้อมูลลูกค้าในระบบ")
    else:
        search = st.text_input(
            "ค้นหาลูกค้าที่ต้องการแก้ไข", placeholder="ชื่อ หรือ เบอร์โทร", key="_edit_c_search"
        )
        matches = customers
        if search:
            q = search.lower()
            matches = [
                c for c in customers
                if q in f"{c['first_name']}{c['last_name']}{c['phone'] or ''}".lower()
            ]

        if not matches:
            st.warning("ไม่พบลูกค้าที่ตรงกับคำค้นหา")
        else:
            picked = st.selectbox(
                "เลือกลูกค้า", matches, format_func=_customer_label, key="_edit_c_pick"
            )
            cid = picked["id"]
            deps = db.count_customer_dependencies(cid)
            dep_text = customer_entry.describe_dependencies(deps)
            st.caption(f"ข้อมูลที่ผูกอยู่: {dep_text or 'ไม่มี'}")

            with st.form(f"_edit_customer_form_{cid}"):
                e1, e2 = st.columns(2)
                with e1:
                    ed_first = st.text_input("ชื่อ *", value=picked["first_name"])
                    ed_last = st.text_input("นามสกุล *", value=picked["last_name"])
                    ed_phone = st.text_input("เบอร์โทร", value=picked["phone"] or "")
                    ed_email = st.text_input("อีเมล", value=picked["email"] or "")
                    genders = (_NONE, *customer_entry.GENDERS)
                    ed_gender = st.selectbox(
                        "เพศ",
                        genders,
                        index=genders.index(picked["gender"]) if picked["gender"] in genders else 0,
                    )
                    ed_dob = st.date_input(
                        "วันเกิด",
                        value=_as_date(picked["date_of_birth"]),
                        min_value=date(1920, 1, 1),
                        max_value=date.today(),
                        format="YYYY-MM-DD",
                    )
                with e2:
                    ed_address = st.text_area("ที่อยู่", value=picked["address"] or "", height=100)
                    b1, b2 = st.columns(2)
                    with b1:
                        ed_subdistrict = st.text_input("แขวง/ตำบล", value=picked["subdistrict"] or "")
                        ed_city = st.text_input("จังหวัด", value=picked["city_province"] or "")
                    with b2:
                        ed_district = st.text_input("เขต/อำเภอ", value=picked["district"] or "")
                        ed_postcode = st.text_input("รหัสไปรษณีย์", value=picked["postcode"] or "")
                    ed_country = st.text_input("ประเทศ", value=picked["country"] or "Thailand")

                edit_submitted = st.form_submit_button("บันทึกการแก้ไข", use_container_width=True)

            if edit_submitted:
                error = customer_entry.update_customer(
                    cid,
                    actor=current_user,
                    actor_role=current_role,
                    first_name=ed_first,
                    last_name=ed_last,
                    phone=ed_phone,
                    email=ed_email,
                    gender=None if ed_gender == _NONE else ed_gender,
                    date_of_birth=ed_dob,
                    address=ed_address,
                    subdistrict=ed_subdistrict,
                    district=ed_district,
                    city_province=ed_city,
                    country=ed_country,
                    postcode=ed_postcode,
                )
                if error:
                    st.error(error)
                else:
                    _flash_and_rerun(
                        f"บันทึกการแก้ไข **{ed_first.strip()} {ed_last.strip()}** เรียบร้อยแล้ว"
                    )

            st.markdown("**ลบลูกค้า (ซ่อนไว้ — กู้คืนได้)**")
            st.caption(
                "ข้อมูลจะไม่ถูกลบออกจากฐานข้อมูล แต่จะถูกซ่อนพร้อมทะเบียนรับประกันของลูกค้ารายนี้ "
                "และบันทึกลงประวัติว่าใครซ่อนเมื่อไหร่ — กู้คืนได้ที่แท็บ “รายการที่ซ่อนไว้” "
                "ส่วนสาย เคส และการเชื่อมสายยังอยู่ครบ"
            )
            confirm_hide = st.checkbox(
                f"ยืนยันซ่อน `{picked['first_name']} {picked['last_name']}`",
                key=f"_confirm_delete_customer_{cid}",
            )
            if st.button("ลบลูกค้ารายนี้", key=f"_delete_customer_{cid}", disabled=not confirm_hide):
                result, error = customer_entry.hide_customer(
                    cid, actor=current_user, actor_role=current_role
                )
                if error:
                    st.error(error)
                else:
                    hidden_w = result.get("warranties") or 0
                    _flash_and_rerun(
                        f"ซ่อนลูกค้าเรียบร้อยแล้ว"
                        + (f" (พร้อมทะเบียนรับประกัน {hidden_w} รายการ)" if hidden_w else "")
                    )

    st.divider()
    st.subheader("ลูกค้าที่เพิ่มล่าสุด")
    _recent_table(
        sorted(customers, key=lambda c: (c["created_at"], c["id"]), reverse=True)[:10],
        {
            "id": lambda c: c["id"],
            "ชื่อ": lambda c: f"{c['first_name']} {c['last_name']}",
            "เบอร์": lambda c: c["phone"] or "—",
            "อีเมล": lambda c: c["email"] or "—",
            "จังหวัด": lambda c: c["city_province"] or "—",
            "เพิ่มเมื่อ": lambda c: labels.thai_time(c["created_at"]),
        },
        "ยังไม่มีข้อมูลลูกค้าในระบบ",
    )

# ─────────────────────────────────────────
# TAB 2 — WARRANTY REGISTRATIONS
# ─────────────────────────────────────────
with tab_warranty:
    customers = db.get_all_customers()
    warranties = db.get_all_warranties()

    if not customers:
        st.warning("ต้องมีลูกค้าในระบบก่อน — เพิ่มลูกค้าที่แท็บ “ลูกค้า” ก่อนบันทึกทะเบียนรับประกัน")
    else:
        cust_map = {
            _customer_label(c): c["id"]
            for c in sorted(customers, key=lambda c: (c["last_name"], c["first_name"]))
        }

        with st.expander("เพิ่มทะเบียนรับประกันใหม่", expanded=not warranties):
            picked_customer = st.selectbox(
                "ลูกค้าเจ้าของทะเบียน *", list(cust_map.keys()), key="_w_customer"
            )
            customer_id = cust_map.get(picked_customer)

            w1, w2, w3 = st.columns(3)
            with w1:
                registration_no = st.text_input("เลขทะเบียนรับประกัน *", placeholder="W011OZ25011")
                certificate_no = st.text_input("เลขที่ใบรับประกัน", placeholder="CERT-OZ-011")
                serial_no = st.text_input("Serial No.", placeholder="SN-OZ-011")
                label_no = st.text_input("Label No.", placeholder="LB-OZ-011")
                channel = _pick_with_other("ช่องทาง (แบรนด์ร้าน)", customer_entry.CHANNELS, "_w_channel")
            with w2:
                brand = _pick_with_other("แบรนด์", customer_entry.BRANDS, "_w_brand")
                category = _pick_with_other("หมวดหมู่", customer_entry.CATEGORIES, "_w_category")
                model = st.text_input("รุ่น", placeholder="Natura Latex")
                size = st.text_input("ขนาด", placeholder="5ft")
                sku = st.text_input("SKU", placeholder="OZ-NL-5FT-011")
            with w3:
                purchase_channel = _pick_with_other(
                    "ช่องทางซื้อ", customer_entry.PURCHASE_CHANNELS, "_w_purchase_channel"
                )
                order_number = st.text_input("เลขที่คำสั่งซื้อ", placeholder="SP2506011")
                warranty_period_months = st.number_input(
                    "ระยะเวลารับประกัน (เดือน)", min_value=0, max_value=600, value=120, step=12
                )
                date_of_purchase = st.date_input("วันที่ซื้อ", value=date.today(), format="YYYY-MM-DD")
                date_of_delivery = st.date_input("วันที่ส่งมอบ", value=None, format="YYYY-MM-DD")

            auto_expiry = customer_entry.compute_expiry_date(date_of_purchase, warranty_period_months)
            use_auto = st.checkbox(
                f"คำนวณวันหมดประกันอัตโนมัติ ({auto_expiry or '—'})", value=True, key="_w_auto_expiry"
            )
            expiry_date = None
            if not use_auto:
                expiry_date = st.date_input("วันหมดประกัน", value=None, format="YYYY-MM-DD")

            remark = st.text_area("หมายเหตุ", height=80)

            st.caption("* จำเป็นต้องกรอก — เลขทะเบียนต้องไม่ซ้ำกับรายการเดิม")
            if st.button("บันทึกทะเบียนรับประกัน", use_container_width=True):
                new_id, error = customer_entry.create_warranty(
                    actor=current_user,
                    actor_role=current_role,
                    registration_no=registration_no,
                    customer_id=customer_id,
                    channel=channel,
                    certificate_no=certificate_no,
                    category=category,
                    brand=brand,
                    model=model,
                    size=size,
                    sku=sku,
                    serial_no=serial_no,
                    label_no=label_no,
                    warranty_period_months=warranty_period_months,
                    date_of_purchase=date_of_purchase,
                    date_of_delivery=date_of_delivery,
                    purchase_channel=purchase_channel,
                    order_number=order_number,
                    expiry_date=None if use_auto else expiry_date,
                    remark=remark,
                )
                if error:
                    st.error(error)
                else:
                    _flash_and_rerun(
                        f"บันทึกทะเบียน **{registration_no.strip()}** เรียบร้อยแล้ว (id={new_id})"
                    )

        st.divider()
        st.subheader("แก้ไข / ลบ ทะเบียนรับประกัน")

        if not warranties:
            st.info("ยังไม่มีทะเบียนรับประกันในระบบ")
        else:
            w_search = st.text_input(
                "ค้นหาทะเบียนที่ต้องการแก้ไข",
                placeholder="เลขทะเบียน, Serial, แบรนด์, รุ่น หรือชื่อลูกค้า",
                key="_edit_w_search",
            )
            w_matches = warranties
            if w_search:
                q = w_search.lower()
                w_matches = [
                    w for w in warranties
                    if q in " ".join(
                        str(w.get(col) or "")
                        for col in ("registration_no", "serial_no", "brand", "model",
                                    "first_name", "last_name", "phone")
                    ).lower()
                ]

            if not w_matches:
                st.warning("ไม่พบทะเบียนที่ตรงกับคำค้นหา")
            else:
                picked_w = st.selectbox(
                    "เลือกทะเบียน",
                    w_matches,
                    format_func=lambda w: (
                        f"{w['registration_no']} — {w['brand'] or '-'} {w['model'] or ''} "
                        f"({w.get('first_name') or '-'} {w.get('last_name') or ''})"
                    ),
                    key="_edit_w_pick",
                )
                wid = picked_w["id"]
                owner_label = next(
                    (label for label, cust_id in cust_map.items() if cust_id == picked_w["customer_id"]),
                    None,
                )

                x1, x2, x3 = st.columns(3)
                with x1:
                    ed_reg = st.text_input(
                        "เลขทะเบียนรับประกัน *", value=picked_w["registration_no"], key=f"_ew_reg_{wid}"
                    )
                    ed_cert = st.text_input(
                        "เลขที่ใบรับประกัน", value=picked_w["certificate_no"] or "", key=f"_ew_cert_{wid}"
                    )
                    ed_serial = st.text_input(
                        "Serial No.", value=picked_w["serial_no"] or "", key=f"_ew_serial_{wid}"
                    )
                    ed_label = st.text_input(
                        "Label No.", value=picked_w["label_no"] or "", key=f"_ew_label_{wid}"
                    )
                    ed_channel = _pick_with_other(
                        "ช่องทาง (แบรนด์ร้าน)", customer_entry.CHANNELS,
                        f"_ew_channel_{wid}", picked_w["channel"],
                    )
                with x2:
                    ed_brand = _pick_with_other(
                        "แบรนด์", customer_entry.BRANDS, f"_ew_brand_{wid}", picked_w["brand"]
                    )
                    ed_category = _pick_with_other(
                        "หมวดหมู่", customer_entry.CATEGORIES, f"_ew_category_{wid}", picked_w["category"]
                    )
                    ed_model = st.text_input("รุ่น", value=picked_w["model"] or "", key=f"_ew_model_{wid}")
                    ed_size = st.text_input("ขนาด", value=picked_w["size"] or "", key=f"_ew_size_{wid}")
                    ed_sku = st.text_input("SKU", value=picked_w["sku"] or "", key=f"_ew_sku_{wid}")
                with x3:
                    ed_owner = st.selectbox(
                        "ลูกค้าเจ้าของทะเบียน *",
                        list(cust_map.keys()),
                        index=list(cust_map.keys()).index(owner_label) if owner_label else 0,
                        key=f"_ew_owner_{wid}",
                    )
                    ed_purchase_channel = _pick_with_other(
                        "ช่องทางซื้อ", customer_entry.PURCHASE_CHANNELS,
                        f"_ew_purchase_{wid}", picked_w["purchase_channel"],
                    )
                    ed_order = st.text_input(
                        "เลขที่คำสั่งซื้อ", value=picked_w["order_number"] or "", key=f"_ew_order_{wid}"
                    )
                    ed_months = st.number_input(
                        "ระยะเวลารับประกัน (เดือน)",
                        min_value=0, max_value=600, step=12,
                        value=int(picked_w["warranty_period_months"] or 0),
                        key=f"_ew_months_{wid}",
                    )
                    ed_purchase_date = st.date_input(
                        "วันที่ซื้อ", value=_as_date(picked_w["date_of_purchase"]),
                        format="YYYY-MM-DD", key=f"_ew_pdate_{wid}",
                    )
                    ed_delivery_date = st.date_input(
                        "วันที่ส่งมอบ", value=_as_date(picked_w["date_of_delivery"]),
                        format="YYYY-MM-DD", key=f"_ew_ddate_{wid}",
                    )

                ed_auto_expiry = customer_entry.compute_expiry_date(ed_purchase_date, ed_months)
                ed_use_auto = st.checkbox(
                    f"คำนวณวันหมดประกันใหม่อัตโนมัติ ({ed_auto_expiry or '—'})",
                    value=False,
                    key=f"_ew_auto_{wid}",
                )
                ed_expiry = None
                if not ed_use_auto:
                    ed_expiry = st.date_input(
                        "วันหมดประกัน", value=_as_date(picked_w["expiry_date"]),
                        format="YYYY-MM-DD", key=f"_ew_expiry_{wid}",
                    )
                ed_remark = st.text_area(
                    "หมายเหตุ", value=picked_w["remark"] or "", height=80, key=f"_ew_remark_{wid}"
                )

                if st.button("บันทึกการแก้ไข", key=f"_save_w_{wid}", use_container_width=True):
                    error = customer_entry.update_warranty(
                        wid,
                        actor=current_user,
                        actor_role=current_role,
                        registration_no=ed_reg,
                        customer_id=cust_map[ed_owner],
                        channel=ed_channel,
                        certificate_no=ed_cert,
                        category=ed_category,
                        brand=ed_brand,
                        model=ed_model,
                        size=ed_size,
                        sku=ed_sku,
                        serial_no=ed_serial,
                        label_no=ed_label,
                        warranty_period_months=ed_months,
                        date_of_purchase=ed_purchase_date,
                        date_of_delivery=ed_delivery_date,
                        purchase_channel=ed_purchase_channel,
                        order_number=ed_order,
                        expiry_date=None if ed_use_auto else ed_expiry,
                        remark=ed_remark,
                    )
                    if error:
                        st.error(error)
                    else:
                        _flash_and_rerun(f"บันทึกการแก้ไขทะเบียน **{ed_reg.strip()}** เรียบร้อยแล้ว")

                st.markdown("**ลบทะเบียนรับประกัน (ซ่อนไว้ — กู้คืนได้)**")
                st.caption(
                    "แถวนี้จะยังอยู่ในฐานข้อมูล แต่ถูกซ่อนจากทุกหน้า และบันทึกลงประวัติว่าใครซ่อน"
                )
                confirm_w = st.checkbox(
                    f"ยืนยันซ่อนทะเบียน `{picked_w['registration_no']}`",
                    key=f"_confirm_delete_w_{wid}",
                )
                if st.button("ลบทะเบียนนี้", key=f"_delete_w_{wid}", disabled=not confirm_w):
                    error = customer_entry.hide_warranty(
                        wid, actor=current_user, actor_role=current_role
                    )
                    if error:
                        st.error(error)
                    else:
                        _flash_and_rerun(f"ซ่อนทะเบียน `{picked_w['registration_no']}` แล้ว")

        st.divider()
        st.subheader("ทะเบียนที่เพิ่มล่าสุด")
        _recent_table(
            sorted(warranties, key=lambda w: (w["created_at"], w["id"]), reverse=True)[:10],
            {
                "เลขทะเบียน": lambda w: w["registration_no"],
                "ลูกค้า": lambda w: f"{w.get('first_name') or '—'} {w.get('last_name') or ''}".strip(),
                "แบรนด์": lambda w: w["brand"] or "—",
                "รุ่น": lambda w: w["model"] or "—",
                "ขนาด": lambda w: w["size"] or "—",
                "วันที่ซื้อ": lambda w: w["date_of_purchase"] or "—",
                "หมดประกัน": lambda w: w["expiry_date"] or "—",
                "เพิ่มเมื่อ": lambda w: labels.thai_time(w["created_at"]),
            },
            "ยังไม่มีทะเบียนรับประกันในระบบ",
        )

# ─────────────────────────────────────────
# TAB 3 — HIDDEN ROWS (restore)
# ─────────────────────────────────────────
with tab_hidden:
    st.caption(
        "รายการที่ถูก \"ลบ\" จะไม่หายไปจากฐานข้อมูล — ถูกซ่อนไว้ที่นี่และกู้คืนได้ทุกเมื่อ"
    )

    hidden_customers = db.get_deleted_customers()
    hidden_warranties = db.get_deleted_warranties()

    st.subheader(f"ลูกค้าที่ซ่อนไว้ ({len(hidden_customers)})")
    if not hidden_customers:
        st.info("ไม่มีลูกค้าที่ถูกซ่อนไว้")
    for row in hidden_customers:
        cols = st.columns([4, 2, 2, 1.4])
        cols[0].markdown(
            f"**{row['first_name']} {row['last_name']}** · `{row['phone'] or '-'}` · id={row['id']}"
        )
        cols[1].caption(f"ซ่อนโดย: {row['deleted_by'] or '—'}")
        cols[2].caption(f"เมื่อ: {labels.thai_time(row['deleted_at'])}")
        if cols[3].button("กู้คืน", key=f"_restore_c_{row['id']}", use_container_width=True):
            result, error = customer_entry.restore_customer(
                row["id"], actor=current_user, actor_role=current_role
            )
            if error:
                st.error(error)
            else:
                back = result.get("warranties") or 0
                _flash_and_rerun(
                    f"กู้คืน **{row['first_name']} {row['last_name']}** แล้ว"
                    + (f" (พร้อมทะเบียนรับประกัน {back} รายการ)" if back else "")
                )

    st.divider()
    st.subheader(f"ทะเบียนรับประกันที่ซ่อนไว้ ({len(hidden_warranties)})")
    if not hidden_warranties:
        st.info("ไม่มีทะเบียนรับประกันที่ถูกซ่อนไว้")
    for row in hidden_warranties:
        cols = st.columns([4, 2, 2, 1.4])
        owner = f"{row.get('first_name') or '—'} {row.get('last_name') or ''}".strip()
        cols[0].markdown(
            f"**{row['registration_no']}** · {row['brand'] or '-'} {row['model'] or ''} · {owner}"
        )
        cols[1].caption(f"ซ่อนโดย: {row['deleted_by'] or '—'}")
        cols[2].caption(f"เมื่อ: {labels.thai_time(row['deleted_at'])}")
        if cols[3].button("กู้คืน", key=f"_restore_w_{row['id']}", use_container_width=True):
            error = customer_entry.restore_warranty(
                row["id"], actor=current_user, actor_role=current_role
            )
            if error:
                st.error(error)
            else:
                _flash_and_rerun(f"กู้คืนทะเบียน `{row['registration_no']}` แล้ว")

