"""Checks applied to LLM answers before they are saved (smartvoice.insight_rules).

Each case below comes from a real failure seen on the 11 production calls
with the previous prompts.
"""

from smartvoice import insight_rules as ir
from smartvoice import ollama_client, prompts

CALL = (
    "Agent: สวัสดีค่ะ กลุ่มบริษัทที่นอนในเครือโลตัสค่ะ\n"
    "Customer: พี่ซื้อที่นอนไป นอนแล้วเป็นผื่นคันแสบจมูกเลยค่ะ\n"
    "Agent: ต้องขออภัยด้วยนะคะ ขออนุญาตขอเลขคำสั่งซื้อหน่อยค่ะ\n"
    "Customer: สั่งทางช้อปปี้ค่ะ\n"
    "Agent: เดี๋ยวส่งเรื่องให้ QC ตรวจสอบนะคะ ขอบคุณที่ติดต่อเข้ามาค่ะ"
)
AGENT = ir.speaker_text(CALL, "Agent")


# ── Quotes ───────────────────────────────────────────────────────────────

def test_quote_found_despite_spacing_and_punctuation():
    assert ir.quote_in_text("ต้องขออภัย ด้วยนะคะ", AGENT)
    assert ir.quote_in_text("'ขอบคุณที่ติดต่อเข้ามาค่ะ'", AGENT)


def test_quote_with_a_small_drift_still_counts():
    # Model dropped "นะ" when copying the line.
    assert ir.quote_in_text("เดี๋ยวส่งเรื่องให้ QC ตรวจสอบคะ", AGENT)


def test_invented_or_trivial_quotes_do_not_count():
    assert not ir.quote_in_text("เข้าใจเลยค่ะ", AGENT)        # the old prompt's example
    assert not ir.quote_in_text("ค่ะ", AGENT)                  # too short to prove anything
    assert not ir.quote_in_text("", AGENT)


def test_customer_lines_are_not_agent_evidence():
    assert not ir.quote_in_text("นอนแล้วเป็นผื่นคันแสบจมูก", AGENT)
    assert ir.quote_in_text("นอนแล้วเป็นผื่นคันแสบจมูก", ir.speaker_text(CALL, "Customer"))


def test_unlabelled_transcript_falls_back_to_all_text():
    assert ir.speaker_text("สวัสดีค่ะ\nครับ", "Agent") == "สวัสดีค่ะ\nครับ"


# ── Speaker-correction splits ────────────────────────────────────────────

SEGMENT = "ค่ะ คุณลูกค้า ค่ะ ต้องการติดตามคำร้องที่ส่งไปทางอีเมลค่ะ คุณลูกค้ามีแจ้งเกี่ยวกับเรื่องอะไรเข้ามานะคะ"


def test_a_split_into_the_segments_own_words_is_kept():
    assert ir.split_keeps_text(
        ["ค่ะคุณลูกค้า", "ค่ะ ต้องการติดตามคำร้องที่ส่งไปทางอีเมลค่ะ", "คุณลูกค้ามีแจ้งเกี่ยวกับเรื่องอะไรเข้ามานะคะ"],
        SEGMENT,
    )
    # fixing a particle is still the same speech
    assert ir.split_keeps_text(["ค่ะ คุณลูกค้า", "ค่ะ ต้องการติดตามคำร้องที่ส่งไปทางอีเมลค่ะ คุณลูกค้ามีแจ้งเกี่ยวกับเรื่องอะไรเข้ามานะค่ะ"], SEGMENT)


def test_a_split_filled_with_prompt_text_is_rejected():
    # call 295: the model wrote its own prompt's agent cues into the transcript
    leaked = 'สวัสดีครับ/ค่ะ [ชื่อบริษัท] ขอบคุณที่ติดต่อ... เรียกอีกฝ่ายว่า "คุณลูกค้า" ขอโทษในนามบริษัท ตั้งคำถาม'
    assert not ir.split_keeps_text(["ค่ะ คุณลูกค้า", leaked], SEGMENT)
    assert not ir.split_keeps_text([leaked + " ต้องการติดตามคำร้องที่ส่งไปทางอีเมลค่ะ"], SEGMENT)


def test_a_split_that_drops_much_of_the_segment_is_rejected():
    assert not ir.split_keeps_text(["ค่ะ คุณลูกค้า", "ค่ะ ต้องการติดตาม"], SEGMENT)
    assert not ir.split_keeps_text([], SEGMENT)


# ── QA scoring ───────────────────────────────────────────────────────────

def test_score_counts_only_verified_items():
    answer = {
        "P1": {"done": True, "quote": "สวัสดีค่ะ กลุ่มบริษัทที่นอนในเครือโลตัสค่ะ"},
        "P2": {"done": True, "quote": "ขออนุญาตขอเลขคำสั่งซื้อหน่อยค่ะ"},
        "P3": {"applicable": True, "done": True, "quote": "เข้าใจเลยค่ะ"},   # not said
        "P4": {"done": False, "quote": ""},
        "P5": {"done": True, "quote": "ขอบคุณที่ติดต่อเข้ามาค่ะ"},
    }
    score, evidence = ir.score_items(answer, ir.POLITENESS_ITEMS, AGENT)
    assert score == 3   # 3 of 5
    assert "คำพูดที่อ้างไม่พบในสาย" in evidence
    assert "กล่าวปิดสาย ('ขอบคุณที่ติดต่อเข้ามาค่ะ')" in evidence


def test_not_applicable_item_is_left_out_of_the_score():
    answer = {key: {"done": True, "quote": "ขอบคุณที่ติดต่อเข้ามาค่ะ"} for key in ir.POLITENESS_ITEMS}
    answer["P3"] = {"applicable": False, "done": False, "quote": ""}
    score, _ = ir.score_items(answer, ir.POLITENESS_ITEMS, AGENT)
    assert score == 5   # 4 of 4 applicable


def test_nothing_verified_scores_one():
    score, evidence = ir.score_items({}, ir.PROBLEM_SOLVING_ITEMS, AGENT)
    assert score == 1
    assert evidence.startswith("ทำได้: ไม่มี")


def test_itemised_answer_drives_evaluate_agent_qa(monkeypatch):
    import json

    answer = {
        "P1": {"done": True, "quote": "สวัสดีค่ะ กลุ่มบริษัทที่นอนในเครือโลตัสค่ะ"},
        "S4": {"done": True, "quote": "เดี๋ยวส่งเรื่องให้ QC ตรวจสอบนะคะ"},
        "next_action": {"pending": True, "todo": "ส่งที่นอนให้ QC ตรวจสอบ", "detail": "", "deadline": "ไม่ระบุในสาย",
                        "follow_up": "โทรแจ้งลูกค้าที่ <เบอร์ลูกค้า>", "owner": "ฝ่าย QC"},
    }
    monkeypatch.setattr(ollama_client, "chat", lambda *a, **k: json.dumps(answer, ensure_ascii=False))
    ap = json.loads(ollama_client.evaluate_agent_qa(CALL)["agent_performance"])

    # P1 quoted + P2 measured from the transcript (every agent line ends with ค่ะ) = 2 of 5;
    # S4 quoted = 1 of 5.
    assert (ap["politeness"], ap["problem_solving"]) == (2, 1)
    assert ap["overall_score"] == 3
    assert ap["next_action"] == "ส่งที่นอนให้ QC ตรวจสอบ | ไม่ระบุในสาย (แนะนำ: ภายใน 3-5 วัน) | โทรแจ้งลูกค้า"
    assert ap["next_action_owner"] == "ฝ่าย QC"


# ── Next action ──────────────────────────────────────────────────────────

def test_nothing_pending_means_case_closed():
    assert ir.build_next_action({"pending": False, "todo": "x"}, CALL) == (ir.CLOSED_NEXT_ACTION, "ไม่มี")


def test_template_leftovers_are_removed():
    assert ir.clean_next_action_text(
        "ติดตามการโอนเงินคืน | [บริบท/รายละเอียด] | ภายใน 7 วันทำการ | โทรแจ้งลูกค้าที่ <เบอร์ที่ลูกค้าให้ไว้> หลังดำเนินการเสร็จ"
    ) == "ติดตามการโอนเงินคืน | ภายใน 7 วันทำการ | โทรแจ้งลูกค้า หลังดำเนินการเสร็จ"
    assert ir.clean_next_action_text("ทำ X | [บริบท]: ตัวที่นอน | [กำหนดเวลา]: 3 วัน") == "ทำ X | ตัวที่นอน | 3 วัน"


def test_refund_on_a_call_without_money_talk_is_rejected():
    # Real case: a question about body weight on a mattress got "ติดตามการโอนเงินคืน".
    weight_call = "Customer: น้ำหนักตัวประมาณห้าสิบ ที่นอนยุบไหมคะ\nAgent: ไม่ยุบค่ะ"
    assert ir.money_action_is_ungrounded("กรุณาติดตามผลการโอนเงินคืน", weight_call)
    assert not ir.money_action_is_ungrounded("กรุณาติดตามผลการโอนเงินคืน", "Customer: ขอคืนเงิน 2,770 บาท")
    assert not ir.money_action_is_ungrounded("ส่งที่นอนให้ QC", weight_call)

    replaced, _ = ollama_client.sanitize_next_action("ติดตามการโอนเงินคืน", "ฝ่ายบัญชี", weight_call)
    assert "เงิน" not in replaced


# ── Anomaly ──────────────────────────────────────────────────────────────

def test_health_complaint_is_flagged_with_severity_from_the_category():
    out = ir.verify_anomaly(
        {"anomaly_detected": True, "category": "C1", "evidence_quote": "นอนแล้วเป็นผื่นคันแสบจมูกเลยค่ะ", "reason": "ลูกค้าแพ้ที่นอน"},
        CALL,
    )
    assert out["anomaly_detected"] and out["anomaly_severity"] == "medium"
    assert out["anomaly_reason"].startswith("[C1] ลูกค้าแพ้ที่นอน — evidence:")


CALM_CALL = "Agent: สวัสดีค่ะ\nCustomer: สั่งทางช้อปปี้ค่ะ ส่งวันไหนคะ\nAgent: พรุ่งนี้ค่ะ"


def test_flag_without_a_real_quote_is_dropped():
    assert not ir.verify_anomaly({"anomaly_detected": True, "category": "A1", "evidence_quote": "ถ้าไม่แก้ผมจะฟ้องเลยนะ"}, CALM_CALL)["anomaly_detected"]
    assert not ir.verify_anomaly({"anomaly_detected": True, "category": "A1"}, CALM_CALL)["anomaly_detected"]


def test_quote_must_carry_its_category_keyword():
    # "สั่งทางช้อปปี้ค่ะ" is real but proves no threat.
    out = ir.verify_anomaly({"anomaly_detected": True, "category": "A2", "evidence_quote": "สั่งทางช้อปปี้ค่ะ"}, CALM_CALL)
    assert not out["anomaly_detected"]


def test_customer_health_complaint_is_caught_even_when_the_model_misses_it():
    out = ir.verify_anomaly({"anomaly_detected": False}, CALL)
    assert out["anomaly_detected"] and out["anomaly_severity"] == "medium"
    assert out["anomaly_reason"].startswith("[C1]") and "ผื่นคัน" in out["anomaly_reason"]


def test_agent_repeating_the_words_does_not_trigger_the_backstop():
    call = "Agent: ลูกค้าแจ้งว่าแพ้ที่นอนใช่ไหมคะ\nCustomer: ไม่ใช่ค่ะ ถามเรื่องส่งของ"
    assert not ir.verify_anomaly({"anomaly_detected": False}, call)["anomaly_detected"]


def test_swearing_customer_is_flagged_low():
    call = "Customer: แม่งเอ้ย ส่งช้าทุกที\nAgent: ขออภัยค่ะ"
    out = ir.verify_anomaly({"anomaly_detected": False}, call)
    assert (out["anomaly_detected"], out["anomaly_severity"]) == (True, "low")


# ── Sentiment guard ──────────────────────────────────────────────────────

def test_thanks_alone_is_not_positive():
    assert ir.check_sentiment("positive", "ขอบคุณครับ ขอบคุณครับ", "ขอบคุณครับ ขอบคุณครับ") == "neutral"
    assert ir.check_sentiment("positive", "ประทับใจมากเลยค่ะ", "ประทับใจมากเลยค่ะ") == "positive"


def test_swearing_customer_is_never_positive():
    # Real call: the model said positive for this customer.
    said = "ทุกอย่างแม่งดีหมดเลยครับ แต่ลูกค้าแม่งใช้งานไม่ได้ กูเสียเงินไปแล้วสามหมื่น"
    assert ir.check_sentiment("positive", "", said) == "negative"
    assert ir.check_sentiment("neutral", "", "ไม่พอใจมากค่ะ") == "negative"


# ── QA answer format ─────────────────────────────────────────────────────

def test_found_list_is_turned_into_items():
    items = ir.items_from_answer({
        "found": [{"item": "P1", "quote": "สวัสดีค่ะ"}, {"item": "s4", "quote": "ส่งเรื่องให้ QC"}, "junk"],
        "customer_had_problem": False,
    })
    assert items["P1"]["done"] and items["S4"]["quote"] == "ส่งเรื่องให้ QC"
    assert items["P3"]["applicable"] is False


def test_agent_words_in_a_mislabelled_line_still_count():
    # Diarization put the agent's closing inside a Customer line.
    call = "Agent: สวัสดีค่ะ\nCustomer: ได้ค่ะ ถ้ายังมีปัญหาแจ้งกลับมาได้นะคะลูกค้า ขอบคุณค่ะ"
    assert ir.agent_said("ถ้ายังมีปัญหาแจ้งกลับมาได้นะคะลูกค้า", call)
    assert not ir.agent_said("ได้ค่ะ ถ้ายังมี", call)   # no agent voice → stays the customer's


def test_wrong_code_with_a_fitting_quote_is_recategorised():
    out = ir.verify_anomaly({"anomaly_detected": True, "category": "A1", "evidence_quote": "เป็นผื่นคันแสบจมูก"}, CALL)
    assert out["anomaly_severity"] == "medium" and out["anomaly_reason"].startswith("[C1]")


def test_sorting_out_an_item_name_is_not_agent_misinformation():
    # Real call (12B model): flagged high-severity B2 for this exchange.
    call = (
        "Agent: ครับ ก็เราไม่เห็นพ็อปเปอร์ของคุณลูกค้าเลยอะค่ะ อ่า\n"
        "Customer: เป็นผ้าปู ไม่ใช่พ็อปเปอร์ ไม่ มันเป็นผ้าปู ผ้ารองกันเปื้อนครับ"
    )
    answer = {"anomaly_detected": True, "category": "B2", "evidence_quote": "ก็เราไม่เห็นพ็อปเปอร์ของคุณลูกค้าเลยอะค่ะ"}
    assert not ir.verify_anomaly(answer, call)["anomaly_detected"]


def test_agent_misinformation_needs_the_customer_to_say_they_were_told_wrong():
    call = (
        "Agent: ส่งได้วันจันทร์ค่ะ\n"
        "Customer: ตอนแรกบอกว่าวันศุกร์ แล้วทำไมตอนนี้บอกไม่ตรงกัน"
    )
    out = ir.verify_anomaly({"anomaly_detected": True, "category": "B2", "evidence_quote": "ส่งได้วันจันทร์ค่ะ"}, call)
    assert (out["anomaly_detected"], out["anomaly_severity"]) == (True, "high")
    assert out["anomaly_reason"].startswith("[B2]")


def test_rude_or_refusing_agent_needs_the_words_in_the_agents_quote():
    call = (
        "Agent: เรื่องของคุณ ทางเราไม่รับผิดชอบค่ะ\n"
        "Customer: ทำไมพูดแบบนี้ ผมจะร้องเรียน\n"
        "Agent: ขออภัยค่ะ เดี๋ยวตรวจสอบให้นะคะ"
    )
    rude = ir.verify_anomaly({"anomaly_detected": True, "category": "B1", "evidence_quote": "เรื่องของคุณ"}, call)
    assert rude["anomaly_reason"].startswith("[B1]")
    refused = ir.verify_anomaly({"anomaly_detected": True, "category": "B3", "evidence_quote": "ทางเราไม่รับผิดชอบค่ะ"}, call)
    assert refused["anomaly_reason"].startswith("[B3]")
    # A polite line is real but proves nothing; neither does the customer's own line.
    polite = {"anomaly_detected": True, "category": "B1", "evidence_quote": "เดี๋ยวตรวจสอบให้นะคะ"}
    assert not ir.verify_anomaly(polite, call)["anomaly_reason"].startswith("[B")
    customer = {"anomaly_detected": True, "category": "B1", "evidence_quote": "ทำไมพูดแบบนี้ ผมจะร้องเรียน"}
    assert ir.verify_anomaly(customer, call)["anomaly_reason"].startswith("[A2]")


def test_legacy_reason_format_is_still_verified():
    call = "Customer: ถ้าไม่แก้ผมจะฟ้องเลยนะ"
    out = ir.verify_anomaly(
        {"anomaly_detected": True, "anomaly_reason": '[A1] ลูกค้าขู่จะฟ้อง — evidence: "ถ้าไม่แก้ผมจะฟ้องเลยนะ"'}, call
    )
    assert out["anomaly_severity"] == "high"


# ── Topics ───────────────────────────────────────────────────────────────

def test_topic_is_clamped_to_the_list():
    assert ir.normalize_topic("แจ้งปัญหาสินค้า") == "แจ้งปัญหาสินค้า"
    assert ir.normalize_topic("อื่นๆ: ถามเบอร์ร้าน") == "อื่นๆ"
    assert ir.normalize_topic("สอบถามเรื่องการจัดส่งสินค้า") == "สอบถามการจัดส่ง"


def test_allergy_has_its_own_problem_type():
    # Real calls: rash / allergy were filed under "สปริงยุบ" and "ผ้าขาด".
    assert "กลิ่น/แพ้/ระคายเคือง" in ollama_client.TOPIC_DETAIL_CHOICES
    assert ollama_client.normalize_topic_detail("แจ้งปัญหาสินค้า", "ลูกค้าแพ้ เป็นผื่นคัน") == "กลิ่น/แพ้/ระคายเคือง"


def test_short_stems_no_longer_snap_unrelated_answers():
    # "รายละเอียด" contains "รา"; "ผ้าห่ม" contains "ผ้า".
    assert ollama_client.normalize_topic_detail("แจ้งปัญหาสินค้า", "ไม่ทราบรายละเอียด") == "อื่นๆ"
    assert ollama_client.normalize_topic_detail("แจ้งปัญหาสินค้า", "ผ้าห่มสีไม่ตรง") == "ขนาด/สเปคผิด"


# ── Brands / platforms ───────────────────────────────────────────────────

def test_brands_copied_from_the_prompt_are_dropped():
    raw = ["Omazz", "Restonic", "Lotus/โลตัส", "Slumberland", "Dunlopillo"]
    assert ir.canonical_mentions(raw, CALL, ir.BRAND_ALIASES) == []   # only the greeting says โลตัส


def test_brand_spellings_merge_into_one_name():
    call = "Customer: ที่นอนโลตัสกับ Restonic ต่างกันยังไง\nAgent: เรสโทนิคแน่นกว่าค่ะ"
    assert ir.canonical_mentions(["Lotus", "โลตัส", "เรสโทนิค", "Restonic"], call, ir.BRAND_ALIASES) == [
        "Lotus (โลตัส)", "Restonic",
    ]


def test_platform_in_thai_spelling_is_recognised():
    assert ir.canonical_mentions(["Shopee", "โทรศัพท์"], CALL, ir.PLATFORM_ALIASES) == ["Shopee"]


# ── Prompts ──────────────────────────────────────────────────────────────

def test_prompts_carry_no_concrete_values_the_model_can_copy():
    _, qa = prompts.build_agent_qa_prompt("Agent: x")
    for leaked in ("ติดตามการโอนเงินคืน", "<เบอร์ที่ลูกค้าให้ไว้>", "เข้าใจเลยค่ะ", "[บริบท/รายละเอียด]"):
        assert leaked not in qa
    _, extraction = prompts.build_extraction_prompt("Agent: x")
    assert '"โทรศัพท์"' not in extraction        # every call is a phone call


def test_case_recency_is_measured_from_the_new_call():
    _, user = prompts.build_case_match_prompt(
        "t", "s",
        [{"id": 1, "status": "open", "subject": "x", "latest_call_at": "2025-11-04T10:00:00", "call_summaries": "-"}],
        new_call_at="2025-11-04T13:30:00",
    )
    assert "ห่างจากสายใหม่ 3 ชม. 30 นาที" in user


def test_named_item_answer_is_scored():
    # Current prompt format: one slot per item, named in Thai, quote or "".
    answer = {
        "ทักทายเปิดสาย": "สวัสดีค่ะ กลุ่มบริษัทที่นอนในเครือโลตัสค่ะ",
        "เห็นใจหรือขอโทษ": "ต้องขออภัยด้วยนะคะ",
        "กล่าวปิดสาย": "",
        "บอกขั้นตอนถัดไป": "เดี๋ยวส่งเรื่องให้ QC ตรวจสอบนะคะ",
        "ลูกค้ามีปัญหา": True,
    }
    assert ir.has_itemised_qa(answer)
    items = ir.items_from_answer(answer)
    assert items["P3"]["applicable"] is True and items["P5"]["done"] is False
    pol, _ = ir.score_items(items, ir.POLITENESS_ITEMS, CALL)
    ps, evidence = ir.score_items(items, ir.PROBLEM_SOLVING_ITEMS, CALL)
    assert pol == 3            # P1 + P2 (measured) + P3 of 5
    assert ps == 1 and "บอกขั้นตอนถัดไป ('เดี๋ยวส่งเรื่องให้ QC ตรวจสอบนะคะ')" in evidence


def test_unassigned_speaker_lines_count_as_agent_evidence():
    # Diarization left the agent's lines as "Speaker 0" on a real call.
    call = "Speaker 0: สวัสดีค่ะ สวัสดีค่ะคุณธนัทธ์นะคะ\nCustomer: ครับ"
    assert ir.agent_said("สวัสดีค่ะ สวัสดีค่ะคุณธนัทธ์นะคะ", call)


def test_polite_particles_are_measured_not_quoted():
    polite = "Agent: สวัสดีค่ะ ยินดีให้บริการค่ะ\nAgent: ขอเลขคำสั่งซื้อหน่อยนะคะ\nCustomer: ได้"
    rude = "Agent: ว่าไง มีอะไร\nAgent: เดี๋ยวดูให้ รอไป\nCustomer: ครับ"
    assert ir.polite_particles_check(polite)["done"]
    assert not ir.polite_particles_check(rude)["done"]


def test_report_to_police_is_not_confused_with_stating_needs():
    # Real call: "แจ้งความต้องการ" (stated my needs) was flagged as a legal threat.
    assert ir.has_keyword("ผมแจ้งความต้องการไปแล้วนะ", ir.CATEGORY_KEYWORDS["A1"]) is None
    assert ir.has_keyword("ผมจะไปแจ้งความ", ir.CATEGORY_KEYWORDS["A1"]) == "แจ้งความ"
    call = "Customer: โอเคผมแจ้งความต้องการผมไปแล้วนะ\nAgent: ค่ะ"
    assert not ir.verify_anomaly({"anomaly_detected": False}, call)["anomaly_detected"]
