import requests
from bs4 import BeautifulSoup
from .url_builder import LinkedInURLBuilder
from ..extractors.linkedin_extractor import LinkedInExtractor
from config.settings import DEFAULT_HEADERS
from utils.sqlite_storage import SQLiteStorage


class JobScraper:
    """Main scraper class for job search websites"""
    
    def __init__(self):
        self.url_builder = LinkedInURLBuilder()
        self.linkedin_extractor = LinkedInExtractor()
        self.headers = DEFAULT_HEADERS
        self.sqlite_storage = SQLiteStorage()
    
    def search_jobs(self, search_config, save_results=True):
        """Search for jobs based on configuration"""
        # Build URL
        search_url = self.url_builder.build_url(search_config)
        print(f"🌐 Search URL: {search_url}")
        
        # Get page content
        soup = self._get_page_content(search_url)
        if not soup:
            return []
        
        # Extract jobs
        jobs = self.linkedin_extractor.extract_jobs(soup, search_config.max_results)
        
        # Save results to SQLite database (with duplicate prevention)
        if save_results and jobs:
            try:
                self.sqlite_storage.append_jobs(jobs, search_config)
            except Exception as e:
                print(f"⚠️  Warning: Could not save results: {e}")
        
        return jobs
    
    def _get_page_content(self, url):
        """Get and parse page content"""
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            print(f"✅ Successfully connected to {url}")
            return soup
            
        except Exception as e:
            print(f"❌ Error connecting to {url}: {e}")
            return None
    
    def display_results(self, jobs):
        """Display job search results"""
        print(f"\n📊 EXTRACTION RESULTS")
        print("="*50)
        print(f"Total jobs found: {len(jobs)}")
        print()
        
        for i, job in enumerate(jobs, 1):
            print(f"--- JOB {i} ---")
            print(f"📋 Title: {job.title}")
            print(f"🏢 Company: {job.company}")
            print(f"📍 Location: {job.location}")
            print(f"📅 Posted: {job.posted_date}")
            print(f"🔗 URL: {job.job_url}")
            print("-" * 30)