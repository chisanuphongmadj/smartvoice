"""Tests for smartvoice.db — schema + idempotent inserts + case counts.

These tests use a temporary SQLite file per test to avoid touching prod data.
"""

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
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
                          "uploaded_by", "uploaded_by_role",
                          "topic_detail"):
            self.assertIn(expected, cols)

    def test_foreign_keys_are_enabled(self):
        conn = db.get_connection()
        enabled = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        conn.close()
        self.assertEqual(enabled, 1)


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


class TestScaleFriendlyHelpers(DBTestCase):
    """Admin page must stay responsive at 10K+ uploads — these helpers replace
    a full-table scan with SQL-side counts + scoped fetches."""

    def _seed(self):
        # 3 uploaded, 1 processing, 2 done, 1 error
        for i in range(3):
            db.insert_call(f"u_{i}.wav", f"hU{i}", f"/u_{i}.wav")
        cid = db.insert_call("p.wav", "hP", "/p.wav")
        db.update_call_status(cid, "processing")
        for i in range(2):
            cid = db.insert_call(f"d_{i}.wav", f"hD{i}", f"/d_{i}.wav")
            db.update_call_status(cid, "done")
        cid = db.insert_call("e.wav", "hE", "/e.wav")
        db.update_call_status(cid, "error", error_msg="boom")

    def test_count_calls_by_status_returns_all_buckets(self):
        self._seed()
        counts = db.count_calls_by_status()
        self.assertEqual(counts["uploaded"], 3)
        self.assertEqual(counts["processing"], 1)
        self.assertEqual(counts["done"], 2)
        self.assertEqual(counts["error"], 1)
        self.assertEqual(counts["total"], 7)

    def test_count_calls_empty_database(self):
        counts = db.count_calls_by_status()
        self.assertEqual(counts, {"uploaded": 0, "processing": 0, "done": 0,
                                  "error": 0, "total": 0})

    def test_get_all_calls_limit_caps_rows(self):
        self._seed()
        self.assertEqual(len(db.get_all_calls(limit=3)), 3)

    def test_get_all_calls_no_limit_returns_everything(self):
        # Backward-compat: callers that don't pass limit still get the full list
        self._seed()
        self.assertEqual(len(db.get_all_calls()), 7)

    def test_get_pending_call_ids_returns_only_uploaded(self):
        self._seed()
        ids = db.get_pending_call_ids()
        self.assertEqual(len(ids), 3)
        # All returned ids must really be 'uploaded' status
        for cid in ids:
            self.assertEqual(db.get_call_by_id(cid)["status"], "uploaded")

    def test_get_processing_calls_returns_only_processing(self):
        self._seed()
        rows = db.get_processing_calls()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "processing")


class TestUpdateCallResultsTopicDetail(DBTestCase):
    """topic_detail must persist (drill-down for "แจ้งปัญหาสินค้า" — Omazz request)."""

    def _seed(self) -> int:
        cid = db.insert_call("c.wav", "hX", "/c.wav")
        return cid

    def test_persists_topic_detail(self):
        cid = self._seed()
        db.update_call_results(
            call_id=cid, transcript="t", summary="s", sentiment="neutral",
            topic="แจ้งปัญหาสินค้า", topic_detail="ผ้าขาด/ผ้าหุ้มชำรุด",
        )
        row = db.get_call_by_id(cid)
        self.assertEqual(row["topic_detail"], "ผ้าขาด/ผ้าหุ้มชำรุด")
        self.assertEqual(row["status"], "done")

    def test_default_topic_detail_is_empty(self):
        cid = self._seed()
        db.update_call_results(
            call_id=cid, transcript="t", summary="s", sentiment="neutral",
            topic="สอบถามข้อมูลสินค้า",
        )
        row = db.get_call_by_id(cid)
        self.assertEqual(row["topic_detail"] or "", "")


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


class TestGetDoneCallsPagination(DBTestCase):
    """Regression: dashboard must be able to cap rows on large datasets without
    breaking the no-arg behavior that other callers (and older code) rely on."""

    def _seed_done_calls(self, n: int) -> list[int]:
        ids = []
        for i in range(n):
            cid = db.insert_call(f"call_{i}.wav", f"hash_{i}", f"/fake_{i}.wav")
            db.update_call_status(cid, "done")
            ids.append(cid)
        return ids

    def test_no_arg_returns_all(self):
        self._seed_done_calls(7)
        self.assertEqual(len(db.get_done_calls()), 7)

    def test_limit_caps_rows(self):
        self._seed_done_calls(10)
        self.assertEqual(len(db.get_done_calls(limit=3)), 3)

    def test_limit_larger_than_dataset_is_safe(self):
        self._seed_done_calls(2)
        self.assertEqual(len(db.get_done_calls(limit=100)), 2)

    def test_offset_skips_rows(self):
        self._seed_done_calls(5)
        page1 = db.get_done_calls(limit=2, offset=0)
        page2 = db.get_done_calls(limit=2, offset=2)
        # Pages should not overlap
        self.assertEqual(len(page1), 2)
        self.assertEqual(len(page2), 2)
        self.assertNotEqual(page1[0]["id"], page2[0]["id"])

    def test_only_done_status_returned(self):
        # uploaded + processing must be excluded
        db.insert_call("uploaded.wav", "h1", "/u.wav")
        cid = db.insert_call("done.wav", "h2", "/d.wav")
        db.update_call_status(cid, "done")
        cid2 = db.insert_call("proc.wav", "h3", "/p.wav")
        db.update_call_status(cid2, "processing")
        rows = db.get_done_calls()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["filename"], "done.wav")

    def test_count_done_calls(self):
        self.assertEqual(db.count_done_calls(), 0)
        self._seed_done_calls(4)
        db.insert_call("uploaded.wav", "u1", "/u.wav")  # not done
        self.assertEqual(db.count_done_calls(), 4)


class TestGetAllCasesFilters(DBTestCase):
    """Regression: Case Management dashboard must be filterable + paginated
    for installs with thousands of cases. Default no-arg behavior is kept."""

    def _seed(self):
        c1 = db.insert_customer(first_name="สุภาพร", last_name="จันทร์แก้ว", phone="0800000001")
        c2 = db.insert_customer(first_name="ธนวัฒน์", last_name="รักษาศิลป์", phone="0800000002")
        # 3 open, 2 follow_up, 1 closed
        db.create_case(c1, "แจ้งปัญหาที่นอน", status="open")
        db.create_case(c1, "สอบถามจัดส่ง", status="open")
        db.create_case(c2, "เปลี่ยนคืน", status="open")
        db.create_case(c1, "ติดตามเคลม", status="follow_up")
        db.create_case(c2, "นัดช่าง", status="follow_up")
        db.create_case(c2, "ปิดเรื่องแล้ว", status="closed")

    def test_no_arg_returns_all(self):
        self._seed()
        self.assertEqual(len(db.get_all_cases()), 6)

    def test_status_filter(self):
        self._seed()
        self.assertEqual(len(db.get_all_cases(status="open")), 3)
        self.assertEqual(len(db.get_all_cases(status="follow_up")), 2)
        self.assertEqual(len(db.get_all_cases(status="closed")), 1)

    def test_search_matches_subject(self):
        self._seed()
        rows = db.get_all_cases(search="แจ้งปัญหา")
        self.assertEqual(len(rows), 1)
        self.assertIn("แจ้งปัญหา", rows[0]["subject"])

    def test_search_matches_customer_name(self):
        self._seed()
        rows = db.get_all_cases(search="ธนวัฒน์")
        self.assertEqual(len(rows), 3)  # 3 cases owned by ธนวัฒน์

    def test_search_matches_phone(self):
        self._seed()
        rows = db.get_all_cases(search="0800000001")
        self.assertEqual(len(rows), 3)  # 3 cases owned by 0800000001

    def test_limit_offset_paginates(self):
        self._seed()
        page1 = db.get_all_cases(limit=2, offset=0)
        page2 = db.get_all_cases(limit=2, offset=2)
        self.assertEqual(len(page1), 2)
        self.assertEqual(len(page2), 2)
        self.assertNotEqual(page1[0]["id"], page2[0]["id"])

    def test_combined_status_and_search(self):
        self._seed()
        rows = db.get_all_cases(status="open", search="ที่นอน")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "open")
        self.assertIn("ที่นอน", rows[0]["subject"])

    def test_count_cases_unfiltered(self):
        self._seed()
        self.assertEqual(db.count_cases(), 6)

    def test_count_cases_with_status(self):
        self._seed()
        self.assertEqual(db.count_cases(status="open"), 3)
        self.assertEqual(db.count_cases(status="closed"), 1)

    def test_count_cases_with_search(self):
        self._seed()
        self.assertEqual(db.count_cases(search="สุภาพร"), 3)


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


class TestRecoverStaleProcessing(DBTestCase):
    def test_recover_stale_processing_resets_old_processing_calls(self):
        call_id = db.insert_call("stale.wav", "h_stale", "/stale.wav")
        db.update_call_status(call_id, "processing")
        stale_time = (
            datetime.now(timezone.utc) - timedelta(minutes=240)
        ).isoformat(timespec="seconds")
        conn = db.get_connection()
        with conn:
            conn.execute(
                "UPDATE calls SET updated_at = ?, processing_step = ? WHERE id = ?",
                (stale_time, "working", call_id),
            )
        conn.close()

        recovered = db.recover_stale_processing(180)
        row = db.get_call_by_id(call_id)

        self.assertEqual(recovered, 1)
        self.assertEqual(row["status"], "uploaded")
        self.assertIsNone(row["processing_step"])
        self.assertIn("Recovered from stale processing", row["error_msg"])

    def test_recover_stale_processing_keeps_recent_processing_calls(self):
        call_id = db.insert_call("recent.wav", "h_recent", "/recent.wav")
        db.update_call_status(call_id, "processing")

        recovered = db.recover_stale_processing(180)
        row = db.get_call_by_id(call_id)

        self.assertEqual(recovered, 0)
        self.assertEqual(row["status"], "processing")


if __name__ == "__main__":
    unittest.main()
