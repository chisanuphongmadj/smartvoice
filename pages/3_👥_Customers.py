from datetime import date

import pandas as pd
import streamlit as st

st.set_page_config(page_title="SmartVoice — ลูกค้าและการรับประกัน", layout="wide")

from smartvoice import db, labels
from smartvoice.auth import PAGE_CUSTOMERS
from smartvoice.customer_entry import compute_expiry_date
from smartvoice.ui_helpers import init_page

init_page(PAGE_CUSTOMERS)

# ─────────────────────────────────────────
# PAGE: CUSTOMERS & WARRANTY
# ─────────────────────────────────────────
st.title("ลูกค้าและการรับประกัน")
st.caption("ค้นหาลูกค้า ดูทะเบียนรับประกัน เคส และสายที่เคยโทรเข้ามา — เพิ่มหรือแก้ไขข้อมูลได้ที่เมนู เพิ่ม/แก้ไขข้อมูลลูกค้า")


def _warranty_expiry(w: dict) -> str | None:
    """Stored expiry, or purchase date + warranty length for older rows that lack one."""
    return w.get("expiry_date") or compute_expiry_date(
        w.get("date_of_purchase"), w.get("warranty_period_months")
    )


def _warranty_state(expiry: str | None) -> str:
    if not expiry:
        return "ไม่ทราบ"
    try:
        return "อยู่ในประกัน" if date.fromisoformat(expiry[:10]) >= date.today() else "หมดประกันแล้ว"
    except ValueError:
        return "ไม่ทราบ"


def _warranty_rows(warranties: list[dict], with_owner: bool) -> pd.DataFrame:
    rows = []
    for w in warranties:
        expiry = _warranty_expiry(w)
        row = {"เลขทะเบียน": w.get("registration_no") or "-"}
        if with_owner:
            row["ลูกค้า"] = f"{w.get('first_name') or ''} {w.get('last_name') or ''}".strip() or "-"
            row["เบอร์โทร"] = w.get("phone") or "-"
        row.update({
            "แบรนด์": w.get("brand") or "-",
            "รุ่น": w.get("model") or "-",
            "ขนาด": w.get("size") or "-",
            "หมวดหมู่": w.get("category") or "-",
            "ช่องทางซื้อ": w.get("purchase_channel") or "-",
            "Serial": w.get("serial_no") or "-",
            "วันที่ซื้อ": labels.thai_time(w.get("date_of_purchase"), with_time=False),
            "หมดประกัน": labels.thai_time(expiry, with_time=False),
            "สถานะประกัน": _warranty_state(expiry),
        })
        rows.append(row)
    return pd.DataFrame(rows)


tab1, tab2 = st.tabs(["ลูกค้า", "ทะเบียนรับประกัน"])

with tab1:
    customers = db.get_all_customers()
    if not customers:
        st.info("ยังไม่มีข้อมูลลูกค้า — เพิ่มลูกค้าได้ที่เมนู เพิ่ม/แก้ไขข้อมูลลูกค้า")
    else:
        search = st.text_input(
            "ค้นหาลูกค้า", placeholder="ชื่อ นามสกุล หรือเบอร์โทร เช่น สมชาย ใจดี หรือ 0812345601"
        )
        if search.strip():
            q = search.strip().lower()
            customers = [
                c for c in customers
                if q in f"{c['first_name']} {c['last_name']} {c['phone'] or ''}".lower()
                or q.replace("-", "").replace(" ", "") in (c["phone"] or "")
            ]
        st.caption(f"พบ {len(customers)} ราย")

        if not customers:
            st.warning("ไม่พบลูกค้าที่ตรงกับคำค้น — ลองพิมพ์แค่ชื่อ หรือเบอร์บางส่วน")
        else:
            st.dataframe(
                pd.DataFrame([
                    {
                        "ชื่อ": f"{c['first_name']} {c['last_name']}",
                        "เบอร์โทร": c["phone"] or "-",
                        "อีเมล": c["email"] or "-",
                        "จังหวัด": c["city_province"] or "-",
                        "เพิ่มเมื่อ": labels.thai_time(c["created_at"], with_time=False),
                    }
                    for c in customers
                ]),
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
                    st.markdown(f"**วันเกิด:** {labels.thai_time(c['date_of_birth'], with_time=False)}")
                    st.markdown(f"**เบอร์:** {c['phone'] or '-'}")
                    st.markdown(f"**อีเมล:** {c['email'] or '-'}")
                with col_b:
                    st.markdown(f"**ที่อยู่:** {c['address'] or '-'}")
                    st.markdown(f"**แขวง/ตำบล:** {c['subdistrict'] or '-'}")
                    st.markdown(f"**เขต/อำเภอ:** {c['district'] or '-'}")
                    st.markdown(f"**จังหวัด:** {c['city_province'] or '-'}")
                    st.markdown(f"**รหัสไปรษณีย์:** {c['postcode'] or '-'}")

                warrs = db.get_warranties_by_customer(c["id"])
                if warrs:
                    st.markdown(f"**ทะเบียนรับประกัน ({len(warrs)} รายการ)**")
                    st.dataframe(_warranty_rows(warrs, with_owner=False), width="stretch", hide_index=True)

                # ── Cases of this customer ──
                cases = db.get_cases_by_customer(c["id"])
                if cases:
                    st.markdown(f"**เคส ({len(cases)} เคส)**")
                    for cs in cases:
                        case_calls = db.get_calls_by_case(cs["id"])
                        owner = cs.get("assignee_name") or "ยังไม่มีคนรับ"
                        with st.expander(
                            f"เคส #{cs['id']}: {cs['subject']}  —  {labels.case_status(cs['status'])}  "
                            f"•  ผู้รับเคส: {owner}  ({len(case_calls)} สาย)"
                        ):
                            st.caption(
                                f"สร้าง: {labels.thai_time(cs.get('created_at'))}  •  "
                                f"อัปเดตล่าสุด: {labels.thai_time(cs.get('updated_at'))}"
                            )
                            for oc in case_calls:
                                # The summary goes on its own line, in full: Thai has
                                # no spaces between words, so any character cut lands
                                # mid-word (every summary in the DB is 130-330 chars).
                                st.markdown(f"- {oc['filename']} ({labels.call_status(oc['status'])})")
                                if oc.get("summary"):
                                    st.caption(oc["summary"])

                # ── Calls linked to this customer (even without a case) ──
                all_calls = db.get_calls_by_customer(c["id"])
                linked_no_case = [cl for cl in all_calls if not cl.get("case_id")]
                if linked_no_case:
                    st.markdown(f"**สายที่เชื่อมไว้แต่ยังไม่มีเคส ({len(linked_no_case)})**")
                    for cl in linked_no_case:
                        _badge = "จับคู่อัตโนมัติจากเบอร์" if cl.get("matched_by") == "auto_phone" else "จับคู่เอง"
                        st.caption(f"- {cl['filename']} ({labels.call_status(cl['status'])}) — {_badge}")
                if not warrs and not cases and not all_calls:
                    st.caption("ลูกค้ารายนี้ยังไม่มีทะเบียนรับประกัน เคส หรือสายในระบบ")

with tab2:
    warranties = db.get_all_warranties()
    if not warranties:
        st.info("ยังไม่มีข้อมูลทะเบียนรับประกัน — เพิ่มได้ที่เมนู เพิ่ม/แก้ไขข้อมูลลูกค้า")
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
            sel_brand = st.multiselect("แบรนด์", brand_options, key="w_brand", placeholder="ทุกแบรนด์")
        with f2:
            sel_channel = st.multiselect("ช่องทางซื้อ", channel_options, key="w_channel", placeholder="ทุกช่องทาง")
        with f3:
            sel_category = st.multiselect("หมวดหมู่", category_options, key="w_category", placeholder="ทุกหมวดหมู่")

        # ── Apply filters ──
        filtered = wdf_all.copy()
        if w_search.strip():
            q = w_search.strip().lower()
            search_cols = [col for col in ("registration_no", "serial_no", "first_name", "last_name", "phone", "brand", "model") if col in filtered.columns]
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
        if filtered.empty:
            st.warning("ไม่พบทะเบียนที่ตรงกับคำค้นหรือตัวกรอง")
        else:
            st.dataframe(
                _warranty_rows(filtered.to_dict("records"), with_owner=True),
                width="stretch",
                hide_index=True,
            )
