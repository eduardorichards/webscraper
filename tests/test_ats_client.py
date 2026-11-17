"""Tests for ATS board parsing and fetching (scraper/sources/ats_client.py).

Uses trimmed real responses in tests/fixtures/; HTTP is mocked.
"""

import json
import unittest
from pathlib import Path
from unittest import mock

import requests

from scraper.sources.ats_client import (
    AtsError, USER_AGENT, board_url, fetch_board, html_to_text,
    normalize_employment_type, parse_ashby, parse_greenhouse, parse_lever, to_utc_iso)

FIXTURES = Path(__file__).resolve().parent / 'fixtures'


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


class TestHelpers(unittest.TestCase):

    def test_to_utc_iso(self):
        self.assertEqual(to_utc_iso('2026-07-22T13:38:40-04:00'), '2026-07-22T17:38:40Z')
        self.assertEqual(to_utc_iso('2026-10-16T10:44:16.327+00:00'), '2026-10-16T10:44:16Z')
        self.assertEqual(to_utc_iso('2026-11-12T08:00:00Z'), '2026-11-12T08:00:00Z')
        self.assertEqual(to_utc_iso('2026-11-12T08:00:00.12345Z'), '2026-11-12T08:00:00Z')
        self.assertEqual(to_utc_iso(1790957920025), '2026-10-02T16:18:40Z')
        self.assertEqual(to_utc_iso('1790957920025'), '2026-10-02T16:18:40Z')
        self.assertIsNone(to_utc_iso(None))
        self.assertIsNone(to_utc_iso(''))
        self.assertIsNone(to_utc_iso('yesterday'))

    def test_employment_types(self):
        self.assertEqual(normalize_employment_type('FullTime'), 'Full-time')
        self.assertEqual(normalize_employment_type('Full Time'), 'Full-time')
        self.assertEqual(normalize_employment_type('full-time'), 'Full-time')
        self.assertEqual(normalize_employment_type('PartTime'), 'Part-time')
        self.assertEqual(normalize_employment_type('Contractor'), 'Contract')
        self.assertEqual(normalize_employment_type('Intern'), 'Internship')
        self.assertEqual(normalize_employment_type('Full-Time | Hybrid'), 'Full-time')
        self.assertEqual(normalize_employment_type('Contract | Remote'), 'Contract')
        self.assertEqual(normalize_employment_type('Freelance'), 'Contract')
        self.assertIsNone(normalize_employment_type('RDD | Argentina'))
        self.assertIsNone(normalize_employment_type('Global | LATAM'))
        self.assertIsNone(normalize_employment_type(None))

    def test_html_to_text(self):
        text = html_to_text('<p>Build <b>APIs</b></p><ul><li>Python</li><li>Go</li></ul>')
        self.assertIn('APIs', text)
        self.assertIn('Python', text)
        self.assertNotIn('<', text)
        self.assertEqual(html_to_text(None), '')

    def test_board_urls(self):
        self.assertEqual(board_url('greenhouse', 'gitlab'),
                         'https://boards-api.greenhouse.io/v1/boards/gitlab/jobs?content=true')
        self.assertEqual(board_url('lever', 'redbee'),
                         'https://api.lever.co/v0/postings/redbee?mode=json')
        self.assertEqual(
            board_url('ashby', 'kraken.com'),
            'https://api.ashbyhq.com/posting-api/job-board/kraken.com?includeCompensation=true')
        with self.assertRaises(ValueError):
            board_url('workday', 'x')


class TestGreenhouse(unittest.TestCase):

    def setUp(self):
        self.jobs = parse_greenhouse(_load('greenhouse_jobs.json'), 'GitLab', 'gitlab')

    def test_fields(self):
        job = self.jobs[0]
        self.assertEqual(job.key, 'greenhouse:gitlab:8638232002')
        self.assertEqual(job.source, 'greenhouse')
        self.assertEqual(job.company, 'GitLab')
        self.assertEqual(job.title, 'Backend Engineer, Python')
        self.assertEqual(job.job_url, 'https://job-boards.greenhouse.io/gitlab/jobs/8638232002')
        self.assertEqual(job.apply_url, job.job_url)
        self.assertIsNone(job.employment_type)
        self.assertTrue(job.remote)

    def test_content_is_unescaped_plain_text(self):
        description = self.jobs[0].description
        self.assertIn("What you'll do", description)
        self.assertIn('Python', description)
        self.assertIn('& Go', description)
        self.assertNotIn('<', description)
        self.assertNotIn('&lt;', description)
        self.assertNotIn('&amp;', description)

    def test_first_published_preferred(self):
        self.assertEqual(self.jobs[0].posted_at, '2026-07-22T17:38:40Z')
        # No first_published: updated_at
        self.assertEqual(self.jobs[1].posted_at, '2026-11-10T12:00:00Z')

    def test_offices_in_locations(self):
        self.assertEqual(self.jobs[0].locations,
                         ['Remote, United States', 'United States of America'])
        self.assertEqual(self.jobs[1].locations,
                         ['Remote, LATAM', 'Buenos Aires, Argentina', 'Americas'])
        self.assertEqual(self.jobs[1].location_raw,
                         'Remote, LATAM; Buenos Aires, Argentina; Americas')


class TestLever(unittest.TestCase):

    def setUp(self):
        self.jobs = parse_lever(_load('lever_postings.json'), 'redbee', 'redbee')

    def test_fields(self):
        job = self.jobs[0]
        self.assertEqual(job.key, 'lever:redbee:f035d332-b86e-4a9f-a6ce-6c22d8c71572')
        self.assertEqual(job.title, 'Developer Backend SSR — Java')
        self.assertEqual(job.job_url,
                         'https://jobs.lever.co/redbee/f035d332-b86e-4a9f-a6ce-6c22d8c71572')
        self.assertEqual(job.apply_url, job.job_url + '/apply')
        self.assertEqual(job.posted_at, '2026-10-02T16:18:40Z')
        self.assertEqual(job.employment_type, 'Full-time')
        self.assertFalse(job.remote)          # hybrid
        self.assertTrue(self.jobs[1].remote)
        self.assertEqual(self.jobs[1].employment_type, 'Full-time')   # "Full Time"

    def test_locations(self):
        # country AR adds "Argentina"; duplicates removed
        self.assertEqual(self.jobs[0].locations, ['Capital Federal', 'Argentina'])
        self.assertEqual(self.jobs[1].locations, ['Bogota', 'Lima'])

    def test_description_parts(self):
        description = self.jobs[0].description
        self.assertTrue(description.startswith('Somos redbee'))
        self.assertIn('Requisitos\nExperiencia con', description)
        self.assertIn('Java', description)
        self.assertNotIn('<li>', description)
        self.assertTrue(description.endswith('Ofrecemos 10 días hábiles de vacaciones.'))
        # Empty lists / additionalPlain don't leave trailing blank parts
        self.assertEqual(self.jobs[1].description, 'Buscamos QA con Playwright.')


class TestAshby(unittest.TestCase):

    def setUp(self):
        self.jobs = parse_ashby(_load('ashby_job_board.json'), 'Kraken', 'kraken.com')

    def test_unlisted_skipped(self):
        self.assertEqual(len(self.jobs), 4)
        self.assertNotIn('Hidden Role', [j.title for j in self.jobs])

    def test_fields(self):
        job = self.jobs[1]
        self.assertEqual(job.key, 'ashby:kraken.com:1b2c3d4e-0000-4a5b-8c7d-111111111111')
        self.assertEqual(job.company, 'Kraken')
        self.assertEqual(job.job_url,
                         'https://jobs.ashbyhq.com/kraken.com/1b2c3d4e-0000-4a5b-8c7d-111111111111')
        self.assertEqual(job.apply_url, job.job_url + '/application')
        self.assertEqual(job.posted_at, '2026-11-12T08:00:00Z')
        self.assertEqual(job.employment_type, 'Full-time')
        self.assertTrue(job.remote)
        self.assertEqual(job.description, 'We use Python, Go and AWS.')
        self.assertEqual(self.jobs[0].posted_at, '2026-10-16T10:44:16Z')
        self.assertEqual(self.jobs[2].employment_type, 'Contract')
        self.assertEqual(self.jobs[3].employment_type, 'Part-time')

    def test_secondary_locations(self):
        self.assertEqual(self.jobs[1].locations,
                         ['Brazil', 'Peru', 'Colombia', 'Argentina', 'Mexico'])


class TestFetchBoard(unittest.TestCase):

    COMPANY = {'name': 'Kraken', 'ats': 'ashby', 'slug': 'kraken.com'}

    def _session(self, status=200, payload=None, exc=None):
        session = mock.Mock()
        if exc is not None:
            session.get.side_effect = exc
        else:
            response = mock.Mock(status_code=status)
            if isinstance(payload, Exception):
                response.json.side_effect = payload
            else:
                response.json.return_value = payload
            session.get.return_value = response
        return session

    def test_ok(self):
        session = self._session(payload=_load('ashby_job_board.json'))
        jobs = fetch_board(self.COMPANY, session=session)
        self.assertEqual(len(jobs), 4)
        url = session.get.call_args[0][0]
        kwargs = session.get.call_args[1]
        self.assertEqual(url, board_url('ashby', 'kraken.com'))
        self.assertEqual(kwargs['timeout'], 15)
        self.assertEqual(kwargs['headers']['User-Agent'], USER_AGENT)

    def test_empty_board_is_not_an_error(self):
        self.assertEqual(fetch_board(self.COMPANY, session=self._session(payload={'jobs': []})), [])
        self.assertEqual(fetch_board({'name': 'X', 'ats': 'lever', 'slug': 'x'},
                                     session=self._session(payload=[])), [])

    def test_errors(self):
        with self.assertRaisesRegex(AtsError, 'HTTP 404'):
            fetch_board(self.COMPANY, session=self._session(status=404, payload={}))
        with self.assertRaisesRegex(AtsError, 'request failed'):
            fetch_board(self.COMPANY, session=self._session(exc=requests.Timeout('slow')))
        with self.assertRaisesRegex(AtsError, 'unexpected response'):
            fetch_board(self.COMPANY, session=self._session(payload=ValueError('not json')))
        with self.assertRaisesRegex(AtsError, 'unexpected response'):
            fetch_board(self.COMPANY, session=self._session(payload=['not', 'a', 'board']))


if __name__ == '__main__':
    unittest.main()
