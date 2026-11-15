"""Tests for the web UI's application type column and filter."""

import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest import mock

import web_app
from utils.sqlite_storage import SQLiteStorage

JOBS = [
    # (linkedin_job_id, apply_type, apply_url)
    ('1001', 'easy_apply', None),
    ('1002', 'external', 'https://jobs.example.com/apply/1002'),
    ('1003', 'external', None),
    ('1004', None, None),
]


class TestApplyColumn(unittest.TestCase):

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        with redirect_stdout(StringIO()):
            SQLiteStorage(db_file=self.db_path)
        conn = sqlite3.connect(self.db_path)
        for job_id, apply_type, apply_url in JOBS:
            conn.execute("INSERT INTO job_searches (linkedin_job_id, title, company, location)"
                         " VALUES (?, ?, ?, 'Remote')", (job_id, f'Dev {job_id}', f'Co {job_id}'))
            conn.execute("INSERT INTO job_posts (linkedin_job_id, date_time, weighted_score,"
                         " apply_type, apply_url) VALUES (?, '2026-11-01T10:00:00Z', 1.0, ?, ?)",
                         (job_id, apply_type, apply_url))
        conn.commit()
        conn.close()

        db_path = self.db_path

        class TempStorage(SQLiteStorage):
            """SQLiteStorage bound to the temp DB, silent on init."""
            def __init__(self, db_file=None):
                with redirect_stdout(StringIO()):
                    super().__init__(db_file=db_file or db_path)

        patcher = mock.patch.object(web_app, 'SQLiteStorage', TempStorage)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = web_app.app.test_client()

    def tearDown(self):
        os.remove(self.db_path)

    def _get(self, query=''):
        response = self.client.get('/?days=all' + query)
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def test_column_renders_each_type(self):
        html = self._get()
        self.assertIn('<span class="apply-badge">Easy Apply</span>', html)
        self.assertIn('<a href="https://jobs.example.com/apply/1002" target="_blank"'
                      ' rel="noopener noreferrer">External</a>', html)
        self.assertIn('Showing 1–4 of 4', html)

    def test_filter_easy_apply(self):
        html = self._get('&apply=easy_apply')
        self.assertIn('Showing 1–1 of 1', html)
        self.assertIn('1001', html)
        self.assertNotIn('>1002<', html)

    def test_filter_external(self):
        html = self._get('&apply=external')
        self.assertIn('Showing 1–2 of 2', html)

    def test_filter_unknown(self):
        html = self._get('&apply=unknown')
        self.assertIn('Showing 1–1 of 1', html)
        self.assertIn('>1004<', html)

    def test_invalid_filter_shows_all(self):
        self.assertIn('Showing 1–4 of 4', self._get('&apply=bogus'))

    def test_sort_links_keep_filter(self):
        html = self._get('&apply=external')
        self.assertIn('apply=external', html.split('<thead>')[1].split('</thead>')[0])


if __name__ == '__main__':
    unittest.main()
