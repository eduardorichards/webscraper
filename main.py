"""
Main entry point for the Job Scraper application
"""

from scraper import JobScraper, SearchConfig
from scraper.models.keyword_config import KeywordConfig
from scraper.core.keyword_matcher import KeywordMatcher
from utils.sqlite_storage import SQLiteStorage


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

def analyze_keywords(keywords=None, weights=None, skip_analyzed=True, top_n=20):
    """
    Analyze stored jobs for keyword matches.

    Args:
        keywords: List of keywords to search for (uses defaults if None)
        weights: Optional dict of keyword weights
        skip_analyzed: Skip jobs already analyzed with these keywords
        top_n: Number of top results to display
    """
    from config.keyword_settings import DEFAULT_KEYWORDS, WEIGHTED_KEYWORDS

    # Use provided keywords or defaults
    if keywords is None:
        keywords = DEFAULT_KEYWORDS
    if weights is None:
        weights = WEIGHTED_KEYWORDS

    print("🔍 KEYWORD ANALYSIS")
    print("=" * 50)

    # Create keyword config
    keyword_config = KeywordConfig(
        keywords=keywords,
        weights=weights
    )

    # Initialize storage and matcher
    storage = SQLiteStorage()
    matcher = KeywordMatcher(storage, keyword_config)

    # Run analysis
    results = matcher.analyze_jobs(skip_analyzed=skip_analyzed)

    # Display results
    if results:
        matcher.display_results(results, top_n=top_n)

        # Show statistics
        stats = storage.get_analysis_stats()
        print(f"\n📈 ANALYSIS STATISTICS:")
        print(f"   Total analyzed: {stats['total_analyzed']}")
        print(f"   Average score: {stats['avg_score']:.1f}")
        print(f"   Max score: {stats['max_score']:.1f}")
        print(f"   Average match %: {stats['avg_match_pct']:.1f}%")
    else:
        print("No jobs to analyze. Run multiple_search() first to collect jobs.")

    return results


if __name__ == "__main__":
    # Run batch job search
    multiple_search()

    # OR analyze existing jobs for keywords
    analyze_keywords()
