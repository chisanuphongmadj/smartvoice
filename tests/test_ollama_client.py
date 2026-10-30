"""Tests for smartvoice.ollama_client — JSON parsing helpers + fallback logic.

Do NOT hit a real Ollama server; all LLM calls are monkey-patched.
"""

import json
import unittest
from unittest.mock import patch

from smartvoice import ollama_client


class TestExtractJson(unittest.TestCase):
    def test_plain_json(self):
        result = ollama_client.extract_json('{"foo": "bar", "n": 1}')
        self.assertEqual(result, {"foo": "bar", "n": 1})

    def test_fenced_json(self):
        raw = '```json\n{"foo": 1}\n```'
        self.assertEqual(ollama_client.extract_json(raw), {"foo": 1})

    def test_json_embedded_in_prose(self):
        raw = 'Here is the result: {"x": 42} — done.'
        self.assertEqual(ollama_client.extract_json(raw), {"x": 42})

    def test_uses_first_json_object_when_multiple_objects_are_present(self):
        raw = 'Example: {"ignore": true}\nFinal: {"x": 42}'
        self.assertEqual(ollama_client.extract_json(raw), {"ignore": True})

    def test_raises_when_no_json(self):
        with self.assertRaises(ValueError):
            ollama_client.extract_json("nothing here")


class TestNextActionOwnerFallback(unittest.TestCase):
    """evaluate_agent_qa should infer next_action_owner when LLM returns 'ไม่มี' for a
    non-closed case."""

    def _mock_chat(self, payload: dict):
        return json.dumps(payload, ensure_ascii=False)

    def _run_with_response(self, mock_payload: dict, conversation=None):
        # By default the call talks about money: a refund task on a call that
        # never mentions it is rejected as ungrounded (see insight_rules).
        conversation = conversation or [
            {"speaker": "Customer", "text": "ขอคืนเงินค่าที่นอน 1,500 บาทค่ะ"},
            {"speaker": "Agent", "text": "รับเรื่องไว้ค่ะ"},
        ]
        with patch.object(ollama_client, "chat", return_value=self._mock_chat(mock_payload)):
            return ollama_client.evaluate_agent_qa(conversation)

    def test_refund_keyword_maps_to_accounting(self):
        out = self._run_with_response({
            "politeness": 5, "problem_solving": 4, "overall_score": 9,
            "next_action": "ติดตามเรื่องคืนเงินลูกค้าภายใน 7 วัน",
            "next_action_owner": "ไม่มี",  # LLM got it wrong
        })
        ap = json.loads(out["agent_performance"])
        self.assertEqual(ap["next_action_owner"], "ฝ่ายบัญชี")

    def test_qc_keyword_maps_to_qc(self):
        out = self._run_with_response({
            "politeness": 4, "problem_solving": 4, "overall_score": 8,
            "next_action": "ตรวจสอบที่นอนกับฝ่าย QC",
            "next_action_owner": "ไม่มี",
        })
        ap = json.loads(out["agent_performance"])
        self.assertEqual(ap["next_action_owner"], "ฝ่าย QC")

    def test_delivery_keyword_maps_to_shipping(self):
        out = self._run_with_response({
            "politeness": 4, "problem_solving": 4, "overall_score": 8,
            "next_action": "จัดส่งที่นอนตัวใหม่ให้ลูกค้า",
            "next_action_owner": "ไม่มี",
        })
        ap = json.loads(out["agent_performance"])
        self.assertEqual(ap["next_action_owner"], "ฝ่ายจัดส่ง")

    def test_generic_followup_falls_back_to_agent(self):
        out = self._run_with_response({
            "politeness": 4, "problem_solving": 4, "overall_score": 8,
            "next_action": "โทรแจ้งผลลูกค้าอีกครั้ง",
            "next_action_owner": "ไม่มี",
        })
        ap = json.loads(out["agent_performance"])
        self.assertEqual(ap["next_action_owner"], "Agent คนเดิม")

    def test_closed_case_stays_none(self):
        out = self._run_with_response({
            "politeness": 5, "problem_solving": 5, "overall_score": 10,
            "next_action": "ไม่มี — เคสปิดสมบูรณ์",
            "next_action_owner": "ไม่มี",
        })
        ap = json.loads(out["agent_performance"])
        self.assertEqual(ap["next_action_owner"], "ไม่มี")

    def test_valid_owner_is_kept_unchanged(self):
        out = self._run_with_response({
            "politeness": 4, "problem_solving": 4, "overall_score": 8,
            "next_action": "ประสานหัวหน้าเพื่ออนุมัติการคืนเงิน",
            "next_action_owner": "หัวหน้าทีม",
        })
        ap = json.loads(out["agent_performance"])
        self.assertEqual(ap["next_action_owner"], "หัวหน้าทีม")

    def test_evidence_fields_are_preserved_for_audit(self):
        out = self._run_with_response({
            "politeness": 4,
            "politeness_evidence": "ทำได้: ใช้คำสุภาพ / ไม่ได้: ไม่กล่าวปิดสาย",
            "problem_solving": 3,
            "problem_solving_evidence": "ทำได้: รับเรื่อง / ไม่ได้: ไม่ระบุเวลา",
            "overall_score": 7,
            "next_action": "โทรแจ้งผลลูกค้าอีกครั้ง",
            "next_action_owner": "Agent คนเดิม",
        })
        ap = json.loads(out["agent_performance"])
        self.assertIn("politeness_evidence", ap)
        self.assertIn("problem_solving_evidence", ap)

    def test_scores_are_clamped_and_overall_is_recomputed(self):
        out = self._run_with_response({
            "politeness": 8,
            "problem_solving": "0",
            "overall_score": 10,
            "next_action": "โทรแจ้งผลลูกค้าอีกครั้ง",
            "next_action_owner": "Agent คนเดิม",
        })
        ap = json.loads(out["agent_performance"])
        self.assertEqual(ap["politeness"], 5)
        self.assertEqual(ap["problem_solving"], 1)
        self.assertEqual(ap["overall_score"], 6)

    def test_copied_prompt_example_next_action_is_replaced(self):
        out = self._run_with_response({
            "politeness": 5,
            "problem_solving": 4,
            "overall_score": 9,
            "next_action": (
                "ติดตามการโอนเงินคืนลูกค้า | จำนวน 15,000 บาท "
                "(ที่นอน Restonic Queen Size รหัส #REG0012) | ภายใน 7 วันทำการ | "
                "โทรแจ้งลูกค้าที่ 081-987-9336 หลังโอนเงินเรียบร้อย + บันทึกใน CRM"
            ),
            "next_action_owner": "ฝ่ายบัญชี",
        }, conversation=[{"speaker": "Agent", "text": "hi"}])
        ap = json.loads(out["agent_performance"])
        self.assertNotIn("15,000", ap["next_action"])
        self.assertNotIn("REG0012", ap["next_action"])
        self.assertNotEqual(ap["next_action_owner"], "ฝ่ายบัญชี")


class TestPromptExampleScrubbing(unittest.TestCase):
    """Regression: Typhoon-8B sometimes lifts the prompt's next_action example
    verbatim (15,000 บาท / #REG0012 / 081-987-9336) even when the actual
    conversation never mentions those values. The scrubber must drop leaked
    sub-clauses while keeping non-leaked content."""

    def _run(self, mock_payload, conversation_text="สวัสดีครับ คุณลูกค้าต้องการสอบถามวันจัดส่ง"):
        conv = [{"speaker": "Agent", "text": conversation_text}]
        with patch.object(ollama_client, "chat", return_value=json.dumps(mock_payload, ensure_ascii=False)):
            out = ollama_client.evaluate_agent_qa(conv)
        return json.loads(out["agent_performance"])

    def test_leaked_refund_template_is_scrubbed(self):
        ap = self._run({
            "politeness": 5, "problem_solving": 4, "overall_score": 9,
            "next_action": "ติดตามการโอนเงินคืนลูกค้า | จำนวน 15,000 บาท (ที่นอน Restonic Queen Size รหัส #REG0012) | ภายใน 7 วันทำการ | โทรแจ้งลูกค้าที่ 081-987-9336 หลังโอนเงินเรียบร้อย + บันทึกใน CRM",
            "next_action_owner": "ฝ่ายบัญชี",
        })
        # Tokens not present in conversation must be gone
        self.assertNotIn("15,000", ap["next_action"])
        self.assertNotIn("REG0012", ap["next_action"])
        self.assertNotIn("081-987-9336", ap["next_action"])

    def test_real_value_present_in_conversation_is_kept(self):
        # If the conversation actually mentions the amount, the scrubber must
        # NOT remove it
        ap = self._run(
            {
                "politeness": 5, "problem_solving": 4, "overall_score": 9,
                "next_action": "ติดตามการโอนเงินคืน | จำนวน 15,000 บาท | ภายใน 7 วันทำการ | โทรแจ้งลูกค้า",
                "next_action_owner": "ฝ่ายบัญชี",
            },
            conversation_text="ลูกค้าขอคืนเงิน 15,000 บาท สำหรับที่นอน",
        )
        self.assertIn("15,000", ap["next_action"])

    def test_fully_leaked_falls_back_to_generic(self):
        # Every segment carries a leaked token → result should fall back to
        # the generic placeholder, never empty string
        ap = self._run({
            "politeness": 5, "problem_solving": 4, "overall_score": 9,
            "next_action": "15,000 | REG0012 | 081-987-9336 | 15000",
            "next_action_owner": "ฝ่ายบัญชี",
        })
        self.assertTrue(ap["next_action"])
        self.assertNotIn("REG0012", ap["next_action"])


class TestSanitizeEvidence(unittest.TestCase):
    """sanitize_evidence must:
      - return real evidence unchanged
      - replace bracket placeholders ([ข้อ + quote สั้น], etc.) with a safe fallback
      - replace vague summaries ("ทำได้: ทุกข้อ") that lack any quote
      - handle empty / None gracefully
    """

    def test_real_evidence_with_quotes_is_preserved(self):
        text = "ทำได้: ทักทาย ('สวัสดีค่ะ ร้านที่นอน'), ขอบคุณ ('ขอบคุณค่ะ') / ไม่ได้: ทวนชื่อ (ไม่พบหลักฐาน)"
        self.assertEqual(ollama_client.sanitize_evidence(text), text)

    def test_leaked_bracket_placeholder_is_replaced(self):
        text = "ทำได้: [ทุกข้อ + quote สั้น] / ไม่ได้: [ไม่มี]"
        out = ollama_client.sanitize_evidence(text)
        self.assertNotIn("[", out)
        self.assertNotIn("ทุกข้อ + quote", out)
        self.assertTrue(out)

    def test_leaked_partial_template_fragment_is_replaced(self):
        text = "ทำได้: [4 ข้อ + quote สั้น] / ไม่ได้: [1 ข้อ + เหตุผลหรือไม่พบหลักฐาน]"
        out = ollama_client.sanitize_evidence(text)
        self.assertNotIn("[", out)
        self.assertNotIn("เหตุผลหรือไม่พบหลักฐาน", out)

    def test_leaked_angle_bracket_placeholder_is_replaced(self):
        # New schema uses <...> — must also be caught if LLM copies it
        text = "ทำได้: <ชื่อข้อจริง> ('<quote Agent>') / ไม่ได้: <ชื่อข้อจริง> (ไม่พบหลักฐาน)"
        out = ollama_client.sanitize_evidence(text)
        self.assertNotIn("<", out)

    def test_vague_summary_without_quotes_is_replaced(self):
        text = "ทำได้: ทุกข้อ / ไม่ได้: ไม่มีข้อที่ไม่ทำ"
        out = ollama_client.sanitize_evidence(text)
        self.assertNotEqual(out, text)
        self.assertNotIn("ทุกข้อ", out)

    def test_vague_summary_with_real_quote_is_kept(self):
        # If the model says "ทุกข้อ" but ALSO supplies an Agent quote, accept it.
        # Avoid the old "พลอยค่ะ" fixture — it now matches the prompt-example
        # leak list and would be scrubbed when no conversation_text is provided.
        text = "ทำได้: ทุกข้อ เช่น ทักทาย ('สวัสดีค่ะ ขอบคุณที่ติดต่อ') / ไม่ได้: ไม่มี"
        self.assertEqual(ollama_client.sanitize_evidence(text), text)

    def test_specific_evidence_without_quote_but_with_no_evidence_marker(self):
        text = "ทำได้: ใช้คำสุภาพ / ไม่ได้: ไม่กล่าวปิดสาย (ไม่พบหลักฐาน)"
        self.assertEqual(ollama_client.sanitize_evidence(text), text)

    def test_empty_string_returns_empty(self):
        self.assertEqual(ollama_client.sanitize_evidence(""), "")

    def test_none_returns_empty(self):
        self.assertEqual(ollama_client.sanitize_evidence(None), "")

    def test_evidence_sanitisation_applied_in_evaluate_agent_qa(self):
        """End-to-end: leaked evidence from LLM is cleaned in the saved JSON."""
        payload = {
            "politeness": 5,
            "politeness_evidence": "ทำได้: [ทุกข้อ + quote สั้น] / ไม่ได้: [ไม่มี]",
            "problem_solving": 4,
            "problem_solving_evidence": "ทำได้: [4 ข้อ + quote สั้น] / ไม่ได้: [1 ข้อ + เหตุผลหรือไม่พบหลักฐาน]",
            "overall_score": 9,
            "next_action": "โทรแจ้งผลลูกค้า",
            "next_action_owner": "Agent คนเดิม",
        }
        with patch.object(ollama_client, "chat", return_value=json.dumps(payload, ensure_ascii=False)):
            out = ollama_client.evaluate_agent_qa([{"speaker": "Agent", "text": "hi"}])
        ap = json.loads(out["agent_performance"])
        self.assertNotIn("[", ap["politeness_evidence"])
        self.assertNotIn("[", ap["problem_solving_evidence"])

    def test_prompt_example_token_scrubbed_when_absent_from_transcript(self):
        # Typhoon-8B used to lift "ร้านที่นอนพลอย" from the prompt example into
        # nearly every politeness_evidence — must be detected and scrubbed when
        # the real transcript never said it.
        text = "ทำได้: ทักทายเปิดสาย ('สวัสดีค่ะ ร้านที่นอนพลอย'), แนะนำตัว ('พลอยค่ะ') / ไม่ได้: ไม่ทวนชื่อ (ไม่พบหลักฐาน)"
        transcript = "Agent: สวัสดีค่ะ บริษัทเอบีซี ยินดีให้บริการค่ะ\nCustomer: ครับ"
        out = ollama_client.sanitize_evidence(text, transcript)
        self.assertNotIn("ร้านที่นอนพลอย", out)
        self.assertNotIn("พลอยค่ะ", out)
        self.assertTrue(out)

    def test_prompt_example_token_kept_when_present_in_transcript(self):
        # If the agent really did say it on this call, the same string in
        # evidence is genuine evidence, not leakage — must NOT be scrubbed.
        text = "ทำได้: ทักทายเปิดสาย ('สวัสดีค่ะ ร้านที่นอนพลอย') / ไม่ได้: ไม่ทวนชื่อ (ไม่พบหลักฐาน)"
        transcript = "Agent: สวัสดีค่ะ ร้านที่นอนพลอย ยินดีให้บริการค่ะ"
        self.assertEqual(ollama_client.sanitize_evidence(text, transcript), text)

    def test_evaluate_agent_qa_scrubs_prompt_example_leak_end_to_end(self):
        # End-to-end: when the LLM emits the canonical leaked example but the
        # mocked transcript doesn't contain those tokens, the saved JSON must
        # not surface them to the dashboard.
        payload = {
            "politeness": 5,
            "politeness_evidence": "ทำได้: ทักทายเปิดสาย ('สวัสดีค่ะ ร้านที่นอนพลอย'), แนะนำตัว ('พลอยค่ะ')",
            "problem_solving": 5,
            "problem_solving_evidence": "ทำได้: เข้าใจปัญหา ('ใช้ที่นอนแล้วนอนไม่หลับ')",
            "overall_score": 10,
            "next_action": "ไม่มี — เคสปิดสมบูรณ์",
            "next_action_owner": "ไม่มี",
        }
        with patch.object(ollama_client, "chat", return_value=json.dumps(payload, ensure_ascii=False)):
            out = ollama_client.evaluate_agent_qa([
                {"speaker": "Agent", "text": "สวัสดีค่ะ บริษัทเอบีซี ยินดีให้บริการค่ะ"},
                {"speaker": "Customer", "text": "ครับ"},
            ])
        ap = json.loads(out["agent_performance"])
        self.assertNotIn("ร้านที่นอนพลอย", ap["politeness_evidence"])
        self.assertNotIn("พลอยค่ะ", ap["politeness_evidence"])
        # problem_solving quote came from the (mocked) transcript context and
        # is unrelated to the leak token — should be preserved.
        self.assertIn("เข้าใจปัญหา", ap["problem_solving_evidence"])


class TestPromptHasNoFakeExampleValues(unittest.TestCase):
    """Regression for the 'ร้านที่นอนพลอย' incident: the Agent QA prompt's
    'รูปแบบที่ถูก' example must not contain concrete fake values that Typhoon
    can copy verbatim into politeness_evidence on every call.

    Why a structural test: sanitize_evidence is a runtime safety net, but the
    real fix is keeping fake values out of the prompt in the first place.
    """

    def test_agent_qa_prompt_has_no_fake_shop_name(self):
        from smartvoice import prompts
        self.assertNotIn("ร้านที่นอนพลอย", prompts.AGENT_QA_USER)

    def test_agent_qa_prompt_has_no_fake_agent_self_quote(self):
        # 'พลอยค่ะ' as a standalone fake quote in the Agent QA example was the
        # other half of the leak — must not reappear in the QA prompt body.
        from smartvoice import prompts
        self.assertNotIn("'พลอยค่ะ'", prompts.AGENT_QA_USER)


class TestCorrectSpeakersRobustness(unittest.TestCase):
    """Regression: LLM sometimes returns malformed JSON arrays (e.g. bare ints)
    and correct_speakers must not crash."""

    def _run(self, llm_response_array):
        raw = json.dumps(llm_response_array, ensure_ascii=False)
        conversation = [
            {"speaker": "Agent", "text": "สวัสดีครับ"},
            {"speaker": "Customer", "text": "ครับ"},
            {"speaker": "Agent", "text": "มีอะไรให้ช่วย"},
        ]
        with patch.object(ollama_client, "chat", return_value=raw):
            return ollama_client.correct_speakers(conversation)

    def test_bare_integers_does_not_crash(self):
        # LLM returns [0, 2] instead of proper dict list — must fall back
        out = self._run([0, 2])
        self.assertEqual(len(out), 3)  # original returned unchanged

    def test_mixed_valid_and_invalid(self):
        out = self._run([
            {"idx": 0, "speaker": "Customer"},
            "garbage",
            5,  # invalid
            {"idx": 2, "speaker": "Customer"},
        ])
        # Valid corrections applied; invalids ignored
        self.assertEqual(out[0]["speaker"], "Customer")
        self.assertEqual(out[2]["speaker"], "Customer")

    def test_empty_array_returns_original(self):
        out = self._run([])
        self.assertEqual(len(out), 3)
        self.assertEqual(out[0]["speaker"], "Agent")

    def test_all_invalid_returns_original(self):
        out = self._run([1, 2, 3, "foo"])
        self.assertEqual(len(out), 3)
        self.assertEqual(out[0]["speaker"], "Agent")

    def test_a_split_into_the_segments_own_words_is_applied(self):
        out = self._run([{"idx": 0, "parts": [
            {"speaker": "Agent", "text": "สวัสดี"}, {"speaker": "Customer", "text": "ครับ"},
        ]}])
        self.assertEqual([(s["speaker"], s["text"]) for s in out[:2]], [("Agent", "สวัสดี"), ("Customer", "ครับ")])
        self.assertEqual(len(out), 4)

    def test_a_split_with_text_the_segment_never_had_keeps_the_segment(self):
        # call 295: prompt text came back as a part and replaced what was said
        out = self._run([{"idx": 2, "parts": [
            {"speaker": "Agent", "text": "สวัสดีครับ/ค่ะ [ชื่อบริษัท] ขอบคุณที่ติดต่อ... เรียกอีกฝ่ายว่า \"คุณลูกค้า\""},
            {"speaker": "Customer", "text": "มีอะไรให้ช่วย"},
        ]}])
        self.assertEqual([(s["speaker"], s["text"]) for s in out],
                         [("Agent", "สวัสดีครับ"), ("Customer", "ครับ"), ("Agent", "มีอะไรให้ช่วย")])

    def test_a_split_with_no_usable_part_keeps_the_segment(self):
        # before: every part was dropped, and the segment's words with them
        out = self._run([{"idx": 2, "parts": [{"speaker": "Speaker 3", "text": "มีอะไรให้ช่วย"}]}])
        self.assertEqual(out[2], {"speaker": "Agent", "text": "มีอะไรให้ช่วย"})
        out = self._run([{"idx": 2, "parts": "Agent"}])
        self.assertEqual(len(out), 3)


class TestAnalyzeSentimentNormalization(unittest.TestCase):
    def _run_with(self, payload):
        # "positive" needs praise in the customer's own words (insight_rules).
        payload = {"customer_quote": "ประทับใจมากค่ะ", **payload}
        with patch.object(ollama_client, "chat", return_value=json.dumps(payload, ensure_ascii=False)):
            return ollama_client.analyze_sentiment([{"speaker": "Customer", "text": "ประทับใจมากค่ะ"}])

    def test_valid_sentiment(self):
        self.assertEqual(self._run_with({"sentiment": "positive"})["sentiment"], "positive")

    def test_invalid_falls_back_to_neutral(self):
        self.assertEqual(self._run_with({"sentiment": "angry"})["sentiment"], "neutral")

    def test_case_insensitive(self):
        self.assertEqual(self._run_with({"sentiment": "POSITIVE"})["sentiment"], "positive")


class TestDetectAnomalyNormalization(unittest.TestCase):
    def _run_with(self, payload):
        with patch.object(ollama_client, "chat", return_value=json.dumps(payload)):
            return ollama_client.detect_anomaly([{"speaker": "Customer", "text": "ขอบคุณค่ะ"}])

    def test_string_false_is_not_truthy(self):
        out = self._run_with({"anomaly_detected": "false", "anomaly_reason": None})
        self.assertIs(out["anomaly_detected"], False)

    def test_invalid_severity_is_cleared(self):
        out = self._run_with({"anomaly_detected": True, "anomaly_severity": "urgent"})
        self.assertEqual(out["anomaly_severity"], "")


class TestPrepareConversationText(unittest.TestCase):
    def test_short_conversation_is_sent_whole(self):
        conversation = [{"speaker": "Customer", "text": f"turn-{i}"} for i in range(70)]
        text = ollama_client._prepare_conversation_text(conversation)
        self.assertIn("turn-35", text)

    def test_long_conversation_keeps_start_and_end(self):
        """The old cut kept the first 6,000 characters and lost the close of
        the call — where the closing greeting and the agreed next step are."""
        conversation = [
            {"speaker": "Customer", "text": f"turn-{i:04d} " + "ก" * 200}
            for i in range(200)
        ]
        text = ollama_client._prepare_conversation_text(conversation)

        self.assertLessEqual(len(text), ollama_client.MAX_CHARS + 200)
        self.assertIn("turn-0000", text)
        self.assertIn("turn-0199", text)
        self.assertNotIn("turn-0100", text)
        self.assertIn("ตัดช่วงกลาง", text)


class TestNormalizeTopicDetail(unittest.TestCase):
    """Drill-down vocabulary for "แจ้งปัญหาสินค้า" (Omazz request) must stay on
    a fixed list so the dashboard can group cleanly."""

    def test_blank_when_topic_is_not_product_issue(self):
        # Even if LLM leaks a value, it should be discarded for non-issue topics
        self.assertEqual(
            ollama_client.normalize_topic_detail("สอบถามการจัดส่ง", "ผ้าขาด/ผ้าหุ้มชำรุด"),
            "",
        )

    def test_exact_match_passes_through(self):
        self.assertEqual(
            ollama_client.normalize_topic_detail(
                ollama_client.PRODUCT_ISSUE_TOPIC, "เตียง/โครงหัก"
            ),
            "เตียง/โครงหัก",
        )

    def test_partial_match_snaps_to_allowed_label(self):
        # LLM said "ผ้าหุ้มขาด" — should snap to "ผ้าขาด/ผ้าหุ้มชำรุด"
        self.assertEqual(
            ollama_client.normalize_topic_detail(
                ollama_client.PRODUCT_ISSUE_TOPIC, "ผ้าหุ้มขาด"
            ),
            "ผ้าขาด/ผ้าหุ้มชำรุด",
        )

    def test_empty_value_falls_back_to_other(self):
        # Product-issue topic but LLM gave no detail → "อื่นๆ" (not blank,
        # so the drill-down chart still accounts for the call)
        self.assertEqual(
            ollama_client.normalize_topic_detail(ollama_client.PRODUCT_ISSUE_TOPIC, ""),
            "อื่นๆ",
        )

    def test_unrelated_text_falls_back_to_other(self):
        self.assertEqual(
            ollama_client.normalize_topic_detail(
                ollama_client.PRODUCT_ISSUE_TOPIC, "ลูกค้าไม่พอใจ"
            ),
            "อื่นๆ",
        )

    def test_non_string_input_falls_back_to_other(self):
        self.assertEqual(
            ollama_client.normalize_topic_detail(ollama_client.PRODUCT_ISSUE_TOPIC, None),
            "อื่นๆ",
        )


class TestExtractSummaryAndTopicsTopicDetail(unittest.TestCase):
    """End-to-end: extraction call must expose topic_detail downstream."""

    def _mock(self, payload: dict):
        return json.dumps(payload, ensure_ascii=False)

    def test_topic_detail_propagates_for_product_issue(self):
        with patch.object(ollama_client, "chat", return_value=self._mock({
            "summary": "ลูกค้าแจ้งที่นอนผ้าขาด",
            "topic": "แจ้งปัญหาสินค้า",
            "topic_detail": "ผ้าขาด/ผ้าหุ้มชำรุด",
            "keywords": ["ผ้าขาด"],
            "brand_mentions": [],
            "platform_mentions": [],
        })):
            out = ollama_client.extract_summary_and_topics(
                [{"speaker": "Customer", "text": "ผ้าขาดครับ"}]
            )
        self.assertEqual(out["topic_detail"], "ผ้าขาด/ผ้าหุ้มชำรุด")

    def test_topic_detail_blanked_for_non_product_topic(self):
        # LLM erroneously fills topic_detail on a delivery question — must blank
        with patch.object(ollama_client, "chat", return_value=self._mock({
            "summary": "ลูกค้าถามวันส่ง",
            "topic": "สอบถามการจัดส่ง",
            "topic_detail": "ผ้าขาด/ผ้าหุ้มชำรุด",
            "keywords": [],
            "brand_mentions": [],
            "platform_mentions": [],
        })):
            out = ollama_client.extract_summary_and_topics(
                [{"speaker": "Customer", "text": "ของส่งเมื่อไหร่"}]
            )
        self.assertEqual(out["topic_detail"], "")


if __name__ == "__main__":
    unittest.main()
