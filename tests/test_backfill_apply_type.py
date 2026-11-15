"""Tests for scripts/backfill_apply_type.py (HTTP mocked, temp DB and lock)."""

import argparse
import os
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from unittest import mock

from scraper.core.detail_scraper import DetailScraper
from scripts import backfill_apply_type as backfill_script
from scripts.backfill_apply_type import (
    LockHeld,
    acquire_lock,
    main,
    parse_since,
    release_lock,
    select_jobs,
)
from utils.sqlite_storage import SQLiteStorage

FIXTURES = Path(__file__).parent / 'fixtures'
EASY_APPLY_HTML = (FIXTURES / 'job_easy_apply.html').read_bytes()
EXTERNAL_HTML = (FIXTURES / 'job_external.html').read_bytes()


def _iso(hours_ago):
    dt = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def _response(job_url, html=b'', final_url=None, status_code=200):
    return mock.Mock(status_code=status_code, content=html, url=final_url or job_url,
                     raise_for_status=mock.Mock())


class BackfillTestCase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, 'jobs.db')
        self.lock_path = Path(self.tmp) / 'logs' / 'scraper.lock'
        with redirect_stdout(StringIO()):
            SQLiteStorage(db_file=self.db_path)
        # DetailScraper sleeps between requests; tests don't
        patcher = mock.patch.object(DetailScraper, '_apply_rate_limiting')
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _insert(self, job_id, hours_ago=1, score=5.0, apply_type=None, apply_url=None):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO job_posts (linkedin_job_id, description, applicant_count,
                applicant_count_qualifier, date_time, scraped_at, total_matches,
                weighted_score, matched_keywords, match_percentage, seniority_level,
                apply_type, apply_url)
            VALUES (?, 'Original description', 25, 'under', ?, ?, 3, ?, 'Python,Docker',
                    40.0, 'Entry level', ?, ?)
        """, (job_id, _iso(hours_ago) if hours_ago is not None else None,
              _iso(hours_ago or 0), score, apply_type, apply_url))
        conn.commit()
        conn.close()

    def _rows(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = {r['linkedin_job_id']: dict(r)
                for r in conn.execute("SELECT * FROM job_posts")}
        conn.close()
        return rows

    def _run(self, argv, pages=None):
        """Run main() with requests.get serving `pages` {job_id: response kwargs}.

        Returns (exit_code, requested job ids, log output).
        """
        pages = pages or {}
        requested = []

        def fake_get(url, **kwargs):
            job_id = url.rstrip('/').rsplit('/', 1)[-1]
            requested.append(job_id)
            page = pages.get(job_id, {})
            if isinstance(page, Exception):
                raise page
            return _response(url, **page)

        with mock.patch('scraper.core.detail_scraper.requests.get', side_effect=fake_get), \
                self.assertLogs(backfill_script.logger, level='INFO') as logs, \
                redirect_stdout(StringIO()) as out:
            backfill_script.logger.info("start")  # assertLogs needs at least one record
            code = main(argv, db_file=self.db_path, lock_path=self.lock_path)
        return code, requested, '\n'.join(logs.output) + out.getvalue()


class TestParseSince(unittest.TestCase):

    def test_valid(self):
        self.assertEqual(parse_since('3d'), '-3 days')
        self.assertEqual(parse_since('12h'), '-12 hours')

    def test_invalid(self):
        for value in ('3', 'd', '0d', '-1d', '3w', '3 days'):
            with self.subTest(value=value):
                with self.assertRaises(argparse.ArgumentTypeError):
                    parse_since(value)


class TestSelection(BackfillTestCase):

    def test_filters_and_order(self):
        self._insert('4000000001', hours_ago=1)                    # selected
        self._insert('4000000002', hours_ago=50)                   # selected (within 3d)
        self._insert('4000000003', hours_ago=24 * 4)               # too old
        self._insert('4000000004', hours_ago=None)                 # no date
        self._insert('4000000005', hours_ago=2, apply_type='external')  # already set
        self._insert('123456789', hours_ago=1)                     # 9 digits
        self._insert('40000000x6', hours_ago=1)                    # not numeric
        self._insert('4000000007', hours_ago=3, score=0.5)         # selected

        jobs = select_jobs(self.db_path)
        self.assertEqual([j['linkedin_job_id'] for j in jobs],
                         ['4000000001', '4000000007', '4000000002'])

    def test_min_score_since_and_limit(self):
        for i in range(5):
            self._insert(f'400000001{i}', hours_ago=i + 1, score=float(i))
        jobs = select_jobs(self.db_path, since=parse_since('4h'), min_score=1, limit=2)
        # Within 4h: i = 0..3; score >= 1: i = 1..3; newest first, limit 2
        self.assertEqual([j['linkedin_job_id'] for j in jobs],
                         ['4000000011', '4000000012'])

    def test_limit_applies_after_id_filter(self):
        self._insert('12345', hours_ago=1)
        self._insert('4000000001', hours_ago=2)
        jobs = select_jobs(self.db_path, limit=1)
        self.assertEqual([j['linkedin_job_id'] for j in jobs], ['4000000001'])


class TestBackfillRun(BackfillTestCase):

    def test_updates_only_apply_columns(self):
        self._insert('4000000001')
        self._insert('4000000002')
        before = self._rows()

        code, requested, output = self._run([], pages={
            '4000000001': {'html': EASY_APPLY_HTML},
            '4000000002': {'html': EXTERNAL_HTML},
        })

        self.assertEqual(code, 0)
        self.assertEqual(sorted(requested), ['4000000001', '4000000002'])
        after = self._rows()
        self.assertEqual(after['4000000001']['apply_type'], 'easy_apply')
        self.assertEqual(after['4000000002']['apply_type'], 'external')
        for job_id in before:
            for column, value in before[job_id].items():
                if column not in ('apply_type', 'apply_url'):
                    self.assertEqual(after[job_id][column], value, (job_id, column))
        self.assertIn('easy_apply=1 / external=1 / closed=0 / unknown=0 / errors=0', output)

    def test_closed_unknown_and_errors_stay_null(self):
        import requests
        self._insert('4000000001', hours_ago=1)
        self._insert('4000000002', hours_ago=2)
        self._insert('4000000003', hours_ago=3)
        before = self._rows()

        code, _, output = self._run([], pages={
            '4000000001': {'final_url': 'https://es.linkedin.com/jobs/x?trk=expired_jd_redirect'},
            '4000000002': {'html': b'<html><body>No apply markers</body></html>'},
            '4000000003': requests.exceptions.ConnectionError('boom'),
        })

        self.assertEqual(code, 0)
        self.assertEqual(self._rows(), before)
        self.assertIn('easy_apply=0 / external=0 / closed=1 / unknown=1 / errors=1', output)

    def test_second_run_only_fetches_rows_still_null(self):
        self._insert('4000000001', hours_ago=1)
        self._insert('4000000002', hours_ago=2)
        pages = {
            '4000000001': {'html': EASY_APPLY_HTML},
            '4000000002': {'final_url': 'https://www.linkedin.com/jobs/search?trk=expired_jd_redirect'},
        }
        self._run([], pages=pages)
        _, requested, _ = self._run([], pages=pages)
        self.assertEqual(requested, ['4000000002'])

    def test_does_not_overwrite_value_set_during_run(self):
        self._insert('4000000001')
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE job_posts SET apply_type = 'external' WHERE linkedin_job_id = ?",
                     ('4000000001',))
        conn.commit()
        conn.close()
        backfill_script.update_apply_type(self.db_path, '4000000001', 'easy_apply', None)
        self.assertEqual(self._rows()['4000000001']['apply_type'], 'external')

    def test_stops_after_consecutive_errors(self):
        import requests
        for i in range(8):
            self._insert(f'40000000{i:02d}', hours_ago=i + 1)
        pages = {f'40000000{i:02d}': requests.exceptions.HTTPError('999')
                 for i in range(8)}

        code, requested, output = self._run([], pages=pages)

        self.assertEqual(code, 1)
        self.assertEqual(len(requested), backfill_script.MAX_CONSECUTIVE_ERRORS)
        self.assertIn('Stopping after 5 consecutive errors (3 jobs not fetched)', output)
        self.assertIn('errors=5', output)

    def test_success_resets_error_streak(self):
        import requests
        ids = [f'40000000{i:02d}' for i in range(7)]
        for i, job_id in enumerate(ids):
            self._insert(job_id, hours_ago=i + 1)
        pages = {job_id: requests.exceptions.HTTPError('999') for job_id in ids}
        pages[ids[3]] = {'html': EASY_APPLY_HTML}  # 3 errors, success, 3 errors

        code, requested, _ = self._run([], pages=pages)
        self.assertEqual(code, 0)
        self.assertEqual(len(requested), 7)

    def test_dry_run_makes_no_requests_or_writes(self):
        self._insert('4000000001')
        before = self._rows()
        code, requested, output = self._run(['--dry-run'])
        self.assertEqual(code, 0)
        self.assertEqual(requested, [])
        self.assertEqual(self._rows(), before)
        self.assertIn('Dry run: 1 jobs would be fetched', output)
        self.assertIn('4000000001', output)
        self.assertFalse(self.lock_path.exists())


class TestLock(BackfillTestCase):

    def test_exits_when_lock_held_by_live_process(self):
        self._insert('4000000001')
        self.lock_path.parent.mkdir(parents=True)
        self.lock_path.write_text(f"{os.getpid()}\n")  # This process is alive

        code, requested, output = self._run([])

        self.assertEqual(code, 1)
        self.assertEqual(requested, [])
        self.assertIn(f'Scraper or another backfill is running (PID {os.getpid()}', output)
        self.assertEqual(self.lock_path.read_text().strip(), str(os.getpid()))
        self.assertIsNone(self._rows()['4000000001']['apply_type'])

    def test_replaces_stale_lock_and_releases_it(self):
        self._insert('4000000001')
        for content in ('999999999\n', 'garbage\n', ''):
            with self.subTest(content=content):
                self.lock_path.parent.mkdir(parents=True, exist_ok=True)
                self.lock_path.write_text(content)
                with mock.patch.object(backfill_script, '_pid_alive', return_value=False):
                    code, _, output = self._run([], pages={
                        '4000000001': {'html': b'<html></html>'}})
                self.assertEqual(code, 0)
                self.assertIn('Stale lock file', output)
                self.assertFalse(self.lock_path.exists())

    def test_lock_holds_our_pid_during_run(self):
        self._insert('4000000001')
        seen = []

        def fake_get(url, **kwargs):
            seen.append(self.lock_path.read_text().strip())
            return _response(url, html=EASY_APPLY_HTML)

        with mock.patch('scraper.core.detail_scraper.requests.get', side_effect=fake_get), \
                redirect_stdout(StringIO()):
            main([], db_file=self.db_path, lock_path=self.lock_path)
        self.assertEqual(seen, [str(os.getpid())])
        self.assertFalse(self.lock_path.exists())

    def test_acquire_raises_when_held(self):
        self.lock_path.parent.mkdir(parents=True)
        self.lock_path.write_text(f"{os.getpid()}\n")
        with self.assertRaises(LockHeld):
            acquire_lock(self.lock_path)

    def test_release_keeps_lock_of_another_process(self):
        self.lock_path.parent.mkdir(parents=True)
        self.lock_path.write_text("12345\n")
        release_lock(self.lock_path)
        self.assertTrue(self.lock_path.exists())


if __name__ == '__main__':
    unittest.main()
