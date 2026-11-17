"""Tests for ATS collection into the shared DB (scraper/sources/ats_collector.py)
and how ATS jobs coexist with LinkedIn jobs: pending analysis, URLs, web UI,
applications, shortlist and backfill. HTTP is mocked."""

import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from unittest import mock

import main
import web_app
from scraper import KeywordConfig, KeywordMatcher, MatchResult
from scraper.sources.ats_client import board_url
from scraper.sources.ats_collector import collect_ats
from scripts.backfill_apply_type import select_jobs
from utils.sqlite_storage import SQLiteStorage

FIXTURES = Path(__file__).resolve().parent / 'fixtures'
KRAKEN_KEEP = ['ashby:kraken.com:1b2c3d4e-0000-4a5b-8c7d-111111111111',   # Argentina secondary
               'ashby:kraken.com:3b2c3d4e-0000-4a5b-8c7d-333333333333']   # AMER
GITLAB_KEEP = 'greenhouse:gitlab:8638232003'
REDBEE_KEEP = 'lever:redbee:f035d332-b86e-4a9f-a6ce-6c22d8c71572'


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


def _ago(**delta):
    return (datetime.now(timezone.utc) - timedelta(**delta)).strftime('%Y-%m-%dT%H:%M:%SZ')


class FakeSession:
    """requests-like session answering board URLs from fixtures."""

    def __init__(self, responses):
        self.responses = responses   # {url: (status, payload)}
        self.urls = []

    def get(self, url, timeout=None, headers=None):
        self.urls.append(url)
        status, payload = self.responses.get(url, (404, {}))
        response = mock.Mock(status_code=status)
        response.json.return_value = payload
        return response


class AtsDbTestCase(unittest.TestCase):
    """Temp DB with its own company and aggregator files."""

    COMPANIES = [
        {"name": "Kraken", "ats": "ashby", "slug": "kraken.com"},
        {"name": "GitLab", "ats": "greenhouse", "slug": "gitlab"},
        {"name": "redbee", "ats": "lever", "slug": "redbee"},
        {"name": "Gone", "ats": "greenhouse", "slug": "gone-board"},
        {"name": "Empty", "ats": "greenhouse", "slug": "empty-board"},
    ]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = os.path.join(self.tmp.name, 'jobs.db')
        self.companies_file = os.path.join(self.tmp.name, 'companies.json')
        self.aggregators_file = os.path.join(self.tmp.name, 'aggregators.json')
        Path(self.companies_file).write_text(json.dumps({"companies": self.COMPANIES}))
        Path(self.aggregators_file).write_text(json.dumps({
            "categories": {"job_board": "x"},
            "companies": [{"company": "redbee", "category": "job_board", "reason": "test"}]}))
        self.storage = self._storage()
        self.keyword_config = KeywordConfig(keywords=['Python', 'Java', 'AWS', 'Go'])
        self.session = FakeSession({
            board_url('ashby', 'kraken.com'): (200, _load('ashby_job_board.json')),
            board_url('greenhouse', 'gitlab'): (200, _load('greenhouse_jobs.json')),
            board_url('lever', 'redbee'): (200, _load('lever_postings.json')),
            board_url('greenhouse', 'empty-board'): (200, {"jobs": [], "meta": {"total": 0}}),
        })

    def _storage(self):
        with redirect_stdout(StringIO()):
            return SQLiteStorage(db_file=self.db_path, companies_file=self.companies_file,
                                 aggregators_file=self.aggregators_file)

    def _collect(self, companies=None):
        sleep = mock.Mock()
        with self.assertLogs('scraper.sources.ats_collector', level='INFO') as logs:
            stats = collect_ats(self.storage, self.keyword_config, companies=companies,
                                session=self.session, sleep=sleep)
        self.logs = logs.output
        self.sleep = sleep
        return stats

    def _query(self, sql, params=()):
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return rows


class TestCollect(AtsDbTestCase):

    def test_stats_per_company(self):
        stats = self._collect()
        self.assertEqual(stats['Kraken'], dict(status='ok', found=4, kept=2, dropped=2,
                                               new=2, existing=0, aggregator=0))
        self.assertEqual(stats['GitLab'], dict(status='ok', found=3, kept=1, dropped=2,
                                               new=1, existing=0, aggregator=0))
        self.assertEqual(stats['redbee']['new'], 1)
        self.assertEqual(stats['redbee']['aggregator'], 1)
        self.assertEqual(stats['Gone']['status'], 'error')
        self.assertEqual(stats['Empty'], dict(status='ok', found=0, kept=0, dropped=0,
                                              new=0, existing=0, aggregator=0))
        # Delay between companies only
        self.assertEqual(self.sleep.call_count, len(self.COMPANIES) - 1)
        self.assertTrue(any('Kraken (ashby:kraken.com): 4 postings, kept 2, dropped 2'
                            in line for line in self.logs))
        self.assertTrue(any('no jobs' in line and 'Empty' in line for line in self.logs))

    def test_job_searches_rows(self):
        self._collect()
        rows = self._query(
            "SELECT linkedin_job_id, title, company, location, source, job_url,"
            " search_keywords, search_location, search_remote, search_run_id, scraped_at"
            " FROM job_searches WHERE company = 'Kraken' ORDER BY linkedin_job_id")
        self.assertEqual([r[0] for r in rows], KRAKEN_KEEP)
        row = rows[0]
        self.assertEqual(row[1:9], (
            'Backend Engineer - Payments', 'Kraken',
            'Brazil; Peru; Colombia; Argentina; Mexico', 'ashby',
            'https://jobs.ashbyhq.com/kraken.com/1b2c3d4e-0000-4a5b-8c7d-111111111111',
            'ats', 'kraken.com', 'Yes'))
        self.assertIsNotNone(row[9])
        self.assertRegex(row[10], r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')

    def test_job_posts_scored(self):
        self._collect()
        row = self._query(
            "SELECT apply_type, apply_url, posted_at, employment_type, description,"
            " weighted_score, matched_keywords, scoring_version, scraped_at, date_time,"
            " applicant_count FROM job_posts WHERE linkedin_job_id = ?", (KRAKEN_KEEP[0],))[0]
        self.assertEqual(row[0], 'external')
        self.assertEqual(row[1], 'https://jobs.ashbyhq.com/kraken.com/'
                                 '1b2c3d4e-0000-4a5b-8c7d-111111111111/application')
        self.assertEqual(row[2], '2026-11-12T08:00:00Z')
        self.assertEqual(row[3], 'Full-time')
        self.assertEqual(row[4], 'We use Python, Go and AWS.')
        self.assertEqual(row[5], 3.0)
        self.assertEqual(set(row[6].split(',')), {'Python', 'Go', 'AWS'})
        self.assertEqual(row[7], self.keyword_config.scoring_version())
        self.assertIsNotNone(row[8])
        self.assertIsNotNone(row[9])
        self.assertIsNone(row[10])
        # Greenhouse: no applyUrl, the posting URL is used
        self.assertEqual(self._query(
            "SELECT apply_url FROM job_posts WHERE linkedin_job_id = ?", (GITLAB_KEEP,)),
            [('https://job-boards.greenhouse.io/gitlab/jobs/8638232003',)])

    def test_dropped_jobs_not_stored(self):
        self._collect()
        keys = {r[0] for r in self._query("SELECT linkedin_job_id FROM job_searches")}
        self.assertEqual(keys, set(KRAKEN_KEEP) | {GITLAB_KEEP, REDBEE_KEEP})

    def test_aggregator_stored_but_not_scored(self):
        self._collect()
        self.assertEqual(self._query(
            "SELECT COUNT(*) FROM job_searches WHERE linkedin_job_id = ?", (REDBEE_KEEP,)),
            [(1,)])
        self.assertEqual(self._query(
            "SELECT COUNT(*) FROM job_posts WHERE linkedin_job_id = ?", (REDBEE_KEEP,)),
            [(0,)])

    def test_search_runs_and_company_stats(self):
        self._collect()
        runs = self._query(
            "SELECT template_name, keywords, location, jobs_found, new_jobs, status, error,"
            " pages_fetched, finished_at IS NOT NULL FROM search_runs ORDER BY id")
        self.assertEqual(runs, [
            ('ats:ashby:kraken.com', 'ats', 'kraken.com', 4, 2, 'ok', None, 1, 1),
            ('ats:greenhouse:gitlab', 'ats', 'gitlab', 3, 1, 'ok', None, 1, 1),
            ('ats:lever:redbee', 'ats', 'redbee', 2, 1, 'ok', None, 1, 1),
            ('ats:greenhouse:gone-board', 'ats', 'gone-board', 0, 0, 'error', 'HTTP 404', 1, 1),
            ('ats:greenhouse:empty-board', 'ats', 'empty-board', 0, 0, 'ok', None, 1, 1),
        ])
        companies = self._query(
            "SELECT name, last_job_count, last_checked_at IS NOT NULL FROM companies"
            " ORDER BY rowid")
        self.assertEqual(companies, [('Kraken', 4, 1), ('GitLab', 3, 1), ('redbee', 2, 1),
                                     ('Gone', 0, 1), ('Empty', 0, 1)])

    def test_second_run_skips_known_jobs(self):
        self._collect()
        searches = self._query("SELECT COUNT(*) FROM job_searches")[0][0]
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE job_posts SET weighted_score = 99 WHERE linkedin_job_id = ?",
                     (KRAKEN_KEEP[0],))
        conn.commit()
        conn.close()

        stats = self._collect()
        self.assertEqual(stats['Kraken']['new'], 0)
        self.assertEqual(stats['Kraken']['existing'], 2)
        self.assertEqual(stats['redbee']['existing'], 1)   # aggregator: no job_posts row
        self.assertEqual(self._query("SELECT COUNT(*) FROM job_searches")[0][0], searches)
        # Existing jobs are not re-scored
        self.assertEqual(self._query(
            "SELECT weighted_score FROM job_posts WHERE linkedin_job_id = ?",
            (KRAKEN_KEEP[0],)), [(99.0,)])

    def test_storage_error_does_not_stop_other_companies(self):
        companies = self.storage.get_companies()
        with mock.patch.object(self.storage, 'save_job_analysis',
                               side_effect=[sqlite3.OperationalError('locked')] + [None] * 10):
            stats = self._collect(companies[:2])
        self.assertEqual(stats['Kraken']['status'], 'error')
        self.assertEqual(stats['GitLab']['status'], 'ok')
        self.assertEqual(self._query(
            "SELECT status, error FROM search_runs WHERE template_name = 'ats:ashby:kraken.com'"),
            [('error', 'locked')])

    def test_main_parse_args(self):
        self.assertEqual(main.parse_args([]).source, 'linkedin')
        self.assertEqual(main.parse_args(['--source', 'ats']).source, 'ats')
        with redirect_stdout(StringIO()), mock.patch('sys.stderr', StringIO()):
            with self.assertRaises(SystemExit):
                main.parse_args(['--source', 'indeed'])


class TestLinkedInFlowIgnoresAts(AtsDbTestCase):

    def test_pending_jobs_are_linkedin_only(self):
        conn = sqlite3.connect(self.db_path)
        conn.executemany(
            "INSERT INTO job_searches (linkedin_job_id, title, company, source, job_url)"
            " VALUES (?, ?, ?, ?, ?)",
            [('4000000001', 'Dev', 'Acme', None, None),
             ('lever:acme:abc-1', 'Dev', 'Acme', 'lever', 'https://jobs.lever.co/acme/abc-1'),
             ('ashby:acme:abc-2', 'Other Dev', 'Acme', 'ashby', 'https://jobs.ashbyhq.com/x')])
        conn.commit()
        conn.close()
        self.assertEqual([j['linkedin_job_id'] for j in self.storage.get_jobs_without_analysis()],
                         ['4000000001'])

        matcher = KeywordMatcher(self.storage, self.keyword_config)
        with mock.patch.object(matcher.detail_scraper, 'scrape_job_details',
                               return_value={'description': 'Python'}) as scrape:
            with redirect_stdout(StringIO()):
                results = matcher.analyze_jobs()
        scrape.assert_called_once_with('https://www.linkedin.com/jobs/view/4000000001/')
        self.assertEqual([r.linkedin_job_id for r in results], ['4000000001'])

    def test_match_result_urls(self):
        self.assertEqual(MatchResult('4000000001').job_url,
                         'https://www.linkedin.com/jobs/view/4000000001/')
        self.assertEqual(MatchResult('lever:acme:1', source_url='https://jobs.lever.co/acme/1')
                         .job_url, 'https://jobs.lever.co/acme/1')

    def test_display_results_uses_stored_url(self):
        self._collect()
        matcher = KeywordMatcher(self.storage, self.keyword_config)
        out = StringIO()
        with redirect_stdout(out):
            matcher.display_results(matcher.get_ranked_jobs(), top_n=10)
        self.assertIn('URL: https://jobs.ashbyhq.com/kraken.com/'
                      '1b2c3d4e-0000-4a5b-8c7d-111111111111', out.getvalue())
        self.assertNotIn('linkedin.com/jobs/view/ashby', out.getvalue())

    def test_backfill_skips_ats_rows(self):
        conn = sqlite3.connect(self.db_path)
        for key in ('4000000001', 'lever:acme:abc-1'):
            conn.execute("INSERT INTO job_posts (linkedin_job_id, date_time, weighted_score)"
                         " VALUES (?, ?, 5)", (key, _ago(hours=1)))
        conn.commit()
        conn.close()
        self.assertEqual([j['linkedin_job_id'] for j in select_jobs(self.db_path)],
                         ['4000000001'])


class TestWebUiWithAts(AtsDbTestCase):

    def setUp(self):
        super().setUp()
        self._collect()
        # One LinkedIn job next to the ATS ones
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT INTO job_searches (linkedin_job_id, title, company, location)"
                     " VALUES ('4000000001', 'LinkedIn Dev', 'Acme', 'Argentina')")
        conn.execute("INSERT INTO job_posts (linkedin_job_id, date_time, weighted_score,"
                     " apply_type) VALUES ('4000000001', ?, 30, 'external')", (_ago(minutes=30),))
        conn.commit()
        conn.close()

        db_path, companies_file, aggregators_file = (
            self.db_path, self.companies_file, self.aggregators_file)

        class TempStorage(SQLiteStorage):
            def __init__(self, db_file=None):
                with redirect_stdout(StringIO()):
                    super().__init__(db_file=db_file or db_path, companies_file=companies_file,
                                     aggregators_file=aggregators_file)

        patcher = mock.patch.object(web_app, 'SQLiteStorage', TempStorage)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = web_app.app.test_client()

    def _get(self, query=''):
        response = self.client.get('/?days=all' + query)
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def test_view_links_and_source_column(self):
        html = self._get()
        self.assertIn('href="https://www.linkedin.com/jobs/view/4000000001/"', html)
        self.assertIn('href="https://jobs.ashbyhq.com/kraken.com/'
                      '1b2c3d4e-0000-4a5b-8c7d-111111111111"', html)
        self.assertIn('href="https://job-boards.greenhouse.io/gitlab/jobs/8638232003"', html)
        self.assertNotIn('linkedin.com/jobs/view/ashby', html)
        self.assertNotIn('linkedin.com/jobs/view/greenhouse', html)
        self.assertIn('<th class="col-opt">Source</th>', html)
        for label in ('LinkedIn', 'Ashby', 'Greenhouse'):
            self.assertIn('<td class="nowrap col-opt">%s</td>' % label, html)

    def test_source_filter_and_chip(self):
        html = self._get('&source=ashby')
        self.assertIn('Backend Engineer - Payments', html)
        self.assertNotIn('LinkedIn Dev', html)
        self.assertNotIn('Junior Backend Engineer (Java)', html)
        self.assertIn('Source: Ashby', html)

        html = self._get('&source=linkedin')
        self.assertIn('LinkedIn Dev', html)
        self.assertNotIn('Backend Engineer - Payments', html)

        # Invalid value → no filter
        html = self._get('&source=indeed')
        self.assertIn('LinkedIn Dev', html)
        self.assertIn('Backend Engineer - Payments', html)
        self.assertNotIn('Source: ', html)

    def test_posted_column_uses_posting_date(self):
        old, recent = _ago(days=40), _ago(hours=1)
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE job_posts SET posted_at = ? WHERE linkedin_job_id = ?",
                     (old, KRAKEN_KEEP[0]))
        conn.execute("UPDATE job_posts SET posted_at = ? WHERE linkedin_job_id = ?",
                     (recent, KRAKEN_KEEP[1]))
        conn.commit()
        conn.close()
        storage = web_app.SQLiteStorage()
        jobs = storage.get_job_summary(days=None, source='ashby')
        self.assertEqual({j['linkedin_job_id']: j['date_time'] for j in jobs},
                         {KRAKEN_KEEP[0]: old, KRAKEN_KEEP[1]: recent})
        # An old posting is outside "last 7 days" although it was just collected
        jobs = storage.get_job_summary(days=7, source='ashby')
        self.assertEqual([j['linkedin_job_id'] for j in jobs], [KRAKEN_KEEP[1]])
        # LinkedIn rows (posted_at NULL) keep date_time
        self.assertEqual(storage.count_job_summary(hours=1, source='linkedin'), 1)

    def test_applications_accept_ats_keys(self):
        response = self.client.post('/api/applications',
                                    json={'linkedin_job_id': KRAKEN_KEEP[0],
                                          'applied_on': '2026-11-17'})
        self.assertEqual(response.status_code, 200)
        html = self._get('&applied=only')
        self.assertIn('Backend Engineer - Payments', html)
        self.assertIn('✓ Applied', html)
        response = self.client.delete('/api/applications',
                                      json={'linkedin_job_id': KRAKEN_KEEP[0]})
        self.assertEqual(response.status_code, 200)
        for bad in ('lever:x', 'ashby:kraken.com:a b'):
            response = self.client.post('/api/applications', json={'linkedin_job_id': bad})
            self.assertEqual(response.status_code, 400, bad)

    def test_shortlist_urls(self):
        response = self.client.get('/api/shortlist?since=365d&min_score=0&apply=all&limit=100')
        jobs = {j['linkedin_job_id']: j for j in response.get_json()['jobs']}
        self.assertEqual(jobs['4000000001']['job_url'],
                         'https://www.linkedin.com/jobs/view/4000000001/')
        self.assertEqual(jobs['4000000001']['source'], 'linkedin')
        self.assertEqual(jobs[GITLAB_KEEP]['job_url'],
                         'https://job-boards.greenhouse.io/gitlab/jobs/8638232003')
        self.assertEqual(jobs[GITLAB_KEEP]['source'], 'greenhouse')


if __name__ == '__main__':
    unittest.main()
