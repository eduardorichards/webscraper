"""Tests for search_runs tracking in main.multiple_search (HTTP mocked)."""

import os
import re
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest import mock

import requests

from main import multiple_search
from scraper import JobScraper
from utils.sqlite_storage import SQLiteStorage

ISO_UTC = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')


def _card(job_id):
    return f"""
    <div class="base-card job-search-card">
      <a class="base-card__full-link job-card-container__link"
         href="https://ar.linkedin.com/jobs/view/dev-{job_id}?trk=public_jobs"></a>
      <h3 class="base-search-card__title">Developer {job_id}</h3>
      <h4 class="base-search-card__subtitle">
        <a href="https://ar.linkedin.com/company/acme?trk=x">Acme</a>
      </h4>
      <span class="job-search-card__location">Buenos Aires, Argentina</span>
    </div>"""


def _response(job_ids, status=200):
    resp = requests.Response()
    resp.status_code = status
    resp._content = ''.join(_card(j) for j in job_ids).encode('utf-8')
    resp.url = 'https://www.linkedin.com/jobs/search'
    return resp


def _template(name, keywords):
    return {
        "name": name,
        "keywords": keywords,
        "location": "Argentina",
        "experience_levels": [1, 2],
        "remote": False,
        "time_posted": "1h",
        "max_results": 100,
    }


class TestSearchRuns(unittest.TestCase):

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        with redirect_stdout(StringIO()):
            self.storage = SQLiteStorage(db_file=self.db_path)
            self.scraper = JobScraper(sqlite_storage=self.storage)

    def tearDown(self):
        os.remove(self.db_path)

    def _run(self, templates, responses):
        """Run multiple_search with requests.get returning `responses` in order."""
        with mock.patch('scraper.core.scraper.requests.get',
                        side_effect=responses) as get, \
                mock.patch('main.time.sleep'), \
                redirect_stdout(StringIO()), \
                self.assertLogs(level='INFO'):
            multiple_search(templates=templates, scraper=self.scraper)
        self.assertEqual(get.call_count, len(templates))

    def _runs(self):
        return list(reversed(self.storage.get_search_runs()))

    def test_counts_and_status(self):
        templates = [
            _template("Java Arg Jr", "Java"),
            _template("Python Arg Jr", "Python"),
            _template("Broken", "Go"),
            _template("Repeat", "Java"),
        ]
        self._run(templates, [
            _response(['1000001', '1000002', '1000003']),
            _response(['1000003', '1000004']),           # 1000003 already seen
            _response([], status=503),                   # HTTP error
            _response(['1000001', '1000001']),           # all seen, dup in page
        ])

        runs = self._runs()
        self.assertEqual(len(runs), 4)
        summary = [(r['template_name'], r['jobs_found'], r['new_jobs'], r['status'])
                   for r in runs]
        self.assertEqual(summary, [
            ("Java Arg Jr", 3, 3, 'ok'),
            ("Python Arg Jr", 2, 1, 'ok'),
            ("Broken", 0, 0, 'error'),
            ("Repeat", 2, 0, 'ok'),
        ])

        self.assertEqual(runs[0]['keywords'], "Java")
        self.assertEqual(runs[0]['location'], "Argentina")
        self.assertIsNone(runs[0]['error'])
        self.assertIn('503', runs[2]['error'])
        for run in runs:
            self.assertRegex(run['started_at'], ISO_UTC)
            self.assertRegex(run['finished_at'], ISO_UTC)
            self.assertLessEqual(run['started_at'], run['finished_at'])

    def test_job_searches_linked_to_run(self):
        self._run([_template("A", "Java"), _template("B", "Python")], [
            _response(['2000001', '2000002']),
            _response(['2000002']),
        ])
        runs = self._runs()

        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT linkedin_job_id, search_run_id, scraped_at FROM job_searches"
            " ORDER BY id").fetchall()
        conn.close()

        self.assertEqual(
            [(r[0], r[1]) for r in rows],
            [('2000001', runs[0]['id']), ('2000002', runs[0]['id']),
             ('2000002', runs[1]['id'])])
        for row in rows:
            self.assertRegex(row[2], ISO_UTC)

    def test_templates_are_not_mutated(self):
        templates = [_template("A", "Java")]
        self._run(templates, [_response(['3000001'])])
        self.assertEqual(templates[0]["name"], "A")

    def test_connection_error_is_recorded(self):
        with mock.patch('scraper.core.scraper.requests.get',
                        side_effect=requests.exceptions.ConnectionError("boom")), \
                mock.patch('main.time.sleep'), \
                redirect_stdout(StringIO()), \
                self.assertLogs(level='INFO'):
            multiple_search(templates=[_template("A", "Java")], scraper=self.scraper)
        run = self._runs()[0]
        self.assertEqual((run['status'], run['jobs_found'], run['new_jobs']), ('error', 0, 0))
        self.assertEqual(run['error'], 'boom')


if __name__ == '__main__':
    unittest.main()
