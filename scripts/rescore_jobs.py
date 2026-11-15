"""Re-score stored job descriptions with the current keyword config.

Recomputes total_matches, weighted_score, matched_keywords, match_percentage
and scoring_version from job_posts.description, without fetching any page.
Only rows with a description are touched (failed/closed fetches have nothing
to score). By default it skips rows already scored with the current
scoring_version, so it's safe to re-run.

Usage:
    python -m scripts.rescore_jobs [--all] [--limit N] [--dry-run]
"""
import argparse
import logging
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.keyword_settings import DEFAULT_KEYWORDS, WEIGHTED_KEYWORDS  # noqa: E402
from scraper.analyzers.keyword_analyzer import KeywordAnalyzer  # noqa: E402
from scraper.models.keyword_config import KeywordConfig  # noqa: E402
from scraper.models.match_result import MatchResult  # noqa: E402
from utils.sqlite_storage import SQLiteStorage  # noqa: E402

logger = logging.getLogger(__name__)

BATCH_SIZE = 500


def default_keyword_config():
    """The keyword config analyze_keywords() uses by default."""
    return KeywordConfig(keywords=list(DEFAULT_KEYWORDS), weights=dict(WEIGHTED_KEYWORDS))


def _selection(version, rescore_all):
    """WHERE clause + params for rows to re-score."""
    where = "description IS NOT NULL"
    params = []
    if not rescore_all:
        where += " AND (scoring_version IS NULL OR scoring_version != ?)"
        params.append(version)
    return where, params


def count_pending(db_file, version, rescore_all=False):
    """Number of rows that would be re-scored."""
    where, params = _selection(version, rescore_all)
    conn = sqlite3.connect(db_file)
    count = conn.execute(f"SELECT COUNT(*) FROM job_posts WHERE {where}", params).fetchone()[0]
    conn.close()
    return count


def rescore(db_file, keyword_config, rescore_all=False, limit=None, batch_size=BATCH_SIZE):
    """Re-score rows in batches (one transaction each), oldest rowid first.

    Returns (rescored, changed): rows updated, and how many of them got a
    different weighted_score.
    """
    version = keyword_config.scoring_version()
    analyzer = KeywordAnalyzer(keyword_config)
    where, params = _selection(version, rescore_all)
    rescored = changed = 0
    last_rowid = 0

    conn = sqlite3.connect(db_file, timeout=30)
    try:
        while limit is None or rescored < limit:
            size = batch_size if limit is None else min(batch_size, limit - rescored)
            rows = conn.execute(
                f"SELECT rowid, linkedin_job_id, description, weighted_score"
                f" FROM job_posts WHERE {where} AND rowid > ?"
                f" ORDER BY rowid LIMIT ?",
                params + [last_rowid, size]).fetchall()
            if not rows:
                break

            updates = []
            for rowid, job_id, description, old_score in rows:
                result = MatchResult(linkedin_job_id=job_id)
                result.keyword_matches = analyzer.analyze(description)
                result.calculate_score(keyword_config)
                if old_score is None or abs(result.weighted_score - old_score) > 1e-9:
                    changed += 1
                updates.append((
                    result.total_matches, result.weighted_score,
                    ','.join(result.matched_keywords), result.match_percentage,
                    result.scoring_version, rowid))
                last_rowid = rowid

            with conn:
                conn.executemany(
                    "UPDATE job_posts SET total_matches = ?, weighted_score = ?,"
                    " matched_keywords = ?, match_percentage = ?, scoring_version = ?"
                    " WHERE rowid = ?", updates)
            rescored += len(rows)
            logger.info("Re-scored %d rows (%d with a new score)", rescored, changed)
    finally:
        conn.close()
    return rescored, changed


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Re-score stored jobs with the current keyword config (no fetching).")
    parser.add_argument('--all', action='store_true', dest='rescore_all',
                        help="also re-score rows already on the current scoring_version")
    parser.add_argument('--limit', type=int, default=None,
                        help="maximum rows to re-score (default: no limit)")
    parser.add_argument('--dry-run', action='store_true',
                        help="print how many rows would be re-scored and exit")
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    return args


def main(argv=None, db_file=None, keyword_config=None):
    """Run the re-score; returns the process exit code."""
    args = _parse_args(argv)
    storage = SQLiteStorage(db_file)  # Applies migrations (scoring_version column)
    keyword_config = keyword_config or default_keyword_config()
    version = keyword_config.scoring_version()

    pending = count_pending(storage.db_file, version, args.rescore_all)
    if args.limit is not None:
        pending = min(pending, args.limit)
    if args.dry_run:
        print(f"Dry run: {pending} jobs would be re-scored (scoring_version {version})")
        return 0

    logger.info("Re-scoring %d jobs with scoring_version %s", pending, version)
    rescored, changed = rescore(storage.db_file, keyword_config,
                                args.rescore_all, args.limit)
    logger.info("Summary: rescored=%d / score_changed=%d / scoring_version=%s",
                rescored, changed, version)
    return 0


if __name__ == '__main__':
    from main import setup_logging
    setup_logging()
    sys.exit(main())
