import requests
from bs4 import BeautifulSoup
import pandas as pd
from utils.helpers import save_to_csv, clean_text
import time

class Jobscraper:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.jobs = []
        
    def test_connection(self, url):
        """Test basic web scraping connection"""
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            print(f"✅ Connection successful to {url}")
            print(f"Page title: {soup.title.string if soup.title else 'No title found'}")
            
            return soup
        
        except Exception as e:
            print(f"❌ Error connecting to {url}: {e}")
            return None
        
    def explore_page_structure(self, soup):
        """Exploring HTML structure tu find job listings"""
        if not soup:
            return
        
        print("\n🔍 Exploring page structure...")
        
        job_containers = soup.find_all(['div', 'article', 'li'], class_=lambda x: x and ('job' in x.lower() or 'aviso' in x.lower() or 'listing' in x.lower()))
        
        print(f"Found {len(job_containers)} potential job containers")
        
        for i, container in enumerate(job_containers[:3]):
            print(f"\n--- Container {i+1} ---")
            print(container.get('class'))
            print(container.text[:200] + "..." if len(container.text) > 200 else container.text)

        
if __name__ == "__main__":
    scraper = Jobscraper()
    
    
    test_url = "https://www.linkedin.com/jobs/search/?currentJobId=4302641864&keywords=java&origin=JOBS_HOME_SEARCH_BUTTON"
    soup = scraper.test_connection(test_url)    
