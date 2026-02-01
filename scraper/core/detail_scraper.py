"""Scraper for LinkedIn job detail pages with anti-detection measures."""
import requests
from bs4 import BeautifulSoup
import time
import random
import re

from config.keyword_settings import (
    USER_AGENTS,
    SCRAPE_MIN_DELAY,
    SCRAPE_MAX_DELAY,
    BATCH_SIZE,
    BATCH_PAUSE,
    RETRY_DELAY,
    MAX_RETRIES,
)


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
            result = {
                'description': self._extract_description(soup),
                'applicant_count': self._extract_applicant_count(soup),
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
        """Extract number of applicants."""
        elem = soup.select_one('span.num-applicants__caption')
        if not elem:
            return None

        text = elem.get_text(strip=True)
        # Extract number from "176 applicants" or "Over 200 applicants"
        match = re.search(r'(\d+)', text.replace(',', ''))
        return int(match.group(1)) if match else None

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
