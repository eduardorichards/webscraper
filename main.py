"""
Main entry point for the Job Scraper application
"""

from scraper import JobScraper, SearchConfig


def main():
    """Main function to run job scraping"""
    
    # Create scraper instance
    scraper = JobScraper()
    
    # Show available experience levels (helpful reference)
    print("🎯 JOB SCRAPER STARTED")
    print("="*50)
    scraper.url_builder.get_experience_level_info()
    
    # Define search configuration with experience levels
    search_config = SearchConfig(
        keywords='python',           # Multi-word keywords work now
        location='Latin america',    # Your location
        time_posted='24h',                  # Recent jobs only
        remote=True,                       # Any location type
        experience_levels=[2],           # Entry level + Associate (junior roles)
        max_results=100           # Number of jobs to extract
    )
    
    # Validate configuration
    is_valid, message = search_config.is_valid()
    if not is_valid:
        print(f"❌ Invalid configuration: {message}")
        return
    
    print(f"🔍 Searching for jobs with: {search_config}")
    print()
    
    # Search for jobs
    jobs = scraper.search_jobs(search_config)
    
    # Display results
    if jobs:
        scraper.display_results(jobs)
    else:
        print("❌ No jobs found or connection failed")


def example_searches():
    """Show different search configuration examples"""
    
    print("\n💡 EXAMPLE SEARCH CONFIGURATIONS:")
    print("="*50)
    
    examples = [
        {
            'name': '🎓 Junior Java Developer',
            'config': SearchConfig(
                keywords='java junior',
                location='Argentina',
                experience_levels=[1, 2],  # Internship + Entry level
                time_posted='1w',
                max_results=20
            )
        },
        {
            'name': '🚀 Senior Full-Stack Remote',
            'config': SearchConfig(
                keywords='full stack javascript',
                location='',  # Any location
                experience_levels=[4, 5],  # Mid-Senior + Director
                remote=True,
                time_posted='24h',
                max_results=10
            )
        },
        {
            'name': '💼 Mid-Level Python Buenos Aires',
            'config': SearchConfig(
                keywords='python django',
                location='Buenos Aires',
                experience_levels=[3, 4],  # Associate + Mid-Senior
                time_posted='1w',
                max_results=25
            )
        },
        {
            'name': '📈 All Levels React Developer',
            'config': SearchConfig(
                keywords='react typescript',
                location='Remote',
                experience_levels=[2, 3, 4],  # Entry to Mid-Senior
                remote=True,
                time_posted='1m',
                max_results=30
            )
        }
    ]
    
    for example in examples:
        print(f"\n{example['name']}")
        print(f"   Keywords: {example['config'].keywords}")
        print(f"   Location: {example['config'].location or 'Any'}")
        print(f"   Experience: {example['config'].experience_levels}")
        print(f"   Remote: {example['config'].remote}")
        print(f"   Time: {example['config'].time_posted}")


if __name__ == "__main__":
    # Run main search
    main()
    
    # Optionally show examples (uncomment to see)
    # example_searches()