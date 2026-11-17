"""One-off backfill of job_posts.apply_type / apply_url for recently analyzed jobs.

Re-fetches the job page of rows with apply_type IS NULL (newest first) using
DetailScraper (same headers, delays, batch pauses and 429 retries) and updates
only apply_type / apply_url. Closed jobs, pages without a marker and failed
fetches stay NULL, so a later run picks them up again.

Takes the same lock as run_scraper.sh (LOG_DIR/scraper.lock), so it never runs
at the same time as the hourly scraper (which skips its run while this holds it).

Usage:
    python -m scripts.backfill_apply_type [--since 3d] [--min-score 0]
                                          [--limit 300] [--dry-run]
"""
import argparse
import logging
import os
import re
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.env import LOG_DIR  # noqa: E402
from scraper.core.detail_scraper import DetailScraper  # noqa: E402
from utils.job_keys import job_url_for  # noqa: E402
from utils.sqlite_storage import SQLiteStorage  # noqa: E402

logger = logging.getLogger(__name__)

LOCK_FILE = LOG_DIR / "scraper.lock"
# Errors don't trigger a delay in DetailScraper; stop instead of hammering
# LinkedIn when it starts blocking us.
MAX_CONSECUTIVE_ERRORS = 5
OUTCOMES = ('easy_apply', 'external', 'closed', 'unknown', 'errors')
MIN_JOB_ID_LENGTH = 10


class LockHeld(Exception):
    """The scraper lock is held by a running process."""

    def __init__(self, pid, path):
        super().__init__(
            f"Scraper or another backfill is running (PID {pid}, lock {path}); exiting.")
        self.pid = pid


def parse_since(value):
    """'3d' / '12h' → SQLite date modifier ('-3 days' / '-12 hours')."""
    match = re.fullmatch(r'(\d+)([dh])', value.strip().lower())
    if not match or int(match.group(1)) < 1:
        raise argparse.ArgumentTypeError(
            f"invalid --since {value!r}: use <N>d or <N>h, e.g. 3d or 12h")
    unit = 'days' if match.group(2) == 'd' else 'hours'
    return f"-{int(match.group(1))} {unit}"


def _read_pid(path):
    """PID stored in the lock file, or None if missing/garbage."""
    try:
        return int(Path(path).read_text().strip())
    except (OSError, ValueError):
        return None


def _pid_alive(pid):
    if pid <= 0:  # os.kill(0, ...) would target our own process group
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # Exists, owned by another user
        return True
    return True


def acquire_lock(lock_path):
    """Create the lock with our PID, using run_scraper.sh's format.

    A lock whose PID is not running (or unreadable) is stale and replaced,
    as run_scraper.sh does. Raises LockHeld if a live process holds it.
    """
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            pid = _read_pid(lock_path)
            if pid is not None and _pid_alive(pid):
                raise LockHeld(pid, lock_path)
            logger.warning("Stale lock file %s (PID %s), removing.", lock_path, pid)
            try:
                os.remove(str(lock_path))
            except FileNotFoundError:
                pass
            continue
        with os.fdopen(fd, 'w') as f:
            f.write(f"{os.getpid()}\n")
        return
    # Someone else re-created the lock between our removal and retry
    raise LockHeld(_read_pid(lock_path), lock_path)


def release_lock(lock_path):
    """Remove the lock only if it still holds our PID."""
    if _read_pid(lock_path) == os.getpid():
        try:
            os.remove(str(lock_path))
        except FileNotFoundError:
            pass


def select_jobs(db_file, since='-3 days', min_score=0, limit=300):
    """Rows still missing apply_type, analyzed within `since`, newest first.

    LinkedIn IDs only: the numeric-ID check leaves out ATS keys
    ('lever:<slug>:<id>'), which are saved with apply_type 'external' anyway.
    """
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT linkedin_job_id, date_time, weighted_score
        FROM job_posts
        WHERE apply_type IS NULL
          AND date_time >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ?)
          AND weighted_score >= ?
          AND length(linkedin_job_id) >= ?
          AND linkedin_job_id NOT GLOB '*[^0-9]*'
        ORDER BY date_time DESC, linkedin_job_id DESC
        LIMIT ?
    """, (since, min_score, MIN_JOB_ID_LENGTH, int(limit))).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_apply_type(db_file, linkedin_job_id, apply_type, apply_url):
    """Set apply_type / apply_url unless another writer already set them."""
    conn = sqlite3.connect(str(db_file))
    conn.execute("""
        UPDATE job_posts SET apply_type = ?, apply_url = ?
        WHERE linkedin_job_id = ? AND apply_type IS NULL
    """, (apply_type, apply_url, linkedin_job_id))
    conn.commit()
    conn.close()


def backfill(db_file, jobs, scraper=None):
    """Fetch each job page and store its apply type.

    Returns (counts, completed): counts per outcome in OUTCOMES, and False if
    the run stopped after MAX_CONSECUTIVE_ERRORS failed fetches in a row.
    """
    scraper = scraper or DetailScraper()
    counts = dict.fromkeys(OUTCOMES, 0)
    consecutive_errors = 0

    for i, job in enumerate(jobs, 1):
        job_id = job['linkedin_job_id']
        details = scraper.scrape_job_details(job_url_for(job_id))

        if details is None:
            outcome = 'errors'
            consecutive_errors += 1
        else:
            consecutive_errors = 0
            apply_type = details.get('apply_type')
            if details.get('closed'):
                outcome = 'closed'
            elif apply_type in ('easy_apply', 'external'):
                outcome = apply_type
                update_apply_type(db_file, job_id, apply_type, details.get('apply_url'))
            else:
                outcome = 'unknown'

        counts[outcome] += 1
        logger.info("[%d/%d] %s: %s", i, len(jobs), job_id,
                    'error' if outcome == 'errors' else outcome)

        if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            logger.error("Stopping after %d consecutive errors (%d jobs not fetched); "
                         "LinkedIn may be blocking requests.",
                         consecutive_errors, len(jobs) - i)
            return counts, False

    return counts, True


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Backfill job_posts.apply_type for recently analyzed jobs.")
    parser.add_argument('--since', type=parse_since, default='3d', metavar='<N>d|<N>h',
                        help="only jobs analyzed within this window (default: 3d)")
    parser.add_argument('--min-score', type=float, default=0.0,
                        help="minimum weighted_score (default: 0)")
    parser.add_argument('--limit', type=int, default=300,
                        help="maximum jobs to fetch (default: 300)")
    parser.add_argument('--dry-run', action='store_true',
                        help="list the jobs that would be fetched and exit")
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error("--limit must be at least 1")
    return args


def main(argv=None, db_file=None, lock_path=LOCK_FILE, scraper=None):
    """Run the backfill; returns the process exit code."""
    args = _parse_args(argv)
    storage = SQLiteStorage(db_file)  # Applies migrations (apply_type columns)
    db_file = storage.db_file

    if args.dry_run:
        jobs = select_jobs(db_file, args.since, args.min_score, args.limit)
        print(f"Dry run: {len(jobs)} jobs would be fetched")
        for job in jobs:
            print(f"  {job['linkedin_job_id']}  {job['date_time']}  "
                  f"score={job['weighted_score']}")
        return 0

    try:
        acquire_lock(lock_path)
    except LockHeld as e:
        logger.error("%s", e)
        return 1

    try:
        jobs = select_jobs(db_file, args.since, args.min_score, args.limit)
        logger.info("Backfilling apply_type for %d jobs", len(jobs))
        counts, completed = backfill(db_file, jobs, scraper)
    finally:
        release_lock(lock_path)

    logger.info("Summary: %s", " / ".join(f"{k}={counts[k]}" for k in OUTCOMES))
    return 0 if completed else 1


if __name__ == '__main__':
    from main import setup_logging
    setup_logging()
    sys.exit(main())
