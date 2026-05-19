from smartvoice import prompts


def test_agent_qa_prompt_marks_inferred_sla_as_recommendation():
    _, user_prompt = prompts.build_agent_qa_prompt("Agent: รับเรื่องไว้ค่ะ")

    assert "ไม่ระบุในสาย" in user_prompt
    assert "แนะนำ" in user_prompt


def test_agent_qa_prompt_does_not_include_concrete_next_action_examples():
    _, user_prompt = prompts.build_agent_qa_prompt("Agent: รับเรื่องไว้ค่ะ")

    for copied_token in ("15,000", "REG0012", "Restonic Queen", "Slumberland King", "Dunlopillo Queen"):
        assert copied_token not in user_prompt


def test_agent_qa_prompt_requires_score_evidence_from_agent_quotes():
    _, user_prompt = prompts.build_agent_qa_prompt("Agent: รับเรื่องไว้ค่ะ")

    assert "ให้คะแนนเฉพาะข้อที่มีหลักฐานจากคำพูด Agent" in user_prompt
    assert "ถ้าทำได้ 0 ข้อ ให้ 1" in user_prompt
    assert "quote สั้น" in user_prompt


def test_anomaly_prompt_forbids_using_example_quotes_as_evidence():
    _, user_prompt = prompts.build_anomaly_prompt("Customer: ขอบคุณค่ะ")

    assert "ห้ามใช้ quote จากตัวอย่าง" in user_prompt
