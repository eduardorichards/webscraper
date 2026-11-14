"""Scraper for LinkedIn job detail pages with anti-detection measures."""
import requests
from bs4 import BeautifulSoup
import time
import random
import re

from config.keyword_settings import USER_AGENTS
from config.env import (
    SCRAPE_MIN_DELAY,
    SCRAPE_MAX_DELAY,
    BATCH_SIZE,
    BATCH_PAUSE,
    RETRY_DELAY,
    MAX_RETRIES,
)


# Logged-out LinkedIn shows bounds instead of exact counts for very low and
# very high numbers. Spanish variants cover pages served in es-* locales.
_UNDER_MARKERS = ('first', 'primer')
_OVER_MARKERS = ('over', 'más de', 'mas de')


def parse_applicant_text(text):
    """Parse LinkedIn's applicant caption into (count, qualifier).

      "Be among the first 25 applicants" → (25, 'under')   fewer than 25
      "Over 200 applicants"              → (200, 'over')   more than 200
      "101 applicants" / "1,234 ..."     → (101, None)     exact

    Returns (None, None) if the text has no number.
    """
    if not text:
        return None, None
    text = text.lower()
    match = re.search(r'\d[\d,.]*', text)
    if not match:
        return None, None
    count = int(re.sub(r'[,.]', '', match.group(0)))

    if any(marker in text for marker in _UNDER_MARKERS):
        return count, 'under'
    if any(marker in text for marker in _OVER_MARKERS):
        return count, 'over'
    return count, None


class DetailScraper:
    """Scrapes job detail pages using requests with anti-detection measures."""

    def __init__(self, min_delay=None, max_delay=None, batch_size=None, batch_pause=None):
        """
        Initialize the detail scraper.

        Args:
            min_delay: Minimum delay between requests (default from config)
            max_delay: Maximum delay between requests (default from config)
            batch_size: Number of jobs per batch before pause (default from config)
            batch_pause: Seconds to pause between batches (default from config)
        """
        self.min_delay = min_delay or SCRAPE_MIN_DELAY
        self.max_delay = max_delay or SCRAPE_MAX_DELAY
        self.batch_size = batch_size or BATCH_SIZE
        self.batch_pause = batch_pause or BATCH_PAUSE
        self.request_count = 0

    def _get_headers(self):
        """Get request headers with rotated user agent."""
        return {
            'User-Agent': random.choice(USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
        }

    def scrape_job_details(self, job_url, retry_count=0):
        """
        Scrape full details from a LinkedIn job page.

        Args:
            job_url: URL of the job posting
            retry_count: Current retry attempt (internal use)

        Returns:
            dict with job details or None if failed
        """
        try:
            response = requests.get(
                job_url,
                headers=self._get_headers(),
                timeout=15
            )

            # Handle rate limiting
            if response.status_code == 429:
                if retry_count < MAX_RETRIES:
                    print(f"  ⚠️ Rate limited. Waiting {RETRY_DELAY}s before retry {retry_count + 1}/{MAX_RETRIES}...")
                    time.sleep(RETRY_DELAY)
                    return self.scrape_job_details(job_url, retry_count + 1)
                else:
                    print(f"  ❌ Max retries reached for {job_url}")
                    return None

            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            # Extract all data
            applicant_count, applicant_count_qualifier = self._extract_applicant_count(soup)
            result = {
                'description': self._extract_description(soup),
                'applicant_count': applicant_count,
                'applicant_count_qualifier': applicant_count_qualifier,
                **self._extract_job_criteria(soup)
            }

            # Rate limiting with batch pauses
            self._apply_rate_limiting()

            return result

        except requests.exceptions.RequestException as e:
            print(f"  ❌ Error scraping {job_url}: {e}")
            return None

    def _apply_rate_limiting(self):
        """Apply rate limiting between requests."""
        self.request_count += 1

        if self.request_count % self.batch_size == 0:
            print(f"\n  ⏸️ Batch complete ({self.request_count} jobs). Pausing {self.batch_pause}s...")
            time.sleep(self.batch_pause)
        else:
            delay = random.uniform(self.min_delay, self.max_delay)
            time.sleep(delay)

    def _extract_description(self, soup):
        """Extract job description text."""
        elem = soup.select_one('div.show-more-less-html__markup')
        if elem:
            # Get text with spaces between elements
            return elem.get_text(separator=' ', strip=True)
        return None

    def _extract_applicant_count(self, soup):
        """Extract the applicant count and its qualifier.

        Returns:
            tuple (count, qualifier) as described in parse_applicant_text();
            (None, None) if the element is missing.
        """
        # Element can be <span> or <figcaption> with same class
        elem = soup.select_one('.num-applicants__caption')
        if not elem:
            return None, None
        return parse_applicant_text(elem.get_text(strip=True))

    def _extract_job_criteria(self, soup):
        """Extract seniority level, employment type, etc."""
        criteria = {
            'seniority_level': None,
            'employment_type': None,
            'job_function': None,
            'industries': None,
        }

        items = soup.select('li.description__job-criteria-item')
        for item in items:
            header = item.select_one('h3.description__job-criteria-subheader')
            value = item.select_one('span.description__job-criteria-text')

            if header and value:
                header_text = header.get_text(strip=True).lower()
                value_text = value.get_text(strip=True)

                if 'seniority' in header_text:
                    criteria['seniority_level'] = value_text
                elif 'employment' in header_text:
                    criteria['employment_type'] = value_text
                elif 'function' in header_text:
                    criteria['job_function'] = value_text
                elif 'industr' in header_text:
                    criteria['industries'] = value_text

        return criteria

    def scrape_batch(self, jobs, progress_callback=None):
        """
        Scrape details for multiple jobs.

        Args:
            jobs: List of job dicts with 'id' and 'job_url' keys
            progress_callback: Optional callback(current, total, job) for progress updates

        Returns:
            dict: {job_id: details_dict or None}
        """
        results = {}
        total = len(jobs)

        print(f"\n🔍 Starting to scrape {total} job detail pages...")
        print(f"   Estimated time: {total * (self.min_delay + self.max_delay) / 2 / 60:.1f} minutes")

        for i, job in enumerate(jobs):
            job_id = job['id']
            job_url = job['job_url']

            if progress_callback:
                progress_callback(i + 1, total, job)
            else:
                print(f"  [{i + 1}/{total}] Scraping: {job.get('title', 'Unknown')[:40]}...")

            details = self.scrape_job_details(job_url)
            results[job_id] = details

        print(f"\n✅ Completed scraping {total} jobs")
        return results
