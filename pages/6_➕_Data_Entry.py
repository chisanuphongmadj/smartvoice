"""Admin-only manual entry for customers and warranty registrations."""

import pandas as pd
import streamlit as st

st.set_page_config(page_title="SmartVoice — Data Entry", page_icon="➕", layout="wide")

from datetime import date

from smartvoice import customer_entry, db
from smartvoice.auth import PAGE_DATA_ENTRY
from smartvoice.ui_helpers import init_page

# Admin only (see smartvoice.auth.ROLE_PERMISSIONS).
current_user, current_role = init_page(PAGE_DATA_ENTRY)

st.title("➕ เพิ่มลูกค้า & ทะเบียนรับประกัน")
st.caption("บันทึกข้อมูลลูกค้าและทะเบียนรับประกันเข้าระบบด้วยมือ — ดูข้อมูลทั้งหมดได้ที่หน้า Customers")

_OTHER = "อื่นๆ"


def _pick_with_other(label: str, options, key: str):
    """Selectbox with an 'อื่นๆ' escape hatch that reveals a free-text input."""
    choice = st.selectbox(label, ("—", *options), key=key)
    if choice == _OTHER:
        return st.text_input(f"{label} (ระบุเอง)", key=f"{key}_other").strip() or None
    return None if choice == "—" else choice


tab_customer, tab_warranty = st.tabs(["👤 เพิ่มลูกค้า", "🛡 เพิ่มทะเบียนรับประกัน"])

# ─────────────────────────────────────────
# TAB 1 — NEW CUSTOMER
# ─────────────────────────────────────────
with tab_customer:
    st.subheader("ข้อมูลลูกค้าใหม่")

    with st.form("_add_customer_form"):
        c1, c2 = st.columns(2)
        with c1:
            first_name = st.text_input("ชื่อ *", placeholder="สมชาย")
            last_name = st.text_input("นามสกุล *", placeholder="ใจดี")
            phone = st.text_input("เบอร์โทร", placeholder="0812345678")
            email = st.text_input("อีเมล", placeholder="somchai@email.com")
            gender = st.selectbox("เพศ", ("—", *customer_entry.GENDERS))
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
        customer_submitted = st.form_submit_button("💾 บันทึกลูกค้า", use_container_width=True)

    if customer_submitted:
        new_id, error = customer_entry.create_customer(
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email,
            gender=None if gender == "—" else gender,
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
            st.success(
                f"บันทึกลูกค้า **{first_name.strip()} {last_name.strip()}** เรียบร้อยแล้ว (id={new_id})"
            )

    st.divider()
    st.subheader("ลูกค้าที่เพิ่มล่าสุด")
    recent_customers = sorted(
        db.get_all_customers(), key=lambda c: (c["created_at"], c["id"]), reverse=True
    )[:10]
    if not recent_customers:
        st.info("ยังไม่มีข้อมูลลูกค้าในระบบ")
    else:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "id": c["id"],
                        "ชื่อ": f"{c['first_name']} {c['last_name']}",
                        "เบอร์": c["phone"] or "—",
                        "อีเมล": c["email"] or "—",
                        "จังหวัด": c["city_province"] or "—",
                        "เพิ่มเมื่อ": c["created_at"][:19].replace("T", " "),
                    }
                    for c in recent_customers
                ]
            ),
            width="stretch",
            hide_index=True,
        )

# ─────────────────────────────────────────
# TAB 2 — NEW WARRANTY REGISTRATION
# ─────────────────────────────────────────
with tab_warranty:
    st.subheader("ทะเบียนรับประกันใหม่")

    customers = db.get_all_customers()
    if not customers:
        st.warning(
            "ต้องมีลูกค้าในระบบก่อน — เพิ่มลูกค้าที่แท็บ 👤 เพิ่มลูกค้า ก่อนบันทึกทะเบียนรับประกัน"
        )
    else:
        cust_map = {
            f"{c['first_name']} {c['last_name']} ({c['phone'] or '-'}) · id={c['id']}": c["id"]
            for c in sorted(customers, key=lambda c: (c["last_name"], c["first_name"]))
        }
        picked = st.selectbox("ลูกค้าเจ้าของทะเบียน *", list(cust_map.keys()), key="_w_customer")
        customer_id = cust_map.get(picked)

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
        if st.button("💾 บันทึกทะเบียนรับประกัน", use_container_width=True):
            new_id, error = customer_entry.create_warranty(
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
                st.success(
                    f"บันทึกทะเบียน **{registration_no.strip()}** เรียบร้อยแล้ว (id={new_id})"
                )

        st.divider()
        st.subheader("ทะเบียนที่เพิ่มล่าสุด")
        recent_warranties = sorted(
            db.get_all_warranties(), key=lambda w: (w["created_at"], w["id"]), reverse=True
        )[:10]
        if not recent_warranties:
            st.info("ยังไม่มีทะเบียนรับประกันในระบบ")
        else:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "เลขทะเบียน": w["registration_no"],
                            "ลูกค้า": f"{w.get('first_name') or '—'} {w.get('last_name') or ''}".strip(),
                            "แบรนด์": w["brand"] or "—",
                            "รุ่น": w["model"] or "—",
                            "ขนาด": w["size"] or "—",
                            "วันที่ซื้อ": w["date_of_purchase"] or "—",
                            "หมดประกัน": w["expiry_date"] or "—",
                            "เพิ่มเมื่อ": w["created_at"][:19].replace("T", " "),
                        }
                        for w in recent_warranties
                    ]
                ),
                width="stretch",
                hide_index=True,
            )
