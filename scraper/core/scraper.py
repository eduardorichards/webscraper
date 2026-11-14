import requests
from bs4 import BeautifulSoup
from .url_builder import LinkedInURLBuilder
from ..extractors.linkedin_extractor import LinkedInExtractor
from config.settings import DEFAULT_HEADERS
from utils.sqlite_storage import SQLiteStorage
from utils.time_utils import utc_now_iso


class JobScraper:
    """Main scraper class for job search websites"""
    
    def __init__(self, sqlite_storage=None):
        self.url_builder = LinkedInURLBuilder()
        self.linkedin_extractor = LinkedInExtractor()
        self.headers = DEFAULT_HEADERS
        self.sqlite_storage = sqlite_storage or SQLiteStorage()
        self.last_new_jobs = 0  # New jobs saved by the last search_jobs() call
    
    def search_jobs(self, search_config, save_results=True, search_run_id=None,
                    raise_errors=False):
        """Search for jobs based on configuration.

        Args:
            search_config: SearchConfig to run
            save_results: Store results in job_searches
            search_run_id: search_runs.id to link the stored rows to
            raise_errors: Propagate fetch/save errors instead of logging them
                and returning what was found (used by the batch run tracking)

        Returns:
            list[Job]. The number of new jobs saved is in self.last_new_jobs.
        """
        self.last_new_jobs = 0

        # Build URL
        search_url = self.url_builder.build_url(search_config)
        print(f"🌐 Search URL: {search_url}")
        
        # Get page content
        scraped_at = utc_now_iso()
        soup = self._get_page_content(search_url, raise_errors=raise_errors)
        if not soup:
            return []
        
        # Extract jobs
        jobs = self.linkedin_extractor.extract_jobs(soup, search_config.max_results)
        
        # Save results to SQLite database
        if save_results and jobs:
            try:
                self.last_new_jobs = self.sqlite_storage.append_jobs(
                    jobs, search_config,
                    search_run_id=search_run_id, scraped_at=scraped_at)
            except Exception as e:
                if raise_errors:
                    raise
                print(f"⚠️  Warning: Could not save results: {e}")
        
        return jobs
    
    def _get_page_content(self, url, raise_errors=False):
        """Get and parse page content"""
        try:
            response = requests.get(url, headers=self.headers)
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