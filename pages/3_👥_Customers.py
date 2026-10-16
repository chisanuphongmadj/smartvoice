import pandas as pd
import streamlit as st

st.set_page_config(page_title="SmartVoice — ลูกค้าและการรับประกัน", layout="wide")

from smartvoice import db
from smartvoice.auth import PAGE_CUSTOMERS
from smartvoice.customer_view import customer_name, customer_rows, render_customer_detail, warranty_rows
from smartvoice.ui_helpers import TABLE_CLICK_MODES, init_page, picked_row

init_page(PAGE_CUSTOMERS)

# ─────────────────────────────────────────
# PAGE: CUSTOMERS & WARRANTY
# ─────────────────────────────────────────
st.title("ลูกค้าและการรับประกัน")
st.caption("ค้นหาลูกค้า ดูทะเบียนรับประกัน ใบสั่งขาย (SO) เคส และสายที่เคยโทรเข้ามา — เพิ่มหรือแก้ไขข้อมูลได้ที่เมนู เพิ่ม/แก้ไขข้อมูลลูกค้า")


@st.dialog("รายละเอียดลูกค้า", width="large")
def _customer_dialog(customer_id: int) -> None:
    render_customer_detail(customer_id)


def _open_on_click(event, memory_key: str, owners: list[tuple], button_key: str) -> None:
    """Open the clicked row's customer once per click, plus a button to reopen it.

    `owners` is (customer_id, name) per table row, in table order.
    """
    row, is_new = picked_row(event, memory_key)
    if row is None or row >= len(owners) or not owners[row][0]:
        return
    customer_id, name = owners[row]
    if is_new:
        _customer_dialog(customer_id)
    if st.button(f"เปิดข้อมูลของ {name} อีกครั้ง", key=button_key):
        _customer_dialog(customer_id)


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
        st.caption(
            f"พบ {len(customers)} ราย — คลิกแถวไหนก็ได้เพื่อเปิดดูทะเบียนรับประกัน "
            "ใบสั่งขาย เคส และสายของลูกค้าคนนั้น"
        )

        if not customers:
            st.warning("ไม่พบลูกค้าที่ตรงกับคำค้น — ลองพิมพ์แค่ชื่อ หรือเบอร์บางส่วน")
        else:
            # The key follows the rows shown, so a new search resets the
            # selection instead of pointing the old row position at someone else.
            event = st.dataframe(
                customer_rows(customers),
                width="stretch",
                hide_index=True,
                on_select="rerun",
                selection_mode=TABLE_CLICK_MODES,
                key=f"_customer_table_{hash(tuple(c['id'] for c in customers))}",
            )
            _open_on_click(
                event, "_customer_table_pick",
                [(c["id"], customer_name(c)) for c in customers],
                "_customer_reopen",
            )

with tab2:
    warranties = db.get_all_warranties()
    if not warranties:
        st.info("ยังไม่มีข้อมูลทะเบียนรับประกัน — เพิ่มได้ที่เมนู เพิ่ม/แก้ไขข้อมูลลูกค้า")
    else:
        wdf_all = pd.DataFrame(warranties)

        # ── Search bar ──
        w_search = st.text_input(
            "ค้นหาทะเบียนรับประกัน",
            placeholder="ชื่อลูกค้า, เบอร์, เลขทะเบียน, Serial, เลขที่ SO, Ref Id, แบรนด์, รุ่น ...",
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
            search_cols = [col for col in ("registration_no", "serial_no", "so_number", "ref_id", "first_name", "last_name", "phone", "brand", "model") if col in filtered.columns]
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
            records = filtered.to_dict("records")
            st.caption("คลิกแถวไหนก็ได้เพื่อเปิดดูข้อมูลทั้งหมดของลูกค้าเจ้าของทะเบียน")
            event = st.dataframe(
                warranty_rows(records, with_owner=True),
                width="stretch",
                hide_index=True,
                on_select="rerun",
                selection_mode=TABLE_CLICK_MODES,
                key=f"_warranty_table_{hash(tuple(r['id'] for r in records))}",
            )
            _open_on_click(
                event, "_warranty_table_pick",
                [(r.get("customer_id"), customer_name(r)) for r in records],
                "_warranty_reopen",
            )
