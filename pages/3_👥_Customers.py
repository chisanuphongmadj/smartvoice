import pandas as pd
import streamlit as st

st.set_page_config(page_title="SmartVoice — Customers", page_icon="👥", layout="wide")

from smartvoice import db
from smartvoice.ui_helpers import init_page

init_page()

# ─────────────────────────────────────────
# PAGE: CUSTOMERS & WARRANTY
# ─────────────────────────────────────────
st.title("👥 Customers & Warranty")

tab1, tab2 = st.tabs(["👤 ลูกค้า", "🛡 ทะเบียนรับประกัน"])

with tab1:
    customers = db.get_all_customers()
    if not customers:
        st.info("ยังไม่มีข้อมูลลูกค้า — รัน `seed_mock_data.py` เพื่อสร้าง mock data")
    else:
        st.caption(f"ทั้งหมด {len(customers)} ราย")
        search = st.text_input("🔍 ค้นหาชื่อ / เบอร์", placeholder="สมชาย หรือ 0812345601")
        if search:
            q = search.lower()
            customers = [c for c in customers if q in (c["first_name"] + c["last_name"] + (c["phone"] or "")).lower()]

        cdf = pd.DataFrame(customers)
        display_cols = ["id", "first_name", "last_name", "phone", "email", "gender", "city_province", "created_at"]
        cdf["created_at"] = cdf["created_at"].str[:10]
        st.dataframe(
            cdf[[c for c in display_cols if c in cdf.columns]],
            width="stretch",
            hide_index=True,
        )

        st.divider()
        st.subheader("รายละเอียดลูกค้า")
        cust_map = {f"{c['first_name']} {c['last_name']} ({c['phone'] or '-'})": c for c in customers}
        sel_name = st.selectbox("เลือกลูกค้า", list(cust_map.keys()))
        if sel_name:
            c = cust_map[sel_name]
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown(f"**ชื่อ:** {c['first_name']} {c['last_name']}")
                st.markdown(f"**เพศ:** {c['gender'] or '-'}")
                st.markdown(f"**วันเกิด:** {c['date_of_birth'] or '-'}")
                st.markdown(f"**เบอร์:** `{c['phone'] or '-'}`")
                st.markdown(f"**อีเมล:** {c['email'] or '-'}")
            with col_b:
                st.markdown(f"**ที่อยู่:** {c['address'] or '-'}")
                st.markdown(f"**แขวง/ตำบล:** {c['subdistrict'] or '-'}")
                st.markdown(f"**เขต/อำเภอ:** {c['district'] or '-'}")
                st.markdown(f"**จังหวัด:** {c['city_province'] or '-'}")
                st.markdown(f"**รหัสไปรษณีย์:** {c['postcode'] or '-'}")

            warrs = db.get_warranties_by_customer(c["id"])
            if warrs:
                st.markdown(f"**ทะเบียนรับประกัน ({len(warrs)} รายการ):**")
                wdf = pd.DataFrame(warrs)
                wcols = ["registration_no", "brand", "model", "size", "purchase_channel", "date_of_purchase", "warranty_period_months"]
                st.dataframe(wdf[[col for col in wcols if col in wdf.columns]], width="stretch", hide_index=True)

with tab2:
    warranties = db.get_all_warranties()
    if not warranties:
        st.info("ยังไม่มีข้อมูลทะเบียนรับประกัน")
    else:
        st.caption(f"ทั้งหมด {len(warranties)} รายการ")

        wdf_all = pd.DataFrame(warranties)
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("ทั้งหมด", len(warranties))
        with m2:
            brands = wdf_all["brand"].value_counts()
            st.metric("แบรนด์หลัก", brands.index[0] if len(brands) else "-")
        with m3:
            channels = wdf_all["purchase_channel"].value_counts()
            st.metric("ช่องทางหลัก", channels.index[0] if len(channels) else "-")
        with m4:
            categories = wdf_all["category"].value_counts()
            st.metric("หมวดหมู่หลัก", categories.index[0] if len(categories) else "-")

        st.divider()
        wcols2 = ["registration_no", "first_name", "last_name", "phone", "brand", "model", "size", "category", "purchase_channel", "date_of_purchase", "warranty_period_months"]
        st.dataframe(
            wdf_all[[c for c in wcols2 if c in wdf_all.columns]],
            width="stretch",
            hide_index=True,
        )
