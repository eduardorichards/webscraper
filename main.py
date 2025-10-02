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

if __name__ == "__main__":
    main()
