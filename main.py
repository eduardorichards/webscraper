"""
Main entry point for the Job Scraper application
"""

from scraper import JobScraper, SearchConfig


def main():
    """Main function to run job scraping"""
    
    scraper = JobScraper()
    
    print("🎯 JOB SCRAPER STARTED")
    print("="*50)
    
    search_config = SearchConfig(
        keywords='python',           
        location='Latin america',   
        time_posted='24h',                 
        remote=True,                     
        experience_levels=[2],         
        max_results=100    
    )
    
    jobs = scraper.search_jobs(search_config, save_results=True)
    
    if jobs:
        scraper.display_results(jobs)
    else:
        print("No jobs found or connection failed")

def search_without_saving():
    """Example: Search without saving results (for testing)"""
    print("\nTESTING MODE - NO STORAGE")
    print("="*40)
    
    scraper = JobScraper()
    
    test_config = SearchConfig(
        keywords='java test',
        location='Argentina',
        experience_levels=[2, 3],
        max_results=5
    )
    
    jobs = scraper.search_jobs(test_config, save_results=False)
    
    print(f"Test search found {len(jobs)} jobs (not saved)")
    
def multiple_search():
    """Run multiple predefined searches"""
    from config.settings import SEARCH_TEMPLATES
    
    scraper = JobScraper()
    total_jobs_found = 0
    
    print("🚀 STARTING BATCH SEARCH")
    print("="*50)
    
    for i, template in enumerate(SEARCH_TEMPLATES, 1):
        search_name = template.pop("name", f"Search {i}")
        print(f"\n📋 Search {i}/{len(SEARCH_TEMPLATES)}: {search_name}")
        print("-" * 40)
        
        search_config = SearchConfig(**template)
        jobs = scraper.search_jobs(search_config, save_results=True)
        total_jobs_found += len(jobs)
        
        print(f"📊 Found {len(jobs)} jobs in this search")
    
    # Show final statistics
    print(f"\n{'='*50}")
    print(f"🎯 BATCH SEARCH COMPLETE")
    print(f"{'='*50}")
    print(f"📊 Total jobs found: {total_jobs_found}")
    print(f"📁 Database file: data/jobs_master.db")
    
    # Show DB statistics
    stats = scraper.sqlite_storage.get_stats()
    if stats:
        print(f"\n📈 SQLite DATABASE STATS:")
        print(f"   Total unique jobs: {stats['total_jobs']}")
        print(f"   Unique companies: {stats['unique_companies']}")
        print(f"   Unique locations: {stats['unique_locations']}")
    
def parse_html():
        from bs4 import BeautifulSoup
        import requests
        
        import os
        
        url = 'https://www.linkedin.com/jobs/search/?keywords=Java&location=Argentina&geoId=100446943&f_E=2&f_TPR=r604800'
        
        page = requests.get(url)
        
        soup = BeautifulSoup(page.text, 'html')
        
        soup = soup.prettify()
        
        os.makedirs
        
        with open('data/linkedin_page.html', 'w', encoding='utf-8') as f:
            f.write(soup)
        

if __name__ == "__main__":
    multiple_search()
