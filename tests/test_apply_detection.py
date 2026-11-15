"""Tests for application type detection and closed-job handling in detail_scraper."""

import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

from bs4 import BeautifulSoup

from scraper.core.detail_scraper import (
    DetailScraper,
    is_closed_job_url,
    parse_apply_type,
)

FIXTURES = Path(__file__).parent / 'fixtures'


def _fixture(name):
    return (FIXTURES / name).read_text(encoding='utf-8')


def _soup(html):
    return BeautifulSoup(html, 'html.parser')


class TestParseApplyType(unittest.TestCase):

    def test_easy_apply_fixture(self):
        self.assertEqual(parse_apply_type(_soup(_fixture('job_easy_apply.html'))), 'easy_apply')

    def test_external_fixture(self):
        self.assertEqual(parse_apply_type(_soup(_fixture('job_external.html'))), 'external')

    def test_unknown_without_markers(self):
        html = _fixture('job_easy_apply.html').replace(
            'public_jobs_apply-link-onsite', 'public_jobs_something-else')
        self.assertIsNone(parse_apply_type(_soup(html)))

    def test_unknown_on_empty_page(self):
        self.assertIsNone(parse_apply_type(_soup('<html><body></body></html>')))

    def test_unknown_when_both_markers_present(self):
        html = ('<button data-tracking-control-name="public_jobs_apply-link-onsite"></button>'
                '<a data-tracking-control-name="public_jobs_apply-link-offsite_join-link"></a>')
        self.assertIsNone(parse_apply_type(_soup(html)))

    def test_closed_notice_is_unknown_never_easy_apply(self):
        html = _fixture('job_easy_apply.html').replace(
            '<h1 class="top-card-layout__title">',
            '<span class="closed-job">No longer accepting applications</span>'
            '<h1 class="top-card-layout__title">')
        self.assertIsNone(parse_apply_type(_soup(html)))

    def test_closed_notice_inside_description_is_ignored(self):
        html = _fixture('job_easy_apply.html').replace(
            'We are looking for',
            'Once filled we are no longer accepting applications. We are looking for')
        self.assertEqual(parse_apply_type(_soup(html)), 'easy_apply')


class TestIsClosedJobUrl(unittest.TestCase):

    def test_job_page_is_open(self):
        self.assertFalse(is_closed_job_url('https://www.linkedin.com/jobs/view/4489354672/'))

    def test_expired_redirect(self):
        self.assertTrue(is_closed_job_url(
            'https://es.linkedin.com/jobs/administrador-de-sistemas-empleos'
            '?trk=expired_jd_redirect&position=1'))

    def test_redirect_away_from_job_view(self):
        self.assertTrue(is_closed_job_url('https://www.linkedin.com/jobs/search?keywords=python'))

    def test_job_view_path_in_query_only_is_closed(self):
        self.assertTrue(is_closed_job_url(
            'https://www.linkedin.com/jobs/search?redirect=/jobs/view/123/'))


class TestScrapeJobDetails(unittest.TestCase):
    """scrape_job_details() with requests.get mocked."""

    def _scrape(self, html, final_url):
        response = mock.Mock(status_code=200, content=html.encode('utf-8'), url=final_url)
        scraper = DetailScraper()
        with mock.patch('scraper.core.detail_scraper.requests.get', return_value=response), \
                mock.patch.object(scraper, '_apply_rate_limiting'), \
                redirect_stdout(StringIO()):
            return scraper.scrape_job_details('https://www.linkedin.com/jobs/view/1/')

    def test_easy_apply_page(self):
        details = self._scrape(_fixture('job_easy_apply.html'),
                               'https://www.linkedin.com/jobs/view/1/')
        self.assertEqual(details['apply_type'], 'easy_apply')
        self.assertIsNone(details['apply_url'])
        self.assertIn('Python', details['description'])
        self.assertEqual(details['seniority_level'], 'Mid-Senior level')

    def test_external_page_has_no_url_when_logged_out(self):
        details = self._scrape(_fixture('job_external.html'),
                               'https://www.linkedin.com/jobs/view/1/')
        self.assertEqual(details['apply_type'], 'external')
        self.assertIsNone(details['apply_url'])

    def test_expired_redirect_is_closed(self):
        details = self._scrape(
            '<html><body>Search results</body></html>',
            'https://es.linkedin.com/jobs/some-search?trk=expired_jd_redirect')
        self.assertEqual(details, {'closed': True})


if __name__ == '__main__':
    unittest.main()
