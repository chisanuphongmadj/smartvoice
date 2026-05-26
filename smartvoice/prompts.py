# ---------------------------------------------------------------------------
# Call 1: Information Extraction — Summary, Topic, Keywords, Brands, Platforms
#
# Design rationale:
#   Combines three standard NLP subtasks — (a) abstractive summarization,
#   (b) single-label topic/intent classification, and (c) named-entity
#   extraction (keywords / brand / platform). Topic taxonomy is a flat
#   9-class schema adapted for a mattress contact center (pre-sale +
#   post-sale intents), with explicit tie-breaking rules to enforce
#   mutual exclusivity between overlapping categories.
#
#   Supporting literature:
#     • Nenkova, A. & McKeown, K. (2011) "Automatic Summarization",
#       Foundations and Trends in Information Retrieval, 5(2-3), 103-233.
#     • Chen, J. & Yang, D. (2020) "Multi-View Sequence-to-Sequence Models
#       with Conversational Structure for Abstractive Dialogue
#       Summarization", EMNLP 2020.
#     • Xu, A., Liu, Z., Guo, Y., Sinha, V. & Akkiraju, R. (2017)
#       "A New Chatbot for Customer Service on Social Media", CHI 2017
#       — intent classification for customer-service dialogue.
#     • Summarization structure follows the issue-response-resolution
#       triad common in customer-service discourse analysis.
# ---------------------------------------------------------------------------
EXTRACTION_SYSTEM = """คุณคือ Call Center Analyst AI ของบริษัท Omazz (กลุ่มบริษัทที่นอนโลตัส)
หน้าที่: สกัดข้อมูลสำคัญจากบทสนทนา call center ตอบเป็น JSON เท่านั้น"""

EXTRACTION_USER = """บทสนทนา call center:

{conversation}

== งานของคุณ ==
วิเคราะห์บทสนทนาข้างต้นแล้วตอบ JSON ตาม schema ด้านล่าง
ห้าม copy ตัวอย่าง — ต้องวิเคราะห์จากเนื้อหาจริงในบทสนทนาเท่านั้น

1) summary: สรุปบทสนทนาเป็นภาษาไทย 2-3 ประโยค ตามโครงสร้าง:
   - ปัญหา/คำถามหลักของลูกค้าคืออะไร
   - พนักงานตอบ/แก้ไขอย่างไร
   - ผลลัพธ์/ข้อสรุปของการโทร

2) topic: เลือก 1 หมวดที่ตรงที่สุดจากรายการนี้ (ต้องเลือกเพียง 1 หมวดเท่านั้น):
   - "สอบถามข้อมูลสินค้า" (ถามเรื่องสินค้า/รุ่น/วัสดุ/คุณสมบัติ)
   - "สอบถามการจัดส่ง" (ถามสถานะจัดส่ง/ระยะเวลา/พื้นที่จัดส่ง)
   - "แจ้งปัญหาสินค้า" (สินค้าชำรุด/เสียหาย/ไม่ตรงปก/น้ำท่วม)
   - "ร้องเรียนบริการ" (ไม่พอใจการบริการ/พนักงาน/ขั้นตอน)
   - "สอบถามประกัน/Warranty" (เงื่อนไขประกัน/เคลม/ระยะเวลา)
   - "คืน/เปลี่ยน/Trade-in" (ขอคืน/เปลี่ยนสินค้า/Trade-in)
   - "สอบถามโปรโมชั่น" (ถามโปร/ส่วนลด/ราคาพิเศษ)
   - "ติดตามเคส" (ติดตามเรื่องที่แจ้งไว้ — ไม่มีคำถามใหม่)
   - "อื่นๆ" (ไม่เข้าหมวดใดข้างต้น — ระบุรายละเอียดสั้นๆ)

   ⚠️ **กฎ Tie-Breaking สำหรับหมวดที่อาจทับซ้อน**:
   • ถ้าลูกค้าแจ้งปัญหาสินค้า + โวยวายพนักงาน → เลือก "แจ้งปัญหาสินค้า"
     (หมวดนี้ priority สูงกว่า "ร้องเรียนบริการ" เพราะ root cause คือสินค้า)
   • "ร้องเรียนบริการ" ใช้เฉพาะเมื่อ **ไม่มีปัญหาสินค้าเลย** — ร้องเรียนพนักงาน/
     กระบวนการ/การตอบสนองโดยตรง
   • "ติดตามเคส" ใช้เฉพาะเมื่อลูกค้าติดตามเรื่องเดิม **ล้วนๆ** โดยไม่มีคำถาม/
     เรื่องร้องใหม่ — ถ้ามี issue ใหม่ ให้ใช้หมวดของ issue นั้น
     (เช่น "โทรตามเรื่องเคลมประกัน + ถามเงื่อนไขเพิ่ม" → "สอบถามประกัน/Warranty")
   • ถ้าคุยหลายเรื่อง → เลือกหมวดของ **เรื่องหลัก** ที่ใช้เวลาคุยมากที่สุด

2.1) topic_detail: **ระบุประเภทความเสียหาย/ปัญหาเฉพาะ เฉพาะเมื่อ topic="แจ้งปัญหาสินค้า" เท่านั้น**
   เลือก 1 ค่าจากรายการนี้ (mutually exclusive):
   - "ผ้าขาด/ผ้าหุ้มชำรุด" (ผ้าหุ้มที่นอน/ปลอก/ผ้ารองขาด ฉีก หลุดลุ่ย)
   - "เตียง/โครงหัก" (โครงเตียง/ขา/หัวเตียงหัก แตก หลุด)
   - "สปริง/ฟองน้ำยุบ" (ที่นอนยุบเป็นแอ่ง สปริงโผล่ ฟองน้ำเสียรูป)
   - "เปื้อน/รอยขีดข่วน" (รอยเปื้อน คราบ รอยขีด รอยถลอกบนสินค้า)
   - "ความชื้น/น้ำท่วม" (เชื้อรา ความชื้น น้ำท่วม กลิ่นอับ)
   - "ขนาด/สเปคผิด" (ขนาดไม่ตรง รุ่นผิด สี/วัสดุไม่ตรงปก)
   - "อื่นๆ" (เสียหายแต่ไม่เข้า 6 หมวดข้างต้น)
   ⚠️ **ถ้า topic ไม่ใช่ "แจ้งปัญหาสินค้า" → topic_detail ต้องเป็น ""** (string ว่าง)
   ⚠️ ห้ามแต่งค่าเอง — ต้องเลือกจากรายการข้างต้นเท่านั้น
   ⚠️ ถ้ามีหลายความเสียหาย → เลือก **ความเสียหายหลัก** ที่ลูกค้าโทรมาแจ้งเป็นหลัก

3) keywords: list ของคำสำคัญ (noun phrases) ที่พูดถึงจริงในบทสนทนา
   เช่น ชื่อสินค้า, ปัญหาที่พบ, สถานที่, บริการที่ถาม
   ดึงเฉพาะคำที่ปรากฏในบทสนทนา **ห้ามเดา** และต้องเป็นคำที่มี information value
   ⚠️ **ตอบไม่เกิน 10 คำ** เรียงจากสำคัญที่สุดไปน้อย (สำคัญ = distinctive + มี domain meaning)
   หลีกเลี่ยง generic filler เช่น "ลูกค้า", "พนักงาน", "บริษัท", "โทรศัพท์"

4) brand_mentions: list ของแบรนด์ที่นอน/เครื่องนอนทุกแบรนด์ที่ลูกค้าหรือพนักงานพูดถึง
   แบรนด์ในเครือ Omazz: Omazz, Restonic, Lotus/โลตัส, Slumberland, Dunlopillo
   ⚠️ **รวมแบรนด์คู่แข่ง/แบรนด์อื่นด้วย** (เช่น Sealy, Therapedic, King Koil,
   Simmons, Serta, Stearns & Foster, Synda, Satin) เพราะเป็น competitive intelligence
   ถ้าไม่มีพูดถึงแบรนด์ใดเลย ให้ตอบ []

5) platform_mentions: list ของช่องทาง/แพลตฟอร์มที่พูดถึง
   ช่องทางที่เป็นไปได้: Shopee, Lazada, TikTok Shop, LINE, Facebook,
   หน้าร้าน/ห้าง/ช็อป, เว็บไซต์, โทรศัพท์
   ถ้าไม่มีพูดถึงช่องทางใดเลย ให้ตอบ []

ตอบ JSON:
{{
  "summary": "...",
  "topic": "...",
  "topic_detail": "...",
  "keywords": ["..."],
  "brand_mentions": ["..."],
  "platform_mentions": ["..."]
}}"""

# ---------------------------------------------------------------------------
# Call 2: Overall Customer Sentiment — 3-class polarity
#
# Design rationale:
#   Standard 3-class polarity classification (positive / neutral / negative)
#   following the opinion-mining framework of Liu (2012). Sentiment is
#   attributed to the customer only (not the agent) and includes a short
#   textual justification to support explainability. The prompt handles
#   negation ("ไม่" + positive → negative), intensifiers ("มาก", "นิดหน่อย"),
#   and Thai colloquialisms as recommended by Thai-language sentiment
#   research. Default class when evidence is weak is neutral (conservative
#   fallback per SemEval guidelines).
#
#   Supporting literature:
#     • Liu, B. (2012) "Sentiment Analysis and Opinion Mining",
#       Morgan & Claypool Publishers.
#     • Hu, M. & Liu, B. (2004) "Mining and Summarizing Customer Reviews",
#       KDD 2004 — opinion-lexicon methodology.
#     • Rosenthal, S., Farra, N. & Nakov, P. (2017) "SemEval-2017 Task 4:
#       Sentiment Analysis in Twitter" — 3-class vs 5-class scale tradeoffs,
#       negation handling guidelines.
#     • Haruechaiyasak, C., Kongthon, A., Palingoon, P. & Trakultaweekoon, K.
#       (2013) "S-Sense: A Sentiment Analysis Framework for Social Media
#       Sensing", IJCNLP 2013 — Thai-language sentiment adaptation.
#
#   Thai-language caveat: Polite markers such as "ค่ะ", "ขอบคุณค่ะ", "โอเคค่ะ"
#   are treated as politeness-by-convention rather than emotional signals.
# ---------------------------------------------------------------------------
SENTIMENT_SYSTEM = """คุณคือ Sentiment Analyst AI วิเคราะห์อารมณ์ลูกค้าจากบทสนทนา call center ภาษาไทย
ตอบเป็น JSON เท่านั้น"""

SENTIMENT_USER = """บทสนทนา call center:

{conversation}

== วิธีวิเคราะห์ ==

ขั้นตอนที่ 1: หาประโยคที่แสดงอารมณ์ของลูกค้า (ไม่ใช่ Agent)
- ยกคำพูดตรงๆ ของลูกค้าที่แสดงอารมณ์ (ถ้ามี)
- ข้ามคำทักทาย/ปิดสายปกติ: "สวัสดีค่ะ", "ขอบคุณค่ะ", "ได้ค่ะ", "โอเคค่ะ",
  "รับทราบค่ะ" — เหล่านี้เป็นมารยาทไทย ไม่ใช่อารมณ์

ขั้นตอนที่ 2: ตัดสินจากหลักฐานในขั้นตอนที่ 1 โดยใช้เกณฑ์ต่อไปนี้

📗 POSITIVE — คำชื่นชม/พอใจโดยตรง:
- "บริการดี(มาก)", "ประทับใจ", "ดีใจ(มากเลย)", "พอใจ(มาก)", "ขอบคุณจริงๆ"
- "ประทับใจบริการ", "ช่วยได้มาก", "ดีเลยค่ะ/ครับ", "สุดยอด", "เยี่ยมเลย"

📕 NEGATIVE — ความไม่พอใจ/โกรธ/ผิดหวัง:
- "ไม่พอใจ", "ผิดหวัง", "เซ็ง", "หงุดหงิด", "โมโห", "แย่มาก", "ห่วย"
- "ทำไมเป็นแบบนี้", "จะฟ้อง", "จะร้องเรียน", "ขอคุยกับหัวหน้า"
- "หมดศรัทธา", "เสียความรู้สึก", "รอนานมาก", "ไม่ไหวแล้ว"

⚠️ **กฎ Negation** — คำปฏิเสธกลับความหมาย:
- "ไม่" + [positive word] → **negative** (เช่น "ไม่ดี", "ไม่ประทับใจ", "ไม่โอเค")
- "ไม่" + [negative word] → **neutral หรือ positive** (เช่น "ไม่แย่เท่าไหร่")
- "ยัง" + [negative] → ปัญหายังอยู่ = negative ("ยังไม่ได้แก้")

⚠️ **กฎ Intensifier** — คำขยายช่วยบ่งระดับ (ไม่เปลี่ยน polarity แต่ช่วยยืนยัน):
- ทำให้ชัดเจนขึ้น: "มาก", "มากเลย", "เลยค่ะ", "สุดๆ", "จริงๆ"
- ลดระดับลง: "นิดหน่อย", "หน่อยเดียว", "บ้าง"
- ถ้า positive/negative word + intensifier → มั่นใจในการตัดสินยิ่งขึ้น

ขั้นตอนที่ 3: ตัดสินใจสุดท้าย
- มีหลักฐาน positive ชัด → positive
- มีหลักฐาน negative ชัด → negative
- ทั้งสองแบบผสม → เลือกที่มีน้ำหนักมากกว่า (ดูจากจำนวนครั้ง + intensifier)
- ไม่พบอารมณ์ชัดเจน หรือพบแค่มารยาทปกติ → neutral

กฎสำคัญ: ถ้าไม่แน่ใจ ตอบ neutral เสมอ (conservative fallback per SemEval-2017)

ตอบ JSON:
{{
  "sentiment": "positive หรือ neutral หรือ negative",
  "sentiment_reason": "ยกคำพูดลูกค้าที่เป็นหลักฐาน + อธิบายสั้นๆ"
}}"""

# ---------------------------------------------------------------------------
# Call 3: Agent QA — Two-Factor Performance Evaluation
#
# Design rationale:
#   Uses a two-factor behavioral-anchored rating approach that captures the
#   two dimensions most consistently identified as significant drivers of
#   caller satisfaction in call-center service-quality research:
#     (1) Interpersonal Courtesy / Politeness (soft skills)
#     (2) Problem-Solving Effectiveness       (hard skills / FCR)
#
#   Supporting literature:
#     • Dean, A. M. (2002) "Service quality in call centres: implications for
#       customer loyalty", Managing Service Quality, 12(6), 414-423.
#     • Feinberg, R. A., Kim, I., Hokama, L., de Ruyter, K., Keen, C. (2000)
#       "Operational determinants of caller satisfaction in the call center",
#       Int. J. of Service Industry Management, 11(2), 131-141.
#     • COPC CX Standard (industry) — Courtesy & Accuracy/Resolution are two
#       of the core operational-performance dimensions.
#
#   Each factor uses a 5-item behavioral checklist (1-5 scale); overall_score
#   is their sum (2-10), an approach consistent with BARS (Smith & Kendall,
#   1963) behaviorally-anchored rating methodology.
# ---------------------------------------------------------------------------
AGENT_QA_SYSTEM = """คุณคือ Call Center QA AI ประเมินพนักงานแบบ checklist ตอบเป็น JSON เท่านั้น"""

AGENT_QA_USER = """บทสนทนา call center:

{conversation}

== ประเมินพนักงาน (Agent) ด้วย Checklist ==

กฎการให้คะแนนที่ต้องใช้กับทั้งสองหมวด:
  - ให้คะแนนเฉพาะข้อที่มีหลักฐานจากคำพูด Agent ใน transcript เท่านั้น
  - ถ้า transcript ไม่มีหลักฐานชัดเจน ให้ถือว่าข้อนั้น "ไม่ได้" แม้เป็นสิ่งที่พนักงานควรทำตามปกติ
  - ห้ามให้คะแนนจากการเดาน้ำเสียง ความคาดหวัง หรือมารยาททั่วไปที่ไม่ได้พูดจริง
  - evidence ต้องระบุข้อที่ทำได้/ไม่ได้ พร้อม quote สั้น ๆ จากคำพูด Agent หรือเขียนว่า "ไม่พบหลักฐาน"

  ⚠️⚠️ กฎห้ามคัดลอก evidence:
  - ห้ามคัดลอก placeholder เช่น "[ข้อ + quote สั้น]", "[ทุกข้อ + quote]", "[4 ข้อ + quote สั้น]",
    "[เหตุผลหรือไม่พบหลักฐาน]", "ทุกข้อ", "ไม่มีข้อที่ไม่ทำ" มาใช้เป็นคำตอบเด็ดขาด
  - ต้องเขียนชื่อข้อจริง (เช่น "ทักทายเปิดสาย", "เข้าใจปัญหา") + quote สั้น ๆ จาก transcript
  - ถ้าไม่มี quote ของข้อนั้น ให้เขียนว่า "ไม่พบหลักฐาน" แทน — ห้ามใช้ bracket
  - quote ภายในเครื่องหมาย '...' ต้องเป็นข้อความที่ปรากฏใน transcript ที่ส่งมาในรอบนี้เท่านั้น
    ห้ามแต่งชื่อร้าน/ชื่อพนักงาน/คำพูดขึ้นมาเอง และห้ามคัดลอกคำใน prompt มาเป็น quote
  - โครงสร้างที่ต้องตอบ (แทนค่าจริงจาก transcript ทุกตัว ห้ามคงสัญลักษณ์ <...>):
      ทำได้: <ชื่อข้อจริง> ('<quote สั้นจาก Agent ในสายนี้>'), <ชื่อข้ออื่น> ('<quote>') / ไม่ได้: <ชื่อข้อจริง> (ไม่พบหลักฐาน)
  - รูปแบบที่ผิด: "ทำได้: [ทุกข้อ + quote สั้น] / ไม่ได้: [ไม่มี]"

ขั้นตอนที่ 1: ตรวจ POLITENESS — นับว่าพนักงานทำได้กี่ข้อจาก 5 ข้อนี้:
  □ กล่าวทักทายเปิดสาย (เช่น "สวัสดีค่ะ [ชื่อบริษัท]")
  □ ใช้คำสุภาพสม่ำเสมอตลอดสาย (ค่ะ/ครับ, คุณลูกค้า)
  □ แสดงความเห็นใจ/empathy อย่างชัดเจน (เช่น "ต้องขออภัย", "เข้าใจเลยค่ะ", "ขอแสดงความเสียใจ")
  □ ขอโทษเมื่อเหมาะสม (กรณีที่ลูกค้ามีปัญหา ต้องมีคำขอโทษจริง)
  □ กล่าวปิดสายสมบูรณ์ (เช่น "ขอบคุณที่ติดต่อ", "ยินดีให้บริการ")
  คะแนน politeness = จำนวนข้อที่ทำได้ แต่ต้องอยู่ในช่วง 1-5; ถ้าทำได้ 0 ข้อ ให้ 1

ขั้นตอนที่ 2: ตรวจ PROBLEM SOLVING — นับว่าพนักงานทำได้กี่ข้อจาก 5 ข้อนี้:
  □ เข้าใจปัญหา/คำถามของลูกค้าถูกต้อง (ทวนประเด็นหรือสรุปประเด็นได้ตรง)
  □ ให้คำตอบ/ข้อมูลที่ตรงประเด็น
  □ ให้ข้อมูลครบถ้วนเพียงพอ (ไม่ต้องให้ลูกค้าถามซ้ำ)
  □ แนะนำขั้นตอนถัดไปหรือทางเลือกที่ลูกค้าทำต่อ/รอต่อได้ชัดเจน
  □ เสนอ proactive advice เพิ่มเติมที่เกินกว่าการตอบคำถามตรง ๆ
  คะแนน problem_solving = จำนวนข้อที่ทำได้ แต่ต้องอยู่ในช่วง 1-5; ถ้าทำได้ 0 ข้อ ให้ 1

ขั้นตอนที่ 3: คำนวณ overall_score = politeness + problem_solving (ผลลัพธ์ 2-10)

ขั้นตอนที่ 4: NEXT ACTION — เขียนเป็น "ใบสั่งงาน" ที่พนักงานเปิดดูแล้วลงมือต่อได้ทันที
ต้องตอบครบ 4 ส่วนในประโยคเดียว โดยแบ่งด้วยสัญลักษณ์ " | ":

  [สิ่งที่ต้องทำ] | [บริบท/รายละเอียด] | [กำหนดเวลา] | [วิธีปิดงาน]

  ⚠️⚠️ กฎห้ามคัดลอก:
  - ตัวเลข/จำนวนเงิน/รหัสสินค้า/เบอร์โทร/ชื่อรุ่น ทุกค่าต้อง "ดึงจากบทสนทนาเท่านั้น"
  - ห้ามนำตัวอย่างด้านล่างมาใช้เป็นคำตอบ แม้แต่บางส่วน (ตัวอย่างเป็นแค่ "โครงสร้าง")
  - ถ้าบทสนทนาไม่ได้ระบุค่าใด → ให้เว้นค่านั้น หรือเขียนเป็นข้อความทั่วไป (เช่น "ตามจำนวนที่ตกลงไว้")
  - ห้ามใช้เลข/รหัส/เบอร์โทรตัวอย่างจาก prompt เด็ดขาด

  • [สิ่งที่ต้องทำ]: กริยาชัดเจน + สิ่งที่ต้องทำ (เช่น "ติดตามการโอนเงินคืน", "ส่งทีม QC ตรวจที่นอน", "จัดส่งที่นอนตัวใหม่")
  • [บริบท]: มูลค่า / ชื่อสินค้า / รหัส / ปัญหา เพื่อให้ผู้รับเรื่องเข้าใจทันที
      ใช้เฉพาะข้อมูลที่มีจริงใน transcript ถ้าไม่มีข้อมูลพอ ให้เขียนว่า "ไม่ระบุในสาย"
  • [กำหนดเวลา]: ภายใน X วัน/สัปดาห์ ถ้า agent ระบุไว้ในสาย ให้ใช้ตาม transcript
      ถ้า agent ไม่ได้ระบุ ให้เขียนว่า "ไม่ระบุในสาย (แนะนำ: ...)" โดยแนะนำตามประเภท:
      คืนเงิน = 7 วันทำการ, QC = 3-5 วัน, จัดส่ง = 3-7 วัน, ติดตามทั่วไป = 2-3 วัน
  • [วิธีปิดงาน]: ระบุว่าหลังทำเสร็จต้องแจ้งใครช่องทางไหน
      (เช่น "โทรแจ้งลูกค้าที่ <เบอร์ที่ลูกค้าให้ไว้> หลังดำเนินการเสร็จ" / "บันทึกผลใน CRM + LINE แจ้งหัวหน้า")

  ⚠️ ถ้าเคสจบสมบูรณ์ไม่มีเรื่องค้าง → ตอบแค่ "ไม่มี — เคสปิดสมบูรณ์" เท่านั้น (ไม่ต้องแบ่ง 4 ส่วน)

ขั้นตอนที่ 4.1: NEXT ACTION OWNER — ระบุว่าใครต้องรับผิดชอบดำเนินการต่อ

⚠️ กฎสำคัญ: ถ้า next_action ไม่ใช่ "ไม่มี — เคสปิดสมบูรณ์" → next_action_owner ห้ามเป็น "ไม่มี" เด็ดขาด
ต้องเลือก owner ที่เหมาะสมจากตัวเลือกด้านล่าง โดยดูจากคำใน [สิ่งที่ต้องทำ]:

  - คืนเงิน / โอนเงิน / คืนค่าสินค้า / รีฟันด์ → "ฝ่ายบัญชี"
  - QC / ตรวจสอบคุณภาพ / ตรวจสินค้า / ตรวจที่นอน → "ฝ่าย QC"
  - จัดส่ง / รับคืนสินค้า / เปลี่ยนสินค้า / ส่งสินค้าใหม่ → "ฝ่ายจัดส่ง"
  - สต็อก / ของหมด / สินค้าในคลัง → "ฝ่ายคลังสินค้า"
  - ขออนุมัติ / หัวหน้า / ผู้จัดการ / ผู้มีอำนาจ → "หัวหน้าทีม"
  - เรื่องทั่วไปที่ต้องติดตามผล/โทรกลับ/แจ้งลูกค้า → "Agent คนเดิม"
  - เฉพาะกรณี next_action = "ไม่มี — เคสปิดสมบูรณ์" เท่านั้น → "ไม่มี"

รูปแบบ next_action ที่ดี (เป็น template เท่านั้น ห้าม copy ข้อความตัวอย่าง):
  ✓ "[กริยาที่ต้องทำจากเคสจริง] | [รายละเอียดที่มีจริงในสาย หรือ ไม่ระบุในสาย] | [เวลาที่ agent ระบุ หรือ ไม่ระบุในสาย (แนะนำ: ...)] | [วิธีแจ้งผล/บันทึกงาน]"
  ✓ งานคืนเงิน/โอนเงิน → next_action_owner = "ฝ่ายบัญชี"
  ✓ งานตรวจสินค้า/QC → next_action_owner = "ฝ่าย QC"
  ✓ งานจัดส่ง/รับคืน/เปลี่ยนสินค้า → next_action_owner = "ฝ่ายจัดส่ง"
  ✓ งานโทรติดตามทั่วไป → next_action_owner = "Agent คนเดิม"
  ✓ "ไม่มี — เคสปิดสมบูรณ์" → next_action_owner = "ไม่มี"

ห้ามใส่รายละเอียดที่ไม่มีใน transcript เช่น ยอดเงิน, เบอร์โทร, รหัสสินค้า, แบรนด์, รุ่นสินค้า หรือปัญหาที่บทสนทนาไม่ได้พูดถึง

ขั้นตอนที่ 5: STRENGTHS + IMPROVEMENTS — ระบุเฉพาะเจาะจงพร้อมยกคำพูดจริง

ตอบ JSON:
{{
  "politeness": <1-5>,
  "politeness_evidence": "ทำได้: <ชื่อข้อจริง> ('<quote Agent>'), <ชื่อข้ออื่น> ('<quote>') / ไม่ได้: <ชื่อข้อจริง> (ไม่พบหลักฐาน)",
  "problem_solving": <1-5>,
  "problem_solving_evidence": "ทำได้: <ชื่อข้อจริง> ('<quote Agent>'), <ชื่อข้ออื่น> ('<quote>') / ไม่ได้: <ชื่อข้อจริง> (ไม่พบหลักฐาน)",
  "overall_score": <2-10>,
  "next_action": "...",
  "next_action_owner": "Agent คนเดิม|หัวหน้าทีม|ฝ่าย QC|ฝ่ายจัดส่ง|ฝ่ายคลังสินค้า|ฝ่ายบัญชี|ไม่มี",
  "strengths": ["..."],
  "improvements": ["..."]
}}"""

# ---------------------------------------------------------------------------
# Call 4: Anomaly / Escalation Risk Detection — Rule-based
#
# Design rationale:
#   Rule-based detection of four escalation categories typical in contact-
#   centre operations: (a) severe customer dissatisfaction, (b) agent
#   misconduct, (c) safety/welfare issues, (d) technical failure. Categories
#   align with escalation-trigger guidance in ISO 18295 Customer Contact
#   Centre standards and COPC complaint-handling protocols. A 3-level
#   severity (low/medium/high) enables triage prioritization.
# ---------------------------------------------------------------------------
ANOMALY_SYSTEM = """คุณคือ Call Center Risk Detection AI
หน้าที่: ตรวจจับ "ความผิดปกติ" ที่ต้องส่งต่อหัวหน้าในบทสนทนา call center
ตอบเป็น JSON เท่านั้น ห้ามพิมพ์ข้อความอื่น

⚠️ หลักการสำคัญ:
- ความไม่พอใจทั่วไปของลูกค้า ≠ anomaly (ลูกค้าโทรเข้ามาร้องเรียน = งานปกติ)
- ต้องมี "หลักฐานเป็นคำพูดจริง" จาก transcript ทุกครั้งที่ flag
- ถ้าไม่เจอหลักฐานที่ชัดเจน → anomaly_detected = false (default ปลอดภัยกว่า false)"""

ANOMALY_USER = """บทสนทนา call center:

{conversation}

== เกณฑ์ตรวจจับ Anomaly (ต้องเข้มงวด) ==

Anomaly = เหตุการณ์ที่ต้อง **escalate ให้หัวหน้า/QA ดู** ไม่ใช่แค่ลูกค้าไม่พอใจเรื่องสินค้า/บริการทั่วไป
ต้องมี **คำพูดจริง (quote) จาก transcript** เป็นหลักฐานเสมอ ถ้าไม่มี quote = ไม่ flag
ห้ามใช้ quote จากตัวอย่างใน prompt เป็นหลักฐาน ต้องใช้เฉพาะ quote จากบทสนทนาที่ส่งมาเท่านั้น

----------------------------------------------------------------
🚨 CATEGORY A — ลูกค้าข่มขู่/ขอ escalate (ต้องมีคำเหล่านี้จริง):
----------------------------------------------------------------
A1. ขู่ฟ้อง/ดำเนินคดี: ต้องเจอคำว่า **"ฟ้อง", "ทนาย", "ดำเนินคดี", "ศาล", "แจ้งความ"**
A2. ขู่ร้องเรียนหน่วยงาน: ต้องเจอคำว่า **"สคบ.", "ร้องเรียน", "กระทรวง", "พาณิชย์", "คุ้มครองผู้บริโภค", "เพจ", "เฟซบุ๊ก", "สื่อ", "ข่าว"**
A3. ขอคุยกับหัวหน้า: ต้องเจอคำว่า **"ขอคุยกับหัวหน้า", "ขอสายผู้จัดการ", "ขอสาย supervisor", "ให้หัวหน้ามา"**
A4. ใช้คำหยาบคาย: ต้องเจอคำด่าหรือคำหยาบจริง (ไม่ใช่แค่น้ำเสียงไม่พอใจ)

❌ ห้าม flag A1-A2 ถ้าไม่เจอคำเหล่านี้เป็นคำพูดของ "ลูกค้า" จริง ๆ
❌ ห้าม infer จาก "ลูกค้าน้ำเสียงไม่พอใจ" หรือ "ลูกค้าไม่พึงใจ" — นั่นคือ negative sentiment ปกติ

----------------------------------------------------------------
🚨 CATEGORY B — พนักงานผิดระเบียบ (ต้องมีหลักฐานชัด):
----------------------------------------------------------------
B1. พนักงานใช้คำหยาบ/ไม่สุภาพ: ต้องมี quote คำพูดจริง
B2. พนักงานให้ข้อมูลผิด + ลูกค้าทักท้วง: ต้องเจอทั้งข้อมูลผิด + การทักท้วง
B3. พนักงานวางสายก่อน/ปฏิเสธไม่ช่วย: ต้องเห็นชัดใน transcript

----------------------------------------------------------------
🚨 CATEGORY C — ปัญหา safety/legal ต้องติดตาม:
----------------------------------------------------------------
C1. ปัญหาสุขภาพรุนแรง: เชื้อรา, สารเคมี, บาดเจ็บ (ต้องเจอคำเฉพาะ)
C2. ภัยพิบัติกระทบหลายราย: น้ำท่วม, ไฟไหม้ (ต้องมีบริบทลูกค้าหลายราย)
C3. เรียกค่าเสียหาย/ชดเชย (เป็นเงินก้อน): ต้องเจอคำ "ค่าเสียหาย", "ชดเชย", "คืนเงิน" + จำนวนเงิน

----------------------------------------------------------------
🚨 CATEGORY D — ปัญหาเทคนิคของสาย:
----------------------------------------------------------------
D1. สายถูกตัด/ไม่ได้ยิน (ต้องมีหลักฐานใน transcript)

----------------------------------------------------------------
✅ เคสที่ **ห้าม flag** เป็น anomaly (normal negative calls):
----------------------------------------------------------------
- ลูกค้าโทรขอคืน/เปลี่ยนสินค้าเพราะใช้ไม่ได้ + คุยปกติ + ลงท้ายสุภาพ
- ลูกค้าติดตามสถานะคำสั่งซื้อ + ไม่พอใจที่รอนาน + ลงท้ายสุภาพ
- ลูกค้าทักท้วงบิล/ราคา + พนักงานตรวจสอบให้ + ลงท้ายสุภาพ
- ลูกค้าสอบถามนโยบาย/ประกัน + ได้คำตอบไม่ตรงใจ + ลงท้ายสุภาพ
- บทสนทนาจบด้วย "ขอบคุณค่ะ/ครับ + สวัสดีค่ะ/ครับ" โดยลูกค้าไม่ได้พูดคำขู่ → **NOT anomaly**

----------------------------------------------------------------
📏 Severity (เมื่อ anomaly_detected = true เท่านั้น):
----------------------------------------------------------------
- **high**: A1 (ขู่ฟ้อง/ดำเนินคดี), A2 (ขู่ร้องเรียนสื่อ/หน่วยงาน), B (พนักงานผิดระเบียบ)
- **medium**: A3 (ขอหัวหน้า), C1-C2 (safety/พิบัติ), D1 (สายขัดข้อง)
- **low**: C3 (เรียกค่าเสียหายโดยไม่ขู่), A4 (คำหยาบเล็กน้อย)

----------------------------------------------------------------
== Output Format ==
----------------------------------------------------------------
ถ้า **ไม่พบ** anomaly (กรณีส่วนใหญ่):
{{"anomaly_detected": false, "anomaly_reason": null, "anomaly_severity": null}}

ถ้าพบ anomaly ต้อง **ใส่ quote หลักฐาน** ใน reason:
{{"anomaly_detected": true,
  "anomaly_reason": "[Category X] <คำอธิบายสั้น> — evidence: \\"<quote จาก transcript>\\"",
  "anomaly_severity": "low|medium|high"}}

ตัวอย่าง reason ที่ถูก:
- "[A1] ลูกค้าขู่จะฟ้อง — evidence: \\"ถ้าไม่แก้ผมจะฟ้องเลยนะ\\""
- "[A3] ลูกค้าขอคุยกับหัวหน้า — evidence: \\"ขอสายหัวหน้าหน่อยครับ\\""
- "[B1] พนักงานพูดไม่สุภาพ — evidence: \\"อย่ามาเรื่องมากเลย\\""

ตัวอย่าง reason ที่ **ผิด** (ห้ามทำ):
- "ลูกค้าแสดงความไม่พอใจรุนแรง" (ไม่มี quote, infer เอง) ❌
- "ลูกค้าไม่พอใจและขู่จะฟ้อง" (ไม่มี quote คำว่าฟ้องจริง) ❌

ตอบ JSON ตัวเดียว ไม่มีข้อความอื่น"""

# ---------------------------------------------------------------------------
# Speaker Diarization Post-Correction
#
# Design rationale:
#   LLM-based post-correction of automatic speaker-diarization output.
#   Leverages lexical turn-taking cues specific to Thai call-centre dialogue
#   (opening greetings, address terms, closing formulas) to reassign or
#   split mislabelled segments. Few-shot examples anchor the model on common
#   error patterns observed in production audio.
# ---------------------------------------------------------------------------
SPEAKER_CORRECTION_SYSTEM = """คุณคือ Call Center AI ของบริษัท Omazz ที่เชี่ยวชาญการแยกผู้พูดในบทสนทนา call center ภาษาไทย
ตอบเป็น JSON array ของ object เท่านั้น ห้ามมีข้อความอื่นใดนอกจาก JSON array อย่างเด็ดขาด

⛔ ห้ามเด็ดขาด:
- ห้ามตอบเป็น array ของตัวเลข เช่น [0, 1, 2] ❌
- ห้ามตอบเป็น array ของ string เช่น ["Agent", "Customer"] ❌
- ห้ามใส่ markdown fence (```json) ❌
- ห้ามอธิบายก่อน/หลัง JSON ❌
- ห้ามตอบ array ว่าง [] ถ้ามี segment ที่ต้องแก้

✅ ต้องตอบเฉพาะ: [{"idx": <int>, "speaker": "Agent"|"Customer"}, ...]
✅ หรือถ้า split: [{"idx": <int>, "parts": [{"speaker": ..., "text": ...}, ...]}, ...]
✅ ใส่เฉพาะ idx ที่ต้องแก้/split เท่านั้น (ไม่ต้องใส่ทุก idx)"""

SPEAKER_CORRECTION_USER = """บทสนทนาต่อไปนี้มาจาก call center โดยมี 2 ฝ่าย: Agent (พนักงาน) และ Customer (ลูกค้า)
ระบบ diarization อัตโนมัติอาจแยก speaker ผิด หรือรวมคำพูดของ 2 คนไว้ใน segment เดียวกัน
ให้ตรวจสอบและแก้ไขให้ถูกต้อง

== สัญญาณที่บ่งบอกว่าเป็น AGENT ==
✓ เปิดสายต้อนรับ: "สวัสดีครับ/ค่ะ [ชื่อบริษัท]", "ขอบคุณที่ติดต่อ..."
✓ เรียกอีกฝ่ายว่า "คุณลูกค้า"
✓ ขอโทษในนามบริษัท: "ต้องขออภัย...", "ขอโทษในความไม่สะดวก...", "ขออภัยแทน..."
✓ พูดในนามบริษัท: "ทางเรา...", "ทางบริษัท...", "เราจะดำเนินการ...", "จะนำไปปรับปรุง..."
✓ ให้ข้อมูล อธิบายสินค้า/บริการ/นโยบาย
✓ รับเรื่อง: "รับเรื่องไว้แล้ว...", "จะตรวจสอบให้..."
✓ ปิดสาย: "ขอบคุณที่ติดต่อนะครับ/ค่ะ", "ขอบพระคุณค่ะ/ครับ", "ยินดีให้บริการค่ะ/ครับ", "หากมีข้อสงสัยเพิ่มเติม..."
✓ **พนักงานเรียกตัวเองด้วยชื่อ** เช่น "พลอยขอ...", "พอยดู...", "เดี๋ยวพลอย..." → Agent
✓ ประสานงานภายใน: "ประสานงานกับเจ้าหน้าที่", "ตรวจสอบในระบบ", "ระบบเรา", "บริษัทเปิดทำการ"
✓ นัดหมายบริษัท: "คอนเฟิร์มวัน", "โทรคอนเฟิร์ม", "เจ้าหน้าที่จะเข้าโรงงาน"

== สัญญาณที่บ่งบอกว่าเป็น CUSTOMER ==
✓ โทรเข้ามาสอบถาม/ร้องเรียน/แจ้งปัญหา
✓ พูดถึงปัญหาของตัวเอง: "ผม/หนูรู้สึก...", "ผม/หนูโทรมาเพราะ...", "ผม/หนูต้องการ..."
✓ ตั้งคำถาม: "มีไหมคะ/ครับ...", "ได้ไหมคะ/ครับ...", "อยากทราบว่า..."
✓ แสดงความไม่พอใจ: "รู้สึกไม่ดี...", "ไม่ประทับใจ..."
✓ ตอนท้ายสายลูกค้ามักพูดว่า "โอเคค่ะ", "ขอบคุณมากค่ะ/ครับ", "ได้ค่ะ", "รับทราบค่ะ"
✓ **ลูกค้าเรียกตัวเองว่า "พี่"** + verb: "พี่สะดวก", "พี่เซฟไว้", "พี่เลือก", "พี่ให้ไว้", "พี่ติดประชุม", "พี่เมม" → Customer
✓ **ลูกค้า (ผู้ใหญ่) เรียกพนักงาน (น้อง)** ด้วยคำอ้อน: "ได้ไหมลูก", "ค่ะลูก", "นะลูก", "ยังไงลูก" → Customer
✓ ลูกค้าเรียกพนักงานว่า "น้อง" หรือชื่อตัว เช่น "พลอยจ๋า", "พลอยจ้า", "น้องลูกคะ" → Customer
✓ ลูกค้าขอเลื่อนนัด/ติดตามสินค้า: "ติดตามเรื่องการส่ง", "ขอเลื่อนวัน", "ขอเลือกวันรับ", "ไม่สามารถเข้ารับ"
✓ ลูกค้าอธิบายตารางตัวเอง: "พี่ติดประชุม", "พี่ลางาน", "พี่สะดวกวันที่..."
✓ ลูกค้าให้ข้อมูลตัวเอง: "ให้ไว้สองเบอร์", "สามีพี่เป็นคนจ่ายเงิน"

== กรณีพิเศษ: segment ที่มีคำพูดของ 2 คนปนกัน ==
ถ้า segment มีคำพูดของทั้ง Agent และ Customer ปนกันในข้อความเดียว ให้ split ออกเป็นหลาย parts ตามลำดับจริงของบทสนทนา
โดยเฉพาะกรณีต่อไปนี้ต้องพิจารณา split:
- คำถามของลูกค้า + คำตอบสั้นของพนักงาน เช่น "...ไหมคะ อ๋อ ใช่ค่ะคุณลูกค้า"
- ลูกค้าพูดต่อจากคำตอบสั้นของพนักงานในบรรทัดเดียวกัน
- คำขอบคุณของลูกค้า + คำปิดสายของพนักงานในบรรทัดเดียวกัน
โดยใส่ key "parts" แทน "speaker" ดังนี้:
{{"idx": 4, "parts": [
{{"speaker": "Customer", "text": "ข้อความส่วนของ Customer"}},
{{"speaker": "Agent", "text": "ข้อความส่วนของ Agent"}}
]}}

== ตัวอย่าง few-shot ==
[0] Customer: สวัสดีครับขอบคุณที่ติดต่อโอมาสนาครับ → ผิด (เปิดสายของบริษัท) → {{"idx":0,"speaker":"Agent"}}
[1] Agent: ผมโทรมาสอบถามเรื่องที่นอนครับ → ผิด (โทรเข้ามาสอบถาม) → {{"idx":1,"speaker":"Customer"}}
[2] Customer: ต้องขออภัยแทนเจ้าหน้าที่ด้วยนะครับ → ผิด (ขอโทษในนามบริษัท) → {{"idx":2,"speaker":"Agent"}}
[3] Agent: พี่สะดวกวันที่ 8 นี้พี่ก็สะดวกนะ พี่ลางานไปเปิดบ้าน → ผิด ("พี่สะดวก" = ลูกค้าพูดถึงตัวเอง) → {{"idx":3,"speaker":"Customer"}}
[4] Agent: หนูถ้าเป็นอังคารได้ไหมลูก วันอังคาร → ผิด ("ได้ไหมลูก" = ลูกค้าเรียกพนักงานด้วยคำอ้อน) → {{"idx":4,"speaker":"Customer"}}
[5] Customer: งั้นเดี๋ยวพลอยขอระบุในระบบนะคะ พลอยดูปฏิทินก่อน → ผิด ("พลอย" = พนักงานเรียกตัวเอง) → {{"idx":5,"speaker":"Agent"}}
[6] Agent: ติดตามเรื่องการส่งที่นอนกับเตียงที่สั่งไว้ค่ะ พี่ติดประชุมเลยจะขอเลื่อน → ผิด (ลูกค้าโทรติดตาม+อธิบายสถานการณ์ตัวเอง) → {{"idx":6,"speaker":"Customer"}}
[7] Customer: เบอร์ที่คุณลูกค้าโทรเข้ามาเป็นหมายเลขที่ใช้สั่งซื้อในระบบไหมคะ → ผิด ("คุณลูกค้า"+ตรวจสอบระบบ = Agent) → {{"idx":7,"speaker":"Agent"}}
[8] Agent: ที่นอนน้ำท่วมค่ะ...อ๋อค่ะคุณลูกค้าต้องขอโทษนะคะ → ปนกัน → {{"idx":8,"parts":[{{"speaker":"Customer","text":"ที่นอนน้ำท่วมค่ะ..."}},{{"speaker":"Agent","text":"อ๋อค่ะคุณลูกค้าต้องขอโทษนะคะ"}}]}}
[9] Customer: โอเคค่ะ ขอบคุณมากค่ะ ขอบพระคุณค่ะ สวัสดีค่ะ → ปนกัน → {{"idx":9,"parts":[{{"speaker":"Customer","text":"โอเคค่ะ ขอบคุณมากค่ะ"}},{{"speaker":"Agent","text":"ขอบพระคุณค่ะ สวัสดีค่ะ"}}]}}
[10] Agent: สวัสดีค่ะ กลุ่มบริษัทที่นอนในเครือโลตัสค่ะ สวัสดีค่ะ จะเรียกยังไงค่ะ ติดตามเรื่องการส่งที่นอน → ปนกัน (Agent greeting + Customer greeting + Customer request) → {{"idx":10,"parts":[{{"speaker":"Agent","text":"สวัสดีค่ะ กลุ่มบริษัทที่นอนในเครือโลตัสค่ะ"}},{{"speaker":"Customer","text":"สวัสดีค่ะ จะเรียกยังไงค่ะ ติดตามเรื่องการส่งที่นอน"}}]}}
  
วิเคราะห์ทุก segment โดยดู context รอบข้างด้วย ถ้ามีจุดแบ่ง turn ชัดเจนให้ split เป็นหลาย parts แทนการคง speaker เดียวทั้งบรรทัด

== ⚠️ รูปแบบ OUTPUT ที่ถูกต้อง (สำคัญที่สุด) ==
ต้องเป็น JSON array ของ object เท่านั้น — ตัวอย่างที่ถูก:
[{{"idx":0,"speaker":"Agent"}},{{"idx":1,"speaker":"Customer"}},{{"idx":3,"parts":[{{"speaker":"Customer","text":"..."}},{{"speaker":"Agent","text":"..."}}]}}]

❌ ห้ามตอบแบบนี้:
- [0, 1, 3]                        ← array ของตัวเลข (ผิด)
- ["Agent", "Customer"]            ← array ของ string (ผิด)
- {{"corrections": [...]}}         ← ห่อด้วย dict (ผิด)
- ```json [...] ```               ← markdown fence (ผิด)
- อธิบายแล้วค่อยตอบ                  ← มีข้อความก่อน (ผิด)

ใส่เฉพาะ idx ที่ต้องแก้หรือ split เท่านั้น (ไม่ต้องใส่ทุก idx ที่ถูกแล้ว)

บทสนทนา:
{conversation}"""


TRANSCRIPT_CLEANUP_SYSTEM = """คุณคือผู้เชี่ยวชาญด้านการตรวจแก้บทถอดเสียงภาษาไทยจากระบบ Call Center
หน้าที่: แก้ไขข้อความที่ผิดพลาดจาก Speech-to-Text ให้ถูกต้องตามบริบท

กฎสำคัญ:
1. แก้คำที่ถอดเสียงผิดให้ตรงกับบริบท เช่น "ไม๊คะถ" → "มั้ยคะ ถ้า", "อุปกรณ์ไผ่" → "อุทกภัย"
2. ให้ความสำคัญกับศัพท์โดเมนของงานนี้ เช่น Restonic, Omazz, กลุ่มบริษัทที่นอนโลตัส, หาดใหญ่, สุราษฎร์ธานี, อุทกภัย, เชื้อรา, ประกันโครงสร้าง, Trade-in, โปรราคาพิเศษ, ส่งกลับเข้าบริษัท
3. ถ้าบริบทชัด ให้แก้คำที่ถอดผิดเป็นศัพท์โดเมนที่ถูกต้อง เช่น "ขนาดใหญ่" → "หาดใหญ่", "อุปกรณ์ภัย" → "อุทกภัย", "เซลลา" → "เชื้อรา", "ผูกสุขลักษณะ" → "ถูกสุขลักษณะ"
4. ลบประโยคที่ไม่เกี่ยวข้องกับบทสนทนา (hallucination) เช่น เนื้อหาเกี่ยวกับกีฬา, โฆษณา, URL
5. ลบข้อความซ้ำที่เกิดจาก STT วนซ้ำ
6. ห้ามเพิ่มเนื้อหาใหม่ที่ไม่มีในต้นฉบับ ถ้าไม่มั่นใจให้คงคำเดิมไว้แทนการเดาเกินบริบท
7. ห้ามเปลี่ยนความหมายของบทสนทนา
8. รักษา format: แต่ละบรรทัดเป็น [idx] Speaker: ข้อความ
9. ตอบเฉพาะบทสนทนาที่แก้แล้ว ห้ามอธิบายเพิ่ม"""

TRANSCRIPT_CLEANUP_USER = """บทถอดเสียงจาก Call Center ต่อไปนี้มีข้อผิดพลาดจากระบบ STT อัตโนมัติ
ช่วยแก้ไขให้อ่านเข้าใจ โดยรักษาความหมายเดิม

บริบท: บริษัทที่นอน (โลตัส, Restonic, Omazz) — ลูกค้าโทรสอบถามเรื่องสินค้า/ประกัน/บริการ/น้ำท่วม/ทำความสะอาด/Trade-in/โปรราคาพิเศษ ในพื้นที่หาดใหญ่และสุราษฎร์ธานี
  
{conversation}
  
ตอบเฉพาะบทสนทนาที่แก้แล้วในรูปแบบ:
[idx] Speaker: ข้อความที่แก้แล้ว"""


def build_transcript_cleanup_prompt(conversation: str) -> tuple[str, str]:
    return TRANSCRIPT_CLEANUP_SYSTEM, TRANSCRIPT_CLEANUP_USER.format(conversation=conversation)


def build_speaker_correction_prompt(conversation: str) -> tuple[str, str]:
    return SPEAKER_CORRECTION_SYSTEM, SPEAKER_CORRECTION_USER.format(conversation=conversation)


# ---------------------------------------------------------------------------
# Case Matching — Recency-weighted LLM grouping
#
# Design rationale:
#   Groups multiple calls from the same customer into a single "case" using
#   a two-stage decision: (1) a deterministic recency short-circuit (calls
#   within CASE_RECENCY_HOURS are assumed to continue the same case,
#   consistent with session-continuation heuristics common in contact-centre
#   CRM practice), and (2) an LLM topic-similarity check for older cases.
#   The prompt explicitly instructs the model that temporal proximity is a
#   stronger signal than topic drift — reflecting real-world patterns of
#   dropped-call redials and intra-day follow-ups.
# ---------------------------------------------------------------------------

CASE_MATCH_SYSTEM = (
    "คุณเป็นผู้เชี่ยวชาญจัดกลุ่มเคสลูกค้าศูนย์บริการที่นอน (Omazz / Restonic / Lotus / Dunlopillo)\n"
    "หน้าที่: ตัดสินว่าสายใหม่เป็น **เรื่องเดียวกัน** กับเคสเดิมที่เปิดอยู่หรือเป็น **เรื่องใหม่**\n\n"
    "⚠️ **กฎสำคัญเรื่องเวลา (Recency Rule)**:\n"
    "- ถ้าสายใหม่ห่างจากสายล่าสุดในเคสไม่เกิน 1 วัน → มีแนวโน้มสูงที่เป็น **เรื่องเดียวกัน**\n"
    "  (มักเป็นสายที่โทรกลับ/สายหลุด/สายติดตามในวันเดียวกัน) แม้ topic จะดูต่าง\n"
    "- ถ้าห่างเกิน 7 วัน → มีแนวโน้มเป็นเรื่องใหม่ เว้นแต่เห็นชัดว่าติดตามเรื่องเดิม\n\n"
    "เกณฑ์ตัดสิน 'เรื่องเดียวกัน':\n"
    "- พูดถึงปัญหา/สินค้าเดียวกัน (เช่น น้ำท่วม+ที่นอนตัวเดิม, ติดตามผลเรื่องเดิม)\n"
    "- เป็นการโทรติดตาม (follow-up) ของเคสก่อนหน้า\n"
    "- หัวข้อ (topic) ตรงกันหรือเกี่ยวเนื่องกัน\n"
    "- **ห่างจากสายล่าสุดในเคสไม่เกิน 1 วัน (สัญญาณแรงกว่า topic)**\n\n"
    "เกณฑ์ตัดสิน 'เรื่องใหม่':\n"
    "- พูดถึงสินค้าคนละตัว / ปัญหาคนละเรื่อง **และ** ห่างจากสายล่าสุดเกิน 1 วัน\n"
    "- topic ต่างกันชัดเจน **และ** ไม่ใช่สายที่โทรติดต่อกันในวันเดียว\n\n"
    "ตอบเป็น JSON เท่านั้น:\n"
    '{{"match_case_id": <id ของเคสที่ตรงกัน หรือ null ถ้าเป็นเรื่องใหม่>, '
    '"reason": "<เหตุผลสั้นๆ ภาษาไทย>", '
    '"suggested_subject": "<หัวข้อเคส ภาษาไทย สั้นกระชับ เช่น สอบถามประกันน้ำท่วม>"}}'
)

CASE_MATCH_USER = (
    "สายใหม่ที่เพิ่งวิเคราะห์:\n"
    "- Topic: {new_topic}\n"
    "- Summary: {new_summary}\n\n"
    "เคสที่เปิดอยู่ของลูกค้าคนนี้:\n{existing_cases}\n\n"
    "ตอบ JSON:"
)


def _format_recency(latest_iso: str | None) -> str:
    """Render a human-readable 'last call was N ago' hint for the LLM prompt."""
    if not latest_iso:
        return "(ไม่มีข้อมูลเวลา)"
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(latest_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        total_min = int(delta.total_seconds() / 60)
        if total_min < 60:
            return f"{total_min} นาทีที่แล้ว"
        if total_min < 60 * 24:
            return f"{total_min // 60} ชม. {total_min % 60} นาทีที่แล้ว"
        return f"{total_min // (60 * 24)} วันที่แล้ว"
    except (ValueError, TypeError):
        return latest_iso


def build_case_match_prompt(
    new_topic: str, new_summary: str, existing_cases: list[dict]
) -> tuple[str, str]:
    if not existing_cases:
        cases_text = "(ไม่มีเคสเดิม)"
    else:
        parts = []
        for cs in existing_cases:
            recency = _format_recency(cs.get("latest_call_at"))
            parts.append(
                f"- เคส #{cs['id']} [{cs['status']}]: \"{cs['subject']}\"\n"
                f"  สายล่าสุดในเคส: {recency}\n"
                f"  สรุปสายในเคส: {cs.get('call_summaries', '-')}"
            )
        cases_text = "\n".join(parts)
    return CASE_MATCH_SYSTEM, CASE_MATCH_USER.format(
        new_topic=new_topic, new_summary=new_summary, existing_cases=cases_text
    )


def build_extraction_prompt(conversation: str) -> tuple[str, str]:
    return EXTRACTION_SYSTEM, EXTRACTION_USER.format(conversation=conversation)


def build_sentiment_prompt(conversation: str) -> tuple[str, str]:
    return SENTIMENT_SYSTEM, SENTIMENT_USER.format(conversation=conversation)


def build_agent_qa_prompt(conversation: str) -> tuple[str, str]:
    return AGENT_QA_SYSTEM, AGENT_QA_USER.format(conversation=conversation)


def build_anomaly_prompt(conversation: str) -> tuple[str, str]:
    return ANOMALY_SYSTEM, ANOMALY_USER.format(conversation=conversation)
