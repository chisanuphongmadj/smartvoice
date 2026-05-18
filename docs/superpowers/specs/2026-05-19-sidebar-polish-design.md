# Sidebar Polish Design

## Goal

ปรับ sidebar ให้ดูสะอาดขึ้นโดยคง mood เดิมของแอปไว้ และไม่กระทบ routing, authentication, หรือ behavior ของระบบ

## Chosen Approach

ใช้แนวทาง **CSS polish + visual hierarchy** โดยคง navigation เดิมของ Streamlit ไว้ทั้งหมด แล้วปรับเฉพาะการจัดวางและการแสดงผล

## Scope

- ปรับ spacing ระหว่างส่วน search, navigation items, และเส้นคั่นด้านล่าง
- ปรับ typography ของ navigation items ให้ดูอ่านง่ายขึ้น
- ทำ active item ให้เด่นขึ้นแบบนุ่มนวลโดยยังใช้โทนสีเดิม
- เก็บการแก้ไว้ใน shared CSS ของ `smartvoice/ui_helpers.py` เป็นหลัก

## Out Of Scope

- ไม่สร้าง custom navigation ใหม่
- ไม่เปลี่ยนชื่อหน้า, icon, หรือโครงสร้าง multipage ของ Streamlit
- ไม่แตะ logic login, session state, routing, หรือข้อมูลในระบบ

## Design Details

### Layout

- เพิ่มระยะหายใจรอบกลุ่ม navigation เล็กน้อย
- ทำระยะห่างระหว่างแต่ละรายการให้สม่ำเสมอ
- ลดความรู้สึกแน่นของส่วนบนโดยจัดระยะจาก search ไปยังเมนูให้สมดุลขึ้น

### Typography

- ใช้น้ำหนักตัวอักษรที่ชัดขึ้นเล็กน้อยสำหรับรายการเมนู
- ปรับ line-height ให้สบายตาขึ้น
- ใช้สี inactive ที่ยังกลืนกับธีมเดิม แต่มี contrast ดีขึ้น

### Active State

- ใช้พื้นหลังบาง ๆ และสีตัวอักษรที่ชัดกว่าเดิม
- ไม่เพิ่ม animation หรือ decoration ที่ดึงความสนใจเกินไป

## Risk Control

- ใช้ selector ที่จำกัดเฉพาะ sidebar navigation เพื่อลดผลกระทบต่อส่วนอื่น
- ไม่เปลี่ยน DOM structure หรือ component API
- ตรวจหน้าจอจริงหลังแก้เพื่อยืนยันว่า login widget และ sidebar info ยังแสดงผลถูกต้อง

## Verification

- เปิดแอปและตรวจ sidebar ในหน้า Home, Admin, Dashboard, Customers, Settings
- ยืนยันว่า active state ตรงกับหน้าปัจจุบัน
- รัน test suite เดิมเพื่อยืนยันว่าไม่มี regression ฝั่งระบบ
