"""Tests for job criteria parsing (seniority, employment type, industries, job function)."""

import unittest
from pathlib import Path

from bs4 import BeautifulSoup

from scraper.core.detail_scraper import DetailScraper

FIXTURES = Path(__file__).parent / 'fixtures'


def _criteria(html):
    return DetailScraper()._extract_job_criteria(BeautifulSoup(html, 'html.parser'))


class TestJobCriteria(unittest.TestCase):

    def test_current_page_has_no_job_function(self):
        # Since ~2026-10-01 logged-out job pages list only these three items
        criteria = _criteria((FIXTURES / 'job_criteria.html').read_text(encoding='utf-8'))
        self.assertEqual(criteria, {
            'seniority_level': 'Mid-Senior level',
            'employment_type': 'Full-time',
            'job_function': None,
            'industries': 'Staffing and Recruiting',
        })

    def test_job_function_still_parsed_when_present(self):
        criteria = _criteria("""
        <ul class="description__job-criteria-list">
          <li class="description__job-criteria-item">
            <h3 class="description__job-criteria-subheader">Job function</h3>
            <span class="description__job-criteria-text">Engineering and Information Technology</span>
          </li>
        </ul>""")
        self.assertEqual(criteria['job_function'], 'Engineering and Information Technology')


if __name__ == '__main__':
    unittest.main()
