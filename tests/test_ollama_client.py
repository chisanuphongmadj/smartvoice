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

    def test_raises_when_no_json(self):
        with self.assertRaises(ValueError):
            ollama_client.extract_json("nothing here")


class TestNextActionOwnerFallback(unittest.TestCase):
    """evaluate_agent_qa should infer next_action_owner when LLM returns 'ไม่มี' for a
    non-closed case."""

    def _mock_chat(self, payload: dict):
        return json.dumps(payload, ensure_ascii=False)

    def _run_with_response(self, mock_payload: dict):
        with patch.object(ollama_client, "chat", return_value=self._mock_chat(mock_payload)):
            return ollama_client.evaluate_agent_qa([{"speaker": "Agent", "text": "hi"}])

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


class TestAnalyzeSentimentNormalization(unittest.TestCase):
    def _run_with(self, payload):
        with patch.object(ollama_client, "chat", return_value=json.dumps(payload)):
            return ollama_client.analyze_sentiment([{"speaker": "A", "text": "x"}])

    def test_valid_sentiment(self):
        self.assertEqual(self._run_with({"sentiment": "positive"})["sentiment"], "positive")

    def test_invalid_falls_back_to_neutral(self):
        self.assertEqual(self._run_with({"sentiment": "angry"})["sentiment"], "neutral")

    def test_case_insensitive(self):
        self.assertEqual(self._run_with({"sentiment": "POSITIVE"})["sentiment"], "positive")


if __name__ == "__main__":
    unittest.main()
