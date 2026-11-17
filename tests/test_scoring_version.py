"""Tests for scoring_version and scripts/rescore_jobs.py (no HTTP)."""

import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest import mock

from scraper import KeywordConfig, KeywordMatcher, MatchResult
from scraper.models import keyword_config as keyword_config_module
from scripts import rescore_jobs
from utils.sqlite_storage import SQLiteStorage


class TestScoringVersion(unittest.TestCase):

    def test_stable_and_short(self):
        a = KeywordConfig(["Java", "SQL"], {"Java": 10, "SQL": 3})
        b = KeywordConfig(["SQL", "Java"], {"SQL": 3.0, "Java": 10.0, "Unused": 99})
        self.assertEqual(a.scoring_version(), b.scoring_version())
        self.assertRegex(a.scoring_version(), r'^[0-9a-f]{12}$')

    def test_changes_with_what_affects_scores(self):
        base = KeywordConfig(["Java", "SQL"], {"Java": 10}).scoring_version()
        self.assertNotEqual(base, KeywordConfig(["Java", "SQL"], {"Java": 8}).scoring_version())
        self.assertNotEqual(base, KeywordConfig(["Java"], {"Java": 10}).scoring_version())
        self.assertNotEqual(base, KeywordConfig(["Java", "SQL"], {"Java": 10},
                                                case_sensitive=True).scoring_version())
        with mock.patch.object(keyword_config_module, 'SCORER_VERSION',
                               keyword_config_module.SCORER_VERSION + 1):
            self.assertNotEqual(base, KeywordConfig(["Java", "SQL"],
                                                    {"Java": 10}).scoring_version())

    def test_calculate_score_sets_version(self):
        config = KeywordConfig(["Java"], {"Java": 2})
        result = MatchResult("4000000001")
        self.assertIsNone(result.scoring_version)
        result.keyword_matches = {"Java": 3}
        result.calculate_score(config)
        self.assertEqual(result.scoring_version, config.scoring_version())

    def test_each_keyword_counts_at_most_twice(self):
        config = KeywordConfig(["Java", "SQL", "Go"], {"Java": 10, "SQL": 3})
        result = MatchResult("4000000001")
        result.keyword_matches = {"Java": 7, "SQL": 1, "Go": 0}
        result.calculate_score(config)
        self.assertEqual(result.weighted_score, 2 * 10 + 1 * 3)
        self.assertEqual(result.total_matches, 8)  # raw counts, uncapped
        self.assertEqual(result.matched_keywords, ["Java", "SQL"])


class _DbTest(unittest.TestCase):

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        with redirect_stdout(StringIO()):
            self.storage = SQLiteStorage(db_file=self.db_path)

    def tearDown(self):
        os.remove(self.db_path)

    def _query(self, sql):
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(sql).fetchall()
        conn.close()
        return rows


class TestMatcherStoresVersion(_DbTest):

    def test_version_only_on_scored_rows(self):
        conn = sqlite3.connect(self.db_path)
        conn.executemany("INSERT INTO job_searches (linkedin_job_id, title, company)"
                         " VALUES (?, ?, 'Acme')",
                         [("4000000001", "A"), ("4000000002", "B"), ("4000000003", "C")])
        conn.commit()
        conn.close()
        config = KeywordConfig(["Java"], {"Java": 2})
        matcher = KeywordMatcher(self.storage, config)
        details = {"4000000001": {"description": "Java and Java"},
                   "4000000002": {"closed": True},
                   "4000000003": None}
        fetch = lambda url: details[url.rstrip('/').rsplit('/', 1)[1]]  # noqa: E731
        with mock.patch.object(matcher.detail_scraper, "scrape_job_details", side_effect=fetch), \
                redirect_stdout(StringIO()), self.assertLogs(level='INFO'):
            matcher.analyze_jobs()
        self.assertEqual(
            self._query("SELECT linkedin_job_id, weighted_score, scoring_version"
                        " FROM job_posts ORDER BY linkedin_job_id"),
            [("4000000001", 4.0, config.scoring_version()),
             ("4000000002", 0.0, None),
             ("4000000003", 0.0, None)])


class TestRescore(_DbTest):

    def setUp(self):
        super().setUp()
        conn = sqlite3.connect(self.db_path)
        conn.executemany(
            "INSERT INTO job_posts (linkedin_job_id, description, date_time, applicant_count,"
            " total_matches, weighted_score, matched_keywords, match_percentage,"
            " scoring_version) VALUES (?, ?, '2026-11-01T10:00:00Z', 7, ?, ?, ?, ?, ?)",
            [("4000000001", "Java Java SQL", 3, 99.0, "Java,SQL", 100.0, None),
             ("4000000002", "python only", 1, 5.0, "Python", 50.0, "oldversion00"),
             ("4000000003", None, 0, 0.0, "", 0.0, None)])       # failed fetch
        conn.commit()
        conn.close()
        self.config = KeywordConfig(["Java", "SQL"], {"Java": 10, "SQL": 3})

    def _main(self, *argv):
        with redirect_stdout(StringIO()) as out:
            code = rescore_jobs.main(list(argv), db_file=self.db_path,
                                     keyword_config=self.config)
        return code, out.getvalue()

    def _rows(self):
        return self._query(
            "SELECT linkedin_job_id, total_matches, weighted_score, matched_keywords,"
            " match_percentage, scoring_version, applicant_count, description"
            " FROM job_posts ORDER BY linkedin_job_id")

    def test_dry_run_changes_nothing(self):
        before = self._rows()
        code, out = self._main("--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("2 jobs would be re-scored", out)
        self.assertEqual(self._rows(), before)

    def test_rescores_with_current_config(self):
        version = self.config.scoring_version()
        with self.assertLogs(level='INFO') as logs:
            self.assertEqual(self._main()[0], 0)
        self.assertEqual(self._rows(), [
            ("4000000001", 3, 23.0, "Java,SQL", 100.0, version, 7, "Java Java SQL"),
            ("4000000002", 0, 0.0, "", 0.0, version, 7, "python only"),
            ("4000000003", 0, 0.0, "", 0.0, None, 7, None),          # untouched
        ])
        self.assertIn("rescored=2 / score_changed=2", logs.output[-1])

    def test_rerun_is_a_noop_unless_all(self):
        with self.assertLogs(level='INFO'):
            self._main()
        self.assertIn("0 jobs would be re-scored", self._main("--dry-run")[1])
        self.assertIn("2 jobs would be re-scored", self._main("--dry-run", "--all")[1])
        with self.assertLogs(level='INFO') as logs:
            self._main("--all")
        self.assertIn("rescored=2 / score_changed=0", logs.output[-1])

    def test_limit_and_batches(self):
        with self.assertLogs(level='INFO'):
            rescored, _ = rescore_jobs.rescore(self.db_path, self.config, limit=1)
        self.assertEqual(rescored, 1)
        with self.assertLogs(level='INFO'):
            rescored, _ = rescore_jobs.rescore(self.db_path, self.config, batch_size=1)
        self.assertEqual(rescored, 1)       # only the remaining one
        self.assertEqual(self._query(
            "SELECT COUNT(*) FROM job_posts WHERE scoring_version IS NOT NULL")[0][0], 2)


if __name__ == '__main__':
    unittest.main()
