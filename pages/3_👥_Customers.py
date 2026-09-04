import pandas as pd
import streamlit as st

st.set_page_config(page_title="SmartVoice — Customers", layout="wide")

from smartvoice import db
from smartvoice.auth import PAGE_CUSTOMERS
from smartvoice.ui_helpers import init_page

init_page(PAGE_CUSTOMERS)

# ─────────────────────────────────────────
# PAGE: CUSTOMERS & WARRANTY
# ─────────────────────────────────────────
st.title("Customers & Warranty")

tab1, tab2 = st.tabs(["ลูกค้า", "ทะเบียนรับประกัน"])

with tab1:
    customers = db.get_all_customers()
    if not customers:
        st.info(
            "ยังไม่มีข้อมูลลูกค้า — รันคำสั่งนี้เพื่อสร้าง mock data:\n\n"
            "```bash\npython scripts/seed_mock_data.py\n```"
        )
    else:
        st.caption(f"ทั้งหมด {len(customers)} ราย")
        search = st.text_input("ค้นหาชื่อ / เบอร์", placeholder="สมชาย หรือ 0812345601")
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
                wcols = ["registration_no", "serial_no", "brand", "model", "size", "purchase_channel", "date_of_purchase", "warranty_period_months"]
                st.dataframe(wdf[[col for col in wcols if col in wdf.columns]], width="stretch", hide_index=True)

            # ── Cases of this customer ──
            cases = db.get_cases_by_customer(c["id"])
            if cases:
                _case_badge = {"open": "เปิด", "follow_up": "ติดตาม", "closed": "ปิด"}
                st.markdown(f"**เคส ({len(cases)} เคส):**")
                for cs in cases:
                    case_calls = db.get_calls_by_case(cs["id"])
                    badge = _case_badge.get(cs["status"], cs["status"])
                    with st.expander(f"เคส #{cs['id']}: {cs['subject']}  —  {badge}  ({len(case_calls)} สาย)"):
                        created = cs.get("created_at", "")[:10]
                        updated = cs.get("updated_at", "")[:10]
                        st.caption(f"สร้าง: {created}  •  อัปเดทล่าสุด: {updated}")
                        if case_calls:
                            for oc in case_calls:
                                st.markdown(
                                    f"- `{oc['filename']}`  "
                                    f"({oc['status']}) — {(oc.get('summary') or '—')[:100]}"
                                )

            # ── Calls linked to this customer (even without a case) ──
            all_calls = db.get_calls_by_customer(c["id"])
            if all_calls:
                linked_no_case = [cl for cl in all_calls if not cl.get("case_id")]
                if linked_no_case:
                    st.markdown(f"**สายที่เชื่อมไว้แต่ยังไม่มีเคส ({len(linked_no_case)}):**")
                    for cl in linked_no_case:
                        _badge = "จับคู่อัตโนมัติ" if cl.get("matched_by") == "auto_phone" else "จับคู่เอง"
                        st.caption(f"- `{cl['filename']}` ({cl['status']}) {_badge}")

with tab2:
    warranties = db.get_all_warranties()
    if not warranties:
        st.info("ยังไม่มีข้อมูลทะเบียนรับประกัน")
    else:
        wdf_all = pd.DataFrame(warranties)

        # ── Search bar ──
        w_search = st.text_input(
            "ค้นหาทะเบียนรับประกัน",
            placeholder="ชื่อลูกค้า, เบอร์, เลขทะเบียน, Serial, แบรนด์, รุ่น ...",
            key="warranty_search",
        )

        # ── Filters ──
        f1, f2, f3 = st.columns(3)
        brand_options = sorted(wdf_all["brand"].dropna().unique().tolist())
        channel_options = sorted(wdf_all["purchase_channel"].dropna().unique().tolist())
        category_options = sorted(wdf_all["category"].dropna().unique().tolist())
        with f1:
            sel_brand = st.multiselect("แบรนด์", brand_options, key="w_brand")
        with f2:
            sel_channel = st.multiselect("ช่องทางซื้อ", channel_options, key="w_channel")
        with f3:
            sel_category = st.multiselect("หมวดหมู่", category_options, key="w_category")

        # ── Apply filters ──
        filtered = wdf_all.copy()
        if w_search:
            q = w_search.lower()
            search_cols = ["registration_no", "serial_no", "first_name", "last_name", "phone", "brand", "model"]
            mask = filtered[search_cols].fillna("").apply(
                lambda row: q in " ".join(row.astype(str)).lower(), axis=1
            )
            filtered = filtered[mask]
        if sel_brand:
            filtered = filtered[filtered["brand"].isin(sel_brand)]
        if sel_channel:
            filtered = filtered[filtered["purchase_channel"].isin(sel_channel)]
        if sel_category:
            filtered = filtered[filtered["category"].isin(sel_category)]

        # ── Metrics ──
        st.caption(f"แสดง {len(filtered)} / {len(wdf_all)} รายการ")
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("ทั้งหมด", len(filtered))
        with m2:
            brands = filtered["brand"].value_counts()
            st.metric("แบรนด์หลัก", brands.index[0] if len(brands) else "-")
        with m3:
            channels = filtered["purchase_channel"].value_counts()
            st.metric("ช่องทางหลัก", channels.index[0] if len(channels) else "-")
        with m4:
            categories = filtered["category"].value_counts()
            st.metric("หมวดหมู่หลัก", categories.index[0] if len(categories) else "-")

        st.divider()
        wcols2 = ["registration_no", "serial_no", "first_name", "last_name", "phone", "brand", "model", "size", "category", "purchase_channel", "date_of_purchase", "warranty_period_months"]
        st.dataframe(
            filtered[[c for c in wcols2 if c in filtered.columns]],
            width="stretch",
            hide_index=True,
        )
