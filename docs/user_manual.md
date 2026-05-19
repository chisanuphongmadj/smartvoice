# SmartVoice — คู่มือการใช้งาน

> **สำหรับ:** ผู้ดูแล Call Center, QA, Supervisor
> **อัปเดตล่าสุด:** 19 พฤษภาคม 2569

---

## SmartVoice ทำอะไรได้

1. ถอดเสียงสายภาษาไทยเป็นข้อความ
2. แยกผู้พูด Agent / Customer
3. วิเคราะห์ summary, topic, sentiment, agent QA, anomaly
4. จัดกลุ่มเคสของลูกค้าคนเดียวกัน
5. เชื่อมสายกับลูกค้าและ warranty จากเบอร์ในชื่อไฟล์
6. แสดง dashboard, ประวัติลูกค้า, และ next action ที่ต้องติดตาม

---

## เริ่มต้นใช้งาน

เปิด `http://localhost:8501`

ใน sidebar จะมี login:

- ถ้าองค์กรตั้ง `SMARTVOICE_USERS` แล้ว ให้ login ด้วย username/password
- ถ้ายังไม่ตั้งค่า ระบบจะเป็น demo/audit mode และให้กรอกชื่อกับ role

เมนูหลัก:

| เมนู | ใช้ทำอะไร |
|------|-----------|
| Home | ดู KPI และ `Deployment readiness` |
| Admin | Upload + process + จัดการสาย/เคส |
| Dashboard | ดูกราฟ, anomaly, agent performance พร้อมหลักฐานคะแนน QA, case summary |
| Customers | ดูลูกค้า, warranty, เคส, สายที่เชื่อมไว้ |
| Settings | ปรับ Demo / Real AI และ config หลัก |

หน้า `Settings` ใช้ได้เฉพาะ `Admin` หรือ `Supervisor`

---

## Workflow หลัก

### 1. Upload

ไปหน้า `Admin` แล้ว upload `.wav` หรือ `.mp3`

ระบบจะ:

- ตรวจชนิดไฟล์จริงจาก magic bytes
- จำกัดไฟล์ไม่เกิน 100 MB
- กันไฟล์ซ้ำด้วย SHA-256
- ดึงเบอร์โทร 10 หลักจากชื่อไฟล์
- เชื่อมลูกค้า + warranty อัตโนมัติถ้าพบเบอร์ในระบบ
- บันทึกชื่อและ role ของผู้ upload

### 2. Process

เลือกได้ 2 แบบ:

- `Process All Pending`
- เปิด card ของไฟล์แล้วกด `Process`

ถ้า Real AI mode แต่ Ollama ยังไม่พร้อม ระบบจะบอกวิธีติดตั้ง/เปิดใช้งานก่อนเริ่ม process

### 3. ติดตามสถานะ

สถานะหลัก:

```text
uploaded → processing → done
                  ↘ error
```

หน้า Admin จะ refresh สถานะอัตโนมัติทุก 3 วินาที และแสดง step ปัจจุบัน เช่น:

- ถอดเสียงและแยกผู้พูด
- ตรวจแก้ transcript
- แก้ speaker turn
- วิเคราะห์บทสนทนา
- บันทึกผล / จัดกลุ่มเคส

### 4. ดูผล

เมื่อสายเป็น `done` จะดูได้:

- ข้อมูลลูกค้าและ warranty ที่เชื่อมไว้
- tagged transcript
- เคสที่สายนี้อยู่
- สายอื่นในเคสเดียวกัน
- สถานะและหัวข้อเคส

---

## ฟีเจอร์หน้า Admin

- ค้นหาจากชื่อไฟล์, เบอร์, หรือผู้อัปโหลด
- กรองตามสถานะ
- เรียงใหม่→เก่า / เก่า→ใหม่ / ตามสถานะ
- เลือกหลายไฟล์เพื่อลบพร้อมกัน
- pagination แบบ `แสดงเพิ่ม`
- ล้าง orphan cases
- เชื่อมลูกค้าด้วยมือเมื่อระบบหาไม่เจอ
- แก้สถานะเคส, แก้หัวข้อเคส, และ merge เข้ากับเคสอื่นของลูกค้าคนเดียวกัน
- re-process สายที่ done แล้ว

---

## Dashboard

Dashboard แสดง:

- KPI จำนวนสายและ sentiment
- Sentiment distribution
- Topic / intent distribution
- Issue keywords
- Brand mentions
- Platform/channel mentions
- Anomaly calls พร้อม severity
- Top 3 issues
- Agent performance
- หลักฐานคะแนน Politeness / Problem Solving สำหรับตรวจสอบเหตุผลของคะแนน
- Case management summary
- ตารางสรุปทุกสาย

Agent performance จะรวมหลายสายที่อยู่ในเคสเดียวกันเป็น 1 แถว:

- คะแนน = ค่าเฉลี่ยในเคส
- Score = Politeness + Problem Solving
- Next Action = จากสายล่าสุด และระบบจะกรองข้อความที่ดูเหมือน copy ตัวอย่างจาก prompt ออก
- ถ้าเคส `closed` จะไม่แสดง next action ค้าง

---

## Customers

### Tab ลูกค้า

- ค้นหาด้วยชื่อหรือเบอร์
- ดูข้อมูลลูกค้า
- ดู warranty ของลูกค้า
- ดูเคสทั้งหมดของลูกค้า
- ดูสายที่เชื่อมแล้วแต่ยังไม่มีเคส

### Tab ทะเบียนรับประกัน

- ค้นหาจากเลขทะเบียน, serial, ชื่อลูกค้า, เบอร์, brand, model
- กรองตาม brand, purchase channel, category

---

## Settings

หน้า Settings ใช้สำหรับ:

- เลือก `Use Demo Laptop Mode`
- เลือก `Use Real AI Mode`
- เปลี่ยน HF token, Ollama URL/model, Whisper model/backend/device/compute
- ดู readiness checks

เมื่อ save ค่าแล้วควร restart แอปเพื่อให้ทุก module โหลด config ใหม่พร้อมกัน

---

## Case Management

สถานะเคส:

| สถานะ | ความหมาย |
|-------|----------|
| `open` | เคสใหม่ |
| `follow_up` | มีสายตามมา |
| `closed` | เคสจบแล้ว |

ระบบ auto-assign เคสตามลำดับ:

1. ถ้ามีเคสเปิดล่าสุดของลูกค้าคนเดิมในช่วง recency window → attach ทันที
2. ถ้าไม่เข้า window → ให้ LLM match topic/summary
3. ถ้าไม่ match → สร้างเคสใหม่

Supervisor สามารถ merge เคสได้จาก card ของสายบนหน้า Admin

---

## Re-process และ Delete

- `Re-process` ใช้รัน analysis ใหม่
- `Delete` จะลบทั้งไฟล์ใน disk และ record ใน DB
- `Delete Selected` ใช้ลบหลายไฟล์พร้อมกัน

การลบไม่สามารถกู้คืนได้

---

## FAQ

### ทำไม Settings เข้าไม่ได้

ต้อง login ก่อน และ role ต้องเป็น `Admin` หรือ `Supervisor`

### ทำไมประมวลผลไม่ได้

เปิด Home หรือ Settings แล้วดู `Deployment readiness`
ถ้า Real AI mode ต้องมี Ollama พร้อมใช้งาน และมี model ที่ตั้งไว้จริง

### ทำไมสายใหม่เข้าเคสเดิมทันที

ถ้าลูกค้าคนเดิมโทรกลับภายใน `CASE_RECENCY_HOURS` ระบบถือว่าเป็น follow-up ของเคสล่าสุดก่อนถาม LLM

### ทำไมบางสายกลับจาก `processing` เป็น `uploaded`

ระบบ recovery จะ reset งานที่ค้างนานเกิน `PROCESSING_STALE_MINUTES` เพื่อให้ process ใหม่ได้

### ดู log ที่ไหน

ดู `data/logs/smartvoice.log`
