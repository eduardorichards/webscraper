"""
Main entry point for the Job Scraper application
"""

import logging
import os
import time
import random
from logging.handlers import RotatingFileHandler

from scraper import JobScraper, SearchConfig
from scraper.models.keyword_config import KeywordConfig
from scraper.core.keyword_matcher import KeywordMatcher
from utils.sqlite_storage import SQLiteStorage


def setup_logging():
    """Configure logging with rotating file handler."""
    log_dir = os.path.join(os.path.dirname(__file__), "data", "logs")
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, "scraper.log")

    handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=7
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    # Also log to stdout
    stdout_handler = logging.StreamHandler()
    stdout_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )
    logger.addHandler(stdout_handler)

    return logger


def multiple_search():
    """Run multiple predefined searches"""
    from config.settings import SEARCH_TEMPLATES

    logger = logging.getLogger()
    scraper = JobScraper()
    total_jobs_found = 0

    logger.info("STARTING BATCH SEARCH")
    print("="*50)

    for i, template in enumerate(SEARCH_TEMPLATES, 1):
        search_name = template.pop("name", f"Search {i}")
        logger.info(f"Search {i}/{len(SEARCH_TEMPLATES)}: {search_name}")
        print("-" * 40)

        search_config = SearchConfig(**template)
        jobs = scraper.search_jobs(search_config, save_results=True)
        total_jobs_found += len(jobs)

        logger.info(f"Found {len(jobs)} jobs in search '{search_name}'")

        # Random delay between searches to avoid rate limiting
        if i < len(SEARCH_TEMPLATES):
            delay = random.uniform(2, 4)
            logger.info(f"Waiting {delay:.1f}s before next search...")
            time.sleep(delay)

    # Show final statistics
    logger.info(f"BATCH SEARCH COMPLETE - Total jobs found: {total_jobs_found}")

    # Show DB statistics
    stats = scraper.sqlite_storage.get_stats()
    if stats:
        logger.info(
            f"DB stats - Total: {stats['total_jobs']}, "
            f"Companies: {stats['unique_companies']}, "
            f"Locations: {stats['unique_locations']}"
        )


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

    logger = logging.getLogger()

    # Use provided keywords or defaults
    if keywords is None:
        keywords = DEFAULT_KEYWORDS
    if weights is None:
        weights = WEIGHTED_KEYWORDS

    logger.info("KEYWORD ANALYSIS")
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
        logger.info(
            f"Analysis stats - Analyzed: {stats['total_analyzed']}, "
            f"Avg score: {stats['avg_score']:.1f}, "
            f"Max score: {stats['max_score']:.1f}"
        )
    else:
        logger.info("No jobs to analyze. Run multiple_search() first to collect jobs.")

    return results


if __name__ == "__main__":
    setup_logging()
    logger = logging.getLogger()

    try:
        # Run batch job search
        multiple_search()

        # Analyze existing jobs for keywords
        analyze_keywords()
    except Exception:
        logger.exception("Scraper failed with an error")
        raise
