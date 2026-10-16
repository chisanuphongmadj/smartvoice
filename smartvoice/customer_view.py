"""How a customer looks on screen — the Customers page's tables and detail dialog."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from smartvoice import db, labels
from smartvoice.customer_entry import compute_expiry_date
from smartvoice.so_view import render_customer_orders
from smartvoice.ui_helpers import render_proof


def customer_name(c: dict) -> str:
    return f"{c.get('first_name') or ''} {c.get('last_name') or ''}".strip() or "-"


def warranty_expiry(w: dict) -> str | None:
    """Stored expiry, or purchase date + warranty length for older rows that lack one."""
    return w.get("expiry_date") or compute_expiry_date(
        w.get("date_of_purchase"), w.get("warranty_period_months")
    )


def warranty_state(expiry: str | None, status: str | None = None) -> str:
    if status == "cancelled":
        return "ยกเลิกแล้ว"
    if not expiry:
        return "ไม่ทราบ"
    try:
        return "อยู่ในประกัน" if date.fromisoformat(expiry[:10]) >= date.today() else "หมดประกันแล้ว"
    except ValueError:
        return "ไม่ทราบ"


def warranty_rows(warranties: list[dict], with_owner: bool) -> pd.DataFrame:
    rows = []
    for w in warranties:
        expiry = warranty_expiry(w)
        row = {"เลขทะเบียน": w.get("registration_no") or "-"}
        if with_owner:
            row["ลูกค้า"] = customer_name(w)
            row["เบอร์โทร"] = w.get("phone") or "-"
        row.update({
            "แบรนด์": w.get("brand") or "-",
            "รุ่น": w.get("model") or "-",
            "ขนาด": w.get("size") or "-",
            "หมวดหมู่": w.get("category") or "-",
            "ช่องทางซื้อ": w.get("purchase_channel") or "-",
            "Serial": w.get("serial_no") or "-",
            "เลขที่ SO": w.get("so_number") or "-",
            "Ref Id": w.get("ref_id") or "-",
            "วันที่ซื้อ": labels.thai_time(w.get("date_of_purchase"), with_time=False),
            "หมดประกัน": labels.thai_time(expiry, with_time=False),
            "สถานะประกัน": warranty_state(expiry, w.get("status")),
            "หลักฐานการซื้อ": "มี" if w.get("proof_path") else "-",
        })
        rows.append(row)
    return pd.DataFrame(rows)


def customer_rows(customers: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "ชื่อ": customer_name(c),
            "เบอร์โทร": c.get("phone") or "-",
            "อีเมล": c.get("email") or "-",
            "จังหวัด": c.get("city_province") or "-",
            "เพิ่มเมื่อ": labels.thai_time(c.get("created_at"), with_time=False),
        }
        for c in customers
    ])


def render_customer_detail(customer_id: int) -> None:
    """Profile, warranties (+ proofs), SOs, cases and linked calls of one customer."""
    c = db.get_customer_by_id(customer_id)
    if not c:
        st.warning("ไม่พบลูกค้ารายนี้แล้ว — อาจถูกซ่อนไว้")
        return

    st.markdown(f"#### {customer_name(c)}")
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(f"**ชื่อเล่น:** {c.get('nick_name') or '-'}")
        st.markdown(f"**ช่องทาง:** {c.get('channel') or '-'}")
        st.markdown(f"**เพศ:** {c.get('gender') or '-'}")
        st.markdown(f"**วันเกิด:** {labels.thai_time(c.get('date_of_birth'), with_time=False)}")
        st.markdown(f"**เบอร์:** {c.get('phone') or '-'}")
        st.markdown(f"**อีเมล:** {c.get('email') or '-'}")
    with col_b:
        st.markdown(f"**ที่อยู่:** {c.get('address') or '-'}")
        st.markdown(f"**แขวง/ตำบล:** {c.get('subdistrict') or '-'}")
        st.markdown(f"**เขต/อำเภอ:** {c.get('district') or '-'}")
        st.markdown(f"**จังหวัด:** {c.get('city_province') or '-'}")
        st.markdown(f"**รหัสไปรษณีย์:** {c.get('postcode') or '-'}")

    warrs = db.get_warranties_by_customer(c["id"])
    if warrs:
        st.markdown(f"**ทะเบียนรับประกัน ({len(warrs)} รายการ)**")
        st.dataframe(warranty_rows(warrs, with_owner=False), width="stretch", hide_index=True)
        with_proof = [w for w in warrs if w.get("proof_path")]
        if with_proof:
            with st.expander(f"หลักฐานการซื้อ ({len(with_proof)})"):
                for w in with_proof:
                    st.caption(f"ทะเบียน {w['registration_no']}")
                    render_proof(w["proof_path"], key=f"_proof_{w['id']}")

    order_count = render_customer_orders(c["id"])

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
                    # The summary goes on its own line, in full: Thai has no
                    # spaces between words, so any character cut lands mid-word.
                    st.markdown(f"- {oc['filename']} ({labels.call_status(oc['status'])})")
                    if oc.get("summary"):
                        st.caption(oc["summary"])

    # Calls linked to this customer that have no case yet.
    all_calls = db.get_calls_by_customer(c["id"])
    linked_no_case = [cl for cl in all_calls if not cl.get("case_id")]
    if linked_no_case:
        st.markdown(f"**สายที่เชื่อมไว้แต่ยังไม่มีเคส ({len(linked_no_case)})**")
        for cl in linked_no_case:
            badge = "จับคู่อัตโนมัติจากเบอร์" if cl.get("matched_by") == "auto_phone" else "จับคู่เอง"
            st.caption(f"- {cl['filename']} ({labels.call_status(cl['status'])}) — {badge}")
    if not warrs and not order_count and not cases and not all_calls:
        st.caption("ลูกค้ารายนี้ยังไม่มีทะเบียนรับประกัน ใบสั่งขาย เคส หรือสายในระบบ")
