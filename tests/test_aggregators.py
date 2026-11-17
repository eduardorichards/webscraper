"""Tests for the aggregator company list: data file, table sync, detail-fetch skip."""

import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

from scraper import KeywordConfig, KeywordMatcher
from utils.aggregators import AGGREGATORS_FILE, load_aggregators
from utils.sqlite_storage import SQLiteStorage

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _write_file(path, companies, categories=("job_board", "mass_reposter")):
    data = {"categories": {c: c for c in categories},
            "companies": [{"company": c, "category": cat, "reason": r}
                          for c, cat, r in companies]}
    Path(path).write_text(json.dumps(data), encoding="utf-8")


class TestDataFile(unittest.TestCase):

    def test_shipped_file_is_valid(self):
        entries = load_aggregators()
        companies = [c for c, _, _ in entries]
        self.assertIn("Quik Hire Staffing", companies)
        self.assertEqual(len(companies), 24)
        self.assertEqual(AGGREGATORS_FILE, PROJECT_ROOT / "config" / "aggregators.json")
        self.assertEqual({cat for _, cat, _ in entries},
                         {"job_board", "talent_marketplace", "mass_reposter"})
        self.assertTrue(all(reason for _, _, reason in entries))

    def test_app_does_not_import_analysis(self):
        for path in PROJECT_ROOT.rglob("*.py"):
            rel = path.relative_to(PROJECT_ROOT)
            if rel.parts[0] in ("analysis", ".venv", "venv", "tests"):
                continue
            source = path.read_text(encoding="utf-8")
            self.assertNotRegex(source, r"(?m)^\s*(from|import)\s+analysis\b", str(rel))

    def test_invalid_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.json"
            _write_file(path, [("Acme", "unknown_category", "x")])
            with self.assertRaisesRegex(ValueError, "unknown category"):
                load_aggregators(path)
            _write_file(path, [("Acme", "job_board", "x"), ("Acme", "job_board", "y")])
            with self.assertRaisesRegex(ValueError, "duplicated"):
                load_aggregators(path)
            _write_file(path, [("  ", "job_board", "x")])
            with self.assertRaisesRegex(ValueError, "without a company"):
                load_aggregators(path)


class _TempDbTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = os.path.join(self.tmp.name, "jobs.db")
        self.agg_path = os.path.join(self.tmp.name, "aggregators.json")

    def _open(self, companies):
        _write_file(self.agg_path, companies)
        with redirect_stdout(StringIO()):
            return SQLiteStorage(db_file=self.db_path, aggregators_file=self.agg_path)

    def _rows(self):
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT company, category, reason FROM aggregator_companies"
                            " ORDER BY company").fetchall()
        conn.close()
        return rows


class TestSync(_TempDbTest):

    def test_sync_is_idempotent_and_follows_the_file(self):
        self._open([("Feed A", "job_board", "feed"), ("Poster B", "mass_reposter", "spam")])
        self._open([("Feed A", "job_board", "feed"), ("Poster B", "mass_reposter", "spam")])
        self.assertEqual(self._rows(), [("Feed A", "job_board", "feed"),
                                        ("Poster B", "mass_reposter", "spam")])

        # Changed reason, removed company, new company
        self._open([("Feed A", "job_board", "feed v2"), ("Board C", "job_board", None)])
        self.assertEqual(self._rows(), [("Board C", "job_board", None),
                                        ("Feed A", "job_board", "feed v2")])

        self._open([])
        self.assertEqual(self._rows(), [])

    def test_blacklist_is_separate(self):
        storage = self._open([("Feed A", "job_board", "feed")])
        storage.add_blacklisted_company("Manual Co")
        self._open([])
        self.assertEqual(storage.get_blacklisted_companies(), ["Manual Co"])
        self.assertEqual(storage.get_aggregator_companies(), [])


class TestDetailFetchSkip(_TempDbTest):

    def setUp(self):
        super().setUp()
        self.storage = self._open([("Feed A", "job_board", "feed")])
        conn = sqlite3.connect(self.db_path)
        conn.executemany(
            "INSERT INTO job_searches (linkedin_job_id, title, company, scraped_at)"
            " VALUES (?, ?, ?, ?)",
            [("4000000001", "Dev", "Acme", "2026-11-14T10:00:00Z"),
             ("4000000002", "Dev", "Feed A", None),                    # old row
             ("4000000003", "QA", "Feed A", "2026-11-14T10:00:00Z"),
             ("4000000004", "Ops", "Feed A", "2026-11-14T12:00:00Z"),
             ("4000000004", "Ops", "Feed A", "2026-11-14T13:00:00Z")])
        conn.commit()
        conn.close()

    def test_queue_excludes_aggregators(self):
        ids = [j["linkedin_job_id"] for j in self.storage.get_jobs_without_analysis()]
        self.assertEqual(ids, ["4000000001"])
        all_ids = [j["linkedin_job_id"] for j in
                   self.storage.get_jobs_without_analysis(exclude_aggregators=False)]
        self.assertEqual(all_ids, ["4000000001", "4000000002", "4000000003", "4000000004"])

    def test_skipped_count(self):
        self.assertEqual(self.storage.count_skipped_aggregator_jobs(), 3)
        self.assertEqual(
            self.storage.count_skipped_aggregator_jobs(since="2026-11-14T11:00:00Z"), 1)
        self.assertEqual(
            self.storage.count_skipped_aggregator_jobs(since="2026-11-14T09:00:00Z"), 2)

    def test_matcher_never_fetches_aggregator_jobs_and_logs_count(self):
        matcher = KeywordMatcher(self.storage, KeywordConfig(keywords=["Java"]))
        with mock.patch.object(matcher.detail_scraper, "scrape_job_details",
                               return_value=None) as fetch, \
                redirect_stdout(StringIO()), \
                self.assertLogs("scraper.core.keyword_matcher", "INFO") as logs:
            matcher.analyze_jobs(since="2026-11-14T11:00:00Z")
        self.assertEqual([c.args[0] for c in fetch.call_args_list],
                         ["https://www.linkedin.com/jobs/view/4000000001/"])
        self.assertIn("Skipped 1 detail fetches for aggregator companies", logs.output[0])
        # Search hits are kept; aggregator jobs get no job_posts row
        conn = sqlite3.connect(self.db_path)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM job_searches").fetchone()[0], 5)
        self.assertEqual(conn.execute("SELECT linkedin_job_id FROM job_posts").fetchall(),
                         [("4000000001",)])
        conn.close()


if __name__ == "__main__":
    unittest.main()
