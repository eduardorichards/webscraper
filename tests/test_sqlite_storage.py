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

    def _set_apply_types(self):
        """Jobs with i % 3 == 0 → easy_apply, 1 → external, 2 → unknown (NULL)."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE job_posts SET apply_type = 'easy_apply'"
                     " WHERE CAST(linkedin_job_id AS INTEGER) % 3 = 0")
        conn.execute("UPDATE job_posts SET apply_type = 'external',"
                     " apply_url = 'https://jobs.example.com/apply'"
                     " WHERE CAST(linkedin_job_id AS INTEGER) % 3 = 1")
        conn.commit()
        conn.close()

    def test_apply_type_filter(self):
        self._set_apply_types()
        for apply_type, expected in (('easy_apply', 'easy_apply'),
                                     ('external', 'external'),
                                     ('unknown', None)):
            with self.subTest(apply_type=apply_type):
                jobs = self.storage.get_job_summary(
                    days=None, apply_type=apply_type, per_page=None)
                self.assertEqual(len(jobs), NUM_JOBS // 3)
                self.assertEqual({j['apply_type'] for j in jobs}, {expected})
                self.assertEqual(
                    self.storage.count_job_summary(days=None, apply_type=apply_type),
                    NUM_JOBS // 3)

    def test_apply_type_filter_none_or_invalid_returns_all(self):
        self._set_apply_types()
        self.assertEqual(self.storage.count_job_summary(days=None), NUM_JOBS)
        self.assertEqual(
            self.storage.count_job_summary(days=None, apply_type='bogus'), NUM_JOBS)

    def test_apply_type_combined_with_other_filters(self):
        self._set_apply_types()
        # i % 3 == 1 (external) and even i (Buenos Aires) → i % 6 == 4
        count = self.storage.count_job_summary(
            days=None, apply_type='external', location='buenos aires')
        self.assertEqual(count, len([i for i in range(NUM_JOBS) if i % 6 == 4]))

    def test_unique_view_exposes_apply_columns(self):
        self._set_apply_types()
        jobs = self.storage.get_job_summary(
            days=None, unique=True, apply_type='external', per_page=None)
        self.assertTrue(jobs)
        self.assertEqual({j['apply_url'] for j in jobs}, {'https://jobs.example.com/apply'})


class TestResultFilters(unittest.TestCase):
    """Text search, employment type, score/match range, keywords, under 25
    and applied filters of get_job_summary / count_job_summary."""

    JOBS = [
        # (id, title, company, score, match %, keywords, employment,
        #  applicants, qualifier)
        ('3001', 'Java Backend Developer', 'Acme', 60.0, 50.0, 'Java,Spring,SQL',
         'Full-time', 25, 'under'),
        ('3002', 'JavaScript Developer', 'Globex', 30.0, 20.0, 'JavaScript,React',
         'Contract', 25, None),            # historical "first 25"
        ('3003', 'Python 100% Remote', 'Initech', 12.0, 10.0, 'Python',
         'Full-time', 87, None),
        ('3004', 'Data Engineer', 'Java_Corp', 5.0, 5.0, None,
         'Part-time', 200, 'over'),
        ('3005', 'Java Backend Developer', 'Acme', 55.0, 45.0, 'Java',
         'Full-time', 12, None),           # twin of 3001 (same title + company)
        ('3006', 'QA Tester', None, 1.0, 1.0, 'SQL', '', None, None),
    ]

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        with redirect_stdout(StringIO()):
            self.storage = SQLiteStorage(db_file=self.db_path)
        conn = sqlite3.connect(self.db_path)
        for (job_id, title, company, score, match, kws, emp, count,
             qualifier) in self.JOBS:
            conn.execute(
                "INSERT INTO job_searches (linkedin_job_id, title, company, location)"
                " VALUES (?, ?, ?, 'Remote')", (job_id, title, company))
            conn.execute(
                "INSERT INTO job_posts (linkedin_job_id, date_time, weighted_score,"
                " match_percentage, matched_keywords, employment_type, applicant_count,"
                " applicant_count_qualifier, description)"
                " VALUES (?, '2026-11-01T10:00:00Z', ?, ?, ?, ?, ?, ?, ?)",
                (job_id, score, match, kws, emp, count, qualifier, 'x' * 600))
        conn.commit()
        conn.close()

    def tearDown(self):
        os.remove(self.db_path)

    def _ids(self, **filters):
        jobs = self.storage.get_job_summary(days=None, per_page=None, **filters)
        ids = sorted(j['linkedin_job_id'] for j in jobs)
        self.assertEqual(self.storage.count_job_summary(days=None, **filters), len(ids))
        return ids

    def test_search_title_and_company_case_insensitive(self):
        self.assertEqual(self._ids(search='JAVA'), ['3001', '3002', '3004', '3005'])
        self.assertEqual(self._ids(search='globex'), ['3002'])

    def test_search_wildcards_are_literal(self):
        self.assertEqual(self._ids(search='100%'), ['3003'])
        self.assertEqual(self._ids(search='a_c'), ['3004'])
        self.assertEqual(self._ids(search='%'), ['3003'])

    def test_employment_types_any_of(self):
        self.assertEqual(self._ids(employment_types=['Contract', 'Part-time']),
                         ['3002', '3004'])
        self.assertEqual(len(self._ids(employment_types=[])), 6)
        self.assertEqual(self.storage.get_employment_types(),
                         ['Contract', 'Full-time', 'Part-time'])

    def test_score_range_and_min_match(self):
        self.assertEqual(self._ids(min_score=10, max_score=55), ['3002', '3003', '3005'])
        self.assertEqual(self._ids(min_match=45), ['3001', '3005'])

    def test_keywords_any_of_with_exact_boundaries(self):
        self.assertEqual(self._ids(keywords=['Java']), ['3001', '3005'])
        self.assertEqual(self._ids(keywords=['JavaScript']), ['3002'])
        self.assertEqual(self._ids(keywords=['SQL', 'Python']), ['3001', '3003', '3006'])

    def test_under_25_includes_historical_25(self):
        # 'under', historical 25 + NULL, exact 12; not 87, 'over' 200, NULL
        self.assertEqual(self._ids(under_25=True), ['3001', '3002', '3005'])

    def test_applied_hides_job_and_its_twins(self):
        self.storage.save_application('3001', '2026-11-10', 'sent CV')
        self.assertEqual(self._ids(applied='hide'), ['3002', '3003', '3004', '3006'])
        self.assertEqual(self._ids(applied='only'), ['3001', '3005'])
        self.assertEqual(len(self._ids(applied='all')), 6)

    def test_applied_null_title_company_not_hidden(self):
        self.storage.save_application('3006', '2026-11-10')
        self.assertEqual(self._ids(applied='only'), ['3006'])
        self.assertNotIn('3006', self._ids(applied='hide'))
        self.assertEqual(len(self._ids(applied='hide')), 5)

    def test_filters_combine(self):
        self.assertEqual(
            self._ids(search='developer', keywords=['Java', 'React'], under_25=True,
                      employment_types=['Full-time'], min_score=56), ['3001'])

    def test_application_upsert_and_remove(self):
        self.storage.save_application('3001', '2026-11-10', 'first')
        self.storage.save_application('3001', '2026-11-11', None)
        apps = self.storage.get_applications()
        self.assertEqual(len(apps), 1)
        self.assertEqual((apps[0]['applied_on'], apps[0]['notes']), ('2026-11-11', None))
        self.assertIsNotNone(apps[0]['created_at'])
        self.storage.remove_application('3001')
        self.assertEqual(self.storage.get_applications(), [])

    def test_application_status_marks_twins_as_similar(self):
        self.storage.save_application('3001', '2026-11-10', 'sent CV')
        jobs = self.storage.get_job_summary(days=None, per_page=None)
        status = self.storage.get_application_status(jobs)
        self.assertEqual(status['3001'],
                         {'applied_on': '2026-11-10', 'notes': 'sent CV', 'similar': False})
        self.assertEqual(status['3005']['similar'], True)
        self.assertEqual(set(status), {'3001', '3005'})

    def test_description_snippets(self):
        snippets = self.storage.get_description_snippets(['3001', '3002', '9999'], length=500)
        self.assertEqual(set(snippets), {'3001', '3002'})
        self.assertEqual(len(snippets['3001']), 500)
        self.assertEqual(self.storage.get_description_snippets([]), {})

    def test_views_expose_new_columns(self):
        job = self.storage.get_job_summary(days=None, unique=True, per_page=None,
                                           search='Initech')[0]
        self.assertEqual(job['employment_type'], 'Full-time')
        self.assertIn('industries', job)
        self.assertIn('applicant_count_qualifier', job)


if __name__ == '__main__':
    unittest.main()
