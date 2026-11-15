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


class TestHideFilters(unittest.TestCase):
    """"Hide aggregators" and "Hide above my level", both on by default."""

    JOBS = [
        # (linkedin_job_id, company, seniority_level)
        ('2001', 'Acme', 'Entry level'),
        ('2002', 'Acme Two', 'Mid-Senior level'),
        ('2003', 'Acme Three', 'Not Applicable'),
        ('2004', 'Acme Four', None),
        ('2005', 'Quik Hire Staffing', 'Entry level'),     # aggregator
        ('2006', 'Acme Six', 'Director'),
    ]

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        with redirect_stdout(StringIO()):
            SQLiteStorage(db_file=self.db_path)
        conn = sqlite3.connect(self.db_path)
        for job_id, company, seniority in self.JOBS:
            conn.execute("INSERT INTO job_searches (linkedin_job_id, title, company, location)"
                         " VALUES (?, ?, ?, 'Remote')", (job_id, f'Dev {job_id}', company))
            conn.execute("INSERT INTO job_posts (linkedin_job_id, date_time, weighted_score,"
                         " seniority_level) VALUES (?, '2026-11-01T10:00:00Z', 1.0, ?)",
                         (job_id, seniority))
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

    def _get(self, query=''):
        response = self.client.get('/?days=all' + query)
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def test_defaults_hide_both(self):
        html = self._get()
        self.assertIn('Showing 1–3 of 3', html)       # 2001, 2003, 2004
        for hidden in ('>2002<', '>2005<', '>2006<'):
            self.assertNotIn(hidden, html)
        self.assertIn('<dd>Not Applicable</dd>', html)
        self.assertRegex(html, r'name="hide_aggregators" value="1" checked')
        self.assertRegex(html, r'name="hide_above_level" value="1" checked')

    def test_show_aggregators(self):
        html = self._get('&hide_aggregators=0&hide_aggregators=1&hide_aggregators=0')
        self.assertIn('Showing 1–4 of 4', html)
        self.assertIn('>2005<', html)

    def test_show_above_level(self):
        html = self._get('&hide_above_level=0')
        self.assertIn('Showing 1–5 of 5', html)
        self.assertIn('<dd>Mid-Senior level</dd>', html)
        self.assertIn('<dd>Director</dd>', html)

    def test_show_all(self):
        self.assertIn('Showing 1–6 of 6', self._get('&hide_aggregators=0&hide_above_level=0'))

    def test_pagination_links_keep_filters(self):
        html = self._get('&hide_above_level=0')
        thead = html.split('<thead>')[1].split('</thead>')[0]
        self.assertIn('hide_above_level=0', thead)
        self.assertIn('hide_aggregators=1', thead)

    def test_no_data_deleted(self):
        self._get()
        conn = sqlite3.connect(self.db_path)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM job_posts").fetchone()[0], 6)
        conn.close()


class TestResultsPage(unittest.TestCase):
    """New filters, chips, presentation helpers and the applications API."""

    JOBS = [
        # (id, title, company, score, keywords, applicants, qualifier, employment)
        ('3001', 'Java Developer', 'Acme', 60.0, 'Java,Spring,SQL,Git,Docker,AWS,Linux',
         25, 'under', 'Full-time'),
        ('3002', 'JS Developer', 'Globex', 30.0, 'JavaScript', 25, None, 'Contract'),
        ('3003', 'Python Dev', 'Initech', 12.0, 'Python', 200, 'over', 'Full-time'),
        ('3004', 'Data Engineer', 'Umbrella', 5.0, None, 87, None, 'Part-time'),
        ('3005', 'Java Developer', 'Acme', 55.0, 'Java', None, None, 'Full-time'),
    ]

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        with redirect_stdout(StringIO()):
            SQLiteStorage(db_file=self.db_path)
        conn = sqlite3.connect(self.db_path)
        for job_id, title, company, score, kws, count, qualifier, emp in self.JOBS:
            conn.execute("INSERT INTO job_searches (linkedin_job_id, title, company, location)"
                         " VALUES (?, ?, ?, 'Remote')", (job_id, title, company))
            conn.execute("INSERT INTO job_posts (linkedin_job_id, date_time, weighted_score,"
                         " matched_keywords, applicant_count, applicant_count_qualifier,"
                         " employment_type, industries, description)"
                         " VALUES (?, '2026-11-01T10:00:00Z', ?, ?, ?, ?, ?,"
                         " 'Software Development', ?)",
                         (job_id, score, kws, count, qualifier, emp,
                          'Description of %s. ' % job_id + 'y' * 600))
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
        self.storage = TempStorage()

    def tearDown(self):
        os.remove(self.db_path)

    def _get(self, query=''):
        response = self.client.get('/?days=all' + query)
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def _chips(self, html):
        if 'id="activeFilters"' not in html:
            return ''
        return html.split('id="activeFilters"')[1].split('</div>')[0]

    def test_text_search(self):
        self.assertIn('Showing 1–2 of 2', self._get('&q=java'))
        self.assertIn('Showing 1–1 of 1', self._get('&q=GLOBEX'))

    def test_employment_multi_select(self):
        html = self._get('&emp=Contract&emp=Part-time')
        self.assertIn('Showing 1–2 of 2', html)
        self.assertRegex(html, r'name="emp" value="Contract" checked')
        self.assertNotRegex(html, r'name="emp" value="Full-time" checked')
        # Options come from the DB
        self.assertIn('name="emp" value="Part-time"', html)

    def test_score_range_and_match(self):
        self.assertIn('Showing 1–2 of 2', self._get('&min_score=10&max_score=40'))
        self.assertIn('Showing 1–5 of 5', self._get('&max_score=bogus&min_match=-1'))

    def test_keyword_filter(self):
        self.assertIn('Showing 1–2 of 2', self._get('&kw=Java'))
        self.assertIn('Showing 1–3 of 3', self._get('&kw=Java&kw=JavaScript'))
        # Keywords outside DEFAULT_KEYWORDS are ignored
        self.assertIn('Showing 1–5 of 5', self._get('&kw=NotAKeyword'))

    def test_under_25_filter(self):
        html = self._get('&under25=1')
        self.assertIn('Showing 1–2 of 2', html)      # 'under' + historical 25
        self.assertIn('>Under 25 applicants <span class="x">', self._chips(html))

    def test_applicants_labels(self):
        html = self._get()
        self.assertEqual(html.count('>&lt;25</td>'), 2)
        self.assertIn('>&gt;200</td>', html)
        self.assertIn('>87</td>', html)

    def test_helpers(self):
        self.assertEqual(web_app.applicants_label({'applicant_count': 25}), '<25')
        self.assertEqual(web_app.applicants_label(
            {'applicant_count': 25, 'applicant_count_qualifier': 'under'}), '<25')
        self.assertEqual(web_app.applicants_label(
            {'applicant_count': 200, 'applicant_count_qualifier': 'over'}), '>200')
        self.assertEqual(web_app.applicants_label({'applicant_count': 12}), '12')
        self.assertEqual(web_app.applicants_label({'applicant_count': None}), '-')
        self.assertEqual([web_app.score_badge(s) for s in (None, 0, 9.9, 10, 25, 49.9, 50, 500)],
                         ['low', 'low', 'low', 'fair', 'good', 'good', 'strong', 'strong'])

    def test_score_badges_and_keyword_chips(self):
        html = self._get()
        self.assertIn('<span class="score score-strong">60.0</span>', html)
        self.assertIn('<span class="score score-good">30.0</span>', html)
        self.assertIn('<span class="score score-fair">12.0</span>', html)
        self.assertIn('<span class="score score-low">5.0</span>', html)
        self.assertIn('<span class="kw-more">+2 more</span>', html)
        self.assertNotIn('<span class="kw">AWS</span>', html)

    def test_expandable_details(self):
        html = self._get('&q=Initech')
        details = html.split('id="details-3003"')[1].split('</tr>')[0]
        self.assertIn('hidden', details.split('>')[0])
        self.assertIn('<dd>Full-time</dd>', details)
        self.assertIn('<dd>Software Development</dd>', details)
        self.assertIn('Description of 3003.', details)
        # Snippet capped at 500 characters
        self.assertIn('y' * (500 - len('Description of 3003. ')) + '…', details)
        self.assertNotIn('y' * 500, details)

    def test_no_light_theme_or_hardcoded_colors(self):
        html = self._get()
        self.assertNotIn('data-theme', html)
        style = html.split('<style>')[1].split('</style>')[0]
        self.assertNotRegex(style, r'#[0-9a-fA-F]{3,6}\b')
        self.assertNotRegex(style, r'rgb\(')

    def test_chips_and_clear_link(self):
        html = self._get('&q=dev&kw=Java&kw=SQL&hide_aggregators=0&applied=all&sort=title&dir=asc')
        chips = self._chips(html)
        self.assertIn('Search: &#34;dev&#34;', chips)
        self.assertIn('All time', chips)
        self.assertIn('Keyword: Java', chips)
        self.assertIn('Keyword: SQL', chips)
        self.assertIn('Aggregators shown', chips)
        self.assertIn('Applied: All', chips)
        self.assertNotIn('Blacklisted shown', chips)
        # Removing one keyword keeps the other and the rest of the filters
        java_chip = [c for c in chips.split('<a ') if 'Keyword: Java' in c][0]
        self.assertIn('kw=SQL', java_chip)
        self.assertNotIn('kw=Java', java_chip)
        self.assertIn('q=dev', java_chip)
        # Clear keeps only sort / dir / per_page
        clear = html.split('id="clearFilters"')[0].rsplit('href="', 1)[1].split('"')[0]
        self.assertEqual(clear, '/?sort=title&amp;dir=asc&amp;per_page=50')

    def test_no_chips_by_default(self):
        response = self.client.get('/')
        self.assertNotIn('id="activeFilters"', response.get_data(as_text=True))

    def test_list_params_kept_in_links(self):
        html = self._get('&kw=Java&kw=Spring&emp=Full-time')
        thead = html.split('<thead>')[1].split('</thead>')[0]
        self.assertIn('kw=Java&amp;kw=Spring', thead)
        self.assertIn('emp=Full-time', thead)

    def _post(self, body, method='POST'):
        return self.client.open('/api/applications', method=method, json=body)

    def test_mark_applied_hides_job_and_twin(self):
        r = self._post({'linkedin_job_id': '3001', 'applied_on': '2026-11-12', 'notes': ' hi '})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['notes'], 'hi')
        html = self._get()
        self.assertIn('Showing 1–3 of 3', html)       # 3001 and its twin 3005 hidden
        html = self._get('&applied=only')
        self.assertIn('Showing 1–2 of 2', html)
        self.assertIn('✓ Applied', html)
        self.assertIn('✓ Similar', html)
        self.assertIn('Showing 1–5 of 5', self._get('&applied=all'))
        self.assertIn('Showing 1–3 of 3', self._get('&applied=bogus'))
        self.assertEqual(self.client.get('/api/applications').get_json()[0]['applied_on'],
                         '2026-11-12')

    def test_unmark_applied(self):
        self._post({'linkedin_job_id': '3001'})
        r = self._post({'linkedin_job_id': '3001'}, method='DELETE')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get('/api/applications').get_json(), [])

    def test_applied_on_defaults_to_today(self):
        r = self._post({'linkedin_job_id': '3002'})
        self.assertEqual(r.status_code, 200)
        self.assertRegex(r.get_json()['applied_on'], r'^\d{4}-\d{2}-\d{2}$')

    def test_application_validation(self):
        cases = [
            ({}, 400),
            ({'linkedin_job_id': 'abc'}, 400),
            ({'linkedin_job_id': '３００１'}, 400),          # non-ASCII digits
            ({'linkedin_job_id': '3001', 'applied_on': '2026-13-01'}, 400),
            ({'linkedin_job_id': '3001', 'applied_on': '12/11/2026'}, 400),
            ({'linkedin_job_id': '3001', 'notes': 'x' * 2001}, 400),
            ({'linkedin_job_id': '9999999999'}, 404),
        ]
        for body, status in cases:
            with self.subTest(body=body):
                self.assertEqual(self._post(body).status_code, status)
        self.assertEqual(self._post({}, method='DELETE').status_code, 400)
        self.assertEqual(self.client.get('/api/applications').get_json(), [])


if __name__ == '__main__':
    unittest.main()
