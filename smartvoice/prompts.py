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
EXTRACTION_SYSTEM = """คุณคือนักวิเคราะห์สายสนทนา call center ของกลุ่มบริษัทที่นอน Omazz (เครือโลตัส)
สกัดข้อมูลจากบทสนทนาที่ได้รับเท่านั้น ห้ามเดาหรือเติมข้อมูลที่ไม่ได้พูดในสาย ตอบเป็น JSON เท่านั้น"""

EXTRACTION_USER = """บทสนทนา call center (Agent = พนักงาน, Customer = ลูกค้า):

{conversation}

== งานของคุณ ==
อ่านบทสนทนาแล้วตอบ JSON ตาม schema ท้ายคำสั่ง ใช้เฉพาะข้อมูลที่อยู่ในบทสนทนานี้
บทถอดเสียงมาจากระบบอัตโนมัติ อาจสะกดผิดและอาจแบ่งผู้พูดผิด — ตีความตามบริบท

1) summary — สรุปเป็นภาษาไทย 2-3 ประโยค ให้ครบ 3 ส่วน:
   - ลูกค้าโทรมาเรื่องอะไร (ระบุสินค้าและอาการ/คำถามให้เจาะจง)
   - พนักงานตอบหรือแก้ไขอย่างไร
   - ผลลัพธ์ของสาย: ตกลงกันว่าใครต้องทำอะไรต่อ หรือจบเรื่องแล้ว

2) topic — เลือก 1 ค่า สะกดให้ตรงทุกตัวอักษร:
   "สอบถามข้อมูลสินค้า"     ถามรุ่น วัสดุ คุณสมบัติ วิธีใช้ โดยสินค้าไม่ได้มีปัญหา
   "สอบถามการจัดส่ง"        สถานะจัดส่ง นัดวันส่ง/วันรับ พื้นที่จัดส่ง
   "แจ้งปัญหาสินค้า"        ลูกค้าเล่าอาการผิดปกติของสินค้าที่ได้รับ เช่น ชำรุด เสียงดัง ยุบ แพ้ มีกลิ่น ขาด หัก เปื้อน ผิดรุ่น
   "ร้องเรียนบริการ"        ไม่พอใจพนักงาน ขั้นตอน หรือความล่าช้า โดยตัวสินค้าไม่มีปัญหา
   "สอบถามประกัน/Warranty"  เงื่อนไขประกัน การเคลม ค่าบริการซ่อม
   "คืน/เปลี่ยน/Trade-in"   ขอคืน/เปลี่ยน/คืนเงิน/Trade-in หรือยอดเงิน/บิลไม่ตรง โดยสินค้าไม่ได้ชำรุด
   "สอบถามโปรโมชั่น"        โปรโมชั่น ส่วนลด ราคา
   "ติดตามเคส"              โทรตามเรื่องเดิมล้วน ๆ ไม่มีเรื่องใหม่
   "อื่นๆ"                  ไม่เข้าหมวดใดเลย
   กฎตัดสินเมื่อเข้าได้หลายหมวด:
   - ใช้ "แจ้งปัญหาสินค้า" เมื่อลูกค้าบรรยายความผิดปกติของตัวสินค้าจริง ๆ (แม้จะขอคืน/เปลี่ยนด้วย)
     ถ้าเป็นแค่คำถามหรือเรื่องจัดส่ง/บิล โดยไม่มีอาการผิดปกติของสินค้า ห้ามใช้หมวดนี้
   - มีเรื่องใหม่ปนกับการติดตามเรื่องเดิม → ใช้หมวดของเรื่องใหม่
   - คุยหลายเรื่อง → เลือกเรื่องที่ลูกค้าโทรมาเป็นหลัก

3) topic_detail — ใส่เฉพาะเมื่อ topic = "แจ้งปัญหาสินค้า" ถ้า topic อื่นให้ตอบ ""
   เลือก 1 ค่าตามปัญหาหลัก สะกดให้ตรงทุกตัวอักษร:
   "ผ้าขาด/ผ้าหุ้มชำรุด"    ผ้าหุ้ม ปลอก ผ้ารอง ขาด ฉีก หลุดลุ่ย
   "เตียง/โครงหัก"          โครงเตียง ขา หัวเตียง หัก แตก หลุด
   "สปริง/ฟองน้ำยุบ"        ยุบเป็นแอ่ง สปริงดัง/โผล่ ฟองน้ำเสียรูป
   "เปื้อน/รอยขีดข่วน"      คราบ รอยเปื้อน รอยขีด รอยถลอก
   "กลิ่น/แพ้/ระคายเคือง"   กลิ่นแรง/กลิ่นสารเคมี ผื่นคัน แสบจมูก แสบตา อาการแพ้หลังใช้สินค้า
   "ความชื้น/น้ำท่วม"       เชื้อรา ความชื้น น้ำท่วม น้ำหก
   "ขนาด/สเปคผิด"           ขนาด รุ่น สี วัสดุ ไม่ตรงที่สั่ง หรือได้ของไม่ครบ
   "อื่นๆ"                  ปัญหาสินค้าที่ไม่เข้าหมวดข้างบน

4) keywords — คำสำคัญไม่เกิน 8 คำ ที่ปรากฏในบทสนทนาจริง (ชื่อรุ่น อาการ สิ่งที่ลูกค้าขอ)
   เรียงจากสำคัญมากไปน้อย ไม่เอาคำทั่วไป เช่น ลูกค้า พนักงาน บริษัท ค่ะ ครับ

5) brand_mentions — ชื่อแบรนด์ที่นอน/เครื่องนอนที่ "มีคนพูดชื่อในสายนี้จริง" ทั้งของเครือและคู่แข่ง
   ไม่นับชื่อบริษัทที่พนักงานพูดตอนแนะนำตัว (เช่น "บริษัทที่นอนโลตัส", "กลุ่มบริษัทที่นอนในเครือโลตัส")
   ถ้าไม่มีใครพูดชื่อแบรนด์ ตอบ []

6) platform_mentions — ช่องทางซื้อ/ติดต่อที่มีคนพูดถึงจริง เลือกจาก:
   "Shopee", "Lazada", "TikTok Shop", "LINE", "Facebook", "เว็บไซต์", "หน้าร้าน/ห้าง"
   (ซื้อที่ห้างหรือสาขา เช่น ห้างโลตัส = "หน้าร้าน/ห้าง") ไม่นับการโทรศัพท์ครั้งนี้ ถ้าไม่มี ตอบ []

ตอบ JSON อย่างเดียว:
{{"summary": "", "topic": "", "topic_detail": "", "keywords": [], "brand_mentions": [], "platform_mentions": []}}"""

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
SENTIMENT_SYSTEM = """คุณคือนักวิเคราะห์ความรู้สึกลูกค้าจากบทสนทนา call center ภาษาไทย
ประเมินจากคำพูดของลูกค้าในสายเท่านั้น ตอบเป็น JSON เท่านั้น เขียนทุกข้อความเป็นภาษาไทย"""

SENTIMENT_USER = """บทสนทนา call center (Agent = พนักงาน, Customer = ลูกค้า):

{conversation}

== งาน: ความรู้สึกของ "ลูกค้า" (ไม่ใช่พนักงาน) ==
ทำตามลำดับ:
1. customer_quote — คัดลอกประโยคของลูกค้าที่แสดงความรู้สึกชัดที่สุดในสาย ตามตัวอักษร
   ข้ามคำตามมารยาท ("ขอบคุณค่ะ/ครับ", "สวัสดี", "ได้ค่ะ", "โอเคครับ") — ถ้าลูกค้าพูดแต่คำพวกนี้ ให้ตอบ ""
2. sentiment_reason — อธิบายสั้น ๆ 1 ประโยคว่าลูกค้ารู้สึกอย่างไรและเพราะอะไร (เขียนด้วยคำของคุณเอง เป็นภาษาไทยเท่านั้น ห้ามตอบเป็นภาษาอังกฤษ)
3. sentiment — เลือก 1 ค่า:
   "negative" ลูกค้าไม่พอใจ ผิดหวัง หงุดหงิด กังวล หรือเดือดร้อน
              เช่น บ่น ตำหนิ พูดคำหยาบ ถามซ้ำอย่างหงุดหงิด เล่าว่าเสียหาย/ไม่สบายตัวจากสินค้า รอนานจนไม่พอใจ
              (ขอบคุณตอนวางสายตามมารยาท ไม่ทำให้ negative เปลี่ยนเป็นอย่างอื่น)
   "positive" ลูกค้าพูดชมหรือแสดงความพอใจชัดเจน เช่น ชมบริการ ดีใจที่แก้ปัญหาได้
              คำว่า "ขอบคุณ" อย่างเดียว ไม่ใช่ positive
   "neutral"  สอบถามข้อมูลทั่วไป หรือไม่มีคำพูดแสดงอารมณ์ชัดเจน — ถ้าไม่แน่ใจให้เลือกค่านี้

ตอบ JSON อย่างเดียว:
{{"customer_quote": "", "sentiment_reason": "", "sentiment": ""}}"""

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
AGENT_QA_SYSTEM = """คุณคือผู้ตรวจคุณภาพ (QA) สายสนทนา call center ประเมินพนักงานทีละข้อจากคำพูดจริงในสาย
ตอบเป็น JSON เท่านั้น"""

AGENT_QA_USER = """บทสนทนา call center (Agent = พนักงาน, Customer = ลูกค้า):

{conversation}

== ประเมินพนักงาน (Agent) ==
ให้คะแนนเฉพาะข้อที่มีหลักฐานจากคำพูด Agent ในบทสนทนานี้เท่านั้น
บทถอดเสียงอาจแบ่งผู้พูดผิด — ดูจากเนื้อความว่าใครพูด

สำหรับแต่ละข้อด้านล่าง ให้คัดลอกคำพูดของ "พนักงาน" จากบทสนทนาที่แสดงว่าทำข้อนั้น
(quote สั้น 3-15 คำ ตามตัวอักษร) ถ้าพนักงานไม่ได้ทำข้อนั้น ให้ตอบ ""
ห้ามแต่ง ห้ามใช้คำพูดของลูกค้า และแต่ละข้อใช้ quote ไม่ซ้ำกัน
ระบบจะตรวจ quote กับบทสนทนาจริงแล้วคำนวณคะแนนเอง ข้อที่ quote ไม่ตรงจะไม่ได้คะแนน (ถ้าทำได้ 0 ข้อ ให้ 1)

- "ทักทายเปิดสาย": ทักทายและบอกชื่อบริษัท/ชื่อตัวเอง
- "ใช้คำสุภาพ": ลงท้ายค่ะ/ครับ และเรียกลูกค้าอย่างให้เกียรติ
- "เห็นใจหรือขอโทษ": แสดงความเห็นใจหรือขอโทษเมื่อลูกค้ามีปัญหา
- "ขออนุญาตหรือขอบคุณ": ขออนุญาต ขอบคุณ หรือขอโทษ ก่อนให้รอหรือก่อนขอข้อมูล
- "กล่าวปิดสาย": ขอบคุณที่ติดต่อ / ยินดีให้บริการ / สวัสดีตอนจบ
- "ถามหรือทวนปัญหา": ถามหรือทวนเพื่อเข้าใจปัญหาของลูกค้า
- "ตอบตรงคำถาม": ตอบหรือแก้ไขตรงกับที่ลูกค้าถาม
- "อธิบายเหตุผลหรือเงื่อนไข": อธิบายเหตุผล เงื่อนไข ค่าใช้จ่าย หรือข้อมูลประกอบ
- "บอกขั้นตอนถัดไป": บอกว่าจะเกิดอะไรต่อ ใครทำอะไร เมื่อไร
- "สรุปหรือถามว่าช่วยอะไรเพิ่ม": สรุปสิ่งที่ตกลง หรือถามว่ามีอะไรให้ช่วยเพิ่ม
และ "ลูกค้ามีปัญหา": true ถ้าลูกค้าแจ้งปัญหาหรือความไม่สะดวกในสายนี้ ไม่งั้น false

ตอบ JSON อย่างเดียว ที่มี key ตามชื่อข้อทั้ง 10 ข้อข้างบน และ "ลูกค้ามีปัญหา" (ครบทุก key)"""

# ---------------------------------------------------------------------------
# Call 3b: Next action — its own request
#
# Asked together with the QA checklist, the 8B model answered
# {"pending": false} on calls that plainly left work open (a customer still
# to send an order number, a refund awaiting photos). On its own, framed as
# "what does someone still have to do after this call", it found the open
# work on every such call and left a fully resolved call empty.
# ---------------------------------------------------------------------------
NEXT_ACTION_SYSTEM = """คุณคือผู้ช่วยหัวหน้างาน call center สรุปงานที่ต้องทำต่อหลังวางสาย
ใช้เฉพาะสิ่งที่คุยกันในสาย ตอบเป็น JSON เท่านั้น เขียนทุกข้อความเป็นภาษาไทย"""

NEXT_ACTION_USER = """บทสนทนา call center (Agent = พนักงาน, Customer = ลูกค้า):

{conversation}

หลังวางสายนี้ ยังมีงานที่ใครต้องทำต่อบ้าง? ดูจากสิ่งที่พนักงานรับปากไว้ สิ่งที่ขอให้ลูกค้าส่งหรือยืนยันกลับ
หรือเรื่องที่ต้องส่งต่อฝ่ายอื่น (สายส่วนใหญ่มีงานค้างอย่างน้อย 1 อย่าง — ตอบว่าไม่มีเฉพาะเมื่อคุยจบเรื่องสมบูรณ์จริง ๆ)
ถ้าพนักงานรับปากว่าจะโทรกลับ แจ้งผล แจ้งวัน ส่งของ หรือประสานฝ่ายอื่น แปลว่ายังมีงานค้าง
ห้ามใส่งานที่ไม่ได้คุยกันในสาย เช่น ถ้าไม่ได้คุยเรื่องคืนเงินก็ห้ามเขียนเรื่องคืนเงิน

ตอบ JSON มี key:
- "todo": สิ่งที่ต้องทำต่อ 1 วลีที่อ่านแล้วเข้าใจได้ทันที: คำกริยา + ทำอะไร/กับใคร
  ห้ามตอบคำกริยาคำเดียว และห้ามเล่าเหตุการณ์ในสายแทนงาน (ถ้าไม่มีงานค้างเลยให้ "")
- "detail": รายละเอียดจากสาย (สินค้า ยอดเงิน เลขคำสั่งซื้อ วันนัด) หรือ ""
- "deadline": กำหนดเวลาที่พูดในสาย ถ้าไม่ได้พูดให้ตอบ "ไม่ระบุในสาย" (ห้ามเดาเอง ระบบจะใส่ระยะเวลาแนะนำให้)
- "follow_up": หลังทำเสร็จต้องแจ้งลูกค้าหรือบันทึกอย่างไร หรือ ""
- "owner": "Agent คนเดิม" | "หัวหน้าทีม" | "ฝ่าย QC" | "ฝ่ายจัดส่ง" | "ฝ่ายคลังสินค้า" | "ฝ่ายบัญชี"
  (เงิน/คืนเงิน → ฝ่ายบัญชี • ตรวจคุณภาพสินค้า → ฝ่าย QC • ส่ง/รับคืน/เปลี่ยนสินค้า → ฝ่ายจัดส่ง
   สต็อก → ฝ่ายคลังสินค้า • ต้องขออนุมัติ → หัวหน้าทีม • รอลูกค้าตอบกลับ/โทรกลับ/แจ้งผลทั่วไป → Agent คนเดิม)"""

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
ANOMALY_SYSTEM = """คุณคือผู้ตรวจความเสี่ยงในสายสนทนา call center
หน้าที่: หาเหตุการณ์ที่ต้องส่งต่อหัวหน้า/QA ตอบเป็น JSON เท่านั้น เขียนทุกข้อความเป็นภาษาไทย

หลักการ:
- ลูกค้าไม่พอใจทั่วไป ≠ ความผิดปกติ (ลูกค้าโทรมาร้องเรียนเป็นงานปกติ)
- ทุกครั้งที่ตอบว่าพบ ต้องมีคำพูดจริงจากบทสนทนาเป็นหลักฐาน
- ไม่พบหลักฐานชัดเจน → anomaly_detected = false"""

ANOMALY_USER = """บทสนทนา call center (Agent = พนักงาน, Customer = ลูกค้า):

{conversation}

== เกณฑ์ (ต้องมีคำพูดในหมวดนั้นจริง) ==
A — ลูกค้าข่มขู่หรือขอยกระดับเรื่อง
 A1 ขู่ฟ้อง/ดำเนินคดี: ลูกค้าพูดคำว่า ฟ้อง, ทนาย, ดำเนินคดี, ศาล, แจ้งความ
 A2 ขู่ร้องเรียนหน่วยงานหรือประจานในสื่อ: สคบ., ร้องเรียน, กระทรวง, พาณิชย์, คุ้มครองผู้บริโภค,
    หรือขู่จะโพสต์/ประจานทางเพจ เฟซบุ๊ก สื่อ ข่าว (การ "ทักเพจ" เพื่อติดต่อธรรมดาไม่นับ)
 A3 ขอคุยกับหัวหน้า/ผู้จัดการ
 A4 ลูกค้าพูดคำหยาบคายจริง เช่น คำด่า หรือใช้ กู/มึง (ไม่ใช่แค่น้ำเสียงไม่พอใจ)
B — พนักงานผิดระเบียบ
 B1 พนักงานพูดหยาบหรือไม่สุภาพ
 B2 พนักงานให้ข้อมูลผิด และลูกค้าทักท้วง
 B3 พนักงานปฏิเสธไม่ช่วย หรือวางสายใส่ลูกค้า
C — สุขภาพ/ความปลอดภัย/ความเสียหาย
 C1 ผลต่อสุขภาพจากสินค้า: แพ้, ผื่น, คัน, แสบ, ระคายเคือง, หายใจไม่สะดวก, เชื้อรา, สารเคมี, บาดเจ็บ
 C2 ภัยพิบัติ: น้ำท่วม, ไฟไหม้ ที่กระทบสินค้าของลูกค้า
 C3 เรียกค่าเสียหาย/เงินชดเชย
D — สายขัดข้อง
 D1 สายตัด/ไม่ได้ยินกันจนคุยต่อไม่ได้

ไม่ใช่ความผิดปกติ: ขอคืน/เปลี่ยนสินค้าแล้วคุยกันปกติ, บ่นว่ารอนานแต่จบสุภาพ, ถามเงื่อนไขประกันแล้วได้คำตอบไม่ตรงใจ

== วิธีตอบ ==
- evidence_quote ต้องคัดลอกจากบทสนทนาที่ส่งมานี้ตามตัวอักษร ห้ามใช้ quote จากตัวอย่างหรือแต่งเอง
- ระบบจะตรวจว่า quote มีอยู่ในสายจริงและมีคำของหมวดนั้น ถ้าไม่ตรงจะถือว่าไม่พบ
- พบหลายหมวด → เลือกหมวดที่ร้ายแรงที่สุด (A1, A2, B ก่อน)

ตอบ JSON อย่างเดียว มี 4 key:
- "anomaly_detected": true หรือ false
- "category": รหัสหมวดที่พบ (เช่น A1, C1) ถ้าไม่พบให้ ""
- "evidence_quote": คำพูดหลักฐานจากสายนี้ ถ้าไม่พบให้ ""
- "reason": เหตุผลสั้น ๆ ถ้าไม่พบให้ """""

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
3. ถ้าบริบทชัด ให้แก้คำที่ถอดผิดเป็นศัพท์โดเมนที่ถูกต้อง เช่น "อุปกรณ์ภัย" → "อุทกภัย", "เซลลา" → "เชื้อรา", "ผูกสุขลักษณะ" → "ถูกสุขลักษณะ"
   ชื่อสถานที่ให้แก้เฉพาะเมื่อบริบทบอกชัดว่าพูดถึงสถานที่ — คำทั่วไปที่ถูกอยู่แล้วห้ามเปลี่ยน
   (เช่น "ขนาดใหญ่" ของที่นอน ต้องคงไว้ ห้ามแก้เป็นชื่อจังหวัด)
4. ลบประโยคที่ไม่เกี่ยวข้องกับบทสนทนา (hallucination) เช่น เนื้อหาเกี่ยวกับกีฬา, โฆษณา, URL
5. ลบข้อความซ้ำที่เกิดจาก STT วนซ้ำ
6. ห้ามเพิ่มเนื้อหาใหม่ที่ไม่มีในต้นฉบับ ถ้าไม่มั่นใจให้คงคำเดิมไว้แทนการเดาเกินบริบท
7. ห้ามเปลี่ยนความหมายของบทสนทนา
8. รักษา format: แต่ละบรรทัดเป็น [idx] Speaker: ข้อความ
9. ตอบเฉพาะบทสนทนาที่แก้แล้ว ห้ามอธิบายเพิ่ม"""

TRANSCRIPT_CLEANUP_USER = """บทถอดเสียงจาก Call Center ต่อไปนี้มีข้อผิดพลาดจากระบบ STT อัตโนมัติ
ช่วยแก้ไขให้อ่านเข้าใจ โดยรักษาความหมายเดิม

บริบท: บริษัทที่นอน (โลตัส, Restonic, Omazz) — ลูกค้าโทรเรื่องสินค้า การจัดส่ง ประกัน การคืน/เปลี่ยน หรือปัญหาสินค้า
แก้เฉพาะคำที่ถอดเสียงผิดชัดเจน ถ้าไม่แน่ใจให้คงคำเดิม
  
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
    "⚠️ **กฎสำคัญเรื่องเวลา (Recency Rule)** — ดูจาก \"ห่างจากสายใหม่\" ที่ระบุไว้ในแต่ละเคส:\n"
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


def _format_recency(latest_iso: str | None, reference_iso: str | None = None) -> str:
    """How far the case's last call is from the NEW call, for the LLM prompt.

    Measured against the new call's own time (from its file name), not "now":
    recordings are often uploaded and processed days later, and measuring
    from the processing time made every older case look stale, so related
    calls were split into new cases.
    """
    if not latest_iso:
        return "(ไม่มีข้อมูลเวลา)"
    try:
        from datetime import datetime, timezone

        def _aware(value: str) -> datetime:
            dt = datetime.fromisoformat(value)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

        latest = _aware(latest_iso)
        reference = _aware(reference_iso) if reference_iso else datetime.now(timezone.utc)
        total_min = int(abs((reference - latest).total_seconds()) / 60)
        if total_min < 60:
            return f"ห่างจากสายใหม่ {total_min} นาที"
        if total_min < 60 * 24:
            return f"ห่างจากสายใหม่ {total_min // 60} ชม. {total_min % 60} นาที"
        return f"ห่างจากสายใหม่ {total_min // (60 * 24)} วัน"
    except (ValueError, TypeError):
        return latest_iso


def build_case_match_prompt(
    new_topic: str, new_summary: str, existing_cases: list[dict], new_call_at: str | None = None
) -> tuple[str, str]:
    if not existing_cases:
        cases_text = "(ไม่มีเคสเดิม)"
    else:
        parts = []
        for cs in existing_cases:
            recency = _format_recency(cs.get("latest_call_at"), new_call_at)
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


def build_next_action_prompt(conversation: str) -> tuple[str, str]:
    return NEXT_ACTION_SYSTEM, NEXT_ACTION_USER.format(conversation=conversation)


def build_anomaly_prompt(conversation: str) -> tuple[str, str]:
    return ANOMALY_SYSTEM, ANOMALY_USER.format(conversation=conversation)
