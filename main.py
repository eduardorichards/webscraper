"""
Main entry point for the Job Scraper application
"""

import logging
import time
import random
from logging.handlers import RotatingFileHandler

from config.env import LOG_DIR, LOG_LEVEL, SEARCH_MIN_DELAY, SEARCH_MAX_DELAY
from scraper import JobScraper, SearchConfig
from scraper.models.keyword_config import KeywordConfig
from scraper.core.keyword_matcher import KeywordMatcher
from utils.sqlite_storage import SQLiteStorage
from utils.time_utils import utc_now_iso


def setup_logging():
    """Configure logging with rotating file handler."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    log_file = LOG_DIR / "scraper.log"

    handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=7
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )

    logger = logging.getLogger()
    logger.setLevel(LOG_LEVEL)
    logger.addHandler(handler)

    # Also log to stdout
    stdout_handler = logging.StreamHandler()
    stdout_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )
    logger.addHandler(stdout_handler)

    return logger


def multiple_search(templates=None, scraper=None):
    """Run multiple predefined searches, recording one search_runs row each.

    Args:
        templates: Search template dicts (default: SEARCH_TEMPLATES)
        scraper: JobScraper to use (default: a new one on the configured DB)
    """
    if templates is None:
        from config.settings import SEARCH_TEMPLATES
        templates = SEARCH_TEMPLATES

    logger = logging.getLogger()
    if scraper is None:
        scraper = JobScraper()
    storage = scraper.sqlite_storage
    total_jobs_found = 0

    logger.info("STARTING BATCH SEARCH")
    print("="*50)

    for i, template in enumerate(templates, 1):
        params = dict(template)  # Don't mutate the shared template
        search_name = params.pop("name", f"Search {i}")
        logger.info(f"Search {i}/{len(templates)}: {search_name}")
        print("-" * 40)

        run_id = storage.start_search_run(
            search_name, params.get("keywords"), params.get("location"))
        try:
            search_config = SearchConfig(**params)
            scraper.search_jobs(
                search_config, save_results=True,
                search_run_id=run_id, raise_errors=True)
        except Exception as e:
            logger.error(f"Search '{search_name}' failed: {e}")
            # Pages saved before the failure stay in job_searches
            storage.finish_search_run(
                run_id, jobs_found=scraper.last_jobs_found,
                new_jobs=scraper.last_new_jobs,
                status='error', error=str(e) or type(e).__name__,
                pages_fetched=scraper.last_pages_fetched,
                hit_page_limit=scraper.last_hit_page_limit)
        else:
            total_jobs_found += scraper.last_jobs_found
            storage.finish_search_run(
                run_id, jobs_found=scraper.last_jobs_found,
                new_jobs=scraper.last_new_jobs, status='ok',
                pages_fetched=scraper.last_pages_fetched,
                hit_page_limit=scraper.last_hit_page_limit)
            logger.info(
                f"Found {scraper.last_jobs_found} jobs ({scraper.last_new_jobs} new) "
                f"in {scraper.last_pages_fetched} page(s) in search '{search_name}'")

        # Random delay between searches to avoid rate limiting
        if i < len(templates):
            delay = random.uniform(SEARCH_MIN_DELAY, SEARCH_MAX_DELAY)
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


def analyze_keywords(keywords=None, weights=None, skip_analyzed=True, top_n=20,
                     since=None):
    """
    Analyze stored jobs for keyword matches.

    Jobs from aggregator companies are not fetched (see KeywordMatcher).

    Args:
        keywords: List of keywords to search for (uses defaults if None)
        weights: Optional dict of keyword weights
        skip_analyzed: Skip jobs already analyzed with these keywords
        top_n: Number of top results to display
        since: UTC ISO timestamp; the skipped aggregator fetches logged are
            those first seen at or after it (default: all pending ones)
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
    results = matcher.analyze_jobs(skip_analyzed=skip_analyzed, since=since)

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
        run_started_at = utc_now_iso()

        # Run batch job search
        multiple_search()

        # Analyze existing jobs for keywords
        analyze_keywords(since=run_started_at)
    except Exception:
        logger.exception("Scraper failed with an error")
        raise
