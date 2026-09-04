"""Read-only audit trail — who did what, when."""

import pandas as pd
import streamlit as st

st.set_page_config(page_title="SmartVoice — Audit Log", layout="wide")

from smartvoice import audit as audit_trail
from smartvoice import db
from smartvoice.auth import PAGE_AUDIT
from smartvoice.ui_helpers import init_page

# Admin / Supervisor only (see smartvoice.auth.ROLE_PERMISSIONS).
current_user, current_role = init_page(PAGE_AUDIT)

st.title("ประวัติการใช้งาน")
st.caption(
    "บันทึกทุกการเข้าสู่ระบบ เพิ่ม แก้ไข ลบ/ซ่อน และกู้คืน — "
    "ตารางนี้เขียนได้อย่างเดียว ไม่มีการแก้หรือลบย้อนหลังจากหน้าไหนในระบบ"
)

_ALL = "ทั้งหมด"
entries_total = db.count_audit_entries()

f1, f2, f3 = st.columns([2, 2, 1])
with f1:
    entity_choice = st.selectbox(
        "ประเภทข้อมูล",
        (_ALL, *audit_trail.ENTITY_LABELS_TH),
        format_func=lambda e: audit_trail.ENTITY_LABELS_TH.get(e, e),
        key="_log_entity",
    )
with f2:
    action_choice = st.selectbox(
        "การกระทำ",
        (_ALL, *audit_trail.ACTION_LABELS_TH),
        format_func=lambda a: audit_trail.ACTION_LABELS_TH.get(a, a),
        key="_log_action",
    )
with f3:
    limit = st.selectbox("จำนวนที่โหลด", (100, 500, 2000), index=0, key="_log_limit")

entries = db.get_audit_log(
    entity=None if entity_choice == _ALL else entity_choice, limit=limit
)
if action_choice != _ALL:
    entries = [e for e in entries if e["action"] == action_choice]

actors = sorted({e["actor"] for e in entries if e["actor"]})
picked_actors = st.multiselect("ผู้ใช้", actors, key="_log_actor")
if picked_actors:
    entries = [e for e in entries if e["actor"] in picked_actors]

search = st.text_input(
    "ค้นหาในรายการ / รายละเอียด", placeholder="ชื่อลูกค้า, เลขทะเบียน, ชื่อไฟล์ ...", key="_log_search"
)


def _describe_changes(changes: dict | None) -> str:
    """Render one entry's `changes` dict as 'field: before → after' text."""
    parts = []
    for field, value in (changes or {}).items():
        if isinstance(value, list) and len(value) == 2:
            before, after = (v if v not in (None, "") else "—" for v in value)
            parts.append(f"{field}: {before} → {after}")
        else:
            parts.append(f"{field}: {value}")
    return ", ".join(parts)


rows = [
    {
        "เมื่อ": entry["created_at"][:19].replace("T", " "),
        "ผู้ใช้": entry["actor"] or "—",
        "บทบาท": entry["actor_role"] or "—",
        "การกระทำ": audit_trail.ACTION_LABELS_TH.get(entry["action"], entry["action"]),
        "ประเภท": audit_trail.ENTITY_LABELS_TH.get(entry["entity"], entry["entity"]),
        "รายการ": (
            f"{entry['entity_label'] or '—'}"
            + (f" (id={entry['entity_id']})" if entry["entity_id"] is not None else "")
        ),
        "รายละเอียด": _describe_changes(entry["changes"]),
    }
    for entry in entries
]

if search:
    q = search.lower()
    rows = [r for r in rows if q in f"{r['รายการ']} {r['รายละเอียด']}".lower()]

st.caption(f"แสดง {len(rows)} รายการ · ทั้งหมดในระบบ {entries_total} รายการ")

if not rows:
    st.info("ไม่พบรายการที่ตรงกับเงื่อนไข")
else:
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    st.download_button(
        "ดาวน์โหลดเป็น CSV",
        data=pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig"),
        file_name="smartvoice_audit_log.csv",
        mime="text/csv",
    )

with st.expander("ระบบบันทึกอะไรบ้าง"):
    st.markdown(
        """
- **การเข้าใช้งาน** — เข้าสู่ระบบสำเร็จ / ไม่สำเร็จ / ออกจากระบบ
- **ลูกค้า & ทะเบียนรับประกัน** — เพิ่ม, แก้ไข (เก็บค่าก่อน→หลังของทุกช่องที่เปลี่ยน), ซ่อน, กู้คืน
- **บัญชีผู้ใช้** — สร้าง, เปลี่ยนบทบาท, เปิด/ปิดใช้งาน, เปลี่ยนรหัสผ่านของตัวเอง
- **สายสนทนา** — อัปโหลด, ลบ, เชื่อมลูกค้า/ทะเบียนแบบ manual
- **เคส** — เปลี่ยนสถานะ, แก้หัวข้อ, รวมเคส
- **ตั้งค่าระบบ** — บันทึกค่าใน Settings และการกด preset

รหัสผ่านและ token ไม่ถูกบันทึกลงประวัติ — เก็บเฉพาะชื่อฟิลด์ว่ามีการเปลี่ยน
        """
    )
