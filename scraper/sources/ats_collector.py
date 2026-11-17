"""Collect jobs from the ATS boards in the companies table (main.py --source ats).

Per active company: one search_runs row ("ats:<ats>:<slug>"), one board
request, the location filter, then for each kept posting not stored yet a
job_searches row and an immediate score (the description comes with the
board, so nothing is fetched per job). Jobs land in the same tables as
LinkedIn jobs, so the web UI, filters and applications work unchanged.
"""
import logging
import random
import time

from config import env
from scraper.analyzers.keyword_analyzer import KeywordAnalyzer
from scraper.models.match_result import MatchResult
from scraper.sources.ats_client import AtsError, fetch_board
from utils.location_filter import check_location
from utils.time_utils import utc_now_iso

logger = logging.getLogger(__name__)


def score_job(job, keyword_config, analyzer=None, now=None):
    """MatchResult for an ATS posting, scored like KeywordMatcher scores
    LinkedIn jobs (same analyzer and calculate_score)."""
    analyzer = analyzer or KeywordAnalyzer(keyword_config)
    now = now or utc_now_iso()
    result = MatchResult(linkedin_job_id=job.key, source_url=job.job_url)
    result.date_time = now
    result.scraped_at = now
    result.description = job.description or None
    result.employment_type = job.employment_type
    result.apply_type = 'external'
    result.apply_url = job.apply_url or job.job_url
    result.posted_at = job.posted_at
    if result.description:
        result.keyword_matches = analyzer.analyze(result.description)
        result.calculate_score(keyword_config)
    else:
        # Nothing scored: NULL scoring_version, like a failed LinkedIn fetch
        result.keyword_matches = {kw: 0 for kw in keyword_config.keywords}
    return result


def collect_company(storage, company, keyword_config, analyzer=None, session=None):
    """Read one company's board and store/score its new kept postings.

    Records a search run and the company's last_checked_at / last_job_count
    whatever happens. Returns a stats dict (status, found, kept, dropped,
    new, existing, aggregator).
    """
    analyzer = analyzer or KeywordAnalyzer(keyword_config)
    name, ats, slug = company['name'], company['ats'], company['slug']
    stats = dict(status='ok', found=0, kept=0, dropped=0, new=0, existing=0,
                 aggregator=0)
    run_id = storage.start_search_run("ats:%s:%s" % (ats, slug), "ats", slug)
    try:
        jobs = fetch_board(company, session=session)
        stats['found'] = len(jobs)
        if not jobs:
            logger.info("%s (%s:%s): no jobs (empty board or unconfirmed slug)",
                        name, ats, slug)

        aggregator = storage.is_aggregator(name)
        scraped_at = utc_now_iso()
        for job in jobs:
            keep, reason = check_location(job.locations, job.description, job.remote)
            if not keep:
                stats['dropped'] += 1
                logger.debug("Dropped %s (%s): %s [%s]", job.key, job.title,
                             reason, job.location_raw)
                continue
            stats['kept'] += 1
            if storage.job_key_exists(job.key):
                stats['existing'] += 1
                continue
            storage.add_ats_job(job, search_run_id=run_id, scraped_at=scraped_at)
            stats['new'] += 1
            if aggregator:
                # Like LinkedIn: aggregator jobs are stored but never scored,
                # so they get no job_posts row
                stats['aggregator'] += 1
                continue
            storage.save_job_analysis(score_job(job, keyword_config, analyzer))
    except Exception as e:
        # AtsError (HTTP/timeout/payload) or a storage failure: record it and
        # let the caller move on to the next company
        stats['status'] = 'error'
        message = str(e) or type(e).__name__
        if isinstance(e, AtsError):
            logger.warning("%s (%s:%s): %s", name, ats, slug, message)
        else:
            logger.exception("%s (%s:%s) failed", name, ats, slug)
        storage.finish_search_run(run_id, jobs_found=stats['found'],
                                  new_jobs=stats['new'], status='error',
                                  error=message, pages_fetched=1)
    else:
        storage.finish_search_run(run_id, jobs_found=stats['found'],
                                  new_jobs=stats['new'], status='ok',
                                  pages_fetched=1)
        logger.info("%s (%s:%s): %d postings, kept %d, dropped %d by location,"
                    " %d new (%d already stored)", name, ats, slug, stats['found'],
                    stats['kept'], stats['dropped'], stats['new'], stats['existing'])
    storage.mark_company_checked(name, stats['found'])
    return stats


def collect_ats(storage, keyword_config, companies=None, session=None,
                sleep=time.sleep):
    """Read every active company's board, waiting ATS_MIN/MAX_DELAY between
    companies. Returns the per-company stats {name: stats}."""
    if companies is None:
        companies = storage.get_companies(active_only=True)
    analyzer = KeywordAnalyzer(keyword_config)
    logger.info("STARTING ATS COLLECTION (%d companies)", len(companies))
    results = {}
    for i, company in enumerate(companies):
        if i:
            sleep(random.uniform(env.ATS_MIN_DELAY, env.ATS_MAX_DELAY))
        results[company['name']] = collect_company(
            storage, company, keyword_config, analyzer=analyzer, session=session)

    errors = [name for name, s in results.items() if s['status'] == 'error']
    logger.info("ATS COLLECTION COMPLETE - %d new jobs, %d kept, %d dropped by"
                " location, %d board error(s)%s",
                sum(s['new'] for s in results.values()),
                sum(s['kept'] for s in results.values()),
                sum(s['dropped'] for s in results.values()),
                len(errors), (": " + ", ".join(errors)) if errors else "")
    return results
