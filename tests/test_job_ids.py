"""Tests for linkedin_job_id extraction and validation in LinkedInExtractor."""

import unittest
from contextlib import redirect_stdout
from io import StringIO

from bs4 import BeautifulSoup

from scraper.extractors.linkedin_extractor import LinkedInExtractor, is_valid_job_id


def _card(href=None, urn=None, title="Developer"):
    urn_attr = f' data-entity-urn="{urn}"' if urn else ''
    link = f'<a class="base-card__full-link" href="{href}"></a>' if href else ''
    return f"""
    <div class="base-card job-search-card"{urn_attr}>
      {link}
      <h3 class="base-search-card__title">{title}</h3>
      <h4 class="base-search-card__subtitle"><a href="https://ar.linkedin.com/company/x">X</a></h4>
      <span class="job-search-card__location">Remote</span>
    </div>"""


class TestIsValidJobId(unittest.TestCase):

    def test_exactly_ten_digits(self):
        self.assertTrue(is_valid_job_id('4475051370'))
        for bad in (None, '', '447505137', '44750513701', '4475O51370', ' 4475051370',
                    '4475051370\n'):
            self.assertFalse(is_valid_job_id(bad), bad)


class TestExtraction(unittest.TestCase):

    def _extract(self, *cards):
        soup = BeautifulSoup(''.join(cards), 'html.parser')
        extractor = LinkedInExtractor()
        with redirect_stdout(StringIO()), \
                self.assertLogs('scraper.extractors.linkedin_extractor', 'DEBUG') as logs:
            # Guarantee at least one record so assertLogs never fails on its own
            import logging
            logging.getLogger('scraper.extractors.linkedin_extractor').debug('start')
            jobs = extractor.extract_jobs(soup, 100)
        return [j.linkedin_job_id for j in jobs], logs.output

    def test_prefers_entity_urn(self):
        ids, _ = self._extract(_card(
            href='https://ar.linkedin.com/jobs/view/dev-at-acme-4000000001',
            urn='urn:li:jobPosting:4475051370'))
        self.assertEqual(ids, ['4475051370'])

    def test_url_takes_last_number_not_title_number(self):
        # "Somewhere" spam: a number from the title is in the slug before the ID
        ids, _ = self._extract(_card(
            href='https://ar.linkedin.com/jobs/view/'
                 'java-developer-58134734372-at-somewhere-4312345678?position=1&pageNum=0',
            title='Java Developer - 58134734372'))
        self.assertEqual(ids, ['4312345678'])

    def test_url_without_slug(self):
        ids, _ = self._extract(_card(href='https://www.linkedin.com/jobs/view/4312345678/'))
        self.assertEqual(ids, ['4312345678'])

    def test_invalid_ids_are_skipped_and_logged(self):
        ids, logs = self._extract(
            _card(urn='urn:li:jobPosting:58134734372', title='Spam 11 digits'),
            _card(href='https://ar.linkedin.com/jobs/view/dev-at-acme-12345', title='Short'),
            _card(title='No link at all'),
            _card(urn='urn:li:jobPosting:4475051370', title='Good'),
        )
        self.assertEqual(ids, ['4475051370'])
        warnings = [line for line in logs if line.startswith('WARNING')]
        self.assertEqual(len(warnings), 3)
        self.assertIn('Spam 11 digits', warnings[0])
        self.assertIn('/jobs/view/dev-at-acme-12345', warnings[1])

    def test_card_count_includes_skipped_cards(self):
        soup = BeautifulSoup(_card(title='No ID') + _card(urn='urn:li:jobPosting:4475051370'),
                             'html.parser')
        extractor = LinkedInExtractor()
        with redirect_stdout(StringIO()), self.assertLogs(level='WARNING'):
            jobs = extractor.extract_jobs(soup, 100)
        self.assertEqual((extractor.last_card_count, len(jobs)), (2, 1))


if __name__ == '__main__':
    unittest.main()
