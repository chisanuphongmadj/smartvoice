"""How a sales order looks on screen — shared by the SO, Customers and Cases pages.

Laid out like the company's printed "ใบสั่งขาย": document details, buyer and
receiver side by side, the item lines, then the totals.
"""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from smartvoice import db, labels


def _d(value) -> str:
    return labels.thai_time(value, with_time=False)


def _name(first, last) -> str:
    return f"{first or ''} {last or ''}".strip()


def order_table(orders: list[dict], with_customer: bool = True) -> pd.DataFrame:
    """One row per SO for list tables."""
    rows = []
    for o in orders:
        row = {
            "เลขที่ SO": o.get("so_number") or "-",
            "วันที่สั่งซื้อ": _d(o.get("order_date") or o.get("document_date")),
            "วันที่จัดส่ง": _d(o.get("shipment_date") or o.get("promised_delivery_date")),
            "ผู้ซื้อ": o.get("sell_to_name") or "-",
            "ผู้รับ": o.get("ship_to_name") or "-",
            "เบอร์ผู้รับ": o.get("ship_to_phone") or "-",
            "รายการ": int(o.get("line_count") or 0),
            "ยอดรวมสุทธิ": labels.baht(o.get("grand_total")),
        }
        if with_customer:
            row["ลูกค้าในระบบ"] = _name(o.get("first_name"), o.get("last_name")) or "ยังไม่จับคู่"
        rows.append(row)
    return pd.DataFrame(rows)


def lines_table(lines: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "ลำดับ": ln.get("line_no") or "",
            "รหัสสินค้า/บาร์โค้ด": ln.get("item_no") or "-",
            "รายละเอียด": ln.get("description") or "-",
            "วันที่ต้องการรับ": _d(ln.get("requested_delivery_date")),
            "หน่วย": ln.get("uom") or "-",
            "คลัง": ln.get("location") or "-",
            "จำนวน": ln.get("quantity") if ln.get("quantity") is not None else "",
            "ราคาต่อหน่วย": labels.baht(ln.get("unit_price"), empty=""),
            "ส่วนลด": labels.baht(ln.get("discount"), empty=""),
            "จำนวนเงิน": labels.baht(ln.get("amount"), empty=""),
        }
        for ln in lines
    ])


def _facts(pairs: list[tuple[str, object]]) -> None:
    shown = [(k, v) for k, v in pairs if v not in (None, "", "-")]
    if not shown:
        st.caption("—")
        return
    st.markdown(
        "<br>".join(f"<b>{html.escape(k)}:</b> {html.escape(str(v))}" for k, v in shown),
        unsafe_allow_html=True,
    )


def render_order(order: dict, show_customer: bool = True) -> None:
    """The full SO: header, parties, lines, totals, linked warranties."""
    st.markdown(f"#### ใบสั่งขาย {order['so_number']}")
    if order.get("deleted_at"):
        st.warning(f"SO นี้ถูกซ่อนไว้เมื่อ {labels.thai_time(order['deleted_at'])}")

    doc_col, sale_col = st.columns(2)
    with doc_col:
        st.markdown("**วันที่**")
        _facts([
            ("วันที่เอกสาร", _d(order.get("document_date"))),
            ("วันที่สั่งซื้อ", _d(order.get("order_date"))),
            ("วันที่จัดส่ง", _d(order.get("shipment_date"))),
            ("วันที่สัญญาส่ง", _d(order.get("promised_delivery_date"))),
            ("วันครบกำหนด", _d(order.get("due_date"))),
        ])
    with sale_col:
        st.markdown("**ข้อมูลการขาย**")
        _facts([
            ("ประเภทการขาย", order.get("sales_type")),
            ("ประเภทการซื้อ", order.get("purchasing_type")),
            ("พนักงานขาย", order.get("salesperson")),
            ("เลขที่เอกสารภายนอก", order.get("external_doc")),
            ("เครดิต", order.get("credit_term")),
            ("เลขที่ PO ลูกค้า", order.get("customer_po_no")),
            ("สกุลเงิน", order.get("currency")),
        ])

    sell_col, ship_col = st.columns(2)
    with sell_col:
        st.markdown("**ผู้ซื้อ (Sell-to)**")
        _facts([
            ("รหัส", order.get("sell_to_no")),
            ("ชื่อ", order.get("sell_to_name")),
            ("ที่อยู่", order.get("sell_to_address")),
            ("ผู้ติดต่อ", order.get("sell_to_contact")),
            ("เบอร์โทร", order.get("sell_to_phone")),
        ])
    with ship_col:
        st.markdown("**ผู้รับ / ที่อยู่จัดส่ง (Ship-to)**")
        _facts([
            ("ชื่อ", order.get("ship_to_name")),
            ("ที่อยู่", order.get("ship_to_address")),
            ("ผู้ติดต่อ", order.get("ship_to_contact")),
            ("เบอร์โทร", order.get("ship_to_phone")),
            ("อีเมล", order.get("ship_to_email")),
        ])

    if show_customer:
        customer = _name(order.get("first_name"), order.get("last_name"))
        st.caption(
            f"ลูกค้าในระบบ: {customer} ({order.get('customer_phone') or '-'})" if customer
            else "ยังไม่ได้จับคู่กับลูกค้าในระบบ (จับคู่อัตโนมัติจากเบอร์ผู้รับ/ผู้ซื้อ)"
        )

    lines = order.get("lines") or []
    st.markdown(f"**รายการสินค้า ({len(lines)})**")
    if lines:
        st.dataframe(lines_table(lines), width="stretch", hide_index=True)
    else:
        st.caption("ไม่มีรายการสินค้า")

    _, totals_col = st.columns([3, 2])
    with totals_col:
        st.dataframe(
            pd.DataFrame([
                {"": "ยอดรวม", "บาท": labels.baht(order.get("total"))},
                {"": "ส่วนลด", "บาท": labels.baht(order.get("discount"))},
                {"": "ยอดหลังหักส่วนลด", "บาท": labels.baht(order.get("net_amount"))},
                {"": "VAT", "บาท": labels.baht(order.get("vat"))},
                {"": "ยอดรวมสุทธิ", "บาท": labels.baht(order.get("grand_total"))},
            ]),
            width="stretch", hide_index=True,
        )
    if order.get("remark"):
        st.markdown(f"**หมายเหตุ:** {html.escape(order['remark'])}", unsafe_allow_html=True)

    warranties = db.get_warranties_by_so_number(order["so_number"])
    if warranties:
        st.markdown(f"**ทะเบียนรับประกันที่อ้างถึง SO นี้ ({len(warranties)})**")
        for w in warranties:
            product = " ".join(str(w.get(k)) for k in ("brand", "model", "size") if w.get(k)) or "ไม่ระบุสินค้า"
            st.caption(
                f"{w.get('registration_no')}  •  {product}  •  {labels.warranty_status(w.get('status'))}"
            )


def order_heading(o: dict) -> str:
    """One-line description of an SO for expanders."""
    parts = [f"SO {o.get('so_number')}"]
    if o.get("order_date") or o.get("document_date"):
        parts.append(f"สั่ง {_d(o.get('order_date') or o.get('document_date'))}")
    if o.get("shipment_date") or o.get("promised_delivery_date"):
        parts.append(f"ส่ง {_d(o.get('shipment_date') or o.get('promised_delivery_date'))}")
    parts.append(f"{int(o.get('line_count') or 0)} รายการ")
    if o.get("grand_total") is not None:
        parts.append(f"{labels.baht(o['grand_total'])} บาท")
    return "  •  ".join(parts)


def render_customer_orders(customer_id: int, limit: int = 10) -> int:
    """A customer's SOs as expanders (newest first). Returns how many exist.

    An expander body runs even while collapsed, so only `limit` are drawn.
    """
    orders = db.get_sales_orders_for_customers([customer_id]).get(customer_id, [])
    if not orders:
        return 0
    st.markdown(f"**ใบสั่งขาย (SO) ({len(orders)})**")
    for o in orders[:limit]:
        with st.expander(order_heading(o)):
            full = db.get_sales_order(so_id=o["id"])
            if full:
                render_order(full, show_customer=False)
    if len(orders) > limit:
        st.caption(f"แสดง {limit} SO ล่าสุด — ดูทั้งหมดได้ที่เมนู ใบสั่งขาย (SO)")
    return len(orders)
