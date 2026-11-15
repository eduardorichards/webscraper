"""Tests for search result pagination ("See more jobs") in JobScraper (HTTP mocked)."""

import logging
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

from config.settings import SEARCH_FIRST_PAGE_SIZE, SEARCH_MORE_PAGE_SIZE
from main import multiple_search
from scraper import JobScraper, SearchConfig
from scraper.core.url_builder import LinkedInURLBuilder
from scraper.extractors.linkedin_extractor import LinkedInExtractor
from utils.sqlite_storage import SQLiteStorage

FIXTURES = Path(__file__).parent / 'fixtures'


def _card(job_id):
    return f"""
    <div class="base-card job-search-card" data-entity-urn="urn:li:jobPosting:{job_id}">
      <a class="base-card__full-link" href="https://ar.linkedin.com/jobs/view/dev-at-acme-{job_id}"></a>
      <h3 class="base-search-card__title">Developer {job_id}</h3>
      <h4 class="base-search-card__subtitle"><a href="https://ar.linkedin.com/company/acme">Acme</a></h4>
      <span class="job-search-card__location">Buenos Aires, Argentina</span>
    </div>"""


def _ids(start, count):
    return [str(4400000000 + i) for i in range(start, start + count)]


def _response(job_ids, status=200):
    resp = requests.Response()
    resp.status_code = status
    resp._content = ''.join(_card(j) for j in job_ids).encode('utf-8')
    resp.url = 'https://www.linkedin.com/jobs/search'
    return resp


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def _config(max_results=250):
    return SearchConfig(keywords="Java", location="Latin America", time_posted="1h",
                        remote=True, experience_levels=[1, 2], max_results=max_results)


class TestSeeMoreUrl(unittest.TestCase):

    def test_same_params_plus_start(self):
        config = _config()
        with redirect_stdout(StringIO()):
            search = urlparse(LinkedInURLBuilder.build_url(config))
        more = urlparse(LinkedInURLBuilder.build_see_more_url(config, 60))
        self.assertEqual(more.netloc, 'www.linkedin.com')
        self.assertEqual(more.path, '/jobs-guest/jobs/api/seeMoreJobPostings/search')
        more_params = parse_qs(more.query)
        self.assertEqual(more_params.pop('start'), ['60'])
        self.assertEqual(more_params, parse_qs(search.query))


class TestFixtures(unittest.TestCase):
    """The extractor handles both page types as LinkedIn served them on 2026-11-14."""

    def _extract(self, name):
        soup = BeautifulSoup((FIXTURES / name).read_text(encoding='utf-8'), 'html.parser')
        extractor = LinkedInExtractor()
        with redirect_stdout(StringIO()):
            jobs = extractor.extract_jobs(soup, 100)
        return extractor, jobs

    def test_search_page(self):
        extractor, jobs = self._extract('search_page.html')
        self.assertEqual(extractor.last_card_count, 2)
        self.assertEqual([j.linkedin_job_id for j in jobs], ['4475051370', '4483331003'])
        self.assertEqual(jobs[0].title, 'Pessoa Desenvolvedora Backend Java SR')
        self.assertEqual(jobs[0].company, 'Banco Bradesco')
        self.assertEqual(jobs[0].company_url, 'https://www.linkedin.com/company/bradesco')

    def test_see_more_page(self):
        extractor, jobs = self._extract('search_see_more.html')
        self.assertEqual([j.linkedin_job_id for j in jobs], ['4483117626', '4481002640'])
        self.assertEqual(jobs[0].title, 'SailPoint ISC Consultant')
        self.assertEqual(jobs[0].location, 'Mexico')


class TestPagination(unittest.TestCase):

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        with redirect_stdout(StringIO()):
            self.storage = SQLiteStorage(db_file=self.db_path)

    def tearDown(self):
        os.remove(self.db_path)

    def _search(self, responses, max_pages=4, config=None):
        scraper = JobScraper(sqlite_storage=self.storage, max_pages=max_pages)
        handler = _ListHandler()
        logger = logging.getLogger('scraper')
        logger.addHandler(handler)
        self.addCleanup(logger.removeHandler, handler)
        with mock.patch('scraper.core.scraper.requests.get',
                        side_effect=responses) as get, \
                mock.patch('scraper.core.scraper.time.sleep') as sleep, \
                redirect_stdout(StringIO()):
            try:
                jobs = scraper.search_jobs(config or _config(), raise_errors=True)
            finally:
                self.urls = [call.args[0] for call in get.call_args_list]
                self.sleep = sleep
                self.logs = handler.messages
        return scraper, jobs

    def _starts(self):
        return [parse_qs(urlparse(u).query).get('start', [None])[0] for u in self.urls]

    def test_short_first_page_fetches_one_page(self):
        scraper, jobs = self._search([_response(_ids(0, 12))])
        self.assertEqual(len(self.urls), 1)
        self.assertEqual((scraper.last_jobs_found, scraper.last_new_jobs,
                          scraper.last_pages_fetched, scraper.last_hit_page_limit),
                         (12, 12, 1, False))
        self.sleep.assert_not_called()

    def test_follows_pages_until_short_page(self):
        full = SEARCH_FIRST_PAGE_SIZE
        more = SEARCH_MORE_PAGE_SIZE
        scraper, jobs = self._search([
            _response(_ids(0, full)),
            _response(_ids(full, more)),
            _response(_ids(full + more, 4)),        # short page → last one
        ])
        self.assertEqual(self._starts(), [None, str(full), str(full + more)])
        self.assertIn('/jobs-guest/jobs/api/seeMoreJobPostings/search', self.urls[1])
        self.assertEqual(len(jobs), full + more + 4)
        self.assertEqual((scraper.last_pages_fetched, scraper.last_hit_page_limit), (3, False))
        self.assertEqual(scraper.last_new_jobs, full + more + 4)
        # Same random delay as between templates, before each extra page
        self.assertEqual(self.sleep.call_count, 2)

    def test_hits_page_limit(self):
        full = SEARCH_FIRST_PAGE_SIZE
        more = SEARCH_MORE_PAGE_SIZE
        scraper, jobs = self._search([
            _response(_ids(0, full)),
            _response(_ids(full, more)),
        ], max_pages=2)
        self.assertEqual(len(self.urls), 2)
        self.assertEqual((scraper.last_pages_fetched, scraper.last_hit_page_limit), (2, True))
        self.assertTrue(any('hit the page limit' in line for line in self.logs))

    def test_stops_when_page_only_repeats_earlier_jobs(self):
        full = SEARCH_FIRST_PAGE_SIZE
        scraper, jobs = self._search([
            _response(_ids(0, full)),
            _response(_ids(0, SEARCH_MORE_PAGE_SIZE)),   # all already seen
        ])
        self.assertEqual(len(self.urls), 2)
        self.assertEqual(len(jobs), full)
        self.assertFalse(scraper.last_hit_page_limit)

    def test_duplicates_across_pages_saved_once(self):
        full = SEARCH_FIRST_PAGE_SIZE
        page2 = _ids(full - 2, 2) + _ids(full, SEARCH_MORE_PAGE_SIZE - 2)
        scraper, jobs = self._search([
            _response(_ids(0, full)),
            _response(page2),                   # 2 repeated, 8 new
            _response([]),
        ])
        ids = [j.linkedin_job_id for j in jobs]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), full + SEARCH_MORE_PAGE_SIZE - 2)
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT COUNT(*), COUNT(DISTINCT linkedin_job_id)"
                            " FROM job_searches").fetchone()
        conn.close()
        self.assertEqual(rows, (len(ids), len(ids)))

    def test_max_results_caps_the_run(self):
        full = SEARCH_FIRST_PAGE_SIZE
        scraper, jobs = self._search([
            _response(_ids(0, full)),
            _response(_ids(full, SEARCH_MORE_PAGE_SIZE)),
        ], config=_config(max_results=full + 5))
        self.assertEqual(len(self.urls), 2)
        self.assertEqual(len(jobs), full + 5)
        self.assertFalse(scraper.last_hit_page_limit)

    def test_retries_after_429(self):
        with mock.patch('scraper.core.scraper.MAX_RETRIES', 2), \
                mock.patch('scraper.core.scraper.RETRY_DELAY', 60):
            scraper, jobs = self._search([
                _response([], status=429),
                _response(_ids(0, 3)),
            ])
        self.assertEqual(len(self.urls), 2)
        self.assertEqual(len(jobs), 3)
        self.sleep.assert_called_once_with(60)

    def test_gives_up_after_max_retries(self):
        with mock.patch('scraper.core.scraper.MAX_RETRIES', 1), \
                self.assertRaises(requests.exceptions.HTTPError):
            self._search([_response([], status=429), _response([], status=429)])

    def test_later_page_failure_keeps_earlier_pages(self):
        full = SEARCH_FIRST_PAGE_SIZE
        scraper = JobScraper(sqlite_storage=self.storage, max_pages=4)
        with mock.patch('scraper.core.scraper.requests.get', side_effect=[
                    _response(_ids(0, full)),
                    _response([], status=503)]), \
                mock.patch('scraper.core.scraper.time.sleep'), \
                redirect_stdout(StringIO()), \
                self.assertRaises(requests.exceptions.HTTPError):
            scraper.search_jobs(_config(), raise_errors=True)
        self.assertEqual((scraper.last_jobs_found, scraper.last_new_jobs,
                          scraper.last_pages_fetched), (full, full, 1))
        conn = sqlite3.connect(self.db_path)
        count = conn.execute("SELECT COUNT(*) FROM job_searches").fetchone()[0]
        conn.close()
        self.assertEqual(count, full)


class TestSearchRunPagination(unittest.TestCase):
    """multiple_search records pages_fetched / hit_page_limit in search_runs."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        with redirect_stdout(StringIO()):
            self.storage = SQLiteStorage(db_file=self.db_path)

    def tearDown(self):
        os.remove(self.db_path)

    def test_runs_record_pages(self):
        full = SEARCH_FIRST_PAGE_SIZE
        more = SEARCH_MORE_PAGE_SIZE
        template = {"keywords": "Java", "location": "Latin America",
                    "experience_levels": [1, 2], "remote": True,
                    "time_posted": "1h", "max_results": 250}
        templates = [dict(template, name="Short"), dict(template, name="Capped"),
                     dict(template, name="Broken")]
        responses = [
            _response(_ids(0, 5)),                          # Short: 1 page
            _response(_ids(100, full)),                     # Capped: 2 full pages
            _response(_ids(200, more)),
            _response(_ids(300, full)),                     # Broken: page 2 fails
            _response([], status=503),
        ]
        scraper = JobScraper(sqlite_storage=self.storage, max_pages=2)
        with mock.patch('scraper.core.scraper.requests.get', side_effect=responses), \
                mock.patch('scraper.core.scraper.time.sleep'), \
                mock.patch('main.time.sleep'), \
                redirect_stdout(StringIO()), \
                self.assertLogs(level='INFO'):
            multiple_search(templates=templates, scraper=scraper)

        runs = list(reversed(self.storage.get_search_runs()))
        summary = [(r['template_name'], r['jobs_found'], r['new_jobs'],
                    r['pages_fetched'], r['hit_page_limit'], r['status'])
                   for r in runs]
        self.assertEqual(summary, [
            ("Short", 5, 5, 1, 0, 'ok'),
            ("Capped", full + more, full + more, 2, 1, 'ok'),
            ("Broken", full, full, 1, 0, 'error'),
        ])
        self.assertIn('503', runs[2]['error'])


if __name__ == '__main__':
    unittest.main()
