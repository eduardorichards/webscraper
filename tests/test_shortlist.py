"""Tests for GET /api/shortlist (Flask test client, temp DB)."""

import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from unittest import mock

import web_app
from utils.sqlite_storage import SQLiteStorage


def _ago(**delta):
    """UTC ISO-8601 timestamp `delta` before now, in the stored format."""
    return (datetime.now(timezone.utc) - timedelta(**delta)).strftime('%Y-%m-%dT%H:%M:%SZ')


JOBS = [
    # (id, title, company, age, score, apply_type, seniority)
    ('4000000001', 'Backend Dev', 'Acme', dict(minutes=30), 40.0, 'external', 'Entry level'),
    ('4000000002', 'Python Dev', 'Globex', dict(minutes=70), 80.0, 'external', None),
    ('4000000003', 'Data Dev', 'Initech', dict(minutes=90), 30.0, 'external', 'Associate'),
    ('4000000004', 'Low Score', 'Hooli', dict(minutes=10), 20.0, 'external', 'Entry level'),
    ('4000000005', 'Old Job', 'Umbrella', dict(hours=5), 90.0, 'external', 'Entry level'),
    ('4000000006', 'Easy Job', 'Stark', dict(minutes=20), 70.0, 'easy_apply', 'Entry level'),
    ('4000000007', 'Unknown Job', 'Wayne', dict(minutes=20), 60.0, None, 'Entry level'),
    ('4000000008', 'Blacklisted', 'BadCo', dict(minutes=20), 95.0, 'external', 'Entry level'),
    ('4000000009', 'Aggregated', 'Quik Hire Staffing', dict(minutes=20), 95.0, 'external',
     'Entry level'),
    ('4000000010', 'Senior Dev', 'Vandelay', dict(minutes=20), 95.0, 'external',
     'Mid-Senior level'),
    ('4000000011', 'Applied Dev', 'Pied Piper', dict(minutes=20), 99.0, 'external',
     'Entry level'),
    # Same (title, company) as the applied job: hidden as its twin
    ('4000000012', 'Applied Dev', 'Pied Piper', dict(minutes=25), 98.0, 'external',
     'Entry level'),
    ('4000000013', 'Two Days Old', 'Soylent', dict(days=2), 50.0, 'external', 'Entry level'),
]


class TestShortlist(unittest.TestCase):

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        with redirect_stdout(StringIO()):
            SQLiteStorage(db_file=self.db_path)
        conn = sqlite3.connect(self.db_path)
        for job_id, title, company, age, score, apply_type, seniority in JOBS:
            conn.execute("INSERT INTO job_searches (linkedin_job_id, title, company, location)"
                         " VALUES (?, ?, ?, 'Remote')", (job_id, title, company))
            conn.execute("INSERT INTO job_posts (linkedin_job_id, date_time, weighted_score,"
                         " match_percentage, matched_keywords, seniority_level,"
                         " employment_type, apply_type, applicant_count,"
                         " applicant_count_qualifier)"
                         " VALUES (?, ?, ?, 25.0, 'Python,SQL', ?, 'Full-time', ?, 25, 'under')",
                         (job_id, _ago(**age), score, seniority, apply_type))
        conn.execute("INSERT INTO blacklisted_companies (company) VALUES ('BadCo')")
        conn.execute("INSERT INTO applications (linkedin_job_id, applied_on)"
                     " VALUES ('4000000011', '2026-11-14')")
        conn.commit()
        conn.close()

        db_path = self.db_path

        class TempStorage(SQLiteStorage):
            def __init__(self, db_file=None):
                with redirect_stdout(StringIO()):
                    super().__init__(db_file=db_file or db_path)

        patcher = mock.patch.object(web_app, 'SQLiteStorage', TempStorage)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = web_app.app.test_client()

    def tearDown(self):
        os.remove(self.db_path)

    def _get(self, query='', status=200):
        response = self.client.get('/api/shortlist' + query)
        self.assertEqual(response.status_code, status, response.get_data(as_text=True))
        return response.get_json()

    @staticmethod
    def _ids(data):
        return [job['linkedin_job_id'] for job in data['jobs']]

    def test_defaults(self):
        data = self._get()
        # Excluded: low score, too old, easy apply, unknown apply type,
        # blacklisted, aggregator, above my level, applied and its twin
        self.assertEqual(self._ids(data), ['4000000002', '4000000001', '4000000003'])
        self.assertEqual(data['params'], {'since': '2h', 'min_score': 25.0, 'limit': 10,
                                          'apply': 'external'})
        self.assertEqual(data['total'], 3)
        self.assertEqual(data['count'], 3)

    def test_item_fields(self):
        job = self._get()['jobs'][0]
        self.assertEqual(job, {
            'linkedin_job_id': '4000000002',
            'title': 'Python Dev',
            'company': 'Globex',
            'location': 'Remote',
            'date_time': job['date_time'],
            'weighted_score': 80.0,
            'match_percentage': 25.0,
            'matched_keywords': ['Python', 'SQL'],
            'seniority_level': None,
            'employment_type': 'Full-time',
            'apply_type': 'external',
            'applicant_count': 25,
            'applicant_count_qualifier': 'under',
            'job_url': 'https://www.linkedin.com/jobs/view/4000000002/',
        })
        self.assertRegex(job['date_time'], r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')

    def test_null_keywords_is_empty_list(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE job_posts SET matched_keywords = NULL"
                     " WHERE linkedin_job_id = '4000000002'")
        conn.commit()
        conn.close()
        self.assertEqual(self._get()['jobs'][0]['matched_keywords'], [])

    def test_ordered_by_score_desc(self):
        scores = [job['weighted_score'] for job in self._get('?since=7d&apply=all')['jobs']]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_limit_keeps_total(self):
        data = self._get('?limit=2')
        self.assertEqual(self._ids(data), ['4000000002', '4000000001'])
        self.assertEqual(data['total'], 3)
        self.assertEqual(data['count'], 2)
        self.assertEqual(data['params']['limit'], 2)

    def test_above_level_title_hidden(self):
        # seniority_level says nothing, the title does
        conn = sqlite3.connect(self.db_path)
        for job_id, title in (('4000000014', 'Lead Engineer, DevOps Platform'),
                              ('4000000015', 'QA Automatizador SSR o SR')):
            conn.execute("INSERT INTO job_searches (linkedin_job_id, title, company)"
                         " VALUES (?, ?, 'Bain')", (job_id, title))
            conn.execute("INSERT INTO job_posts (linkedin_job_id, date_time, weighted_score,"
                         " seniority_level, apply_type)"
                         " VALUES (?, ?, 85.0, 'Not Applicable', 'external')",
                         (job_id, _ago(minutes=5)))
        conn.commit()
        conn.close()
        self.assertEqual(self._ids(self._get()),
                         ['4000000015', '4000000002', '4000000001', '4000000003'])

    def test_apply_easy_apply(self):
        self.assertEqual(self._ids(self._get('?apply=easy_apply')), ['4000000006'])

    def test_apply_all_includes_unknown(self):
        self.assertEqual(self._ids(self._get('?apply=all')),
                         ['4000000002', '4000000006', '4000000007', '4000000001',
                          '4000000003'])

    def test_since(self):
        self.assertNotIn('4000000005', self._ids(self._get('?since=1h')))
        self.assertEqual(self._ids(self._get('?since=1h')), ['4000000001'])
        data = self._get('?since=6H')
        self.assertIn('4000000005', self._ids(data))
        self.assertEqual(data['params']['since'], '6h')
        data = self._get('?since=3d')
        self.assertEqual(self._ids(data)[0], '4000000005')
        self.assertIn('4000000013', self._ids(data))
        self.assertEqual(data['params']['since'], '3d')

    def test_min_score(self):
        data = self._get('?min_score=50')
        self.assertEqual(self._ids(data), ['4000000002'])
        self.assertEqual(data['params']['min_score'], 50.0)
        self.assertEqual(self._ids(self._get('?min_score=0'))[-1], '4000000004')

    def test_empty_params_use_defaults(self):
        data = self._get('?since=&min_score=&limit=&apply=')
        self.assertEqual(data['params'], {'since': '2h', 'min_score': 25.0, 'limit': 10,
                                          'apply': 'external'})

    def test_invalid_params(self):
        cases = [
            ('since', '2'), ('since', '0h'), ('since', '2w'), ('since', '-1h'),
            ('since', '9999d'), ('since', '8761h'),
            ('min_score', '-1'), ('min_score', 'nan'), ('min_score', 'inf'),
            ('min_score', 'abc'),
            ('limit', '0'), ('limit', '101'), ('limit', 'abc'), ('limit', '2.5'),
            ('apply', 'unknown'), ('apply', 'External'),
        ]
        for name, value in cases:
            with self.subTest(name=name, value=value):
                data = self._get('?%s=%s' % (name, value), status=400)
                self.assertEqual(list(data['invalid']), [name])

    def test_limits_accepted(self):
        self.assertEqual(self._get('?limit=100')['params']['limit'], 100)
        self.assertEqual(self._get('?since=365d')['params']['since'], '365d')
        self.assertEqual(self._get('?since=8760h')['params']['since'], '8760h')

    def test_all_invalid_params_listed(self):
        data = self._get('?since=x&min_score=-5&limit=0&apply=bogus', status=400)
        self.assertEqual(data['error'], 'invalid parameters')
        self.assertEqual(set(data['invalid']), {'since', 'min_score', 'limit', 'apply'})


if __name__ == '__main__':
    unittest.main()
