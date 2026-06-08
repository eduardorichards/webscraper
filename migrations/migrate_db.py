#!/usr/bin/env python3
"""
Migrate jobs_master.db from old schema (jobs + job_analyses) to new schema
(job_searches + job_posts). Backs up the database before making any changes.
"""

import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = Path("data/database/jobs_master.db")


def backup_db():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = DB_PATH.with_suffix(f".db.bak.{timestamp}")
    shutil.copy2(DB_PATH, backup_path)
    print(f"Backup created: {backup_path}")
    return backup_path


def print_counts_before(conn):
    cur = conn.cursor()
    jobs = cur.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    analyses = cur.execute("SELECT COUNT(*) FROM job_analyses").fetchone()[0]
    distinct = cur.execute(
        "SELECT COUNT(DISTINCT linkedin_job_id) FROM job_analyses"
    ).fetchone()[0]
    print(f"\n--- Before migration ---")
    print(f"  jobs:                              {jobs}")
    print(f"  job_analyses:                      {analyses}")
    print(f"  job_analyses (distinct linkedin):  {distinct}  ← expected job_posts count")
    return jobs, distinct


def print_counts_after(conn):
    cur = conn.cursor()
    searches = cur.execute("SELECT COUNT(*) FROM job_searches").fetchone()[0]
    posts = cur.execute("SELECT COUNT(*) FROM job_posts").fetchone()[0]
    print(f"\n--- After migration ---")
    print(f"  job_searches:  {searches}")
    print(f"  job_posts:     {posts}")
    return searches, posts


def migrate(conn):
    cur = conn.cursor()

    # Drop new tables if they were pre-created empty by the app
    cur.execute("DROP TABLE IF EXISTS job_searches")
    cur.execute("DROP TABLE IF EXISTS job_posts")

    # Create new tables
    cur.execute("""
        CREATE TABLE job_searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            linkedin_job_id TEXT NOT NULL,
            title TEXT,
            company TEXT,
            location TEXT,
            company_url TEXT,
            search_keywords TEXT,
            search_location TEXT,
            search_experience TEXT,
            search_remote TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE job_posts (
            linkedin_job_id TEXT UNIQUE NOT NULL,
            description TEXT,
            applicant_count INTEGER,
            date_time TIMESTAMP,
            total_matches INTEGER,
            weighted_score REAL,
            matched_keywords TEXT,
            match_percentage REAL,
            employment_type TEXT,
            job_function TEXT,
            seniority_level TEXT,
            industries TEXT
        )
    """)

    # Migrate jobs → job_searches (drop posted_date and job_url)
    cur.execute("""
        INSERT INTO job_searches (
            linkedin_job_id, title, company, location, company_url,
            search_keywords, search_location, search_experience, search_remote
        )
        SELECT
            linkedin_job_id, title, company, location, company_url,
            search_keywords, search_location, search_experience, search_remote
        FROM jobs
    """)
    print(f"  Migrated {cur.rowcount} rows into job_searches")

    # Migrate job_analyses → job_posts (dedup: keep highest weighted_score per linkedin_job_id)
    cur.execute("""
        INSERT INTO job_posts (
            linkedin_job_id, description, applicant_count, date_time,
            total_matches, weighted_score, matched_keywords, match_percentage,
            employment_type, job_function, seniority_level, industries
        )
        SELECT
            ja1.linkedin_job_id, ja1.description, ja1.applicant_count, ja1.analyzed_at,
            ja1.total_matches, ja1.weighted_score, ja1.matched_keywords, ja1.match_percentage,
            ja1.employment_type, ja1.job_function, NULL, NULL
        FROM job_analyses ja1
        WHERE ja1.id = (
            SELECT ja2.id FROM job_analyses ja2
            WHERE ja2.linkedin_job_id = ja1.linkedin_job_id
            ORDER BY ja2.weighted_score DESC, ja2.id DESC
            LIMIT 1
        )
    """)
    print(f"  Migrated {cur.rowcount} rows into job_posts")

    # Drop old views and tables (views first to avoid dependency errors)
    cur.execute("DROP VIEW IF EXISTS job_summary_unique")
    cur.execute("DROP VIEW IF EXISTS job_summary")
    cur.execute("DROP TABLE job_analyses")
    cur.execute("DROP TABLE jobs")
    print("  Dropped old views (job_summary_unique, job_summary) and tables (jobs, job_analyses)")


def main():
    if not DB_PATH.exists():
        print(f"ERROR: Database not found at {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    backup_db()

    conn = sqlite3.connect(DB_PATH)
    try:
        jobs_before, distinct_before = print_counts_before(conn)

        print("\nRunning migration...")
        conn.execute("BEGIN")
        migrate(conn)
        conn.commit()

        searches_after, posts_after = print_counts_after(conn)

        # Sanity check
        ok = True
        if searches_after != jobs_before:
            print(f"\nWARNING: job_searches count ({searches_after}) != old jobs count ({jobs_before})")
            ok = False
        if posts_after != distinct_before:
            print(f"\nWARNING: job_posts count ({posts_after}) != expected ({distinct_before})")
            ok = False
        if ok:
            print("\nMigration completed successfully.")

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: Migration failed — {e}", file=sys.stderr)
        print("Database has been rolled back. Backup is still available.", file=sys.stderr)
        conn.close()
        sys.exit(1)

    conn.close()


if __name__ == "__main__":
    main()
