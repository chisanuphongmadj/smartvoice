"""
Seed mock customers and warranty registrations for SmartVoice demo.
Run: .venv\Scripts\python.exe seed_mock_data.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

from smartvoice import db

db.init_db()

CUSTOMERS = [
    dict(first_name="สมชาย",   last_name="ใจดี",      phone="0812345601", email="somchai@email.com",   gender="MALE",   date_of_birth="1985-03-12", address="123 ถ.พระราม 4",  subdistrict="คลองเตย",   district="คลองเตย",   city_province="กรุงเทพมหานคร", postcode="10110"),
    dict(first_name="สมหญิง",   last_name="รักดี",      phone="0812345602", email="somying@email.com",   gender="FEMALE", date_of_birth="1990-07-25", address="456 ถ.สุขุมวิท", subdistrict="บางนา",      district="บางนา",      city_province="กรุงเทพมหานคร", postcode="10260"),
    dict(first_name="วิชัย",    last_name="มั่นคง",     phone="0812345603", email="wichai@email.com",    gender="MALE",   date_of_birth="1978-11-08", address="789 ถ.เพชรบุรี", subdistrict="ราชเทวี",    district="ราชเทวี",    city_province="กรุงเทพมหานคร", postcode="10400"),
    dict(first_name="นภา",      last_name="สว่างใจ",    phone="0812345604", email="napa@email.com",      gender="FEMALE", date_of_birth="1995-02-14", address="321 ถ.ลาดพร้าว", subdistrict="จตุจักร",    district="จตุจักร",    city_province="กรุงเทพมหานคร", postcode="10900"),
    dict(first_name="ประเสริฐ", last_name="ทองดี",      phone="0812345605", email="prasert@email.com",   gender="MALE",   date_of_birth="1982-09-30", address="654 ถ.งามวงศ์วาน",subdistrict="บางเขน",     district="บางเขน",     city_province="กรุงเทพมหานคร", postcode="10220"),
    dict(first_name="มาลี",     last_name="ดอกไม้",     phone="0812345606", email="malee@email.com",     gender="FEMALE", date_of_birth="1988-05-20", address="11 ถ.นิมมานเหมินท์",subdistrict="สุเทพ",    district="เมือง",      city_province="เชียงใหม่",      postcode="50200"),
    dict(first_name="อนุชา",    last_name="แสงสว่าง",   phone="0812345607", email="anucha@email.com",    gender="MALE",   date_of_birth="1975-12-03", address="88 ถ.ท่าแพ",     subdistrict="ช้างคลาน",   district="เมือง",      city_province="เชียงใหม่",      postcode="50100"),
    dict(first_name="รัตนา",    last_name="พึ่งบุญ",    phone="0812345608", email="rattana@email.com",   gender="FEMALE", date_of_birth="1993-08-17", address="42 ถ.สีลม",      subdistrict="สีลม",       district="บางรัก",     city_province="กรุงเทพมหานคร", postcode="10500"),
    dict(first_name="ธนกร",     last_name="วงศ์เจริญ",  phone="0812345609", email="thanakorn@email.com", gender="MALE",   date_of_birth="1980-04-22", address="77 ถ.บางนา-ตราด",subdistrict="บางนา",      district="บางนา",      city_province="กรุงเทพมหานคร", postcode="10260"),
    dict(first_name="จิราภา",   last_name="หมื่นชนะ",   phone="0812345610", email="jirapa@email.com",    gender="FEMALE", date_of_birth="1997-01-09", address="5 ถ.มิตรภาพ",    subdistrict="ในเมือง",    district="เมือง",      city_province="ขอนแก่น",        postcode="40000"),
]

WARRANTY_DATA = [
    dict(registration_no="W001OZ25001", channel="Omazz",     certificate_no="CERT-OZ-001", category="Mattress", brand="Omazz",     model="Natura Latex",    size="5ft",  sku="OZ-NL-5FT-001",  serial_no="SN-OZ-001", label_no="LB-OZ-001", warranty_period_months=120, date_of_purchase="2024-06-15", date_of_delivery="2024-06-20", purchase_channel="Shopee",    order_number="SP2406001", expiry_date="2034-06-15"),
    dict(registration_no="W002DL25002", channel="Dunlopillo", certificate_no="CERT-DL-002", category="Mattress", brand="Dunlopillo", model="Celeste Spring",  size="6ft",  sku="DL-CS-6FT-002",  serial_no="SN-DL-002", label_no="LB-DL-002", warranty_period_months=120, date_of_purchase="2024-08-10", date_of_delivery="2024-08-15", purchase_channel="Lazada",    order_number="LZ2408002", expiry_date="2034-08-10"),
    dict(registration_no="W003OZ25003", channel="Omazz",     certificate_no="CERT-OZ-003", category="Mattress", brand="Omazz",     model="Platinum Pocket",  size="3.5ft",sku="OZ-PP-35-003",   serial_no="SN-OZ-003", label_no="LB-OZ-003", warranty_period_months=120, date_of_purchase="2024-09-01", date_of_delivery="2024-09-05", purchase_channel="TikTok Shop",order_number="TT2409003",expiry_date="2034-09-01"),
    dict(registration_no="W004SE25004", channel="Omazz",     certificate_no="CERT-SE-004", category="Mattress", brand="Sealy",     model="PosturePedic",    size="5ft",  sku="SE-PP-5FT-004",  serial_no="SN-SE-004", label_no="LB-SE-004", warranty_period_months=120, date_of_purchase="2024-07-20", date_of_delivery="2024-07-25", purchase_channel="Store",     order_number="ST2407004", expiry_date="2034-07-20"),
    dict(registration_no="W005DL25005", channel="Dunlopillo", certificate_no="CERT-DL-005", category="Pillow",   brand="Dunlopillo", model="Latex Pillow",    size="Standard", sku="DL-LP-STD-005", serial_no="SN-DL-005", label_no="LB-DL-005", warranty_period_months=12, date_of_purchase="2025-01-10", date_of_delivery="2025-01-12", purchase_channel="LINE",      order_number="LN2501005", expiry_date="2026-01-10"),
    dict(registration_no="W006OZ25006", channel="Omazz",     certificate_no="CERT-OZ-006", category="Mattress", brand="Omazz",     model="Memory Foam Pro", size="6ft",  sku="OZ-MF-6FT-006",  serial_no="SN-OZ-006", label_no="LB-OZ-006", warranty_period_months=120, date_of_purchase="2024-11-05", date_of_delivery="2024-11-10", purchase_channel="Shopee",    order_number="SP2411006", expiry_date="2034-11-05"),
    dict(registration_no="W007DL25007", channel="Dunlopillo", certificate_no="CERT-DL-007", category="Mattress", brand="Dunlopillo", model="Hypnos Spring",  size="5ft",  sku="DL-HS-5FT-007",  serial_no="SN-DL-007", label_no="LB-DL-007", warranty_period_months=120, date_of_purchase="2025-01-25", date_of_delivery="2025-01-30", purchase_channel="Lazada",    order_number="LZ2501007", expiry_date="2035-01-25"),
    dict(registration_no="W008OZ25008", channel="Omazz",     certificate_no="CERT-OZ-008", category="Mattress", brand="Omazz",     model="Cloud 9",         size="3.5ft",sku="OZ-C9-35-008",   serial_no="SN-OZ-008", label_no="LB-OZ-008", warranty_period_months=120, date_of_purchase="2024-12-18", date_of_delivery="2024-12-22", purchase_channel="TikTok Shop",order_number="TT2412008",expiry_date="2034-12-18"),
    dict(registration_no="W009SE25009", channel="Omazz",     certificate_no="CERT-SE-009", category="Mattress", brand="Sealy",     model="Conform Essential",size="5ft", sku="SE-CE-5FT-009",  serial_no="SN-SE-009", label_no="LB-SE-009", warranty_period_months=120, date_of_purchase="2025-02-14", date_of_delivery="2025-02-18", purchase_channel="Store",     order_number="ST2502009", expiry_date="2035-02-14"),
    dict(registration_no="W010OZ25010", channel="Omazz",     certificate_no="CERT-OZ-010", category="Topper",   brand="Omazz",     model="Latex Topper",    size="6ft",  sku="OZ-LT-6FT-010",  serial_no="SN-OZ-010", label_no="LB-OZ-010", warranty_period_months=24,  date_of_purchase="2025-03-01", date_of_delivery="2025-03-05", purchase_channel="Shopee",    order_number="SP2503010", expiry_date="2027-03-01"),
]

def seed():
    # Check if already seeded
    existing = db.get_all_customers()
    phones = {c["phone"] for c in existing}

    customer_ids = []
    for c in CUSTOMERS:
        if c["phone"] in phones:
            row = db.get_customer_by_phone(c["phone"])
            customer_ids.append(row["id"])
            print(f"  skip customer {c['first_name']} {c['last_name']} (exists)")
        else:
            cid = db.insert_customer(**c)
            customer_ids.append(cid)
            print(f"  + customer {c['first_name']} {c['last_name']} → id={cid}")

    existing_warr = {w["registration_no"] for w in db.get_all_warranties()}
    for i, w in enumerate(WARRANTY_DATA):
        if w["registration_no"] in existing_warr:
            print(f"  skip warranty {w['registration_no']} (exists)")
        else:
            wid = db.insert_warranty(customer_id=customer_ids[i], **w)
            print(f"  + warranty {w['registration_no']} ({w['brand']} {w['model']}) → id={wid}")

    print(f"\nDone: {len(customer_ids)} customers, {len(WARRANTY_DATA)} warranties")

if __name__ == "__main__":
    seed()
