# รายการแก้ไขรายงาน — ปรับให้ตรงกับระบบปัจจุบัน

> เอกสารนี้รวบรวมจุดที่ต้องแก้ไขในรายงานบทที่ 1, 2 และ 3  
> โดยอ้างอิงจาก source code จริงในโปรเจกต์ SmartVoice ณ วันที่ 20 พฤษภาคม 2569 (ก่อนส่งมอบ 23 พ.ค. 2569)
> **วิธีใช้**: คัดลอกข้อความ "✅ แก้เป็น" ไปแทนที่ข้อความ "❌ ข้อความเดิม" ในรายงาน

---

## อัปเดตเพิ่มเติมจากสถานะปัจจุบัน

ถ้าจะให้รายงานสะท้อนโค้ดเวอร์ชันปัจจุบันครบถ้วน ควรเพิ่มประเด็นต่อไปนี้ด้วย:

- ระบบมีหน้า `Settings` สำหรับสลับ Demo / Real AI และแก้ค่าหลักใน `.env`
- มี `Deployment readiness` checks บนหน้า Home และ Settings
- มี sidebar login แบบ PBKDF2 ผ่าน `SMARTVOICE_USERS` พร้อม demo/audit fallback
- ตาราง `calls` มี `uploaded_by` และ `uploaded_by_role` สำหรับ audit trail
- auto case assignment มี recency short-circuit ผ่าน `CASE_RECENCY_HOURS` ก่อนให้ LLM match
- ระบบ recover งานที่ค้างในสถานะ `processing` ผ่าน `PROCESSING_STALE_MINUTES`
- หน้า Admin รองรับ search/filter/sort, bulk delete, orphan-case cleanup, และ merge case
- ชุดทดสอบปัจจุบันยืนยันแล้ว `145 passed`

---

## บทที่ 1

### 1.2 วัตถุประสงค์

❌ **ข้อความเดิม (ข้อ 1):**
> พัฒนา pipeline สำหรับรับไฟล์เสียง (WAV/MP3), ลด noise, ถอดเสียงด้วย Whisper, แยกผู้พูดด้วย Pyannote และส่งผลลัพธ์ให้ LLM วิเคราะห์ (sentiment, topic, summary, keywords, brand/platform mentions, anomaly detection) แล้วเก็บในฐานข้อมูล

✅ **แก้เป็น:**
> พัฒนา AI Pipeline แบบ 4 ขั้นตอนสำหรับรับไฟล์เสียง (.wav/.mp3) ประกอบด้วย การลดเสียงรบกวน (Noise Reduction) ด้วย noisereduce, การถอดเสียงเป็นข้อความ (Speech-to-Text) ด้วยโมเดล Whisper (biodatlab/distill-whisper-th-large-v3) ผ่าน HuggingFace Transformers, การแยกผู้พูด (Speaker Diarization) ด้วย Pyannote speaker-diarization-3.1, การแก้ไขบทถอดเสียงและระบุ Speaker ด้วย LLM พร้อม Heuristic Rule-based Correction และการวิเคราะห์เชิงลึกด้วย LLM (Typhoon2 8B) แบบ **4 Prompt Calls แยกอิสระ** ได้แก่ (1) Extraction — สรุป, หัวข้อ, คำสำคัญ, แบรนด์, แพลตฟอร์ม (2) Sentiment Analysis — วิเคราะห์อารมณ์ลูกค้าแบบ Chain-of-Thought (3) Agent QA — ประเมินพนักงานแบบ Checklist-based Scoring (4) Anomaly Detection — ตรวจจับความผิดปกติ โดยผลลัพธ์ทั้งหมดจัดเก็บในฐานข้อมูล SQLite

**เหตุผล:** ระบบปัจจุบันแบ่ง LLM analysis เป็น 4 calls แยก ไม่ใช่ single call และใช้โมเดล `biodatlab/distill-whisper-th-large-v3` (ไม่ใช่ `biodatlab/whisper-th-large-v3-combined`)

---

### 1.3 ขอบเขตของโครงการ

❌ **ข้อความเดิม (ผู้ดูแลระบบ → หน้าที่):**
> ควบคุมกระบวนการทำงานของ AI Pipeline ซึ่งประกอบด้วยการแปลงเสียงเป็นข้อความ (Speech-to-Text) ด้วย Whisper การแยกผู้พูด (Speaker Diarization) ด้วย Pyannote และการวิเคราะห์ข้อมูลด้วยโมเดลภาษา Typhoon

✅ **แก้เป็น:**
> ควบคุมกระบวนการทำงานของ AI Pipeline ซึ่งประกอบด้วยการลดเสียงรบกวน (Noise Reduction) การแปลงเสียงเป็นข้อความ (Speech-to-Text) ด้วย Whisper (biodatlab/distill-whisper-th-large-v3) การแยกผู้พูด (Speaker Diarization) ด้วย Pyannote speaker-diarization-3.1 การแก้ไขบทถอดเสียงด้วย LLM (Transcript Cleanup & Speaker Correction) การปรับแก้ Domain-specific Text ด้วย Regex-based Normalization และการวิเคราะห์เชิงลึก 4 ด้านด้วยโมเดลภาษา Typhoon2 8B ผ่าน Ollama

---

❌ **ข้อความเดิม (ผู้ใช้งาน → สิทธิ์):**
> สามารถดูผลการวิเคราะห์ เช่น สรุปบทสนทนา (Summary), อารมณ์ของลูกค้า (Sentiment), และหัวข้อการติดต่อ (Intent)

✅ **แก้เป็น:**
> สามารถดูผลการวิเคราะห์ เช่น สรุปบทสนทนา (Summary), อารมณ์ของลูกค้าพร้อมเหตุผล (Sentiment & Sentiment Reason), หัวข้อการติดต่อ (Topic/Intent), คำสำคัญ (Keywords), แบรนด์ที่พูดถึง (Brand Mentions), แพลตฟอร์ม/ช่องทาง (Platform Mentions), คะแนนประเมินพนักงาน (Politeness, Problem Solving, Overall Score) พร้อมหลักฐานคะแนน, สิ่งที่ต้องดำเนินการต่อ (Next Action), จุดแข็ง/จุดปรับปรุง (Strengths/Improvements), และผลตรวจจับความผิดปกติ (Anomaly Detection) พร้อมระดับความรุนแรง (Severity)

---

### 1.4 ซอฟต์แวร์และฮาร์ดแวร์ที่ใช้พัฒนา

❌ **ข้อความเดิม (โมเดล STT):**
> โมเดล Speech-to-Text ได้แก่ Whisper (biodatlab/whisper-th-large-v3-combined) และ faster-whisper ใช้สำหรับแปลงข้อมูลเสียงเป็นข้อความ โดยรองรับภาษาไทยและเพิ่มประสิทธิภาพในการประมวลผล

✅ **แก้เป็น:**
> โมเดล Speech-to-Text ได้แก่ Whisper (biodatlab/distill-whisper-th-large-v3) ซึ่งเป็นโมเดลที่ถูก Distill (กลั่นกรองความรู้) จากโมเดลขนาดใหญ่เพื่อให้มีความแม่นยำสูงสำหรับภาษาไทยโดยเฉพาะ โดยรันผ่าน HuggingFace Transformers Pipeline บนอุปกรณ์ CUDA (GPU) ในรูปแบบ float16 ระบบรองรับ Backend 2 แบบ ได้แก่ HuggingFace Transformers สำหรับโมเดล Fine-tuned ภาษาไทย และ faster-whisper สำหรับโมเดลมาตรฐาน (เช่น large-v3) โดยให้ผลลัพธ์เป็น Word-level Timestamps ระบบยังมีกลไก Initial Prompt ที่ใส่ศัพท์เฉพาะทาง (Domain Hotwords) เช่น Restonic, Omazz, หาดใหญ่, อุทกภัย, Trade-in เพื่อเพิ่มความแม่นยำในการถอดเสียงศัพท์โดเมน

---

❌ **ข้อความเดิม (โมเดลภาษา):**
> โมเดลภาษาขนาดใหญ่ Typhoon2 ขนาด 8B Instruct ใช้สำหรับวิเคราะห์ข้อมูลเชิงลึก เช่น การวิเคราะห์อารมณ์ (Sentiment Analysis), การจำแนกเจตนา (Intent Detection), และการสรุปเนื้อหาการสนทนา (Summary)

✅ **แก้เป็น:**
> โมเดลภาษาขนาดใหญ่ Typhoon2 ขนาด 8B Instruct (scb10x/llama3.1-typhoon2-8b-instruct) รันผ่าน Ollama ที่ http://localhost:11434 ใช้สำหรับงาน 6 อย่าง ได้แก่ (1) ตรวจแก้บทถอดเสียง (Transcript Cleanup) ด้วย Domain-specific Prompt (2) แก้ไขการระบุผู้พูด (Speaker Correction) ด้วย Few-Shot Prompting (3) สกัดข้อมูล — สรุปบทสนทนา, หัวข้อ, คำสำคัญ, แบรนด์, แพลตฟอร์ม (4) วิเคราะห์อารมณ์ลูกค้า (Sentiment Analysis) แบบ Chain-of-Thought โดยกำหนดให้ neutral เป็นค่า default (5) ประเมินคุณภาพพนักงาน (Agent QA) แบบ Checklist-based Scoring 5 ข้อต่อหมวด (6) ตรวจจับความผิดปกติ (Anomaly Detection) พร้อมระดับความรุนแรง

---

**เพิ่มเติม (ซอฟต์แวร์ที่ขาด):**

> - **noisereduce** สำหรับลดเสียงรบกวน (Noise Reduction) ด้วยค่า prop_decrease=0.35
> - **scipy** สำหรับ Resampling สัญญาณเสียงเป็น 16 kHz Mono
> - **Plotly** สำหรับสร้างกราฟแบบ Interactive บน Dashboard (Pie Chart, Bar Chart, Gauge Chart)
> - **Pandas** สำหรับจัดการข้อมูลเชิงตาราง

---

### 1.6.3 ระบบวิเคราะห์บทสนทนาด้วยปัญญาประดิษฐ์

❌ **ข้อความเดิม:**
> ระบบนำบทสนทนาที่ผ่านการแปลงและแยกผู้พูดเข้าสู่การวิเคราะห์ด้วยโมเดลภาษาขนาดใหญ่ Typhoon 8B ที่รันผ่าน Ollama ภายในเครื่อง โดยใช้เทคนิค Prompt Engineering เพื่อวิเคราะห์ข้อมูลเชิงลึก ได้แก่
> การ mapping ผู้พูดเป็น Agent และ Customer
> การวิเคราะห์อารมณ์ของลูกค้า (Sentiment Analysis)
> การจำแนกเจตนา (Intent Detection)
> การสรุปบทสนทนา (Summary)
> การประเมินคุณภาพพนักงาน (Agent Performance)
> การสกัดคำสำคัญ (Keywords)
> การตรวจจับความผิดปกติ (Anomaly Detection)
> ผลลัพธ์จะอยู่ในรูปแบบ JSON เพื่อให้ง่ายต่อการจัดเก็บและแสดงผล

✅ **แก้เป็น:**
> ระบบนำบทสนทนาที่ผ่านการแปลง แยกผู้พูด และตรวจแก้แล้วเข้าสู่การวิเคราะห์ด้วยโมเดลภาษาขนาดใหญ่ Typhoon2 8B Instruct ที่รันผ่าน Ollama ภายในเครื่อง โดยใช้เทคนิค Prompt Engineering แบ่งการวิเคราะห์เป็น **4 Prompt Calls แยกอิสระ** เพื่อให้แต่ละงานมีความแม่นยำสูงสุด ได้แก่
>
> **Call 1: Extraction** — สกัดข้อมูลจากบทสนทนา ประกอบด้วย สรุปบทสนทนา (Summary), หัวข้อการติดต่อ (Topic) จาก 9 หมวดที่กำหนด, คำสำคัญ (Keywords), แบรนด์ที่พูดถึง (Brand Mentions) เช่น Omazz, Restonic, Lotus และแพลตฟอร์ม/ช่องทาง (Platform Mentions) เช่น Shopee, Lazada, LINE
>
> **Call 2: Sentiment Analysis** — วิเคราะห์อารมณ์ลูกค้าด้วยเทคนิค Chain-of-Thought (CoT) โดยขั้นตอนที่ 1 สกัดประโยคที่แสดงอารมณ์จากคำพูดของลูกค้า ขั้นตอนที่ 2 ตัดสินจากหลักฐาน โดยกำหนดให้ neutral เป็นค่า default เพื่อป้องกัน Bias จากมารยาทไทย (เช่น "ขอบคุณค่ะ" ตอนปิดสาย ไม่นับเป็น positive) ผลลัพธ์เป็น Positive/Neutral/Negative พร้อมเหตุผล (Sentiment Reason)
>
> **Call 3: Agent QA** — ประเมินคุณภาพพนักงานด้วยเกณฑ์ Checklist-based Scoring แบ่งเป็น 2 หมวด หมวดละ 5 ข้อ ได้แก่ (A) Politeness — ทักทาย, สุภาพ, empathy, ขอโทษ, ปิดสาย (คะแนน 1-5) (B) Problem Solving — เข้าใจปัญหา, ตอบตรงประเด็น, ข้อมูลครบ, แนะนำขั้นตอน, proactive advice (คะแนน 1-5) (C) Overall Score = A + B (2-10) โดยต้องมีหลักฐานจากคำพูด Agent ใน transcript สำหรับคะแนนย่อย และ backend จะ clamp คะแนนพร้อมคำนวณ overall_score ซ้ำเพื่อความถูกต้อง นอกจากนี้ยังระบุ Next Action, Strengths และ Improvements โดยใช้ temperature=0.3 เพื่อให้คะแนนมีความหลากหลายระหว่างสายที่ต่างกัน
>
> **Call 4: Anomaly Detection** — ตรวจจับความผิดปกติ 4 ประเภท ได้แก่ ลูกค้าไม่พอใจรุนแรง, พนักงานพฤติกรรมไม่เหมาะสม, ปัญหาร้ายแรง (สุขภาพ/ความปลอดภัย) และสายมีปัญหาทางเทคนิค ผลลัพธ์ระบุ anomaly_detected (true/false), anomaly_reason และ anomaly_severity (low/medium/high)
>
> ผลลัพธ์ทั้ง 4 Calls จะถูก merge เป็น JSON Structure เดียวเพื่อจัดเก็บในฐานข้อมูล

---

### 1.6.5 ระบบแสดงผลข้อมูล (Dashboard)

❌ **ข้อความเดิม:**
> ระบบพัฒนา Web Application ด้วย Streamlit สำหรับแสดงผลข้อมูลเชิงวิเคราะห์ โดยใช้ Plotly ในการสร้างกราฟแบบ Interactive เช่น กราฟ Sentiment, กราฟ Intent, ตารางสรุปบทสนทนา

✅ **แก้เป็น:**
> ระบบพัฒนา Web Application ด้วย Streamlit สำหรับแสดงผลข้อมูลเชิงวิเคราะห์ โดยใช้ Plotly ในการสร้างกราฟแบบ Interactive ประกอบด้วย
> - **Sentiment Distribution** — กราฟวงกลม (Pie Chart) แสดงสัดส่วน Positive/Neutral/Negative
> - **Topic/Intent Distribution** — กราฟแท่งแนวนอน (Bar Chart) แสดงจำนวนสายแยกตามหัวข้อ 9 หมวด โดยกรอง empty topics ออก
> - **Issue Keywords** — แสดงคำสำคัญที่พบบ่อยจากทุกสาย
> - **Brand Mentions** — แสดงแบรนด์ที่ลูกค้าพูดถึง (Omazz, Restonic, Lotus ฯลฯ)
> - **Platform/Channel Mentions** — แสดงช่องทางที่พูดถึง (Shopee, Lazada, LINE ฯลฯ)
> - **Agent Performance** — แสดงคะแนน Politeness (1-5), Problem Solving (1-5), Overall Score (2-10), หลักฐานคะแนน QA, Next Action และผู้รับผิดชอบ
> - **Anomaly Detection** — แสดงสัดส่วนสายปกติ/ผิดปกติ พร้อม Severity Badge (Low/Medium/High)
> - **Call Summaries** — ตารางแสดงข้อมูลรายสาย ได้แก่ Filename, Sentiment, Topic, Keywords, Anomaly, Summary และวันที่สร้าง
>
> ผู้ใช้งานสามารถกรองข้อมูลตามช่วงเวลาได้

---

## บทที่ 2

### 2.3 การแปลงเสียงเป็นข้อความ (Speech-to-Text)

❌ **ข้อความเดิม:**
> ในระบบ SmartVoice มีการออกแบบให้รองรับการทำงานของ STT ได้หลายรูปแบบ โดยใช้โมเดล Whisper เป็นแกนหลัก โดยหากใช้โมเดลมาตรฐาน (เช่น large-v3) ระบบจะเลือก Faster-Whisper อัตโนมัติ หากใช้โมเดล fine-tuned บน HuggingFace (เช่น biodatlab/whisper-th-large-v3-combined) จะใช้ HuggingFace Transformers pipeline

✅ **แก้เป็น:**
> ในระบบ SmartVoice มีการออกแบบให้รองรับการทำงานของ STT ได้ 2 Backend โดยใช้โมเดล Whisper เป็นแกนหลัก ระบบจะเลือก Backend อัตโนมัติตามประเภทโมเดล ได้แก่ (1) **HuggingFace Transformers Pipeline** สำหรับโมเดลที่ถูก Fine-tune สำหรับภาษาไทย เช่น biodatlab/distill-whisper-th-large-v3 ซึ่งเป็นโมเดลหลักที่ใช้ในระบบ รันบน CUDA (GPU) ด้วย float16 เพื่อประสิทธิภาพสูงสุด (2) **faster-whisper** (CTranslate2) สำหรับโมเดลมาตรฐาน เช่น large-v3, large-v3-turbo ที่ต้องการความเร็วในการประมวลผล
>
> ระบบมีกลไก Initial Prompt (Context Prompt) ที่ประกอบด้วยศัพท์เฉพาะทาง (Domain Hotwords) จำนวนมาก เช่น Restonic, Omazz, กลุ่มบริษัทที่นอนโลตัส, หาดใหญ่, สุราษฎร์ธานี, อุทกภัย, เชื้อรา, Trade-in, โปรราคาพิเศษ เพื่อช่วยให้ Whisper ถอดเสียงศัพท์โดเมนได้ถูกต้องและลดการเกิด Hallucination
>
> นอกจากนี้ ระบบยังมีขั้นตอน Post-processing หลังถอดเสียง ได้แก่ **Domain Text Normalization** ซึ่งเป็น Regex-based Pattern Matching จำนวนกว่า 40 กฎ สำหรับแก้ไขคำที่ Whisper ถอดผิดเป็นประจำ เช่น "ขนาดใหญ่" → "หาดใหญ่", "อุปกรณ์ภัย" → "อุทกภัย", "เซลลา" → "เชื้อรา", "ผูกสุขลักษณะ" → "ถูกสุขลักษณะ" และ **LLM-based Transcript Cleanup** ที่ใช้ Typhoon2 ตรวจแก้บทถอดเสียงอีกรอบโดยอ้างอิงบริบทโดเมน

---

### 2.4 การระบุผู้พูด (Speaker Diarization)

❌ **ข้อความเดิม:**
> ผลลัพธ์จากขั้นตอนนี้จะถูกนำมาเชื่อมกับข้อมูลข้อความ (Transcript) เพื่อสร้างโครงสร้างบทสนทนาแบบ "Speaker-aware" ซึ่งเป็นพื้นฐานสำคัญของการวิเคราะห์ เช่น การแยก Customer และ Agent ในขั้นตอนถัดไป

✅ **แก้เป็น:**
> ผลลัพธ์จากขั้นตอน Diarization จะถูกนำมาเชื่อมกับข้อมูลข้อความ (Transcript) ในระดับคำ (Word-level) เพื่อสร้างโครงสร้างบทสนทนาแบบ "Speaker-aware" จากนั้นระบบจะดำเนินการปรับแต่งเพิ่มเติมหลายขั้นตอน ได้แก่
> - **Merge Gap ≤ 0.2 วินาที** — รวม Segment ของผู้พูดคนเดียวกันที่อยู่ใกล้กัน
> - **Stabilize Short Segments** — ดูดซับ Segment สั้น (< 15 ตัวอักษร และ < 2 วินาที) เข้ากับ Segment ก่อนหน้า ยกเว้นคำตอบสั้นของ Agent เช่น "ใช่ครับ" "ถูกต้องค่ะ"
> - **Split Mixed Turns** — แยก Segment ที่มีคำพูดของทั้ง Agent และ Customer ปนกัน โดยใช้ Heuristic Rule-based Detection กว่า 10 กฎ เช่น แยกคำถามลูกค้า + คำตอบสั้นพนักงาน, แยกคำขอบคุณลูกค้า + คำปิดสายพนักงาน
> - **LLM-based Speaker Correction** — ส่งบทสนทนาไปให้ Typhoon2 ตรวจสอบและแก้ไข Speaker Label ด้วย Few-Shot Prompting พร้อมตัวอย่างกรณีที่มักผิด
> - **Heuristic Fallback** — ใช้ Agent Marker Phrases (เช่น "คุณลูกค้า", "ต้องขออภัย", "ทางเราจะ") เป็น Fallback กรณี LLM ไม่สามารถระบุได้
> - **Rule-based Enforcement** — บังคับให้ Segment ที่มี Agent Marker ต้องเป็น Agent
>
> กระบวนการนี้ทำให้การระบุ Agent/Customer มีความแม่นยำสูงขึ้นอย่างมาก เป็นพื้นฐานสำคัญของการวิเคราะห์เชิงลึกในขั้นตอนถัดไป

---

### 2.5 การประมวลผลภาษาธรรมชาติ (NLP)

❌ **ข้อความเดิม:**
> การทำงานของ NLP ในระบบครอบคลุมหลายด้าน ได้แก่
> การวิเคราะห์อารมณ์ (Sentiment Analysis)
> การจำแนกเจตนา (Intent Detection)
> การสรุปบทสนทนา (Summarization)
> การประเมินคุณภาพพนักงาน (Agent Performance Evaluation)
> การตรวจจับความผิดปกติ (Anomaly Detection)
> การสกัด Brand/Platform mentions

✅ **แก้เป็น:**
> การทำงานของ NLP ในระบบแบ่งเป็น 2 ระดับ ได้แก่
>
> **ระดับที่ 1: Pre-analysis (ก่อนวิเคราะห์)**
> - **Transcript Cleanup** — ตรวจแก้คำที่ถอดผิดจาก STT ด้วย Domain-specific Prompt ที่มีรายการศัพท์เฉพาะทางและตัวอย่าง Common STT Confusions
> - **Speaker Correction** — แก้ไข Speaker Label ที่ Diarization ระบุผิด ด้วย Few-Shot Prompting พร้อมรองรับ Segment ที่มีคำพูดของ 2 คนปนกัน (Mixed Turns) โดยใช้ JSON Array Format ที่รองรับทั้ง single speaker และ multi-part splits
>
> **ระดับที่ 2: Analysis (วิเคราะห์เชิงลึก) — แบ่งเป็น 4 Prompt Calls แยกอิสระ**
> - **Call 1: Extraction** — สรุปบทสนทนา (Summary), จำแนกหัวข้อ (Topic/Intent) จาก 9 หมวดที่กำหนด, สกัดคำสำคัญ (Keywords), ระบุแบรนด์ (Brand Mentions) และแพลตฟอร์ม (Platform Mentions)
> - **Call 2: Sentiment Analysis** — วิเคราะห์อารมณ์ลูกค้าด้วยเทคนิค Chain-of-Thought (CoT) พร้อมเหตุผลประกอบ
> - **Call 3: Agent QA** — ประเมินพนักงานด้วย Checklist-based Scoring (Politeness 1-5, Problem Solving 1-5, Overall 2-10) พร้อม evidence, Next Action, Strengths, Improvements
> - **Call 4: Anomaly Detection** — ตรวจจับความผิดปกติ 4 ประเภท พร้อมระดับ Severity (Low/Medium/High)
>
> การแบ่งเป็น 4 Calls แยกอิสระช่วยให้แต่ละงานได้ Prompt ที่เฉพาะเจาะจง ลดปัญหา Prompt ยาวเกินไปที่ทำให้ LLM ขนาด 8B ให้ผลลัพธ์ไม่ดี

---

### 2.6 การวิเคราะห์อารมณ์ (Sentiment Analysis)

❌ **ข้อความเดิม:**
> ระบบ SmartVoice ใช้โมเดล LLM (Typhoon) วิเคราะห์เฉพาะข้อความของฝั่งลูกค้า โดยผลลัพธ์จะถูกจัดประเภทเป็น Positive, Neutral และ Negative ซึ่งสามารถนำไปใช้วิเคราะห์คุณภาพการให้บริการได้

✅ **แก้เป็น:**
> ระบบ SmartVoice ใช้โมเดล LLM (Typhoon2 8B) วิเคราะห์อารมณ์ลูกค้าด้วยเทคนิค **Chain-of-Thought (CoT)** ซึ่งเป็น Prompt แบบ 2 ขั้นตอน ดังนี้
> - **ขั้นตอนที่ 1**: สกัดประโยคที่แสดงอารมณ์จริงของลูกค้า โดยข้ามคำทักทาย/ปิดสายปกติ เช่น "สวัสดีค่ะ", "ขอบคุณค่ะ", "ได้ค่ะ" ซึ่งเป็นมารยาทไทยไม่ใช่สัญญาณอารมณ์
> - **ขั้นตอนที่ 2**: ตัดสินจากหลักฐานในขั้นตอนที่ 1 — หากพบคำชื่นชมเจาะจง → Positive, หากพบคำไม่พอใจ → Negative, หากไม่พบอารมณ์ชัดเจน → Neutral (ค่า default)
>
> การออกแบบ Prompt ลักษณะนี้ช่วยแก้ปัญหา **All-Positive Bias** ที่พบในเวอร์ชันแรก ซึ่ง LLM มักตีความ "ขอบคุณค่ะ" ตอนปิดสายว่าเป็น Positive ทุกสาย
>
> ผลลัพธ์ประกอบด้วย sentiment (Positive/Neutral/Negative) และ sentiment_reason (เหตุผลพร้อมยกคำพูดลูกค้าที่เป็นหลักฐาน)

---

### 2.7 การจัดเก็บข้อมูล (Data Management)

❌ **ข้อความเดิม (ข้อมูลที่จัดเก็บ):**
> Transcript, Sentiment, Intent, Summary, Metadata ของการโทร

✅ **แก้เป็น:**
> ข้อมูลที่จัดเก็บในตาราง calls ประกอบด้วย filename, file_hash (SHA-256), file_path, transcript, summary, sentiment, sentiment_reason, topic, speaker_mapping, agent_performance (JSON พร้อมคะแนน QA และ evidence), keywords (JSON Array), brand_mentions (JSON Array), platform_mentions (JSON Array), anomaly_detected (Boolean), anomaly_reason, anomaly_severity, customer_phone, case_id, uploaded_by, uploaded_by_role, status (uploaded/processing/done/error), error_msg, processing_step, created_at และ updated_at

---

### 2.9 สรุปเครื่องมือและเทคโนโลยีที่ใช้

❌ **ข้อความเดิม:**
> ระบบ biodatlab/whisper-th-large-v3-combined ถูกออกแบบให้ทำงานภายใต้แนวคิด Local AI Processing Architecture

✅ **แก้เป็น:**
> ระบบ SmartVoice ถูกออกแบบให้ทำงานภายใต้แนวคิด Local AI Processing Architecture

---

❌ **ข้อความเดิม (Whisper):**
> Whisper (Speech-to-Text Model) ใช้สำหรับแปลงเสียงเป็นข้อความ โดยรองรับการทำงานผ่าน HuggingFace Transformers และ Faster-Whisper ซึ่งให้ผลลัพธ์ที่มีความแม่นยำสูง

✅ **แก้เป็น:**
> **Whisper — biodatlab/distill-whisper-th-large-v3** (Speech-to-Text Model) ใช้สำหรับแปลงเสียงเป็นข้อความภาษาไทย โดยเป็นโมเดล Distilled ที่ถูก Fine-tune สำหรับภาษาไทยโดยเฉพาะ รันผ่าน HuggingFace Transformers Pipeline บน CUDA (GPU) ด้วย float16 ระบบรองรับ faster-whisper เป็น Backend สำรองสำหรับโมเดลมาตรฐาน ทั้งสอง Backend ให้ผลลัพธ์เป็น Word-level Timestamps พร้อมกลไก Domain Hotwords Initial Prompt และ Hallucination Filter

---

❌ **ข้อความเดิม (Typhoon):**
> Typhoon (Large Language Model ผ่าน Ollama) ใช้สำหรับวิเคราะห์ข้อมูลข้อความ เช่น การวิเคราะห์อารมณ์ (Sentiment), การจำแนกเจตนา (Intent), การสกัดคำสำคัญ และการสรุปบทสนทนา โดยทำงานภายในเครื่อง

✅ **แก้เป็น:**
> **Typhoon2 8B Instruct** (scb10x/llama3.1-typhoon2-8b-instruct ผ่าน Ollama) ใช้สำหรับงาน NLP ทั้งหมดในระบบ ได้แก่ ตรวจแก้บทถอดเสียง (Transcript Cleanup), แก้ไข Speaker Label (Speaker Correction) ด้วย Few-Shot Prompting, สกัดข้อมูล (Summary, Topic, Keywords, Brand Mentions, Platform Mentions), วิเคราะห์อารมณ์ (Sentiment Analysis) ด้วย Chain-of-Thought, ประเมินพนักงาน (Agent QA) ด้วย Checklist-based Scoring และตรวจจับความผิดปกติ (Anomaly Detection) โดยทำงานภายในเครื่องทั้งหมด ไม่ส่งข้อมูลออกภายนอก

---

**เพิ่มท้ายรายการเครื่องมือ:**

> - **noisereduce** สำหรับ Noise Reduction (prop_decrease=0.35)
> - **scipy** สำหรับ Audio Resampling (16 kHz Mono)

---

## บทที่ 3

### Conceptual Framework — Process

❌ **ข้อความเดิม:**
> ขั้นตอนแรกคือการแปลงเสียงเป็นข้อความ (Speech-to-Text) ด้วยโมเดล Whisper (biodatlab/whisper-th-large-v3-combined หรือ faster-whisper large-v3)

✅ **แก้เป็น:**
> ขั้นตอนแรกคือการเตรียมเสียง (Audio Preprocessing) ด้วยการแปลง Sampling Rate เป็น 16 kHz Mono และลดเสียงรบกวน (Noise Reduction) จากนั้นแปลงเสียงเป็นข้อความ (Speech-to-Text) ด้วยโมเดล Whisper (biodatlab/distill-whisper-th-large-v3 ผ่าน HuggingFace Transformers หรือ faster-whisper สำหรับโมเดลมาตรฐาน)

---

❌ **ข้อความเดิม:**
> ขั้นตอนที่สองคือการวิเคราะห์ภาษาธรรมชาติ (Natural Language Processing) ด้วยโมเดลภาษาขนาดใหญ่ Typhoon2 (scb10x/llama3.1-typhoon2-8b-instruct) ที่รันภายในเครื่องผ่าน Ollama เพื่อวิเคราะห์อารมณ์ (Sentiment Analysis) ระบุเจตนาการติดต่อ (Intent/Topic Detection) ประเมินคุณภาพการให้บริการของพนักงาน (Agent Performance) สกัดคำสำคัญ (Keywords) และสรุปบทสนทนา (Summary)

✅ **แก้เป็น:**
> ขั้นตอนที่สองคือการประมวลผลภาษาธรรมชาติ (NLP) ด้วยโมเดล Typhoon2 8B Instruct ผ่าน Ollama แบ่งเป็น Pre-analysis (ตรวจแก้บทถอดเสียงและแก้ไข Speaker Label) และ Analysis (วิเคราะห์เชิงลึก 4 Prompt Calls แยกอิสระ ได้แก่ Extraction, Sentiment Analysis แบบ Chain-of-Thought, Agent QA แบบ Checklist-based Scoring และ Anomaly Detection)

---

### Software Architecture — 3.1 โครงสร้าง Package หลัก

❌ **ข้อความเดิม (ollama_client.py):**
> โมดูล ollama_client.py รับผิดชอบการสื่อสารกับ Ollama Server โดยส่ง Prompt ที่สร้างจาก prompts.py ไปยัง Typhoon2 และรับผลลัพธ์กลับมาในรูปแบบ JSON

✅ **แก้เป็น:**
> โมดูล ollama_client.py รับผิดชอบการสื่อสารกับ Ollama Server โดยมีฟังก์ชันหลัก 7 ฟังก์ชัน ได้แก่ (1) chat() — ส่ง Prompt ไปยัง Typhoon2 รองรับ configurable temperature (2) cleanup_transcript() — ตรวจแก้บทถอดเสียง (3) correct_speakers() — แก้ Speaker Label ด้วย Few-Shot Prompting รองรับ Mixed Turn Splitting (4) extract_summary_and_topics() — Call 1 สกัด Summary/Topic/Keywords/Brands/Platforms (5) analyze_sentiment() — Call 2 วิเคราะห์ Sentiment แบบ CoT (6) evaluate_agent_qa() — Call 3 ประเมินพนักงานด้วย Checklist (temperature=0.3) (7) detect_anomaly() — Call 4 ตรวจจับความผิดปกติ โดยฟังก์ชัน analyze_transcript() จะเรียก Call 1-4 แล้ว merge ผลลัพธ์เป็น dict เดียว

---

❌ **ข้อความเดิม (prompts.py):**
> โมดูล prompts.py เก็บ Prompt Template สำหรับการวิเคราะห์บทสนทนา (Analysis Prompt) และการแก้ไขการระบุผู้พูด (Speaker Correction Prompt) โดยใช้เทคนิค Few-Shot Prompting ผ่าน Typhoon2

✅ **แก้เป็น:**
> โมดูล prompts.py เก็บ Prompt Template 6 ชุด ได้แก่ (1) EXTRACTION — สกัด Summary, Topic (9 หมวด), Keywords, Brand Mentions, Platform Mentions (2) SENTIMENT — วิเคราะห์อารมณ์แบบ Chain-of-Thought 2 ขั้นตอน โดยกำหนด neutral เป็น default (3) AGENT_QA — ประเมินพนักงานแบบ Checklist 5 ข้อ 2 หมวด (Politeness, Problem Solving) (4) ANOMALY — ตรวจจับความผิดปกติ 4 ประเภทพร้อม Severity (5) SPEAKER_CORRECTION — แก้ Speaker Label ด้วย Few-Shot Examples 7 ตัวอย่าง รองรับ Mixed Turn Splitting ด้วย JSON "parts" format (6) TRANSCRIPT_CLEANUP — ตรวจแก้คำถอดผิดด้วย Domain-specific Guidance โดยทุก Prompt ใช้ Python `.format()` สำหรับแทรกบทสนทนา

---

❌ **ข้อความเดิม (pipeline.py):**
> โมดูล pipeline.py เป็นส่วนประสานงานกระบวนการทำงานทั้งหมด (Orchestrator) โดยเรียกใช้ STT Module เพื่อถอดเสียงและระบุผู้พูด จากนั้นผ่านกระบวนการปรับแต่งผลลัพธ์ด้วยการรวม segment ที่อยู่ใกล้กัน (Merge Gap ≤ 0.2 วินาที) และกรอง segment ที่สั้นเกินไปออก (น้อยกว่า 15 ตัวอักษร และสั้นกว่า 2 วินาที) ก่อนส่งบทสนทนาไปวิเคราะห์ด้วย LLM

✅ **แก้เป็น:**
> โมดูล pipeline.py เป็นส่วนประสานงานกระบวนการทำงานทั้งหมด (Orchestrator) ประกอบด้วย 4 ขั้นตอนหลัก:
>
> **[1/4] ถอดเสียงและแยกผู้พูด** — เรียก STT Module เพื่อถอดเสียงพร้อม Word-level Timestamps และ Diarization จากนั้นปรับแต่งผลลัพธ์ด้วย Merge Gap ≤ 0.2 วินาที, Stabilize Short Segments (< 15 ตัวอักษร, < 2 วินาที โดยยกเว้นคำตอบสั้นของ Agent), Domain Text Normalization (Regex กว่า 40 กฎ) และ Heuristic Turn Splitting กว่า 10 กฎ (Split Opening Mixed Turns, Split Question+Answer, Split Closing Turns, Split Embedded Customer Reactions ฯลฯ)
>
> **[2/4] ตรวจแก้บทถอดเสียงด้วย AI** — ส่งบทสนทนาไปให้ Typhoon2 ตรวจแก้คำถอดผิด จากนั้นรัน Turn Splitting Heuristics อีกรอบ
>
> **[3/4] แก้ Speaker Turn ด้วย AI** — ส่งบทสนทนาไปให้ Typhoon2 แก้ Speaker Label ด้วย Few-Shot Prompting จากนั้นรัน Turn Splitting + Rule Enforcement + Transcript Cleanup อีกรอบ
>
> **[4/4] วิเคราะห์บทสนทนาด้วย AI** — เรียก analyze_transcript() ซึ่งรัน 4 Prompt Calls แยกอิสระ (Extraction, Sentiment, Agent QA, Anomaly) จากนั้น Apply LLM Speaker Mapping พร้อม Heuristic Fallback และ Rule-based Agent Marker Correction
>
> ทุกขั้นตอนมีการอัปเดต processing_step ให้ผู้ใช้ติดตามความก้าวหน้าผ่านหน้า Admin

---

### 3.2 Sub-package STT (smartvoice/stt/)

❌ **ข้อความเดิม (transcribe.py):**
> โมดูล transcribe.py รองรับ 2 Backend ได้แก่ HuggingFace Transformers Pipeline สำหรับโมเดล biodatlab/whisper-th-large-v3-combined ที่ถูก Fine-tune สำหรับภาษาไทยโดยเฉพาะ

✅ **แก้เป็น:**
> โมดูล transcribe.py รองรับ 2 Backend ได้แก่ HuggingFace Transformers Pipeline สำหรับโมเดล biodatlab/distill-whisper-th-large-v3 ที่ถูก Distill และ Fine-tune สำหรับภาษาไทยโดยเฉพาะ โดยมีกลไก Chunked Generation (ตัดเสียงเป็นช่วง ~15 วินาที แล้วประมวลผลแยก) เพื่อให้ได้ Timestamp ที่แม่นยำ มีกลไก Pseudo-word Splitting สำหรับแยกข้อความภาษาไทยเป็นหน่วยคำ (เนื่องจากภาษาไทยไม่มีช่องว่างระหว่างคำ) และมี Hallucination Filter สำหรับตรวจจับและกรองข้อความที่ Whisper สร้างขึ้นซ้ำๆ

---

### การออกแบบฐานข้อมูล (Database Design)

❌ **ข้อความเดิม (ตาราง calls):**
> ตาราง calls เป็นหัวใจของระบบ จัดเก็บข้อมูลการโทรทั้งหมด ได้แก่ ... ผลวิเคราะห์อารมณ์ (sentiment) หัวข้อการติดต่อ (topic) ผลประเมินพนักงานในรูปแบบ JSON (agent_performance) คำสำคัญ (keywords) แบรนด์ที่พูดถึง (brand_mentions) แพลตฟอร์มที่กล่าวถึง (platform_mentions) และข้อมูลความผิดปกติ (anomaly_detected, anomaly_reason) พร้อมสถานะการประมวลผล (status) ที่มีค่าได้แก่ uploaded, processing, done และ error

✅ **แก้เป็น:**
> ตาราง calls เป็นหัวใจของระบบ จัดเก็บข้อมูลการโทรทั้งหมด ได้แก่ ชื่อไฟล์ (filename), ค่า SHA-256 Hash สำหรับป้องกันการบันทึกซ้ำ (file_hash UNIQUE), ที่อยู่ไฟล์เสียง (file_path), บทสนทนาที่ถอดเสียงแล้ว (transcript), สรุปบทสนทนา (summary), ผลวิเคราะห์อารมณ์ (sentiment) พร้อมเหตุผล (sentiment_reason), หัวข้อการติดต่อ (topic), การจับคู่ผู้พูด (speaker_mapping), ผลประเมินพนักงานในรูปแบบ JSON (agent_performance) ซึ่งประกอบด้วย politeness (1-5), politeness_evidence, problem_solving (1-5), problem_solving_evidence, overall_score (2-10), next_action, strengths และ improvements, คำสำคัญในรูปแบบ JSON Array (keywords), แบรนด์ที่พูดถึง (brand_mentions), แพลตฟอร์มที่กล่าวถึง (platform_mentions), ข้อมูลความผิดปกติ (anomaly_detected, anomaly_reason) พร้อมระดับความรุนแรง (anomaly_severity เป็น low/medium/high), ขั้นตอนที่กำลังประมวลผล (processing_step), สถานะ (status ได้แก่ uploaded/processing/done/error), ข้อความ error (error_msg) และ timestamps (created_at, updated_at)
>
> ระบบมีกลไก Auto Migration ที่ตรวจสอบ Column ที่มีอยู่และเพิ่ม Column ใหม่อัตโนมัติ เพื่อรองรับการอัปเกรด Schema โดยไม่สูญเสียข้อมูลเดิม

---

### Workflow — ขั้นตอนที่ 3

❌ **ข้อความเดิม:**
> ขั้นตอนที่ 3: Speech-to-Text & Speaker Diarization ... ทั้งนี้เพื่อเพิ่มความแม่นยำ ระบบจะปลด Whisper Model ออกจาก GPU ก่อนรัน Diarization เพื่อป้องกันปัญหา Out-of-Memory

✅ **ถูกต้องแล้ว** — ข้อมูลนี้ถูกต้อง ระบบจริงปลด Whisper Model ออกจาก GPU ก่อนรัน Diarization

---

### Workflow — ขั้นตอนที่ 4

❌ **ข้อความเดิม:**
> ขั้นตอนที่ 4: AI Analysis (การวิเคราะห์ด้วย LLM) ระบบส่งบทสนทนาที่ได้พร้อม Prompt ไปยัง Ollama Server ที่รัน Typhoon2 บน http://localhost:11434/ โดย LLM จะระบุ Speaker Mapping (SPEAKER_XX → Agent/Customer) วิเคราะห์อารมณ์ลูกค้า ระบุหัวข้อการติดต่อ ประเมินคุณภาพพนักงาน สกัดคำสำคัญ แบรนด์ แพลตฟอร์ม และตรวจจับความผิดปกติ โดยผลลัพธ์ทั้งหมดอยู่ในรูปแบบ JSON Structure หลังจากนั้นระบบนำ Speaker Mapping จาก LLM มาแก้ไข Label ในบทสนทนา และหากการระบุผู้พูดไม่สมบูรณ์ จะใช้ Heuristic Rule-based Correction โดยตรวจสอบ Agent Marker Phrases เป็น Fallback

✅ **แก้เป็น:**
> ขั้นตอนที่ 4: AI Analysis (การวิเคราะห์ด้วย LLM) ระบบดำเนินการใน 3 ขั้นตอนย่อย ได้แก่
>
> **ขั้นตอน 4a: ตรวจแก้บทถอดเสียง (Transcript Cleanup)** — ส่งบทสนทนาไปให้ Typhoon2 ตรวจแก้คำที่ STT ถอดผิด โดยใช้ Domain-specific Prompt ที่มีรายการศัพท์เฉพาะทาง (Restonic, Omazz, หาดใหญ่, อุทกภัย ฯลฯ) และตัวอย่าง Common STT Confusions จากนั้นรัน Turn Splitting Heuristics + Domain Normalization อีกรอบ
>
> **ขั้นตอน 4b: แก้ Speaker Label (Speaker Correction)** — ส่งบทสนทนาไปให้ Typhoon2 ตรวจสอบและแก้ไข Speaker Label ด้วย Few-Shot Prompting 7 ตัวอย่าง รองรับ Mixed Turn Splitting ด้วย JSON "parts" format จากนั้นรัน Turn Splitting + Rule Enforcement + Transcript Cleanup อีกรอบ และใช้ Heuristic Fallback ด้วย Agent Marker Phrases กรณี LLM ไม่สามารถระบุได้
>
> **ขั้นตอน 4c: วิเคราะห์เชิงลึก (4 Prompt Calls)** — ส่งบทสนทนาสุดท้ายไปวิเคราะห์ด้วย 4 Prompt Calls แยกอิสระ ได้แก่ (1) Extraction — Summary, Topic, Keywords, Brands, Platforms (2) Sentiment — อารมณ์ลูกค้าแบบ CoT พร้อมเหตุผล (3) Agent QA — ประเมินพนักงานแบบ Checklist (temperature=0.3) (4) Anomaly Detection — ตรวจจับความผิดปกติพร้อม Severity
>
> ผลลัพธ์ทั้ง 4 Calls ถูก merge เป็น JSON Structure เดียวและบันทึกลงฐานข้อมูล

---

### Workflow — ขั้นตอนที่ 6

❌ **ข้อความเดิม (บางส่วน):**
> กราฟสัดส่วนอารมณ์ลูกค้า กราฟแท่งแยกตามหัวข้อการติดต่อ คะแนนประเมินพนักงาน และตารางสรุปรายสาย (Call Summary)

✅ **แก้เป็น:**
> กราฟวงกลม (Pie Chart) แสดงสัดส่วนอารมณ์ลูกค้า (Positive/Neutral/Negative), กราฟแท่งแนวนอน (Bar Chart) แสดงจำนวนสายแยกตามหัวข้อ 9 หมวด, รายการคำสำคัญที่พบบ่อย (Issue Keywords), รายการแบรนด์ที่ลูกค้าพูดถึง (Brand Mentions), รายการแพลตฟอร์ม/ช่องทาง (Platform Mentions), คะแนนประเมินพนักงาน (Politeness, Problem Solving, Overall Score) ในรูปแบบ Gauge Chart, สัดส่วนสายปกติ/ผิดปกติพร้อม Severity Badge และตารางสรุปรายสาย (Call Summary) แสดง Filename, Sentiment, Topic, Keywords, Anomaly Status, Summary และวันที่

---

## สรุปจุดแก้ไขหลัก (Quick Reference)

| หัวข้อ | ข้อมูลเดิม (ผิด) | ข้อมูลใหม่ (ถูกต้อง) |
|---|---|---|
| ชื่อโมเดล STT | biodatlab/whisper-th-large-v3-combined | **biodatlab/distill-whisper-th-large-v3** |
| ชื่อโมเดล LLM | Typhoon 8B / Typhoon | **Typhoon2 8B Instruct (scb10x/llama3.1-typhoon2-8b-instruct)** |
| LLM Analysis | Single call | **4 Prompt Calls แยกอิสระ** (Extraction, Sentiment, Agent QA, Anomaly) |
| Sentiment technique | ไม่ระบุ | **Chain-of-Thought (CoT) 2 ขั้นตอน, neutral เป็น default** |
| Agent QA technique | ไม่ระบุ | **Checklist-based Scoring 5 ข้อ 2 หมวด, temperature=0.3** |
| Anomaly Detection | anomaly_detected + reason | **+ anomaly_severity (low/medium/high)** |
| Sentiment | sentiment เท่านั้น | **+ sentiment_reason (เหตุผลพร้อมหลักฐาน)** |
| ชื่อระบบใน 2.9 | biodatlab/whisper-th-large-v3-combined | **SmartVoice** |
| Pre-analysis LLM | ไม่ระบุ | **Transcript Cleanup + Speaker Correction (Few-Shot)** |
| Domain Normalization | ไม่ระบุ | **Regex กว่า 40 กฎ** |
| Turn Splitting | ไม่ระบุ | **Heuristic Rule-based กว่า 10 กฎ** |
| DB Migration | ไม่ระบุ | **Auto Migration ตรวจสอบ/เพิ่ม Column อัตโนมัติ** |

---

# ส่วนที่ 2 — แก้ไขตามคอมเมนต์อาจารย์ (รอบ 2)

ปรับรายงานตามคอมเมนต์อาจารย์ 4 ข้อหลัก: (1) APA7 + Thai spacing (2) วัตถุประสงค์ใหม่ (3) เนื้อหาที่ขาด (Customer Insight, LLM/STT theory, Evaluation, Tech Stack rationale, Security, Hardware Architecture, Literature Review) (4) References จากงานวิจัย/หนังสือ

วิธีใช้: copy ข้อความในแต่ละหัวข้อไปวางใน Word

---

## A. Format Checklist (APA7 + Thai Spacing)

### A.1 กฎการเว้นวรรคภาษาไทย (ตรวจทั้งเล่ม)

- **กฎ 1:** เว้นวรรค 1 ช่องเท่านั้น ห้ามเว้น 2 ช่อง+
- **กฎ 2:** ไม้ยมก `ๆ` ต้องเว้นวรรคทั้งก่อนและหลัง 1 ช่อง เช่น `ในมิติต่าง ๆ`
- **กฎ 3:** คำอังกฤษในประโยคไทย ต้องเว้นวรรคก่อน-หลังคำอังกฤษ เช่น `ใช้โมเดล Whisper เพื่อถอดเสียง`
- **กฎ 4:** เครื่องหมาย `,` `.` `:` ไม่เว้นวรรคก่อน เว้นหลัง 1 ช่อง

### A.2 จุดผิดที่พบใน PDF ปัจจุบัน

| หน้า | ข้อความผิด | ปัญหา | แก้เป็น |
|------|-------------|--------|---------|
| 15 | `ใช้โมเดลpyannote/speakerdiarization` | ไม่มีช่องว่าง + ชื่อโมเดลผิด | `ใช้โมเดล pyannote/speaker-diarization-3.1` |
| 16 | `Speaker Correction**` | มี `**` ค้างจาก Markdown | ลบ `**` ออก |
| 19 | `ภายนอก- SQLite` | ติดกัน + bullet ไม่ถูก | แยกบรรทัด + ใส่ bullet ใหม่ |
| 29 | `เป็กระบวนการ` | สะกดผิด | `เป็นกระบวนการ` |
| 31 | หน้าว่าง "Flowchart" | ยังไม่มีเนื้อหา | เพิ่ม Flowchart diagram |

### A.3 APA7 In-text Citation

- ผู้แต่ง 1–2 คน: `(Radford & Sutskever, 2023)` หรือ `Radford และ Sutskever (2023)`
- ผู้แต่ง 3+ คน: `(Vaswani et al., 2017)` ใช้ `et al.` ตั้งแต่ครั้งแรก
- เว็บ/เอกสารทั่วไป: หลีกเลี่ยง ใช้เฉพาะเอกสารทางการจากองค์กรน่าเชื่อถือ

---

## B. วัตถุประสงค์ใหม่ (SMART) — แทนที่หัวข้อ 1.2

> **1.2 วัตถุประสงค์ของโครงการ**
>
> 1. เพื่อพัฒนาระบบถอดเสียงการสนทนาของศูนย์บริการลูกค้าบริษัท Omazz ให้เป็นข้อความภาษาไทยแบบอัตโนมัติ พร้อมระบุผู้พูด (Agent และ Customer) โดยมีเป้าหมาย Word Error Rate (WER) ไม่เกินร้อยละ 20 และ Speaker Attribution Accuracy ไม่น้อยกว่าร้อยละ 85
>
> 2. เพื่อวิเคราะห์ข้อมูลเชิงลึก (Customer Insight) จากบทสนทนาใน 4 มิติ ได้แก่ อารมณ์ลูกค้า (Sentiment), หัวข้อการติดต่อ (Topic/Intent), คุณภาพการให้บริการพนักงาน (Agent QA) และการตรวจจับเหตุผิดปกติ (Anomaly) โดยมี Sentiment Classification Accuracy ไม่น้อยกว่าร้อยละ 80 เทียบกับการตรวจของผู้เชี่ยวชาญ
>
> 3. เพื่อออกแบบฐานข้อมูลเชิงสัมพันธ์ที่เชื่อมโยงการโทร ลูกค้า ทะเบียนรับประกัน และเคสร้องเรียน (Case Management) เพื่อค้นหาประวัติย้อนหลังและติดตามเคสที่ยังไม่ปิด
>
> 4. เพื่อพัฒนา Dashboard แบบโต้ตอบ (Interactive Dashboard) สำหรับแสดงสถิติเชิงวิเคราะห์ของบทสนทนา รองรับการกรองตามช่วงเวลา ประเภทการติดต่อ และระดับความรุนแรง
>
> 5. เพื่อออกแบบระบบให้ทำงานภายในเครื่องขององค์กร (On-Premise) ไม่ส่งข้อมูลลูกค้าออกสู่บริการภายนอก สอดคล้องกับ พ.ร.บ. คุ้มครองข้อมูลส่วนบุคคล พ.ศ. 2562 (PDPA)

**เหตุผล:** วัตถุประสงค์ใหม่เป็น SMART (Specific, Measurable, Achievable, Relevant, Time-bound) เน้นเป้าหมายธุรกิจแทน technical implementation

---

## C. Customer Insight — หลักการและวิธีการ (เพิ่มเป็นหัวข้อ 2.1 ใหม่)

> **2.1 แนวคิดเรื่อง Customer Insight**
>
> Customer Insight หรือข้อมูลเชิงลึกของลูกค้า หมายถึง การตีความพฤติกรรม ความต้องการ ความพึงพอใจ และความคาดหวังของลูกค้าจากข้อมูลที่เก็บได้ โดยไม่ใช่เพียงข้อมูลดิบ (Raw Data) แต่เป็นความเข้าใจที่นำไปประกอบการตัดสินใจทางธุรกิจได้จริง (Ordenes et al., 2014) ข้อมูลที่ใช้สร้าง Customer Insight ครอบคลุมทั้งข้อมูลเชิงโครงสร้าง (ประวัติการซื้อ, ข้อมูลประชากรศาสตร์) และข้อมูลไม่มีโครงสร้าง (บทสนทนาเสียง, รีวิว, สื่อสังคม) (Davenport et al., 2020)
>
> **หลักการสำคัญของ Customer Insight**
>
> 1. **Voice of the Customer (VoC)** — การรับฟังเสียงลูกค้าจากช่องทางที่ลูกค้าแสดงความคิดเห็นจริง เช่น ศูนย์บริการลูกค้า, แบบสอบถาม, รีวิว Pang และ Lee (2008) อธิบายว่า Opinion Mining ช่วยให้องค์กรเข้าใจทัศนคติที่อยู่ใต้ข้อความได้อย่างเป็นระบบ
>
> 2. **Sentiment Analysis** — จำแนกอารมณ์จากข้อความเป็น Positive, Negative, Neutral โดยอาศัย NLP (Medhat et al., 2014)
>
> 3. **Topic Modeling / Intent Detection** — จำแนกหัวข้อหรือเจตนาของการติดต่อ เพื่อให้องค์กรทราบว่าลูกค้าติดต่อด้วยเรื่องใดบ่อยที่สุด
>
> 4. **Anomaly Detection** — ตรวจจับรูปแบบผิดปกติ เช่น การร้องเรียนรุนแรง การขู่ฟ้อง พฤติกรรมพนักงานไม่เหมาะสม
>
> **วิธีการทางเทคนิคสำหรับสร้าง Customer Insight จากเสียงสนทนา** แบ่งเป็น 3 ขั้นตอน ได้แก่ (1) Speech-to-Text แปลงข้อมูลเสียงไม่มีโครงสร้างเข้าสู่การประมวลผล (2) Natural Language Processing (NLP) สกัดข้อมูลเชิงลึก และ (3) Business Visualization แสดงผลให้ผู้บริหารตีความได้ง่าย
>
> ในโครงการ SmartVoice การสร้าง Customer Insight ครอบคลุมทั้ง 4 ด้านข้างต้น โดยใช้ Whisper สำหรับถอดเสียง, Pyannote สำหรับแยกผู้พูด และ Typhoon2 8B ผ่าน Ollama สำหรับสกัดข้อมูลเชิงลึก ทั้งหมดประมวลผลภายในเครื่องเพื่อคุ้มครองข้อมูลส่วนบุคคลของลูกค้า

---

## D. Literature Review — 10 งานวิจัย (เพิ่มเป็นหัวข้อ 2.2 ใหม่)

> **2.2 ทบทวนวรรณกรรมที่เกี่ยวข้อง**
>
> การทบทวนวรรณกรรมในหัวข้อนี้ครอบคลุมงานวิจัย 10 ชิ้นที่เกี่ยวข้องกับการสร้าง Customer Insight ด้วยปัญญาประดิษฐ์ แบ่งเป็น 3 กลุ่ม ได้แก่ (1) Sentiment Analysis และ NLP สำหรับธุรกิจ (2) AI ในงานบริการลูกค้า และ (3) เทคโนโลยี Foundation Model ที่เกี่ยวข้อง
>
> **กลุ่มที่ 1: Sentiment Analysis และ NLP สำหรับธุรกิจ**
>
> **(1) Pang และ Lee (2008)** ในงาน *Opinion Mining and Sentiment Analysis* ได้วางรากฐานทางทฤษฎีของการวิเคราะห์ความคิดเห็น โดยนำเสนอเทคนิคการจำแนกเอกสารตามอารมณ์ (Document-level), ประโยค (Sentence-level) และการสกัดทัศนคติเฉพาะประเด็น (Aspect-based Sentiment Analysis) งานนี้เป็น reference หลักของสาขา Opinion Mining ที่ยังถูกอ้างอิงจนถึงปัจจุบัน
>
> **(2) Medhat, Hassan, และ Korashy (2014)** ในงาน *Sentiment Analysis Algorithms and Applications: A Survey* ได้สำรวจอัลกอริทึม Sentiment Analysis ครอบคลุมทั้ง Machine Learning (Naive Bayes, SVM, Maximum Entropy) และ Lexicon-based Approaches พบว่า Hybrid Approach ที่รวม ML กับ Lexicon ให้ผลลัพธ์ดีที่สุดในหลายโดเมน
>
> **(3) Ordenes, Theodoulidis, Burton, Gruber, และ Zaki (2014)** ในงาน *Analyzing Customer Experience Feedback Using Text Mining* เสนอกรอบการวิเคราะห์ feedback ลูกค้าด้วย Text Mining ครอบคลุม 3 มิติ ได้แก่ Activity, Resource และ Context ซึ่งช่วยให้องค์กรเข้าใจประสบการณ์ของลูกค้าได้ละเอียดขึ้น
>
> **กลุ่มที่ 2: AI ในงานบริการลูกค้าและธุรกิจ**
>
> **(4) Davenport, Guha, Grewal, และ Bressgott (2020)** ในงาน *How Artificial Intelligence Will Change the Future of Marketing* นำเสนอกรอบ AI Marketing Matrix แบ่งระดับการใช้ AI ในการตลาดเป็น 4 ระดับ ได้แก่ Task Automation, Machine Learning, Deep Learning และ AI-Augmented Experience ระบุว่า AI จะเปลี่ยนการสร้าง Customer Insight ในระดับบุคคลได้อย่างมีนัยสำคัญ
>
> **(5) Kumar, Rajan, Venkatesan, และ Lecinski (2019)** ในงาน *Understanding the Role of Artificial Intelligence in Personalized Engagement Marketing* ศึกษาการใช้ AI สร้างการมีส่วนร่วมกับลูกค้าแบบรายบุคคล พบว่า AI ที่ใช้ข้อมูล Voice-of-Customer สามารถเพิ่ม Customer Lifetime Value ได้อย่างมีนัยสำคัญ
>
> **(6) Xu, Shieh, van Esch, และ Ling (2020)** ในงาน *AI Customer Service: Task Complexity, Problem-Solving Ability, and Usage Intention* ศึกษาปัจจัยที่ส่งผลต่อการยอมรับ AI ในงานบริการลูกค้า พบว่าความซับซ้อนของงาน (Task Complexity) และความสามารถแก้ปัญหา (Problem-Solving Ability) ของ AI เป็นปัจจัยสำคัญต่อ Usage Intention
>
> **(7) Prentice, Weaven, และ Wong (2020)** ในงาน *Linking AI Quality Performance and Customer Engagement* พบว่าความแม่นยำและเวลาตอบสนองของ AI ส่งผลต่อ Customer Engagement อย่างมีนัยสำคัญ โดยเฉพาะในกลุ่มลูกค้าที่มีความพึงพอใจกับ AI สูง
>
> **กลุ่มที่ 3: เทคโนโลยี Foundation Model**
>
> **(8) Vaswani และคณะ (2017)** ในงาน *Attention Is All You Need* นำเสนอสถาปัตยกรรม Transformer ซึ่งเป็นรากฐานของโมเดลภาษาสมัยใหม่ทั้งหมด รวมถึง BERT, GPT, Whisper และ Typhoon โดย Self-Attention Mechanism ช่วยให้โมเดลเรียนรู้ความสัมพันธ์ของคำในบริบทได้ดีกว่า RNN
>
> **(9) Radford และคณะ (2023)** ในงาน *Robust Speech Recognition via Large-Scale Weak Supervision* นำเสนอโมเดล Whisper ที่ train จากข้อมูลเสียง 680,000 ชั่วโมง ครอบคลุม 99 ภาษารวมถึงภาษาไทย ใช้ Transformer-based Encoder-Decoder Architecture ผลการทดลองแสดงว่า Whisper มีความคงทน (Robustness) ต่อเสียงรบกวน สำเนียง และคำศัพท์เฉพาะทางสูงกว่าระบบ STT เชิงพาณิชย์หลายตัว
>
> **(10) Wei และคณะ (2022)** ในงาน *Chain-of-Thought Prompting Elicits Reasoning in Large Language Models* นำเสนอเทคนิค Chain-of-Thought (CoT) Prompting ทำให้ LLM ให้เหตุผลเป็นขั้นตอนได้ดีขึ้น พบว่า CoT สามารถเพิ่มความแม่นยำในงาน Reasoning ได้อย่างมีนัยสำคัญ ในโครงการ SmartVoice งานนี้เป็นฐานของการออกแบบ Sentiment Analysis Prompt แบบ 2 ขั้นตอน
>
> **สังเคราะห์ช่องว่างงานวิจัย (Research Gap)**
>
> งานวิจัยที่ทบทวนมาข้างต้นส่วนใหญ่เน้นการวิเคราะห์ข้อความภาษาอังกฤษและทำงานแบบ Cloud-based ซึ่งมีความเสี่ยงด้านความปลอดภัยเมื่อใช้กับข้อมูลลูกค้าของศูนย์บริการในไทย โครงการ SmartVoice จึงเติมเต็มช่องว่างโดย (1) ใช้โมเดลที่ Fine-tune สำหรับภาษาไทยโดยเฉพาะ (2) ออกแบบให้ทำงานแบบ On-Premise ทั้งหมด และ (3) รวม 4 มิติของ Customer Insight (Sentiment, Topic, Agent QA, Anomaly) ไว้ในระบบเดียว

---

## E. ทฤษฎี LLM / STT / AI (เพิ่มเนื้อหาใน บท 2)

### E.1 หลักการ Speech-to-Text (เพิ่มในหัวข้อ 2.3)

> **หลักการของ Speech-to-Text**
>
> Speech-to-Text (STT) หรือ Automatic Speech Recognition (ASR) เป็นกระบวนการแปลงสัญญาณเสียงพูด x(t) ให้เป็นลำดับของคำ W = (w₁, w₂, ..., wₙ) โดยโจทย์หลักคือการหาลำดับคำที่มีความน่าจะเป็นสูงสุดเมื่อกำหนดสัญญาณเสียง ซึ่งเขียนในรูป Bayesian ได้เป็น
>
> W* = argmax P(W|X) = argmax P(X|W) · P(W)
>
> โดย P(X|W) คือ Acoustic Model และ P(W) คือ Language Model (Jurafsky & Martin, 2024)
>
> **วิธีการสมัยใหม่ (End-to-End Deep Learning)**
>
> ระบบ ASR สมัยใหม่ใช้ Deep Neural Network แบบ End-to-End ที่ไม่ต้องแยก Acoustic Model กับ Language Model ออกจากกัน โดยมีสถาปัตยกรรมหลัก 3 แบบ ได้แก่
>
> 1. **CTC-based Models** (Connectionist Temporal Classification) เหมาะสำหรับการ train โดยไม่ต้องมี alignment ของเสียงกับคำ
> 2. **Attention-based Encoder-Decoder** ใช้ Attention Mechanism เพื่อให้ decoder มองกลับไปยังส่วนของเสียงที่เกี่ยวข้องในแต่ละ time step
> 3. **Transformer-based Models** เช่น Whisper ที่ใช้ self-attention แทน RNN ให้ประสิทธิภาพสูงและ train ได้แบบ parallel
>
> **โมเดล Whisper ในโครงการ SmartVoice** พัฒนาโดย OpenAI (Radford et al., 2023) train จากข้อมูลเสียงและข้อความคู่กัน 680,000 ชั่วโมง ครอบคลุม 99 ภาษารวมถึงภาษาไทย สถาปัตยกรรมเป็น Transformer-based Encoder-Decoder รับ Log-Mel Spectrogram เป็น input ของ Encoder และให้ Decoder สร้างข้อความออกมา โครงการนี้ใช้โมเดล biodatlab/distill-whisper-th-large-v3 ซึ่งเป็นเวอร์ชันที่ถูก Fine-tune สำหรับภาษาไทยโดยเฉพาะและผ่านกระบวนการ Knowledge Distillation (Hinton et al., 2015) เพื่อลดขนาดโมเดลโดยคงความแม่นยำไว้
>
> **Speaker Diarization** เป็นกระบวนการตอบคำถาม "ใครพูดเมื่อใด" ในไฟล์เสียง โดย Pyannote (Bredin et al., 2020) ใช้ Deep Neural Network ที่ train ให้ (1) ตรวจจับการมีเสียงพูด (Voice Activity Detection) (2) สกัด Speaker Embedding ของแต่ละช่วงเสียง และ (3) จัดกลุ่ม embedding ด้วย Agglomerative Clustering เพื่อระบุผู้พูด โดยเวอร์ชัน 3.1 ใช้ Powerset Multi-class Cross Entropy Loss (Plaquet & Bredin, 2023) ที่รองรับการพูดทับเสียงกัน (Overlapping Speech)

### E.2 หลักการ Large Language Models (เพิ่มในหัวข้อ 2.5)

> **สถาปัตยกรรม Transformer**
>
> Transformer เป็นสถาปัตยกรรม Deep Learning ที่ Vaswani และคณะ (2017) นำเสนอ โดยมีนวัตกรรมหลักคือ Self-Attention Mechanism ซึ่งคำนวณค่าความสำคัญของแต่ละคำในบริบทผ่านสมการ
>
> Attention(Q, K, V) = softmax(QKᵀ / √dₖ) · V
>
> โดย Q, K, V คือ Query, Key และ Value Matrices ที่ได้จากการแปลง input ด้วย learned weights ซึ่งทำให้โมเดลสามารถเรียนรู้ความสัมพันธ์ของคำที่อยู่ไกลกัน (Long-range Dependencies) ได้ดีกว่า RNN แบบเดิม
>
> **Pre-training และ Fine-tuning**
>
> LLM สมัยใหม่ผ่าน 2 ขั้นตอนหลัก ได้แก่
>
> 1. **Pre-training** — train บนข้อมูลข้อความขนาดใหญ่ด้วย Self-supervised Learning เช่น Next-token Prediction เพื่อเรียนรู้ไวยากรณ์ ความหมาย และความรู้ทั่วไป
> 2. **Fine-tuning / Instruction Tuning** — ปรับแต่งบนข้อมูล instruction–response เพื่อให้โมเดลตอบคำถามตามคำสั่ง (Brown et al., 2020)
>
> **Typhoon2 8B** ที่ใช้ในโครงการเป็นโมเดลที่ถูก Fine-tune จาก LLaMA 3.1 8B (Touvron et al., 2023) ให้เชี่ยวชาญภาษาไทยและรองรับบริบทวัฒนธรรมไทย ขนาด 8 พันล้านพารามิเตอร์ ซึ่งเล็กพอที่จะรันบน GPU ระดับ consumer (RTX 5070 Ti 16GB) ได้
>
> **Prompt Engineering Techniques**
>
> ระบบ SmartVoice ใช้เทคนิค Prompt Engineering 3 แบบ ได้แก่
>
> 1. **Few-Shot Prompting** (Brown et al., 2020) — ให้ตัวอย่าง 5–7 ตัวอย่างใน Prompt เพื่อให้โมเดลเรียนรู้รูปแบบโดยไม่ต้อง Fine-tune ใช้ในการแก้ไข Speaker Label
> 2. **Chain-of-Thought (CoT)** (Wei et al., 2022) — บังคับให้โมเดลให้เหตุผลเป็นขั้นตอนก่อนตอบ ใช้ในการวิเคราะห์ Sentiment เพื่อลด Bias จากมารยาททางภาษาไทย
> 3. **Checklist-based Prompting** — แยกการประเมินเป็น checklist หลายข้อ เพื่อให้ผลลัพธ์มีความสม่ำเสมอและตรวจสอบได้ ใช้ในการประเมินคุณภาพพนักงาน (Agent QA)

---

## F. การประเมินผลระบบ (Evaluation Methods) — เพิ่มเป็นหัวข้อ 3.6 ใหม่

> **3.6 วิธีการประเมินผลระบบ**
>
> ระบบ SmartVoice ถูกประเมินผลใน 4 ระดับ ได้แก่ ระดับส่วนประกอบย่อย (Component-level), ระดับงานรวม (Task-level), ระดับระบบโดยรวม (System-level) และระดับผู้ใช้ (User-level) เพื่อให้ครอบคลุมทั้งความถูกต้องทางเทคนิคและความพึงพอใจของผู้ใช้งาน
>
> **3.6.1 Component-level Evaluation**
>
> **(ก) Speech-to-Text Accuracy** ประเมินด้วย Word Error Rate (WER) ซึ่งเป็น metric มาตรฐานของงาน ASR ตามสมการ
>
> WER = (S + D + I) / N
>
> โดย S = คำที่ถูกแทนที่ผิด, D = คำที่ถูกลบ, I = คำที่เพิ่มเข้ามาผิด, N = จำนวนคำทั้งหมดใน reference transcript เป้าหมายของโครงการคือ WER ไม่เกินร้อยละ 20 บนชุดทดสอบของ Omazz Call Center (Jurafsky & Martin, 2024)
>
> **(ข) Speaker Diarization Accuracy** ประเมินด้วย Diarization Error Rate (DER) ซึ่งประกอบด้วย 3 ส่วน ได้แก่ Miss (เสียงพูดที่ไม่ถูกตรวจจับ), False Alarm (ช่วงที่ไม่มีเสียงพูดแต่ถูกตรวจจับว่ามี) และ Speaker Confusion (การระบุผู้พูดผิดคน) และ Speaker Attribution Accuracy ซึ่งวัดความถูกต้องในการระบุบทพูดว่าเป็นของ Agent หรือ Customer
>
> **3.6.2 Task-level Evaluation**
>
> **(ก) Sentiment Classification Accuracy** ประเมินด้วย Precision, Recall และ F1-score ต่อแต่ละ class (Positive/Neutral/Negative) เปรียบเทียบกับการ label โดยผู้เชี่ยวชาญ 2 คน โดยต้องมี Inter-annotator Agreement (Cohen's Kappa ≥ 0.6) ก่อนจึงนับ label เป็น ground truth
>
> **(ข) Topic Classification Accuracy** ประเมินด้วย Macro-F1 ของการจำแนก 9 หมวด เพื่อไม่ให้หมวดที่มีข้อมูลน้อยถูกครอบงำด้วยหมวดที่มีข้อมูลมาก
>
> **(ค) Agent QA Score Correlation** เปรียบเทียบคะแนนที่ LLM ให้กับคะแนนที่ QA Manager ให้ โดยใช้ Pearson Correlation Coefficient ต้องมีค่า r ≥ 0.7 จึงถือว่ายอมรับได้
>
> **(ง) Anomaly Detection** ประเมินด้วย Precision-Recall ที่จุดต่าง ๆ และ Area Under Precision-Recall Curve (AUPRC) เนื่องจากข้อมูลมี class imbalance (สายปกติมากกว่าสายผิดปกติมาก)
>
> **3.6.3 System-level Evaluation**
>
> **(ก) Processing Time** ประเมินเวลาทั้งหมดที่ใช้ต่อสาย เป้าหมายคือไม่เกิน 2 นาทีสำหรับสายความยาว 5 นาที (บน GPU RTX 5070 Ti)
>
> **(ข) Resource Utilization** วัด GPU Memory Peak, CPU Usage และ Disk I/O เพื่อยืนยันว่าระบบสามารถรันบนฮาร์ดแวร์ที่กำหนดได้
>
> **(ค) Reliability** วัด Error Rate (สายที่ประมวลผลไม่สำเร็จ) ต้องต่ำกว่าร้อยละ 5
>
> **3.6.4 User-level Evaluation**
>
> ทดสอบด้วยการให้ผู้ใช้จริง (QA Manager ของ Omazz) ใช้งานระบบแล้วตอบแบบสอบถาม System Usability Scale (SUS) ซึ่งมี 10 คำถามให้คะแนน 1–5 จากนั้นคำนวณคะแนน SUS (0–100) โดยเป้าหมายคือ SUS ≥ 68 (ระดับ "Good" ตามมาตรฐาน) และเก็บ qualitative feedback เพื่อปรับปรุง UX

---

## G. Tech Stack — วิธีคิดและเหตุผลการเลือก (เพิ่มเป็นหัวข้อ 3.1.1 ใหม่)

> **3.1.1 วิธีคิดในการเลือก Tech Stack**
>
> การเลือกเทคโนโลยีในโครงการ SmartVoice ยึดหลัก 4 ประการ ได้แก่ (1) ความเป็นส่วนตัวของข้อมูล (Data Privacy) (2) ต้นทุนที่ยั่งยืน (Sustainable Cost) (3) ความเหมาะสมกับภาษาไทย (Thai Language Support) และ (4) ความสามารถในการขยายระบบ (Scalability) โดยมีการเปรียบเทียบทางเลือกแต่ละชั้น ดังตาราง
>
> | ชั้น | ทางเลือก A | ทางเลือก B | ทางเลือกที่เลือก | เหตุผล |
> |------|------------|------------|-------------------|--------|
> | **STT** | Google Cloud Speech-to-Text | Whisper (OpenAI Cloud API) | **biodatlab/distill-whisper-th-large-v3 (local)** | Cloud API ส่งข้อมูลออกนอกองค์กรเสี่ยงต่อ PDPA และโมเดล fine-tune สำหรับภาษาไทยให้ WER ต่ำกว่า Whisper มาตรฐาน |
> | **Diarization** | AWS Transcribe | NVIDIA NeMo | **Pyannote speaker-diarization-3.1 (local)** | เป็น open-source ที่ train บน public data แบบโปร่งใส รองรับ on-premise และรองรับ Overlapping Speech ผ่าน Powerset Loss |
> | **LLM** | GPT-4 API | Claude API | **Typhoon2 8B ผ่าน Ollama (local)** | ข้อมูลการสนทนาของลูกค้าไม่สามารถส่งออกสู่ cloud ได้ Typhoon2 เชี่ยวชาญภาษาไทย ขนาด 8B รันบน RTX 5070 Ti ได้ |
> | **Database** | PostgreSQL | MongoDB | **SQLite (ออกแบบให้ย้ายเป็น PostgreSQL ได้)** | Prototype ระยะเริ่มต้น ไม่ต้องมี DB server แยก ติดตั้งง่าย และย้ายเมื่อ scale ได้โดยแก้ connection string |
> | **Web Framework** | FastAPI + React | Flask + Vue | **Streamlit** | เป็น internal tool สำหรับ QA/Manager ไม่ใช่ public website Streamlit ลดเวลาพัฒนา front-end และรองรับ rapid prototyping |
> | **Visualization** | Matplotlib | Chart.js | **Plotly** | ให้กราฟ interactive (zoom, hover, filter) โดยไม่ต้องเขียน JavaScript เพิ่ม และ integrate กับ Streamlit ได้ดี |
> | **Audio Processing** | librosa | torchaudio | **noisereduce + scipy** | noisereduce ใช้ Spectral Gating เหมาะกับเสียงพูดในสภาพแวดล้อมจริง และ scipy เป็น dependency พื้นฐาน ไม่เพิ่ม complexity |
>
> **การตัดสินใจสำคัญด้านสถาปัตยกรรม**
>
> 1. **Local-first Architecture** — ตัดสินใจว่า cloud ทุกประเภทไม่เหมาะสำหรับข้อมูลบทสนทนาของลูกค้าจริง เพื่อป้องกันการ leak ข้อมูลและสอดคล้องกับ PDPA
> 2. **Hybrid Storage** — แยกข้อมูลเสียงต้นฉบับ (large binary) ไว้ใน file system และผลลัพธ์การวิเคราะห์ (structured data) ไว้ใน SQLite เพื่อให้ query เร็วและ backup ได้ง่าย
> 3. **LLM Prompt Split** — แบ่งการวิเคราะห์เป็น 4 Prompt Calls แทน Call เดียว เพราะโมเดล 8B ให้ผลลัพธ์ JSON ไม่สมบูรณ์เมื่อ Prompt ยาวเกินไป (พบว่า error rate ลดลงจาก ~20% เหลือ ~3% หลังแยก)

---

## H. Security — การรักษาความปลอดภัย 4 ระดับ (เพิ่มเป็นหัวข้อ 3.7 ใหม่)

> **3.7 การรักษาความปลอดภัยของระบบ (Security Architecture)**
>
> ระบบ SmartVoice ถูกออกแบบให้มีการรักษาความปลอดภัย 4 ระดับตามหลัก Defense in Depth ได้แก่ (1) Application Security (2) Data Security (3) Network Security และ (4) Infrastructure Security
>
> **3.7.1 Application Security (ความปลอดภัยระดับแอปพลิเคชัน)**
>
> - **Input Validation** — ระบบตรวจสอบไฟล์อัปโหลดก่อนบันทึก โดยใช้ Magic-Byte Sniffing เพื่อยืนยันว่าเป็นไฟล์ WAV/MP3 จริง ไม่ใช่ไฟล์ที่เปลี่ยนนามสกุล พร้อมจำกัดขนาดไฟล์ไม่เกิน 100 MB เพื่อป้องกัน Resource Exhaustion
> - **Filename Sanitization** — ลบอักขระอันตราย (`..`, `/`, `\`, `<`, `>`) ออกจากชื่อไฟล์ก่อนบันทึกลง disk เพื่อป้องกัน Path Traversal Attack
> - **SQL Injection Prevention** — ใช้ Parameterized Query ทุกจุดที่มี user input (ไม่มีการต่อ string ตรง) โดย sqlite3.Connection.execute() รับ tuple ของ parameters แยกจาก SQL template
> - **Secret Management** — เก็บ HF_TOKEN และ credentials อื่น ๆ ใน .env (git-ignored) ไม่ hardcode ใน source code
> - **Error Message Sanitization** — error message ที่แสดงให้ user ไม่เปิดเผย stack trace หรือ path ภายในเครื่อง ส่วน stack trace เต็มจะถูกเขียนลง log file แทน
>
> **3.7.2 Data Security (ความปลอดภัยระดับข้อมูล)**
>
> - **Data Minimization** — เก็บเฉพาะ field ที่จำเป็นต่อการวิเคราะห์ ไม่เก็บ metadata ส่วนตัวของลูกค้าที่ไม่เกี่ยวข้อง (เช่น IP address, device fingerprint)
> - **Access Control** — ฐานข้อมูล SQLite เก็บในโฟลเดอร์ที่จำกัดสิทธิ์ระดับระบบปฏิบัติการ ให้เฉพาะ user ที่รัน Streamlit เข้าถึงได้
> - **Audit Log** — ทุกการประมวลผลสายและ error ถูกบันทึกใน data/logs/smartvoice.log พร้อม timestamp สำหรับ trail ย้อนหลัง
> - **PII Protection** — Dashboard ไม่แสดง transcript เต็ม แสดงเฉพาะ summary ที่ LLM สรุปแล้ว เพื่อลดการเปิดเผยคำพูดตัวต่อตัวของลูกค้า
> - **Retention Policy** — มีกลไกลบไฟล์เสียงและ record ในฐานข้อมูลได้เมื่อหมดอายุการเก็บรักษา พร้อม cascade ลบข้อมูลที่เกี่ยวข้อง (เคส, linkage)
>
> **3.7.3 Network Security (ความปลอดภัยระดับเครือข่าย)**
>
> - **On-Premise Deployment** — ระบบทั้งหมดทำงานภายใน Localhost ไม่มีการ bind port ออก public network
> - **No External API Calls** — ไม่มีการเรียก cloud API ใด ๆ ระหว่างการวิเคราะห์ ข้อมูลไม่ออกสู่ internet เลย
> - **Firewall** — กำหนดให้ Ollama Server ที่ port 11434 และ Streamlit ที่ port 8501 เปิดเฉพาะ 127.0.0.1 ไม่เปิด 0.0.0.0
>
> **3.7.4 Infrastructure Security (ความปลอดภัยระดับโครงสร้างพื้นฐาน)**
>
> - **OS Hardening** — ติดตั้ง OS Security Patches ล่าสุด, ปิด service ที่ไม่จำเป็น
> - **Dependency Management** — Pin เวอร์ชันของทุก library ใน requirements.txt และตรวจสอบ vulnerability ด้วย pip-audit เป็นระยะ
> - **Model Integrity** — ตรวจสอบ checksum ของ weight ที่ดาวน์โหลดจาก HuggingFace เพื่อป้องกัน supply-chain attack
> - **Physical Security** — เครื่องที่รัน SmartVoice อยู่ใน server room ที่มีการควบคุมการเข้าถึง เพื่อป้องกันการขโมย disk ที่มี SQLite database
>
> **3.7.5 ความสอดคล้องกับ พ.ร.บ. คุ้มครองข้อมูลส่วนบุคคล พ.ศ. 2562 (PDPA)**
>
> ระบบออกแบบให้สอดคล้องกับหลัก 7 ประการของ PDPA ได้แก่ Lawfulness, Purpose Limitation, Data Minimization, Accuracy, Storage Limitation, Integrity & Confidentiality และ Accountability โดยเฉพาะการประมวลผลภายในเครื่องทั้งหมดช่วยลดความเสี่ยงของ Cross-border Data Transfer

---

## I. Hardware Architecture (เพิ่มเป็นหัวข้อ 3.8 ใหม่)

> **3.8 สถาปัตยกรรมฮาร์ดแวร์ (Hardware Architecture)**
>
> ระบบ SmartVoice ถูกออกแบบให้ทำงานบนเครื่องเดียว (Single-Node Deployment) ที่เน้นการประมวลผล AI แบบ GPU-accelerated เพื่อให้ได้ความเร็วเพียงพอต่อการใช้งานจริง สถาปัตยกรรมฮาร์ดแวร์ประกอบด้วย 4 ส่วนหลัก ดังนี้
>
> **3.8.1 Compute Layer (ชั้นประมวลผล)**
>
> **CPU: Intel Core i7-14700 (20 cores, 28 threads)** รับผิดชอบงานที่เป็น CPU-bound ได้แก่
> - การ preprocess เสียง (noise reduction, resampling)
> - การจัดการ I/O (อ่าน/เขียนไฟล์, network)
> - การ coordinate ระหว่าง thread และ process
> - การ query SQLite
>
> **GPU: NVIDIA RTX 5070 Ti 16GB VRAM** รับผิดชอบงานที่เป็น compute-intensive ได้แก่
> - การ inference ของ Whisper (~6 GB VRAM)
> - การ inference ของ Pyannote (~2 GB VRAM)
> - การ inference ของ Typhoon2 8B (~8 GB VRAM ด้วย 4-bit quantization)
> - Whisper และ Pyannote รันแยกกันโดยมีการปลด model ออกจาก VRAM ก่อน load model ถัดไป เพื่อป้องกัน Out-of-Memory
>
> **3.8.2 Memory Layer (ชั้นหน่วยความจำ)**
>
> **RAM: 32 GB DDR5** รองรับ
> - กระบวนการ Python (baseline ~2 GB + pipeline processing ~4 GB)
> - Buffer ของไฟล์เสียงที่กำลังประมวลผล (~500 MB/ไฟล์)
> - Streamlit session state
> - OS และ background services
>
> **3.8.3 Storage Layer (ชั้นจัดเก็บ)**
>
> **NVMe SSD 1TB** แบ่งพื้นที่ใช้งานเป็น 4 ส่วน
> - ไฟล์เสียงต้นฉบับใน `data/raw_audio/` (~5–10 MB/ไฟล์)
> - ฐานข้อมูล SQLite ใน `data/smartvoice.db` (~1–5 KB/สาย)
> - Model weights ที่ cache (~10 GB รวม Whisper + Pyannote + Typhoon2)
> - Log files ใน `data/logs/` (rotating 5 MB × 3 backups)
>
> **3.8.4 Deployment Topology**
>
> ระบบทำงานบน 2 เครื่องที่มี spec ใกล้เคียงกัน ได้แก่
> - **เครื่องที่ 1 (Development)**: Intel Core i7-14700, 32 GB RAM, 1 TB SSD, RTX 5070 Ti 16GB
> - **เครื่องที่ 2 (Testing/Demo)**: Intel Core i5-14400F, 32 GB RAM, 1 TB SSD, RTX 5070 Ti 16GB
>
> ทั้งสองเครื่องใช้สำหรับการทดสอบและสาธิตระบบ โดยไม่ได้เชื่อมต่อกันผ่าน cluster เนื่องจากระบบถูกออกแบบเป็น Single-node ซึ่งเพียงพอต่อ workload ระดับ prototype ของ call center ขนาดกลาง
>
> **3.8.5 การขยายระบบในอนาคต (Future Scalability)**
>
> หากต้องรองรับ workload เพิ่มขึ้น สามารถ scale ได้ 2 รูปแบบ ได้แก่
>
> - **Vertical Scaling** — อัปเกรด GPU เป็นรุ่นที่มี VRAM มากขึ้น (เช่น RTX A6000 48GB) เพื่อรัน LLM ขนาดใหญ่ขึ้น (70B) โดยไม่ต้อง quantize
> - **Horizontal Scaling** — แยก Ollama Server ออกจาก Application Server โดยใช้ Load Balancer เพื่อกระจายคำขอ LLM ไปยัง GPU หลายตัว และเปลี่ยน SQLite เป็น PostgreSQL เพื่อรองรับ concurrent write

---

## J. บรรณานุกรม APA7 (แทนที่หน้า "แหล่งอ้างอิงตามเครื่องมือ" หน้า 21–23)

> **บรรณานุกรม (References)**
>
> Bredin, H., Yin, R., Coria, J. M., Gelly, G., Korshunov, P., Lavechin, M., Fustes, D., Titeux, H., Bouaziz, W., & Gill, M.-P. (2020). Pyannote.audio: Neural building blocks for speaker diarization. In *ICASSP 2020 – 2020 IEEE International Conference on Acoustics, Speech and Signal Processing* (pp. 7124–7128). IEEE. https://doi.org/10.1109/ICASSP40776.2020.9052974
>
> Brown, T. B., Mann, B., Ryder, N., Subbiah, M., Kaplan, J., Dhariwal, P., Neelakantan, A., Shyam, P., Sastry, G., Askell, A., Agarwal, S., Herbert-Voss, A., Krueger, G., Henighan, T., Child, R., Ramesh, A., Ziegler, D. M., Wu, J., Winter, C., … Amodei, D. (2020). Language models are few-shot learners. *Advances in Neural Information Processing Systems*, 33, 1877–1901.
>
> Davenport, T. H., Guha, A., Grewal, D., & Bressgott, T. (2020). How artificial intelligence will change the future of marketing. *Journal of the Academy of Marketing Science*, 48(1), 24–42. https://doi.org/10.1007/s11747-019-00696-0
>
> Devlin, J., Chang, M.-W., Lee, K., & Toutanova, K. (2019). BERT: Pre-training of deep bidirectional transformers for language understanding. In *Proceedings of the 2019 Conference of the North American Chapter of the Association for Computational Linguistics: Human Language Technologies* (Vol. 1, pp. 4171–4186). Association for Computational Linguistics. https://doi.org/10.18653/v1/N19-1423
>
> Goodfellow, I., Bengio, Y., & Courville, A. (2016). *Deep learning*. MIT Press.
>
> Hinton, G., Vinyals, O., & Dean, J. (2015). *Distilling the knowledge in a neural network* [Preprint]. arXiv. https://doi.org/10.48550/arXiv.1503.02531
>
> Jurafsky, D., & Martin, J. H. (2024). *Speech and language processing: An introduction to natural language processing, computational linguistics, and speech recognition with language models* (3rd ed., draft). Stanford University. https://web.stanford.edu/~jurafsky/slp3/
>
> Kumar, V., Rajan, B., Venkatesan, R., & Lecinski, J. (2019). Understanding the role of artificial intelligence in personalized engagement marketing. *California Management Review*, 61(4), 135–155. https://doi.org/10.1177/0008125619859317
>
> Medhat, W., Hassan, A., & Korashy, H. (2014). Sentiment analysis algorithms and applications: A survey. *Ain Shams Engineering Journal*, 5(4), 1093–1113. https://doi.org/10.1016/j.asej.2014.04.011
>
> Ordenes, F. V., Theodoulidis, B., Burton, J., Gruber, T., & Zaki, M. (2014). Analyzing customer experience feedback using text mining: A linguistics-based approach. *Journal of Service Research*, 17(3), 278–295. https://doi.org/10.1177/1094670514524625
>
> Pang, B., & Lee, L. (2008). Opinion mining and sentiment analysis. *Foundations and Trends in Information Retrieval*, 2(1–2), 1–135. https://doi.org/10.1561/1500000011
>
> Plaquet, A., & Bredin, H. (2023). Powerset multi-class cross entropy loss for neural speaker diarization. In *Proceedings of Interspeech 2023* (pp. 3222–3226). ISCA. https://doi.org/10.21437/Interspeech.2023-205
>
> Prentice, C., Weaven, S., & Wong, I. A. (2020). Linking AI quality performance and customer engagement: The moderating effect of AI preference. *International Journal of Hospitality Management*, 90, 102629. https://doi.org/10.1016/j.ijhm.2020.102629
>
> Radford, A., Kim, J. W., Xu, T., Brockman, G., McLeavey, C., & Sutskever, I. (2023). Robust speech recognition via large-scale weak supervision. In *Proceedings of the 40th International Conference on Machine Learning* (pp. 28492–28518). PMLR. https://proceedings.mlr.press/v202/radford23a.html
>
> Silberschatz, A., Korth, H. F., & Sudarshan, S. (2019). *Database system concepts* (7th ed.). McGraw-Hill Education.
>
> Touvron, H., Lavril, T., Izacard, G., Martinet, X., Lachaux, M.-A., Lacroix, T., Rozière, B., Goyal, N., Hambro, E., Azhar, F., Rodriguez, A., Joulin, A., Grave, E., & Lample, G. (2023). *LLaMA: Open and efficient foundation language models* [Preprint]. arXiv. https://doi.org/10.48550/arXiv.2302.13971
>
> Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., Jones, L., Gomez, A. N., Kaiser, Ł., & Polosukhin, I. (2017). Attention is all you need. *Advances in Neural Information Processing Systems*, 30, 5998–6008.
>
> Wei, J., Wang, X., Schuurmans, D., Bosma, M., Ichter, B., Xia, F., Chi, E., Le, Q. V., & Zhou, D. (2022). Chain-of-thought prompting elicits reasoning in large language models. *Advances in Neural Information Processing Systems*, 35, 24824–24837.
>
> Xu, Y., Shieh, C.-H., van Esch, P., & Ling, I.-L. (2020). AI customer service: Task complexity, problem-solving ability, and usage intention. *Australasian Marketing Journal*, 28(4), 189–199. https://doi.org/10.1016/j.ausmj.2020.03.005
>
> สำนักงานคณะกรรมการคุ้มครองข้อมูลส่วนบุคคล. (2562). *พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล พ.ศ. 2562*. ราชกิจจานุเบกษา, 136(69 ก), 52–95.

### หมายเหตุการใช้งาน References

1. **ตรวจสอบ DOI/URL ก่อนใช้** — DOI ที่ให้ไว้คือของจริง แต่ควรเปิดดูเพื่อยืนยันว่าเข้าถึงได้ จริง
2. **รูปแบบใน Word** — เมื่อ paste ลง Word:
   - ตั้งย่อหน้าแบบ Hanging Indent 0.5"
   - ใช้ font TH Sarabun New 16pt (ตามมาตรฐานไทย) หรือ Times New Roman 12pt
   - ชื่อวารสารและหนังสือใช้ *italic* (ในบางข้อที่ใส่ markdown `*...*` ไว้)
3. **เรียงตามตัวอักษร A–Z** — list นี้เรียงแล้ว เพิ่ม reference ใหม่ให้เรียงต่อไปตามตัวอักษร
4. **In-text Citation** — เวลาอ้างในเนื้อหา ใช้ `(Author, Year)` ไม่ใช่ `(ชื่อ, ปี ค.ศ.)` สำหรับ reference ต่างประเทศ และ `(ชื่อ, ปี พ.ศ.)` สำหรับ reference ไทย

---

## K. Checklist สรุปก่อนส่งรายงาน

### ✅ การปรับเนื้อหา (10 ข้อตามอาจารย์)

- [ ] แก้ **APA7** ทั้ง in-text citation และ reference list (ดูส่วน A และ J)
- [ ] แก้ **เว้นวรรค** 1 ช่อง + ไม้ยมกมีเว้นวรรคหน้า-หลัง (ดูส่วน A)
- [ ] แทนที่ **วัตถุประสงค์** 1.2 ด้วย SMART (ดูส่วน B)
- [ ] เพิ่ม **Customer Insight** เป็นหัวข้อ 2.1 (ดูส่วน C)
- [ ] เพิ่ม **Literature Review** 10 งาน เป็นหัวข้อ 2.2 (ดูส่วน D)
- [ ] เพิ่ม **ทฤษฎี STT/LLM** ในหัวข้อ 2.3 และ 2.5 (ดูส่วน E)
- [ ] เพิ่ม **Evaluation Methods** เป็นหัวข้อ 3.6 (ดูส่วน F)
- [ ] เพิ่ม **Tech Stack Rationale** เป็นหัวข้อ 3.1.1 (ดูส่วน G)
- [ ] เพิ่ม **Security 4 ระดับ** เป็นหัวข้อ 3.7 (ดูส่วน H)
- [ ] เพิ่ม **Hardware Architecture** เป็นหัวข้อ 3.8 (ดูส่วน I)

### ✅ การปรับเนื้อหา (จากรอบ 1)

- [ ] แก้ **ชื่อโมเดล STT** → `biodatlab/distill-whisper-th-large-v3`
- [ ] แก้ **ชื่อ LLM** → `Typhoon2 8B Instruct (scb10x/llama3.1-typhoon2-8b-instruct)`
- [ ] ระบุ **4 Prompt Calls แยกอิสระ**
- [ ] ระบุ **Chain-of-Thought** ใน Sentiment
- [ ] ระบุ **Checklist-based Scoring** ใน Agent QA
- [ ] เพิ่ม `anomaly_severity` และ `sentiment_reason`
- [ ] ระบุ **Regex Normalization** 40 กฎ
- [ ] ระบุ **Heuristic Turn Splitting** 10+ กฎ
- [ ] เพิ่ม **Flowchart** หน้าสุดท้าย

### ✅ การตรวจทานคำผิด

- [ ] หน้า 15: `pyannote/speakerdiarization` → `pyannote/speaker-diarization-3.1`
- [ ] หน้า 16: ลบ `**` ที่ค้างจาก Markdown
- [ ] หน้า 19: แยกบรรทัด `ภายนอก-SQLite`
- [ ] หน้า 29: `เป็กระบวนการ` → `เป็นกระบวนการ`
