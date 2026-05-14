import unittest

from smartvoice.pipeline import (
    _aggressive_relabel_from_strong_cues,
    _enforce_role_rules,
    _merge_adjacent_same_speaker,
    _split_answer_prefixed_turns,
    _split_embedded_customer_reaction_turns,
    _split_followup_question_turns,
    _split_leading_agent_continuation_turns,
    _split_long_segments_by_sentence,
    _split_mixed_question_answer_turns,
    _split_opening_mixed_turns,
    _split_trailing_customer_question_turns,
    _stabilize_sandwiched_turns,
)


class TestPipelineTurnHeuristics(unittest.TestCase):
    def test_split_answer_prefixed_turns(self):
        conversation = [
            {
                "speaker": "Customer",
                "text": "ใช่ค่ะคุณลูกค้าอยู่ในเครือของโลตัสใช่ไหมทีนี้พอดีที่นอนของพี่น้ำท่วมค่ะ",
                "start": 0.0,
                "end": 8.0,
            }
        ]

        result = _split_answer_prefixed_turns(conversation)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["speaker"], "Agent")
        self.assertEqual(result[0]["text"], "ใช่ค่ะคุณลูกค้า")
        self.assertEqual(result[1]["speaker"], "Customer")
        self.assertIn("อยู่ในเครือของโลตัสใช่ไหม", result[1]["text"])

    def test_split_mixed_question_answer_turns_with_tail(self):
        conversation = [
            {
                "speaker": "Customer",
                "text": "อ๋อค่ะเหรอก็คือมันซักยังไงก็ไม่ได้อยู่แล้วนะเพราะมันหนาแล้วมันลึกใช่ไหมฮะใช่ค่ะก็คือมันจะแห้งข้างนอก",
                "start": 0.0,
                "end": 10.0,
            }
        ]

        result = _split_mixed_question_answer_turns(conversation)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["speaker"], "Customer")
        self.assertEqual(result[1]["speaker"], "Agent")
        self.assertTrue(result[1]["text"].startswith("ใช่ค่ะ"))
        self.assertIn("จะแห้งข้างนอก", result[1]["text"])

    def test_split_opening_mixed_turns(self):
        conversation = [
            {
                "speaker": "Agent",
                "text": "สวัสดีค่ะกลุ่มบริษัทที่นอนโลตัสค่ะ ค่ะพี่สอบถามหน่อย ตัวที่นอน Restonic อยู่ในเครือไหมคะ อ๋อ ใช่ค่ะ คุณลูกค้าอยู่ในเครือของโลตัสใช่ไหม",
                "start": 0.0,
                "end": 12.0,
            }
        ]

        result = _split_opening_mixed_turns(conversation)
        result = _split_mixed_question_answer_turns(result)

        self.assertEqual(len(result), 4)
        self.assertEqual(result[0]["speaker"], "Agent")
        self.assertIn("กลุ่มบริษัทที่นอนโลตัส", result[0]["text"])
        self.assertEqual(result[1]["speaker"], "Customer")
        self.assertIn("ตัวที่นอน Restonic อยู่ในเครือไหมคะ", result[1]["text"])
        self.assertEqual(result[2]["speaker"], "Agent")
        self.assertIn("ใช่ค่ะ", result[2]["text"])
        self.assertEqual(result[3]["speaker"], "Customer")
        self.assertIn("อยู่ในเครือของโลตัสใช่ไหม", result[3]["text"])

    def test_split_followup_question_turns(self):
        conversation = [
            {
                "speaker": "Agent",
                "text": "การใช้งานโครงสร้างซึ่งน้ำท่วมก็อยู่นอกเหนือประกันทีนี้โดยปกติทางบริษัทมีTrade-inเหมือนสินค้าชนิดอื่นไหม",
                "start": 0.0,
                "end": 8.0,
            }
        ]

        result = _split_followup_question_turns(conversation)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["speaker"], "Agent")
        self.assertIn("นอกเหนือประกัน", result[0]["text"])
        self.assertEqual(result[1]["speaker"], "Customer")
        self.assertIn("Trade-in", result[1]["text"])

    def test_split_trailing_customer_question_turns(self):
        conversation = [
            {
                "speaker": "Agent",
                "text": "คือมันจะไม่ถูกสุขลักษณะในการนำมาใช้งานแล้วค่ะ อ๋อค่ะเหรอก็คือมันซักยังไงก็ไม่ได้อยู่แล้วนะเพราะมันหนาแล้วมันลึกใช่ไหมฮะ",
                "start": 0.0,
                "end": 9.0,
            }
        ]

        result = _split_trailing_customer_question_turns(conversation)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["speaker"], "Agent")
        self.assertIn("ไม่ถูกสุขลักษณะ", result[0]["text"])
        self.assertEqual(result[1]["speaker"], "Customer")
        self.assertIn("ซักยังไง", result[1]["text"])

    def test_split_embedded_customer_reaction_turns(self):
        conversation = [
            {
                "speaker": "Agent",
                "text": "เราก็เลยคิดว่ามันจะไม่ถูกสุขลักษณะในการนำมาใช้งานแล้วค่ะ มีหน้าเขาทิ้งกันเยอะ เออใช่ค่ะเพราะว่ามันถ้าเกิดว่าน้ำหกแบบแก้วนึง",
                "start": 0.0,
                "end": 8.0,
            }
        ]

        result = _split_embedded_customer_reaction_turns(conversation)

        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["speaker"], "Agent")
        self.assertIn("ไม่ถูกสุขลักษณะ", result[0]["text"])
        self.assertEqual(result[1]["speaker"], "Customer")
        self.assertIn("มีหน้าเขาทิ้งกันเยอะ", result[1]["text"])
        self.assertEqual(result[2]["speaker"], "Agent")
        self.assertIn("ใช่ค่ะ", result[2]["text"])

    def test_split_leading_agent_continuation_turns(self):
        conversation = [
            {"speaker": "Agent", "text": "ใช่ค่ะ", "start": 0.0, "end": 0.8},
            {
                "speaker": "Customer",
                "text": "ก็คือมันจะแห้งข้างนอก แต่ว่าข้างในเนี้ยคือพี่พยายามใช้เครื่องอบไอน้ำแล้ว",
                "start": 0.8,
                "end": 5.0,
            },
        ]

        result = _split_leading_agent_continuation_turns(conversation)

        self.assertEqual(len(result), 3)
        self.assertEqual(result[1]["speaker"], "Agent")
        self.assertIn("จะแห้งข้างนอก", result[1]["text"])
        self.assertEqual(result[2]["speaker"], "Customer")
        self.assertIn("พี่พยายาม", result[2]["text"])

    def test_enforce_role_rules_flips_trade_in_question_to_customer(self):
        conversation = [
            {
                "speaker": "Agent",
                "text": "ทีนี้โดยปกติทางบริษัทมี Trade-in เหมือนสินค้าชนิดอื่นไหม",
                "start": 0.0,
                "end": 4.0,
            }
        ]

        result = _enforce_role_rules(conversation)

        self.assertEqual(result[0]["speaker"], "Customer")

    def test_stabilize_sandwiched_turns_keeps_short_agent_answer(self):
        conversation = [
            {"speaker": "Customer", "text": "อยู่ในเครือไหมคะ", "start": 0.0, "end": 1.5},
            {"speaker": "Agent", "text": "ใช่ค่ะ", "start": 1.5, "end": 2.0},
            {"speaker": "Customer", "text": "พอดีที่นอนน้ำท่วมค่ะ", "start": 2.0, "end": 4.0},
        ]

        result = _stabilize_sandwiched_turns(conversation)

        self.assertEqual(result[1]["speaker"], "Agent")

    def test_stabilize_sandwiched_turns_reassigns_middle_flip(self):
        conversation = [
            {
                "speaker": "Agent",
                "text": "ค่ะใช่ค่ะเพราะว่ามันถ้าเกิดว่าน้ำหกแบบแก้วนึง",
                "start": 0.0,
                "end": 3.0,
            },
            {
                "speaker": "Customer",
                "text": "มันยังทำความสะอาดได้ใช่ไหมใช่",
                "start": 3.0,
                "end": 4.2,
            },
            {
                "speaker": "Agent",
                "text": "แต่ถ้าเกิดว่าเป็นน้ำท่วมเนี่ยคือมันไม่เหมาะกับการเอามาใช้งานแล้วนะคะ",
                "start": 4.2,
                "end": 8.0,
            },
        ]

        result = _stabilize_sandwiched_turns(conversation)

        self.assertEqual(result[1]["speaker"], "Agent")

    def test_merge_adjacent_same_speaker_after_reassignment(self):
        conversation = [
            {"speaker": "Agent", "text": "ใช่ค่ะ", "start": 0.0, "end": 1.0},
            {"speaker": "Agent", "text": "ก็คือมันจะแห้งแค่ข้างนอก", "start": 1.1, "end": 3.0},
        ]

        result = _merge_adjacent_same_speaker(conversation)

        self.assertEqual(len(result), 1)
        self.assertIn("ใช่ค่ะ", result[0]["text"])
        self.assertIn("จะแห้งแค่ข้างนอก", result[0]["text"])


class TestSplitLongSegmentsBySentence(unittest.TestCase):
    def test_short_segment_is_not_split(self):
        conv = [{"speaker": "Agent", "text": "สวัสดีค่ะ", "start": 0.0, "end": 1.0}]
        self.assertEqual(_split_long_segments_by_sentence(conv), conv)

    def test_empty_conversation_is_noop(self):
        self.assertEqual(_split_long_segments_by_sentence([]), [])

    def test_mega_segment_splits_at_sentence_boundaries(self):
        # Long segment containing multiple turns with polite-particle boundaries
        text = (
            "คุณสุกิตนะคะ ใช่ค่ะ เหมือนของคุณลูกค้ามีเรื่องส่งไว้ไหมคะ "
            "เพราะว่าที่พอดูจากในระบบเหมือนจะมีโรงส่งไว้วันที่ 2 มกราเลยอะค่ะ "
            "ทีเนี้ยแต่ 2 มกราก็จะไม่มีคนมันอยู่นะคะน้อง"
        )
        conv = [{"speaker": "Agent", "text": text, "start": 10.0, "end": 40.0}]

        result = _split_long_segments_by_sentence(conv)

        # Must produce multiple chunks
        self.assertGreater(len(result), 1)
        # Speaker label is preserved across all chunks (correct_speakers will re-label)
        self.assertTrue(all(r["speaker"] == "Agent" for r in result))
        # Timing bounds are preserved
        self.assertAlmostEqual(result[0]["start"], 10.0)
        self.assertAlmostEqual(result[-1]["end"], 40.0)
        # Chunks are time-ordered without overlap
        for i in range(len(result) - 1):
            self.assertLessEqual(result[i]["end"], result[i + 1]["start"] + 1e-6)
        # No chunk exceeds roughly the original length
        self.assertLessEqual(max(len(r["text"]) for r in result), len(text))

    def test_segment_without_boundary_particles_is_not_split(self):
        # Long segment but no polite particles followed by space → no split
        text = "ก" * 300
        conv = [{"speaker": "Agent", "text": text, "start": 0.0, "end": 10.0}]

        result = _split_long_segments_by_sentence(conv)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], text)

    def test_text_content_is_preserved(self):
        text = (
            "สวัสดีค่ะ กลุ่มบริษัทที่นอนในเครือโลตัสค่ะ "
            "จะเรียกยังไงค่ะ ติดตามเรื่องการส่งที่นอนค่ะ "
            "ได้เลยค่ะ ขอตรวจสอบสักครู่นะคะ"
        )
        conv = [{"speaker": "Agent", "text": text, "start": 0.0, "end": 15.0}]

        result = _split_long_segments_by_sentence(conv)

        # Reconstruct text from chunks — should contain all original content
        reconstructed = " ".join(r["text"] for r in result)
        # Every original word should appear in reconstructed
        for word in text.split():
            self.assertIn(word, reconstructed)


class TestAggressiveRelabelFromStrongCues(unittest.TestCase):
    def test_customer_self_reference_flips_to_customer(self):
        # Wrongly labelled Agent, but text has "พี่สะดวก" → must flip to Customer
        conv = [{"speaker": "Agent", "text": "พี่สะดวกวันที่ 8 นี้ พี่ลางานไปเปิดบ้าน", "start": 0, "end": 5}]

        result = _aggressive_relabel_from_strong_cues(conv)

        self.assertEqual(result[0]["speaker"], "Customer")

    def test_customer_vocative_luk_flips_to_customer(self):
        # "ได้ไหมลูก" — customer addressing young agent → flip to Customer
        conv = [{"speaker": "Agent", "text": "หนูถ้าเป็นอังคารได้ไหมลูก วันอังคาร", "start": 0, "end": 3}]

        result = _aggressive_relabel_from_strong_cues(conv)

        self.assertEqual(result[0]["speaker"], "Customer")

    def test_agent_self_name_ploi_flips_to_agent(self):
        # "พลอยขอ..." — agent using their own name → flip to Agent
        conv = [{"speaker": "Customer", "text": "งั้นเดี๋ยวพลอยขอระบุในระบบนะคะ", "start": 0, "end": 4}]

        result = _aggressive_relabel_from_strong_cues(conv)

        self.assertEqual(result[0]["speaker"], "Agent")

    def test_company_speak_flips_to_agent(self):
        conv = [{"speaker": "Customer", "text": "เบอร์ที่คุณลูกค้าโทรเข้ามาใช่ไหมคะ", "start": 0, "end": 3}]

        result = _aggressive_relabel_from_strong_cues(conv)

        self.assertEqual(result[0]["speaker"], "Agent")

    def test_customer_request_verb_flips_to_customer(self):
        conv = [{"speaker": "Agent", "text": "ติดตามเรื่องการส่งที่นอนที่สั่งไว้ค่ะ", "start": 0, "end": 3}]

        result = _aggressive_relabel_from_strong_cues(conv)

        self.assertEqual(result[0]["speaker"], "Customer")

    def test_mixed_cues_leaves_label_unchanged(self):
        # Text has both customer and agent cues → keep as-is (let splitter handle)
        conv = [{
            "speaker": "Agent",
            "text": "พี่สะดวกวันที่ 8 นะคะ คุณลูกค้า",
            "start": 0,
            "end": 3,
        }]

        result = _aggressive_relabel_from_strong_cues(conv)

        self.assertEqual(result[0]["speaker"], "Agent")  # unchanged

    def test_no_cue_leaves_label_unchanged(self):
        conv = [{"speaker": "Agent", "text": "ค่ะ โอเค", "start": 0, "end": 1}]

        result = _aggressive_relabel_from_strong_cues(conv)

        self.assertEqual(result[0]["speaker"], "Agent")

    def test_empty_conversation_is_noop(self):
        self.assertEqual(_aggressive_relabel_from_strong_cues([]), [])

    def test_correctly_labeled_segments_not_changed(self):
        # Already correctly labeled — should stay the same
        conv = [
            {"speaker": "Agent", "text": "สวัสดีค่ะ กลุ่มบริษัทที่นอนในเครือโลตัสค่ะ", "start": 0, "end": 2},
            {"speaker": "Customer", "text": "พี่สะดวกวันที่ 8 ค่ะ", "start": 2, "end": 4},
        ]

        result = _aggressive_relabel_from_strong_cues(conv)

        self.assertEqual(result[0]["speaker"], "Agent")
        self.assertEqual(result[1]["speaker"], "Customer")


if __name__ == "__main__":
    unittest.main()
