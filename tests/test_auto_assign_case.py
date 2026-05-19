"""Regression tests for smartvoice.pipeline._auto_assign_case.

Covers:
  - Recency short-circuit (same customer, recent open case) → no LLM, attach
  - Stale open case + different topic → LLM path + new case when LLM says so
  - No customer link → no-op (no case created)
"""

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from smartvoice import db, pipeline


class PipelineDBTestCase(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._patcher = patch.dict(os.environ, {"DB_PATH": self.db_path})
        self._patcher.start()
        db.init_db()

    def tearDown(self):
        self._patcher.stop()
        try:
            os.remove(self.db_path)
        except OSError:
            pass

    def _setup_customer_with_call(self, phone="0819879336"):
        cid = db.insert_customer(first_name="x", last_name="y", phone=phone)
        call_id = db.insert_call("a.wav", "ha", "/a.wav")
        db.link_call_customer(call_id=call_id, customer_id=cid, matched_by="auto_phone")
        return cid, call_id


class TestRecencyShortCircuit(PipelineDBTestCase):
    def test_recent_call_merges_without_llm(self):
        """Second call 18 min after first should merge into same case — no LLM call."""
        cid, call1 = self._setup_customer_with_call()

        # First call → creates case #1 (no open cases exist yet)
        pipeline._auto_assign_case(call1, {"topic": "คืน/เปลี่ยน/Trade-in", "summary": "s1"})
        call1_row = db.get_call_by_id(call1)
        self.assertIsNotNone(call1_row["case_id"])
        case_id = call1_row["case_id"]

        # Second call 18 min later, DIFFERENT topic — should still merge via recency
        call2 = db.insert_call("b.wav", "hb", "/b.wav")
        db.link_call_customer(call_id=call2, customer_id=cid, matched_by="auto_phone")

        # Mock ollama — must NOT be called
        with patch("smartvoice.pipeline.ollama_client") as mock_llm:
            pipeline._auto_assign_case(call2, {"topic": "สอบถามประกัน", "summary": "s2"})
            mock_llm.match_case.assert_not_called()

        call2_row = db.get_call_by_id(call2)
        self.assertEqual(call2_row["case_id"], case_id)
        # Case status should be bumped to follow_up
        case = db.get_case_by_id(case_id)
        self.assertEqual(case["status"], "follow_up")

    def test_filename_call_datetime_prevents_false_recent_merge(self):
        cid = db.insert_customer(first_name="x", last_name="y", phone="0819879336")
        call1 = db.insert_call(
            "20260101090000-0819879336-104-Inbound.wav",
            "ha",
            "/a.wav",
        )
        db.link_call_customer(call_id=call1, customer_id=cid, matched_by="auto_phone")
        pipeline._auto_assign_case(call1, {"topic": "สอบถามการจัดส่ง", "summary": "s1"})
        old_case = db.get_call_by_id(call1)["case_id"]

        call2 = db.insert_call(
            "20260110100000-0819879336-104-Inbound.wav",
            "hb",
            "/b.wav",
        )
        db.link_call_customer(call_id=call2, customer_id=cid, matched_by="auto_phone")

        with patch("smartvoice.pipeline.ollama_client") as mock_llm:
            mock_llm.match_case.return_value = {
                "match_case_id": None,
                "suggested_subject": "เรื่องใหม่",
            }
            pipeline._auto_assign_case(call2, {"topic": "สอบถามโปรโมชั่น", "summary": "s2"})
            mock_llm.match_case.assert_called_once()

        call2_row = db.get_call_by_id(call2)
        self.assertIsNotNone(call2_row["case_id"])
        self.assertNotEqual(call2_row["case_id"], old_case)

    def test_stale_case_falls_through_to_llm(self):
        """If last call is older than CASE_RECENCY_HOURS, LLM is consulted."""
        cid, call1 = self._setup_customer_with_call()
        # Manually create an OLD case with an old call
        old_case = db.create_case(cid, "old subject")
        conn = db.get_connection()
        old_time = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        with conn:
            conn.execute(
                "UPDATE calls SET case_id = ?, created_at = ? WHERE id = ?",
                (old_case, old_time, call1),
            )
        conn.close()

        call2 = db.insert_call("b.wav", "hb", "/b.wav")
        db.link_call_customer(call_id=call2, customer_id=cid, matched_by="auto_phone")

        # LLM says "new case"
        with patch("smartvoice.pipeline.ollama_client") as mock_llm:
            mock_llm.match_case.return_value = {
                "match_case_id": None,
                "suggested_subject": "เรื่องใหม่",
            }
            pipeline._auto_assign_case(call2, {"topic": "X", "summary": "s"})
            mock_llm.match_case.assert_called_once()

        call2_row = db.get_call_by_id(call2)
        self.assertIsNotNone(call2_row["case_id"])
        self.assertNotEqual(call2_row["case_id"], old_case)


class TestNoCustomerLink(PipelineDBTestCase):
    def test_no_link_skips_case_assignment(self):
        call_id = db.insert_call("nolink.wav", "h", "/n.wav")
        pipeline._auto_assign_case(call_id, {"topic": "X", "summary": "s"})
        row = db.get_call_by_id(call_id)
        self.assertIsNone(row["case_id"])


if __name__ == "__main__":
    unittest.main()
