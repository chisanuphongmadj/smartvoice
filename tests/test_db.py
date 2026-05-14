"""Tests for smartvoice.db — schema + idempotent inserts + case counts.

These tests use a temporary SQLite file per test to avoid touching prod data.
"""

import os
import tempfile
import unittest
from unittest.mock import patch

from smartvoice import db


class DBTestCase(unittest.TestCase):
    """Base class that creates a fresh temp DB for each test."""

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


class TestSchema(DBTestCase):
    def test_all_tables_created(self):
        conn = db.get_connection()
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        for expected in ("calls", "customers", "warranty_registrations",
                          "call_customer_links", "cases"):
            self.assertIn(expected, tables)

    def test_calls_has_new_columns(self):
        conn = db.get_connection()
        cols = {r[1] for r in conn.execute("PRAGMA table_info(calls)").fetchall()}
        conn.close()
        # Columns added via _migrate
        for expected in ("case_id", "customer_phone", "sentiment_reason",
                          "anomaly_severity", "processing_step",
                          "uploaded_by", "uploaded_by_role"):
            self.assertIn(expected, cols)


class TestIdempotentInserts(DBTestCase):
    def test_insert_customer_returns_existing_id_if_phone_duplicate(self):
        id1 = db.insert_customer(
            first_name="สมชาย", last_name="ใจดี", phone="0812345678"
        )
        id2 = db.insert_customer(
            first_name="Somchai", last_name="Jaidee", phone="0812345678"
        )
        self.assertEqual(id1, id2)

    def test_insert_customer_without_phone_allows_duplicates(self):
        id1 = db.insert_customer(first_name="A", last_name="B")
        id2 = db.insert_customer(first_name="A", last_name="B")
        self.assertNotEqual(id1, id2)

    def test_insert_warranty_returns_existing_id_if_registration_duplicate(self):
        cid = db.insert_customer(first_name="x", last_name="y", phone="0800000000")
        wid1 = db.insert_warranty(registration_no="REG001", customer_id=cid, brand="Omazz")
        wid2 = db.insert_warranty(registration_no="REG001", customer_id=cid, brand="Other")
        self.assertEqual(wid1, wid2)


class TestCaseCounts(DBTestCase):
    def test_empty_database(self):
        counts = db.get_case_counts()
        self.assertEqual(counts["total"], 0)
        self.assertEqual(counts["open"], 0)
        self.assertEqual(counts["follow_up"], 0)
        self.assertEqual(counts["closed"], 0)

    def test_mixed_statuses(self):
        cid = db.insert_customer(first_name="x", last_name="y", phone="0899999999")
        db.create_case(cid, "subject 1", status="open")
        db.create_case(cid, "subject 2", status="open")
        db.create_case(cid, "subject 3", status="follow_up")
        db.create_case(cid, "subject 4", status="closed")
        counts = db.get_case_counts()
        self.assertEqual(counts["total"], 4)
        self.assertEqual(counts["open"], 2)
        self.assertEqual(counts["follow_up"], 1)
        self.assertEqual(counts["closed"], 1)


class TestOrphanCaseCleanup(DBTestCase):
    """Regression: deleting a call must also clean up its orphan case."""

    def _setup_call_with_case(self, phone="0800000001"):
        cid = db.insert_customer(first_name="x", last_name="y", phone=phone)
        call_id = db.insert_call(f"call-{phone}.wav", f"hash-{phone}", "/fake.wav")
        db.link_call_customer(call_id=call_id, customer_id=cid, matched_by="auto_phone")
        case_id = db.create_case(cid, "test subject")
        db.assign_call_to_case(call_id, case_id)
        return call_id, case_id, cid

    def test_delete_call_removes_orphan_case(self):
        call_id, case_id, _ = self._setup_call_with_case()
        self.assertEqual(db.count_orphan_cases(), 0)
        removed = db.delete_call(call_id)
        self.assertEqual(removed, 1)
        self.assertIsNone(db.get_case_by_id(case_id))

    def test_delete_call_keeps_shared_case(self):
        """Case with 2 calls should survive if only 1 call is deleted."""
        call1, case_id, cid = self._setup_call_with_case(phone="0800000010")
        # Add a second call to the same case
        call2 = db.insert_call("call2.wav", "hash2", "/fake2.wav")
        db.link_call_customer(call_id=call2, customer_id=cid, matched_by="manual")
        db.assign_call_to_case(call2, case_id)
        removed = db.delete_call(call1)
        self.assertEqual(removed, 0)
        self.assertIsNotNone(db.get_case_by_id(case_id))

    def test_delete_calls_bulk_cleans_multiple_orphans(self):
        call1, case1, _ = self._setup_call_with_case(phone="0800000020")
        call2, case2, _ = self._setup_call_with_case(phone="0800000021")
        removed = db.delete_calls_bulk([call1, call2])
        self.assertEqual(removed, 2)
        self.assertIsNone(db.get_case_by_id(case1))
        self.assertIsNone(db.get_case_by_id(case2))

    def test_count_and_delete_orphan_cases(self):
        cid = db.insert_customer(first_name="x", last_name="y", phone="0800000030")
        # Create 3 cases with no calls attached
        db.create_case(cid, "orphan 1")
        db.create_case(cid, "orphan 2")
        db.create_case(cid, "orphan 3")
        self.assertEqual(db.count_orphan_cases(), 3)
        n = db.delete_orphan_cases()
        self.assertEqual(n, 3)
        self.assertEqual(db.count_orphan_cases(), 0)

    def test_delete_call_also_removes_customer_link(self):
        call_id, _, cid = self._setup_call_with_case(phone="0800000040")
        self.assertIsNotNone(db.get_call_customer_link(call_id))
        db.delete_call(call_id)
        self.assertIsNone(db.get_call_customer_link(call_id))


class TestGetCallsByCustomer(DBTestCase):
    def test_empty(self):
        cid = db.insert_customer(first_name="x", last_name="y", phone="0812345678")
        self.assertEqual(db.get_calls_by_customer(cid), [])

    def test_returns_linked_calls(self):
        cid = db.insert_customer(first_name="x", last_name="y", phone="0812345678")
        call_id = db.insert_call("call.wav", "hash123", "/fake/path.wav")
        db.link_call_customer(call_id=call_id, customer_id=cid, matched_by="auto_phone")
        rows = db.get_calls_by_customer(cid)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], call_id)
        self.assertEqual(rows[0]["matched_by"], "auto_phone")


class TestMergeCases(DBTestCase):
    """Regression: merge_cases must move all calls + delete src case."""

    def _setup_two_cases(self):
        cid = db.insert_customer(first_name="x", last_name="y", phone="0800000050")
        call_a = db.insert_call("a.wav", "ha", "/a.wav")
        call_b = db.insert_call("b.wav", "hb", "/b.wav")
        db.link_call_customer(call_id=call_a, customer_id=cid, matched_by="auto_phone")
        db.link_call_customer(call_id=call_b, customer_id=cid, matched_by="auto_phone")
        case_a = db.create_case(cid, "subject A")
        case_b = db.create_case(cid, "subject B")
        db.assign_call_to_case(call_a, case_a)
        db.assign_call_to_case(call_b, case_b)
        return call_a, call_b, case_a, case_b

    def test_merge_moves_calls_and_deletes_src(self):
        call_a, call_b, case_a, case_b = self._setup_two_cases()
        moved = db.merge_cases(src_case_id=case_b, dst_case_id=case_a)
        self.assertEqual(moved, 1)
        # case_b must be gone
        self.assertIsNone(db.get_case_by_id(case_b))
        # case_a must now hold both calls
        calls = db.get_calls_by_case(case_a)
        ids = {c["id"] for c in calls}
        self.assertEqual(ids, {call_a, call_b})

    def test_merge_same_id_is_noop(self):
        _, _, case_a, _ = self._setup_two_cases()
        self.assertEqual(db.merge_cases(case_a, case_a), 0)
        self.assertIsNotNone(db.get_case_by_id(case_a))

    def test_merge_invalid_id_raises(self):
        with self.assertRaises(ValueError):
            db.merge_cases(99999, 88888)


class TestInsertCallWithUploader(DBTestCase):
    """Regression: insert_call must persist uploaded_by + uploaded_by_role."""

    def test_insert_without_uploader_keeps_nulls(self):
        """Backward-compat: old callers that don't pass uploader info still work."""
        cid = db.insert_call("a.wav", "h_legacy", "/a.wav")
        row = db.get_call_by_id(cid)
        self.assertIsNone(row["uploaded_by"])
        self.assertIsNone(row["uploaded_by_role"])

    def test_insert_with_uploader_persists_both_fields(self):
        cid = db.insert_call(
            "b.wav", "h_new", "/b.wav",
            uploaded_by="สุภาพร จันทร์แก้ว",
            uploaded_by_role="Supervisor",
        )
        row = db.get_call_by_id(cid)
        self.assertEqual(row["uploaded_by"], "สุภาพร จันทร์แก้ว")
        self.assertEqual(row["uploaded_by_role"], "Supervisor")


class TestLatestCallTimeInCase(DBTestCase):
    def test_empty_case_returns_none(self):
        cid = db.insert_customer(first_name="x", last_name="y", phone="0800000060")
        case_id = db.create_case(cid, "empty")
        self.assertIsNone(db.latest_call_time_in_case(case_id))

    def test_returns_max_created_at(self):
        cid = db.insert_customer(first_name="x", last_name="y", phone="0800000061")
        case_id = db.create_case(cid, "with calls")
        c1 = db.insert_call("a.wav", "h1", "/a.wav")
        c2 = db.insert_call("b.wav", "h2", "/b.wav")
        db.assign_call_to_case(c1, case_id)
        db.assign_call_to_case(c2, case_id)
        latest = db.latest_call_time_in_case(case_id)
        self.assertIsNotNone(latest)
        # Should be an ISO-like timestamp string
        self.assertIn("T", latest)


if __name__ == "__main__":
    unittest.main()
