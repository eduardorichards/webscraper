import logging
import random
import time

import requests
from bs4 import BeautifulSoup
from .url_builder import LinkedInURLBuilder
from ..extractors.linkedin_extractor import LinkedInExtractor
from config.env import (
    MAX_RETRIES,
    RETRY_DELAY,
    SEARCH_MAX_DELAY,
    SEARCH_MAX_PAGES,
    SEARCH_MIN_DELAY,
)
from config.settings import DEFAULT_HEADERS, SEARCH_FIRST_PAGE_SIZE, SEARCH_MORE_PAGE_SIZE
from utils.sqlite_storage import SQLiteStorage
from utils.time_utils import utc_now_iso

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15  # seconds


class JobScraper:
    """Main scraper class for job search websites"""

    def __init__(self, sqlite_storage=None, max_pages=None):
        self.url_builder = LinkedInURLBuilder()
        self.linkedin_extractor = LinkedInExtractor()
        self.headers = DEFAULT_HEADERS
        self.sqlite_storage = sqlite_storage or SQLiteStorage()
        self.max_pages = max_pages or SEARCH_MAX_PAGES
        self._reset_run_stats()

    def _reset_run_stats(self):
        """Stats of the last search_jobs() call, kept up to date page by page
        so they're still valid when a later page raises."""
        self.last_jobs_found = 0  # Jobs saved (IDs repeated across pages counted once)
        self.last_new_jobs = 0  # Of those, IDs not in job_searches before the run
        self.last_pages_fetched = 0  # Result pages fetched successfully
        self.last_hit_page_limit = False  # Stopped at max_pages with more results left

    def search_jobs(self, search_config, save_results=True, search_run_id=None,
                    raise_errors=False):
        """Search for jobs based on configuration, following result pages.

        Fetches the search page, then the "See more jobs" pages, until a page
        is shorter than a full page, brings no new job IDs, max_results is
        reached or max_pages pages were fetched. Each page is saved as soon
        as it's fetched, so a failure on a later page keeps the earlier ones.

        Args:
            search_config: SearchConfig to run
            save_results: Store results in job_searches
            search_run_id: search_runs.id to link the stored rows to
            raise_errors: Propagate fetch/save errors instead of logging them
                and returning what was found (used by the batch run tracking)

        Returns:
            list[Job] found across all pages. Run stats are in self.last_*.
        """
        self._reset_run_stats()
        all_jobs = []
        seen_ids = set()
        cards_seen = 0
        max_results = search_config.max_results

        for page in range(self.max_pages):
            if page == 0:
                url = self.url_builder.build_url(search_config)
                full_page = SEARCH_FIRST_PAGE_SIZE
            else:
                # Same delay as between search templates
                time.sleep(random.uniform(SEARCH_MIN_DELAY, SEARCH_MAX_DELAY))
                url = self.url_builder.build_see_more_url(search_config, cards_seen)
                full_page = SEARCH_MORE_PAGE_SIZE
            print(f"🌐 Search URL (page {page + 1}): {url}")

            scraped_at = utc_now_iso()
            soup = self._get_page_content(url, raise_errors=raise_errors)
            if not soup:
                break
            self.last_pages_fetched += 1

            page_jobs = self.linkedin_extractor.extract_jobs(
                soup, max_results - cards_seen)
            card_count = self.linkedin_extractor.last_card_count
            cards_seen += card_count

            # LinkedIn may repeat a job on a later page: keep the first one
            jobs = [job for job in page_jobs if job.linkedin_job_id not in seen_ids]
            if page > 0 and page_jobs and not jobs:
                logger.info("Page %d repeated earlier jobs only; stopping", page + 1)
                break
            seen_ids.update(job.linkedin_job_id for job in jobs)

            if save_results and jobs:
                try:
                    self.last_new_jobs += self.sqlite_storage.append_jobs(
                        jobs, search_config,
                        search_run_id=search_run_id, scraped_at=scraped_at)
                except Exception as e:
                    if raise_errors:
                        raise
                    print(f"⚠️  Warning: Could not save results: {e}")
            all_jobs.extend(jobs)
            self.last_jobs_found = len(all_jobs)

            if card_count < full_page or cards_seen >= max_results:
                break
            if page == self.max_pages - 1:
                self.last_hit_page_limit = True
                logger.warning(
                    "Search '%s' / '%s' hit the page limit (%d pages, %d cards): "
                    "more results were left unfetched",
                    search_config.keywords, search_config.location,
                    self.max_pages, cards_seen)

        return all_jobs

    def _get_page_content(self, url, raise_errors=False):
        """Get and parse page content, retrying after HTTP 429."""
        try:
            for attempt in range(MAX_RETRIES + 1):
                response = requests.get(url, headers=self.headers,
                                        timeout=REQUEST_TIMEOUT)
                if response.status_code != 429 or attempt == MAX_RETRIES:
                    break
                logger.warning(
                    "Rate limited (429). Waiting %ss before retry %d/%d",
                    RETRY_DELAY, attempt + 1, MAX_RETRIES)
                time.sleep(RETRY_DELAY)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')
            print(f"✅ Successfully connected to {url}")
            return soup

        except Exception as e:
            print(f"❌ Error connecting to {url}: {e}")
            if raise_errors:
                raise
            return None

    def display_results(self, jobs):
        """Display job search results"""
        print(f"\n📊 EXTRACTION RESULTS")
        print("="*50)
        print(f"Total jobs found: {len(jobs)}")
        print()

        for i, job in enumerate(jobs, 1):
            print(f"--- JOB {i} ---")
            print(f"🆔 Job ID: {job.linkedin_job_id}")
            print(f"📋 Title: {job.title}")
            print(f"🏢 Company: {job.company}")
            print(f"📍 Location: {job.location}")
            print("-" * 30)
