"""Tests for the idempotent schema migrations in SQLiteStorage._ensure_db_exists."""

import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO

from utils.sqlite_storage import SQLiteStorage

# Schema as it was before search_runs / scraped_at / applicant_count_qualifier
LEGACY_SCHEMA = """
CREATE TABLE job_searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    linkedin_job_id TEXT,
    title TEXT,
    company TEXT,
    location TEXT,
    company_url TEXT,
    search_keywords TEXT,
    search_location TEXT,
    search_experience TEXT,
    search_remote TEXT
);
CREATE TABLE job_posts (
    linkedin_job_id TEXT UNIQUE NOT NULL,
    description TEXT,
    applicant_count INTEGER,
    date_time TIMESTAMP,
    total_matches INTEGER,
    weighted_score REAL,
    matched_keywords TEXT,
    match_percentage REAL,
    employment_type TEXT,
    job_function TEXT,
    seniority_level TEXT,
    industries TEXT
);
CREATE TABLE blacklisted_companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT UNIQUE NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class TestMigrations(unittest.TestCase):

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        os.remove(self.db_path)  # Let each test decide how the DB starts

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _open_storage(self):
        with redirect_stdout(StringIO()):
            return SQLiteStorage(db_file=self.db_path)

    def _columns(self, table):
        conn = sqlite3.connect(self.db_path)
        cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
        conn.close()
        return cols

    def _query(self, sql, params=()):
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return rows

    def _create_legacy_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.executescript(LEGACY_SCHEMA)
        conn.executemany(
            "INSERT INTO job_searches (linkedin_job_id, title, company, location)"
            " VALUES (?, ?, ?, ?)",
            [('100', 'Dev A', 'Acme', 'Remote'),
             ('200', 'Dev B', 'Globex', 'Remote'),
             ('300', 'Dev C', 'Initech', 'Remote'),
             ('300', 'Dev C', 'Initech', 'Remote')])
        conn.executemany(
            "INSERT INTO job_posts (linkedin_job_id, applicant_count, date_time,"
            " weighted_score) VALUES (?, ?, ?, ?)",
            [('100', 201, '2026-10-01T10:00:00Z', 5.0),   # old "Over 200"
             ('200', 25, '2026-10-02T10:00:00Z', 3.0),    # old "first 25" (or exact 25)
             ('300', 87, '2026-10-03T10:00:00Z', 1.0)])
        conn.commit()
        conn.close()

    def _assert_migrated_schema(self):
        self.assertIn('scraped_at', self._columns('job_searches'))
        self.assertIn('search_run_id', self._columns('job_searches'))
        self.assertIn('scraped_at', self._columns('job_posts'))
        self.assertIn('applicant_count_qualifier', self._columns('job_posts'))
        self.assertIn('apply_type', self._columns('job_posts'))
        self.assertIn('apply_url', self._columns('job_posts'))
        self.assertIn('scoring_version', self._columns('job_posts'))
        self.assertIn('posted_at', self._columns('job_posts'))
        self.assertIn('source', self._columns('job_searches'))
        self.assertIn('job_url', self._columns('job_searches'))
        self.assertEqual(
            self._columns('companies'),
            ['name', 'ats', 'slug', 'priority', 'hires_in_ar', 'notes',
             'active', 'last_checked_at', 'last_job_count'])
        self.assertGreater(self._query("SELECT COUNT(*) FROM companies")[0][0], 0)
        self.assertEqual(
            self._columns('search_runs'),
            ['id', 'template_name', 'keywords', 'location', 'started_at',
             'finished_at', 'jobs_found', 'new_jobs', 'status', 'error',
             'pages_fetched', 'hit_page_limit'])
        self.assertEqual(self._columns('aggregator_companies'),
                         ['company', 'category', 'reason'])
        self.assertGreater(
            self._query("SELECT COUNT(*) FROM aggregator_companies")[0][0], 0)
        indexes = {r[0] for r in self._query(
            "SELECT name FROM sqlite_master WHERE type = 'index'")}
        self.assertIn('idx_job_searches_run', indexes)
        self.assertIn('idx_job_posts_employment_type', indexes)
        self.assertEqual(self._columns('applications'),
                         ['linkedin_job_id', 'applied_on', 'notes', 'created_at',
                          'updated_at'])

    def test_fresh_db_init_twice(self):
        self._open_storage()
        self._open_storage()
        self._assert_migrated_schema()
        # No duplicated columns
        cols = self._columns('job_posts')
        self.assertEqual(len(cols), len(set(cols)))

    def test_legacy_db_migrates_without_data_loss(self):
        self._create_legacy_db()
        self._open_storage()
        self._assert_migrated_schema()

        self.assertEqual(self._query("SELECT COUNT(*) FROM job_searches")[0][0], 4)
        self.assertEqual(self._query("SELECT COUNT(*) FROM job_posts")[0][0], 3)
        # New columns stay NULL on existing rows: no backfill
        self.assertEqual(self._query(
            "SELECT COUNT(*) FROM job_searches"
            " WHERE scraped_at IS NOT NULL OR search_run_id IS NOT NULL")[0][0], 0)
        self.assertEqual(self._query(
            "SELECT COUNT(*) FROM job_posts WHERE scraped_at IS NOT NULL")[0][0], 0)
        self.assertEqual(self._query(
            "SELECT COUNT(*) FROM job_posts"
            " WHERE apply_type IS NOT NULL OR apply_url IS NOT NULL")[0][0], 0)
        self.assertEqual(self._query(
            "SELECT COUNT(*) FROM job_posts WHERE scoring_version IS NOT NULL")[0][0], 0)
        # Old rows are LinkedIn rows: source NULL, no job_url, no posted_at
        self.assertEqual(self._query(
            "SELECT COUNT(*) FROM job_searches"
            " WHERE source IS NOT NULL OR job_url IS NOT NULL")[0][0], 0)
        self.assertEqual(self._query(
            "SELECT COUNT(*) FROM job_posts WHERE posted_at IS NOT NULL")[0][0], 0)
        # The views still show them, dated by date_time
        self.assertEqual(
            self._query("SELECT date_time, source, job_url FROM job_summary"
                        " WHERE linkedin_job_id = '300'"),
            [('2026-10-03T10:00:00Z', None, None)])
        # Other data untouched
        self.assertEqual(
            self._query("SELECT date_time, weighted_score FROM job_posts"
                        " WHERE linkedin_job_id = '300'"),
            [('2026-10-03T10:00:00Z', 1.0)])

    def test_legacy_201_becomes_over_200(self):
        self._create_legacy_db()
        self._open_storage()
        rows = dict((r[0], (r[1], r[2])) for r in self._query(
            "SELECT linkedin_job_id, applicant_count, applicant_count_qualifier"
            " FROM job_posts"))
        self.assertEqual(rows['100'], (200, 'over'))
        self.assertEqual(rows['200'], (25, None))   # historical 25s left as-is
        self.assertEqual(rows['300'], (87, None))

    def test_legacy_db_init_twice_is_idempotent(self):
        self._create_legacy_db()
        self._open_storage()
        snapshot = self._query("SELECT * FROM job_posts ORDER BY linkedin_job_id")
        self._open_storage()
        self._assert_migrated_schema()
        self.assertEqual(
            self._query("SELECT * FROM job_posts ORDER BY linkedin_job_id"), snapshot)
        self.assertEqual(self._query("SELECT COUNT(*) FROM job_searches")[0][0], 4)
        self.assertEqual(
            self._query("SELECT COUNT(*) FROM aggregator_companies")[0][0],
            self._query("SELECT COUNT(DISTINCT company) FROM aggregator_companies")[0][0])
        self.assertEqual(
            self._query("SELECT COUNT(*) FROM companies")[0][0],
            self._query("SELECT COUNT(DISTINCT name) FROM companies")[0][0])

    def test_search_runs_without_pagination_columns(self):
        # search_runs as created before pagination: rows keep NULL pages
        conn = sqlite3.connect(self.db_path)
        conn.executescript(LEGACY_SCHEMA)
        conn.execute("""
            CREATE TABLE search_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, template_name TEXT,
                keywords TEXT, location TEXT, started_at TEXT, finished_at TEXT,
                jobs_found INTEGER, new_jobs INTEGER,
                status TEXT CHECK (status IN ('ok', 'error')), error TEXT)""")
        conn.execute("INSERT INTO search_runs (template_name, jobs_found, status)"
                     " VALUES ('Java', 60, 'ok')")
        conn.commit()
        conn.close()
        self._open_storage()
        self._open_storage()
        self._assert_migrated_schema()
        self.assertEqual(
            self._query("SELECT template_name, jobs_found, status, pages_fetched,"
                        " hit_page_limit FROM search_runs"),
            [('Java', 60, 'ok', None, None)])

    def test_data_fix_does_not_touch_exact_201_saved_after_migration(self):
        self._create_legacy_db()
        self._open_storage()
        # A genuine exact count of 201 recorded by the new parser
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO job_posts (linkedin_job_id, applicant_count) VALUES ('400', 201)")
        conn.commit()
        conn.close()

        self._open_storage()
        self.assertEqual(
            self._query("SELECT applicant_count, applicant_count_qualifier"
                        " FROM job_posts WHERE linkedin_job_id = '400'"),
            [(201, None)])

    def test_applications_survive_reinit(self):
        storage = self._open_storage()
        storage.save_application('100', '2026-11-10', 'notes')
        snapshot = self._query("SELECT * FROM applications")
        self._open_storage()
        self.assertEqual(self._query("SELECT * FROM applications"), snapshot)

    def test_schedule_tables_added_to_legacy_db_and_survive_reinit(self):
        self._create_legacy_db()
        storage = self._open_storage()
        self.assertEqual(self._columns('schedule_runs'),
                         ['id', 'name', 'started_at', 'window_from', 'finished_at',
                          'status', 'summary'])
        self.assertEqual(self._columns('job_reviews'),
                         ['linkedin_job_id', 'status', 'reason', 'run_id', 'reviewed_at',
                          'updated_at'])
        run = storage.start_schedule_run('apply')
        storage.save_job_review('100', 'skipped', 'closed', run['id'])
        storage.finish_schedule_run(run['id'], 'completed')
        runs = self._query("SELECT * FROM schedule_runs")
        reviews = self._query("SELECT * FROM job_reviews")
        self._open_storage()
        self.assertEqual(self._query("SELECT * FROM schedule_runs"), runs)
        self.assertEqual(self._query("SELECT * FROM job_reviews"), reviews)

    def test_views_still_work_after_migration(self):
        self._create_legacy_db()
        storage = self._open_storage()
        self.assertEqual(storage.count_job_summary(days=None), 3)
        self.assertEqual(storage.count_job_summary(days=None, unique=True), 3)
        self.assertEqual(
            storage.count_job_summary(days=None, unique=True, apply_type='unknown'), 3)
        job = storage.get_job_summary(days=None, unique=True, per_page=None)[0]
        self.assertIn('apply_type', job)
        self.assertIn('apply_url', job)
        self.assertIn('seniority_level', job)
        self.assertIn('employment_type', job)
        self.assertIn('applicant_count_qualifier', job)


if __name__ == '__main__':
    unittest.main()
