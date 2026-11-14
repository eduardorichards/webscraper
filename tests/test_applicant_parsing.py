"""Tests for LinkedIn applicant caption parsing (no network)."""

import unittest

from bs4 import BeautifulSoup

from scraper.core.detail_scraper import DetailScraper, parse_applicant_text


class TestParseApplicantText(unittest.TestCase):

    def test_variants(self):
        cases = [
            # Under: logged-out LinkedIn hides low counts
            ("Be among the first 25 applicants", (25, 'under')),
            ("BE AMONG THE FIRST 25 APPLICANTS", (25, 'under')),
            ("Be among the first 10 applicants", (10, 'under')),
            ("Sé de los primeros 25 solicitantes", (25, 'under')),
            # Over: high counts are capped
            ("Over 200 applicants", (200, 'over')),
            ("Más de 200 solicitantes", (200, 'over')),
            # Exact
            ("101 applicants", (101, None)),
            ("1 applicant", (1, None)),
            ("1,234 applicants", (1234, None)),
            ("25 applicants", (25, None)),
            ("57 solicitudes", (57, None)),
            # Unparseable
            ("", (None, None)),
            (None, (None, None)),
            ("No applicants yet", (None, None)),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(parse_applicant_text(text), expected)


class TestExtractApplicantCount(unittest.TestCase):

    def _extract(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        return DetailScraper()._extract_applicant_count(soup)

    def test_span_caption(self):
        html = ('<span class="num-applicants__caption topcard__flavor--metadata">'
                '\n  Over 200 applicants\n</span>')
        self.assertEqual(self._extract(html), (200, 'over'))

    def test_figcaption_caption(self):
        html = ('<figcaption class="num-applicants__caption">'
                'Be among the first 25 applicants</figcaption>')
        self.assertEqual(self._extract(html), (25, 'under'))

    def test_missing_element(self):
        self.assertEqual(self._extract('<div>nothing here</div>'), (None, None))


if __name__ == '__main__':
    unittest.main()
