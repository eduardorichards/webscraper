"""Tests for SQLiteStorage job summary pagination and filtering."""

import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO

from utils.sqlite_storage import SQLiteStorage

NUM_JOBS = 120


def _iso(dt):
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


class TestJobSummaryPagination(unittest.TestCase):
    """get_job_summary / count_job_summary against a temporary DB."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        with redirect_stdout(StringIO()):
            self.storage = SQLiteStorage(db_file=self.db_path)
        self._seed()

    def tearDown(self):
        os.remove(self.db_path)

    def _seed(self):
        """Insert NUM_JOBS jobs: job i is posted i hours ago, score i % 10.

        Even jobs are in "Buenos Aires, Argentina", odd ones in "Remote";
        companies rotate across Acme / Globex / Initech. Job 0 has no date
        and job 1 has no applicant count, to check NULL ordering.
        """
        now = datetime.now(timezone.utc)
        companies = ['Acme', 'Globex', 'Initech']
        conn = sqlite3.connect(self.db_path)
        for i in range(NUM_JOBS):
            job_id = f'{i:05d}'
            location = 'Buenos Aires, Argentina' if i % 2 == 0 else 'Remote'
            conn.execute(
                "INSERT INTO job_searches (linkedin_job_id, title, company, location)"
                " VALUES (?, ?, ?, ?)",
                (job_id, f'Developer {i}', companies[i % 3], location)
            )
            date_time = None if i == 0 else _iso(now - timedelta(hours=i, minutes=1))
            applicants = None if i == 1 else i
            conn.execute(
                "INSERT INTO job_posts (linkedin_job_id, date_time, applicant_count,"
                " weighted_score, total_matches, match_percentage)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (job_id, date_time, applicants, float(i % 10), i % 10, float(i % 10) * 10)
            )
        conn.commit()
        conn.close()

    def _ids(self, jobs):
        return [j['linkedin_job_id'] for j in jobs]

    def test_pages_do_not_overlap(self):
        page1 = self.storage.get_job_summary(days=None, page=1, per_page=50)
        page2 = self.storage.get_job_summary(days=None, page=2, per_page=50)
        page3 = self.storage.get_job_summary(days=None, page=3, per_page=50)

        self.assertEqual(len(page1), 50)
        self.assertEqual(len(page2), 50)
        self.assertEqual(len(page3), NUM_JOBS - 100)
        all_ids = self._ids(page1) + self._ids(page2) + self._ids(page3)
        self.assertEqual(len(set(all_ids)), NUM_JOBS)

    def test_page_beyond_end_is_empty(self):
        self.assertEqual(self.storage.get_job_summary(days=None, page=99, per_page=50), [])

    def test_per_page_none_returns_all(self):
        self.assertEqual(len(self.storage.get_job_summary(days=None, per_page=None)), NUM_JOBS)

    def test_default_order_is_date_desc_nulls_last(self):
        jobs = self.storage.get_job_summary(days=None, per_page=None)
        self.assertEqual(jobs[0]['linkedin_job_id'], '00001')  # most recent
        self.assertIsNone(jobs[-1]['date_time'])               # NULL last

    def test_count_without_filters(self):
        self.assertEqual(self.storage.count_job_summary(days=None), NUM_JOBS)

    def test_count_with_location_filter_is_case_insensitive(self):
        total = self.storage.count_job_summary(days=None, location='argentina')
        self.assertEqual(total, NUM_JOBS // 2)
        self.assertEqual(self.storage.count_job_summary(days=None, location='BUENOS'), total)
        jobs = self.storage.get_job_summary(days=None, location='argentina', per_page=None)
        self.assertEqual(len(jobs), total)
        self.assertTrue(all('Argentina' in j['location'] for j in jobs))

    def test_count_with_hours_filter(self):
        # Jobs 1..10 were posted between 1h01m and 10h01m ago; job 0 has no date
        self.assertEqual(self.storage.count_job_summary(days=None, hours=11), 10)
        jobs = self.storage.get_job_summary(days=None, hours=11, per_page=None)
        self.assertEqual(sorted(self._ids(jobs)), [f'{i:05d}' for i in range(1, 11)])

    def test_count_with_combined_filters(self):
        # Even i in 1..47 with score i % 10 >= 5 → 6, 8, 16, 18, 26, 28, 36, 38, 46
        expected = sum(1 for i in range(1, 48) if i % 2 == 0 and i % 10 >= 5)
        total = self.storage.count_job_summary(
            days=None, hours=48, location='argentina', min_score=5)
        self.assertEqual(total, expected)
        jobs = self.storage.get_job_summary(
            days=None, hours=48, location='argentina', min_score=5, per_page=None)
        self.assertEqual(len(jobs), expected)

    def test_count_matches_paginated_rows(self):
        filters = dict(days=None, location='remote', min_score=3)
        total = self.storage.count_job_summary(**filters)
        rows = []
        page = 1
        while True:
            batch = self.storage.get_job_summary(page=page, per_page=25, **filters)
            if not batch:
                break
            rows.extend(batch)
            page += 1
        self.assertEqual(len(rows), total)
        self.assertEqual(len(set(self._ids(rows))), total)

    def test_valid_sort(self):
        asc = self.storage.get_job_summary(
            days=None, sort='applicant_count', direction='asc', per_page=None)
        values = [j['applicant_count'] for j in asc]
        self.assertIsNone(values[-1])  # NULL last even when ascending
        self.assertEqual(values[:-1], sorted(values[:-1]))

        desc = self.storage.get_job_summary(
            days=None, sort='weighted_score', direction='desc', per_page=None)
        scores = [j['weighted_score'] for j in desc]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_invalid_sort_falls_back_to_default(self):
        default = self._ids(self.storage.get_job_summary(days=None, per_page=None))
        for sort, direction in [
            ('DROP', 'desc'),
            ('title; DROP TABLE job_posts; --', 'asc'),
            ('description', 'asc'),
            ('title', 'sideways'),
            ('title', 'asc; DROP TABLE job_posts'),
        ]:
            with self.subTest(sort=sort, direction=direction):
                jobs = self.storage.get_job_summary(
                    days=None, sort=sort, direction=direction, per_page=None)
                self.assertEqual(self._ids(jobs), default)
        # Tables are still there
        self.assertEqual(self.storage.count_job_summary(days=None), NUM_JOBS)

    def test_hide_blacklisted_excludes_companies(self):
        self.storage.add_blacklisted_company('Acme')
        jobs = self.storage.get_job_summary(days=None, hide_blacklisted=True, per_page=None)
        expected = NUM_JOBS - NUM_JOBS // 3
        self.assertEqual(len(jobs), expected)
        self.assertNotIn('Acme', {j['company'] for j in jobs})
        self.assertEqual(self.storage.count_job_summary(days=None, hide_blacklisted=True), expected)

        # Without the flag, blacklisted companies are still returned
        self.assertEqual(self.storage.count_job_summary(days=None, hide_blacklisted=False), NUM_JOBS)


if __name__ == '__main__':
    unittest.main()
