"""SQLite storage for job search results with duplicate prevention."""
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

from config.env import DB_PATH
from config.settings import TARGET_SENIORITY_LEVELS
from utils.aggregators import load_aggregators
from utils.companies import load_companies
from utils.job_keys import LINKEDIN, LINKEDIN_JOB_BASE_URL, LINKEDIN_KEY_SQL, SOURCES  # noqa: F401
from utils.seniority import levels_above, title_above_level
from utils.time_utils import utc_now_iso


class SQLiteStorage:
    def __init__(self, db_file=None, aggregators_file=None, companies_file=None):
        if db_file is None:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            db_file = DB_PATH

        self.db_file = Path(db_file)
        # None = config/aggregators.json
        self.aggregators_file = aggregators_file
        # None = config/companies.json
        self.companies_file = companies_file
        self._ensure_db_exists()

    def _ensure_db_exists(self):
        """Create tables if missing and apply idempotent schema migrations.

        Everything runs in one IMMEDIATE transaction: concurrent inits (cron
        scraper + web app) are serialized, and a failure leaves the DB untouched.
        """
        conn = sqlite3.connect(self.db_file, isolation_level=None)
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN IMMEDIATE")
            self._create_schema(cursor)
            cursor.execute("COMMIT")
        except Exception:
            cursor.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        print(f"✅ SQLite database ready at: {self.db_file}")

    @staticmethod
    def _add_column_if_missing(cursor, table, column, definition):
        """Add a column unless it exists. Returns True if it was added."""
        cursor.execute(f"PRAGMA table_info({table})")
        if column in {row[1] for row in cursor.fetchall()}:
            return False
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        return True

    def _create_schema(self, cursor):
        """Create tables, indexes and views; migrate older databases in place."""
        # Table 1: Search results (linkedin_job_id is NOT unique)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS job_searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            linkedin_job_id TEXT,
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

        # Table 2: Job post details (linkedin_job_id IS unique)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS job_posts (
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

        # Table 3: Blacklisted companies
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS blacklisted_companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT UNIQUE NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Table 4: One row per search template execution
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS search_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template_name TEXT,
            keywords TEXT,
            location TEXT,
            started_at TEXT,
            finished_at TEXT,
            jobs_found INTEGER,
            new_jobs INTEGER,
            status TEXT CHECK (status IN ('ok', 'error')),
            error TEXT
        )
        """)

        # Table 5: Aggregator / job-board companies, synced from
        # config/aggregators.json below. Separate from the manual blacklist.
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS aggregator_companies (
            company TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            reason TEXT
        )
        """)

        # Table 6: Jobs I applied to (one row per linkedin_job_id)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            linkedin_job_id TEXT PRIMARY KEY,
            applied_on TEXT NOT NULL,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """)

        # Table 7: Companies whose ATS job boards are read (main.py --source
        # ats), synced from config/companies.json below. last_checked_at /
        # last_job_count are written by the collector, never by the sync.
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            name TEXT PRIMARY KEY,
            ats TEXT NOT NULL,
            slug TEXT NOT NULL,
            priority TEXT,
            hires_in_ar TEXT,
            notes TEXT,
            active INTEGER DEFAULT 1,
            last_checked_at TEXT,
            last_job_count INTEGER
        )
        """)

        # Migrations: columns added after the first release. Existing rows
        # keep NULL (ADD COLUMN does not rewrite the table).
        self._add_column_if_missing(cursor, 'job_searches', 'scraped_at', 'TEXT')
        self._add_column_if_missing(
            cursor, 'job_searches', 'search_run_id',
            'INTEGER REFERENCES search_runs(id)')
        self._add_column_if_missing(cursor, 'job_posts', 'scraped_at', 'TEXT')
        if self._add_column_if_missing(
                cursor, 'job_posts', 'applicant_count_qualifier', 'TEXT'):
            # One-time data fix, run only when the column is first added: the
            # old parser stored "Over 200 applicants" as 201. Running it on
            # every init would also rewrite genuine exact counts of 201.
            cursor.execute("""
            UPDATE job_posts
            SET applicant_count = 200, applicant_count_qualifier = 'over'
            WHERE applicant_count = 201 AND applicant_count_qualifier IS NULL
            """)
        # 'easy_apply' | 'external' | NULL (unknown); apply_url only for external
        self._add_column_if_missing(cursor, 'job_posts', 'apply_type', 'TEXT')
        self._add_column_if_missing(cursor, 'job_posts', 'apply_url', 'TEXT')
        # Hash of the keyword config that produced the score; NULL = unknown
        # (scored before versioning) or nothing scored (failed/closed fetch)
        self._add_column_if_missing(cursor, 'job_posts', 'scoring_version', 'TEXT')
        # Result pages fetched; 1 if the run stopped at SEARCH_MAX_PAGES with
        # more results left. NULL on runs before pagination.
        self._add_column_if_missing(cursor, 'search_runs', 'pages_fetched', 'INTEGER')
        self._add_column_if_missing(cursor, 'search_runs', 'hit_page_limit', 'INTEGER')
        # Job source: NULL = LinkedIn, else 'greenhouse' / 'lever' / 'ashby'
        # (see utils/job_keys.py). job_url: posting URL for non-LinkedIn jobs.
        self._add_column_if_missing(cursor, 'job_searches', 'source', 'TEXT')
        self._add_column_if_missing(cursor, 'job_searches', 'job_url', 'TEXT')
        # Posting date given by the source (ATS boards); NULL for LinkedIn,
        # whose date_time is close to the posting time already
        self._add_column_if_missing(cursor, 'job_posts', 'posted_at', 'TEXT')

        self._sync_aggregators(cursor)
        self._sync_companies(cursor)

        # Indexes
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_job_searches_run
        ON job_searches(search_run_id)
        """)
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_job_searches_linkedin_id
        ON job_searches(linkedin_job_id)
        """)
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_job_posts_score
        ON job_posts(weighted_score DESC)
        """)
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_job_posts_datetime
        ON job_posts(date_time DESC)
        """)
        # Makes get_employment_types() an index-only scan
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_job_posts_employment_type
        ON job_posts(employment_type)
        """)

        # View: combined job data for display. date_time is the source's
        # posting date when known (ATS jobs), else when the job was analyzed.
        cursor.execute("DROP VIEW IF EXISTS job_summary")
        cursor.execute("""
        CREATE VIEW job_summary AS
        SELECT
            jp.linkedin_job_id,
            js.title,
            js.company,
            js.location,
            COALESCE(jp.posted_at, jp.date_time) AS date_time,
            jp.applicant_count,
            jp.weighted_score,
            jp.match_percentage,
            jp.total_matches,
            jp.matched_keywords,
            jp.apply_type,
            jp.apply_url,
            jp.seniority_level,
            jp.applicant_count_qualifier,
            jp.employment_type,
            jp.industries,
            js.source,
            js.job_url
        FROM job_posts jp
        INNER JOIN job_searches js ON js.linkedin_job_id = jp.linkedin_job_id
        GROUP BY jp.linkedin_job_id
        ORDER BY jp.weighted_score DESC
        """)

        # Deduplicated view: max 2 per (title, company)
        cursor.execute("DROP VIEW IF EXISTS job_summary_unique")
        cursor.execute("""
        CREATE VIEW job_summary_unique AS
        SELECT linkedin_job_id, title, company, location, date_time,
               applicant_count, weighted_score, match_percentage,
               total_matches, matched_keywords, apply_type, apply_url,
               seniority_level, applicant_count_qualifier, employment_type,
               industries, source, job_url
        FROM (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY title, company
                    ORDER BY
                        CASE WHEN applicant_count IS NULL THEN 1 ELSE 0 END,
                        applicant_count ASC
                ) as row_num
            FROM job_summary
        )
        WHERE row_num <= 2
        ORDER BY weighted_score DESC
        """)

    def _sync_aggregators(self, cursor):
        """Make aggregator_companies match the data file (idempotent).

        Inserts new companies, updates changed category/reason, and deletes
        companies no longer listed. Unchanged rows aren't written.
        """
        entries = load_aggregators(self.aggregators_file)
        for company, category, reason in entries:
            cursor.execute(
                "INSERT OR IGNORE INTO aggregator_companies (company, category, reason)"
                " VALUES (?, ?, ?)", (company, category, reason))
            cursor.execute(
                "UPDATE aggregator_companies SET category = ?, reason = ?"
                " WHERE company = ? AND (category IS NOT ? OR reason IS NOT ?)",
                (category, reason, company, category, reason))
        companies = [company for company, _, _ in entries]
        placeholders = ", ".join("?" * len(companies))
        cursor.execute(
            f"DELETE FROM aggregator_companies WHERE company NOT IN ({placeholders})",
            companies)

    def _sync_companies(self, cursor):
        """Make companies match the data file (idempotent).

        Inserts new companies, updates changed config fields, and deletes
        companies no longer listed. last_checked_at / last_job_count are
        never touched for listed companies.
        """
        entries = load_companies(self.companies_file)
        fields = ('ats', 'slug', 'priority', 'hires_in_ar', 'notes', 'active')
        for entry in entries:
            values = [entry[f] if f != 'active' else int(entry[f]) for f in fields]
            cursor.execute(
                "INSERT OR IGNORE INTO companies (name, %s) VALUES (?, %s)"
                % (", ".join(fields), ", ".join("?" * len(fields))),
                [entry['name']] + values)
            cursor.execute(
                "UPDATE companies SET %s WHERE name = ? AND (%s)"
                % (", ".join("%s = ?" % f for f in fields),
                   " OR ".join("%s IS NOT ?" % f for f in fields)),
                values + [entry['name']] + values)
        names = [entry['name'] for entry in entries]
        placeholders = ", ".join("?" * len(names))
        cursor.execute(f"DELETE FROM companies WHERE name NOT IN ({placeholders})", names)

    def get_companies(self, active_only=True):
        """Companies to read ATS boards from, as dicts, in data-file order
        (rowid) so the list order is the reading order."""
        query = "SELECT * FROM companies"
        if active_only:
            query += " WHERE active = 1"
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query + " ORDER BY rowid").fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def mark_company_checked(self, name, job_count):
        """Record when a company's board was last read and how many postings
        it returned (0 for errors and empty boards)."""
        conn = sqlite3.connect(self.db_file)
        conn.execute(
            "UPDATE companies SET last_checked_at = ?, last_job_count = ? WHERE name = ?",
            (utc_now_iso(), job_count, name))
        conn.commit()
        conn.close()

    def is_aggregator(self, company):
        """True if the company is in aggregator_companies."""
        conn = sqlite3.connect(self.db_file)
        row = conn.execute("SELECT 1 FROM aggregator_companies WHERE company = ?",
                           (company,)).fetchone()
        conn.close()
        return row is not None

    def job_key_exists(self, key):
        """True if the key has a job_searches or a job_posts row."""
        conn = sqlite3.connect(self.db_file)
        row = conn.execute(
            "SELECT 1 FROM job_searches WHERE linkedin_job_id = ?"
            " UNION ALL SELECT 1 FROM job_posts WHERE linkedin_job_id = ? LIMIT 1",
            (key, key)).fetchone()
        conn.close()
        return row is not None

    def add_ats_job(self, job, search_run_id=None, scraped_at=None):
        """Insert the job_searches row of an ATS posting (an AtsJob)."""
        conn = sqlite3.connect(self.db_file)
        conn.execute("""
            INSERT INTO job_searches (
                linkedin_job_id, title, company, location, search_keywords,
                search_location, search_remote, scraped_at, search_run_id,
                source, job_url
            ) VALUES (?, ?, ?, ?, 'ats', ?, ?, ?, ?, ?, ?)
        """, (job.key, job.title, job.company, job.location_raw, job.slug,
              'Yes' if job.remote else 'No', scraped_at or utc_now_iso(),
              search_run_id, job.source, job.job_url))
        conn.commit()
        conn.close()

    def get_aggregator_companies(self):
        """Return [{'company', 'category', 'reason'}] sorted by company."""
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT company, category, reason FROM aggregator_companies"
            " ORDER BY company ASC").fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def start_search_run(self, template_name, keywords, location):
        """Insert a search_runs row for a template execution; return its id.

        status/finished_at stay NULL until finish_search_run() is called, so
        a row left that way means the run was interrupted.
        """
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO search_runs (template_name, keywords, location, started_at)
            VALUES (?, ?, ?, ?)
        """, (template_name, keywords, location, utc_now_iso()))
        run_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return run_id

    def finish_search_run(self, run_id, jobs_found, new_jobs, status, error=None,
                          pages_fetched=None, hit_page_limit=None):
        """Record the outcome of a search run ('ok' or 'error')."""
        if hit_page_limit is not None:
            hit_page_limit = int(bool(hit_page_limit))
        conn = sqlite3.connect(self.db_file)
        conn.execute("""
            UPDATE search_runs
            SET finished_at = ?, jobs_found = ?, new_jobs = ?, status = ?, error = ?,
                pages_fetched = ?, hit_page_limit = ?
            WHERE id = ?
        """, (utc_now_iso(), jobs_found, new_jobs, status, error,
              pages_fetched, hit_page_limit, run_id))
        conn.commit()
        conn.close()

    def get_search_runs(self, limit=50):
        """Return the most recent search runs, newest first."""
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM search_runs ORDER BY id DESC LIMIT ?", (int(limit),)
        ).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def append_jobs(self, jobs, search_config, search_run_id=None, scraped_at=None):
        """Insert search results into job_searches table.

        Returns:
            int: number of new jobs, i.e. distinct linkedin_job_ids in `jobs`
            not already present in job_searches before this call.
        """
        if not jobs:
            print("No jobs to append to SQLite database")
            return 0

        if scraped_at is None:
            scraped_at = utc_now_iso()

        conn = sqlite3.connect(self.db_file, isolation_level=None)
        cursor = conn.cursor()

        # Count new IDs in the same transaction as the insert
        cursor.execute("BEGIN IMMEDIATE")
        try:
            new_ids = set()
            for job_id in {job.linkedin_job_id for job in jobs if job.linkedin_job_id}:
                cursor.execute(
                    "SELECT 1 FROM job_searches WHERE linkedin_job_id = ? LIMIT 1",
                    (job_id,)
                )
                if cursor.fetchone() is None:
                    new_ids.add(job_id)

            added = 0
            for job in jobs:
                cursor.execute("""
                INSERT INTO job_searches (
                    linkedin_job_id, title, company, location, company_url,
                    search_keywords, search_location, search_experience, search_remote,
                    scraped_at, search_run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    job.linkedin_job_id,
                    job.title,
                    job.company,
                    job.location,
                    job.company_url,
                    search_config.keywords,
                    search_config.location,
                    ','.join(map(str, search_config.experience_levels)) if search_config.experience_levels else '',
                    'Yes' if search_config.remote else 'No',
                    scraped_at,
                    search_run_id,
                ))
                added += 1

            cursor.execute("COMMIT")
        except Exception:
            cursor.execute("ROLLBACK")
            raise
        finally:
            conn.close()

        print(f"✅ Added {added} search results to SQLite database "
              f"({len(new_ids)} new jobs)")
        return len(new_ids)

    def get_total_jobs(self):
        """Get total number of unique linkedin_job_ids in searches."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(DISTINCT linkedin_job_id) FROM job_searches")
        total = cursor.fetchone()[0]

        conn.close()
        return total

    def get_stats(self):
        """Get statistics about stored jobs."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(DISTINCT linkedin_job_id) FROM job_searches")
        total_jobs = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT company) FROM job_searches")
        unique_companies = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT location) FROM job_searches")
        unique_locations = cursor.fetchone()[0]

        conn.close()
        return {
            'total_jobs': total_jobs,
            'unique_companies': unique_companies,
            'unique_locations': unique_locations,
            'file_path': self.db_file
        }

    # Candidate jobs for detail scraping: LinkedIn IDs only (other sources
    # are scored when collected), max 2 IDs per (title, company), the first
    # ones seen, without a job_posts row yet
    _PENDING_JOBS_SQL = """
        WITH unique_jobs AS (
            SELECT linkedin_job_id, title, company,
                ROW_NUMBER() OVER (
                    PARTITION BY title, company
                    ORDER BY id ASC
                ) as row_num
            FROM job_searches
            WHERE """ + LINKEDIN_KEY_SQL.format(col="linkedin_job_id") + """
            GROUP BY linkedin_job_id
        )
        SELECT uj.linkedin_job_id, uj.title, uj.company
        FROM unique_jobs uj
        LEFT JOIN job_posts jp ON uj.linkedin_job_id = jp.linkedin_job_id
        WHERE uj.row_num <= 2
          AND jp.linkedin_job_id IS NULL
    """
    _AGGREGATOR_CLAUSE = "uj.company IN (SELECT company FROM aggregator_companies)"

    def get_jobs_without_analysis(self, exclude_aggregators=True):
        """
        Get distinct linkedin_job_ids that haven't been analyzed yet.
        Returns max 2 per (title, company) pair to avoid analyzing excessive duplicates.

        With exclude_aggregators (default), jobs from aggregator_companies are
        left out: their search hits are kept but their pages aren't fetched.
        """
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = self._PENDING_JOBS_SQL
        if exclude_aggregators:
            query += f" AND NOT {self._AGGREGATOR_CLAUSE}"
        cursor.execute(query + " ORDER BY uj.linkedin_job_id ASC")

        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def count_skipped_aggregator_jobs(self, since=None):
        """Count unanalyzed aggregator jobs that get_jobs_without_analysis()
        leaves out, i.e. detail fetches skipped.

        since: UTC ISO timestamp; only jobs first seen in a search at or
        after it (None = all pending, including rows without scraped_at).
        """
        query = f"SELECT COUNT(*) FROM ({self._PENDING_JOBS_SQL} AND {self._AGGREGATOR_CLAUSE}"
        params = []
        if since is not None:
            # First seen at or after `since`: no earlier (or undated) hit
            query += (" AND NOT EXISTS (SELECT 1 FROM job_searches js"
                      " WHERE js.linkedin_job_id = uj.linkedin_job_id"
                      " AND (js.scraped_at IS NULL OR js.scraped_at < ?))")
            params.append(since)
        query += ")"
        conn = sqlite3.connect(self.db_file)
        count = conn.execute(query, params).fetchone()[0]
        conn.close()
        return count

    def save_job_analysis(self, match_result):
        """Save or update job post analysis results."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        matched_keywords_str = ','.join(match_result.matched_keywords)

        cursor.execute("""
            INSERT OR REPLACE INTO job_posts (
                linkedin_job_id, description, applicant_count, date_time,
                total_matches, weighted_score, matched_keywords, match_percentage,
                employment_type, job_function, seniority_level, industries,
                applicant_count_qualifier, scraped_at, apply_type, apply_url,
                scoring_version, posted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            match_result.linkedin_job_id,
            match_result.description,
            match_result.applicant_count,
            match_result.date_time,
            match_result.total_matches,
            match_result.weighted_score,
            matched_keywords_str,
            match_result.match_percentage,
            match_result.employment_type,
            match_result.job_function,
            match_result.seniority_level,
            match_result.industries,
            match_result.applicant_count_qualifier,
            match_result.scraped_at,
            match_result.apply_type,
            match_result.apply_url,
            match_result.scoring_version,
            match_result.posted_at,
        ))

        conn.commit()
        conn.close()

    def get_analyzed_jobs(self, min_score=0, min_keywords=0,
                          order_by='weighted_score DESC', limit=None):
        """Get analyzed jobs with optional filtering."""
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = """
            SELECT
                jp.linkedin_job_id, js.title, js.company, js.location,
                jp.description, jp.applicant_count, jp.date_time,
                jp.employment_type, jp.job_function, jp.seniority_level,
                jp.industries, jp.total_matches, jp.weighted_score,
                jp.matched_keywords, jp.match_percentage, js.source, js.job_url
            FROM job_posts jp
            INNER JOIN job_searches js ON js.linkedin_job_id = jp.linkedin_job_id
            WHERE jp.weighted_score >= ?
            GROUP BY jp.linkedin_job_id
        """
        params = [min_score]

        if min_keywords > 0:
            query += " HAVING (LENGTH(jp.matched_keywords) - LENGTH(REPLACE(jp.matched_keywords, ',', '')) + 1) >= ?"
            params.append(min_keywords)

        query += f" ORDER BY {order_by}"

        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        results = []
        for row in rows:
            result = dict(row)
            if result.get('matched_keywords'):
                result['matched_keywords'] = result['matched_keywords'].split(',')
            results.append(result)

        return results

    def get_analysis_stats(self):
        """Get statistics about analyzed jobs."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                COUNT(*) as total_analyzed,
                AVG(weighted_score) as avg_score,
                MAX(weighted_score) as max_score,
                AVG(match_percentage) as avg_match_pct
            FROM job_posts
        """)

        row = cursor.fetchone()
        conn.close()

        return {
            'total_analyzed': row[0],
            'avg_score': row[1] or 0,
            'max_score': row[2] or 0,
            'avg_match_pct': row[3] or 0
        }

    # Whitelist of sortable columns: user input only ever selects a key here
    SORT_COLUMNS = {
        'linkedin_job_id': 'linkedin_job_id',
        'title': 'title',
        'company': 'company',
        'location': 'location',
        'date_time': 'date_time',
        'applicant_count': 'applicant_count',
        'total_matches': 'total_matches',
        'weighted_score': 'weighted_score',
        'match_percentage': 'match_percentage',
    }
    SORT_DIRECTIONS = {'asc': 'ASC', 'desc': 'DESC'}
    DEFAULT_SORT = 'date_time'
    DEFAULT_DIRECTION = 'desc'
    # Application type filter values; 'unknown' matches NULL
    APPLY_FILTERS = ('easy_apply', 'external', 'unknown')
    # Applied filter values: 'hide' / 'only' also match postings with the
    # same (title, company) as an applied job, since job_summary_unique
    # keeps up to 2 postings per pair
    APPLIED_FILTERS = ('hide', 'only', 'all')
    # Source filter values (utils/job_keys.py); 'linkedin' matches NULL
    SOURCE_FILTERS = SOURCES
    # seniority_level values hidden by hide_above_level (from config.settings)
    ABOVE_TARGET_LEVELS = levels_above(TARGET_SENIORITY_LEVELS)

    # Row of the summary view `v` is an applied job or a (title, company) twin
    # of one. IFNULL: rows with a NULL title/company count as not applied.
    _APPLIED_SQL = (
        "(v.linkedin_job_id IN (SELECT linkedin_job_id FROM applications)"
        " OR IFNULL((v.title, v.company) IN ("
        "SELECT s.title, s.company FROM applications a"
        " JOIN job_searches s ON s.linkedin_job_id = a.linkedin_job_id), 0))"
    )
    # "Under 25 applicants": 'under' qualifier, or a historical 25 with no
    # qualifier (the old parser stored "Be among the first 25" that way)
    _UNDER_25_SQL = (
        "(applicant_count < 25 OR (applicant_count = 25 AND"
        " (applicant_count_qualifier IS NULL OR applicant_count_qualifier = 'under')))"
    )

    @staticmethod
    def _like_pattern(text):
        """%text% for LIKE ... ESCAPE '\\', with wildcards in text escaped."""
        escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"%{escaped}%"

    def _build_summary_filters(self, min_score=0, days=7, location=None,
                               hours=None, hide_blacklisted=False,
                               apply_type=None, hide_aggregators=False,
                               hide_above_level=False, search=None,
                               employment_types=None, max_score=None,
                               min_match=None, keywords=None, under_25=False,
                               applied='all', source=None):
        """Build the WHERE clause and bound params shared by summary queries.

        The view must be aliased `v`. List filters (employment_types,
        keywords) match any of their values; an empty list is no filter.
        """
        clauses = ["weighted_score >= ?"]
        params = [min_score]

        if max_score is not None:
            clauses.append("weighted_score <= ?")
            params.append(max_score)

        if min_match is not None:
            clauses.append("match_percentage >= ?")
            params.append(min_match)

        if days is not None:
            clauses.append("date_time >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ?)")
            params.append(f"-{int(days)} days")

        if hours is not None:
            clauses.append("date_time >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ?)")
            params.append(f"-{int(hours)} hours")

        if location:
            clauses.append("LOWER(location) LIKE LOWER(?)")
            params.append(f"%{location}%")

        if search:
            clauses.append("(LOWER(title) LIKE LOWER(?) ESCAPE '\\'"
                           " OR LOWER(company) LIKE LOWER(?) ESCAPE '\\')")
            pattern = self._like_pattern(search)
            params.extend([pattern, pattern])

        if employment_types:
            placeholders = ", ".join("?" * len(employment_types))
            clauses.append(f"employment_type IN ({placeholders})")
            params.extend(employment_types)

        if keywords:
            # matched_keywords is comma-separated: the commas around each
            # value keep "Java" from matching "JavaScript"
            clauses.append("(" + " OR ".join(
                ["instr(',' || matched_keywords || ',', ?) > 0"] * len(keywords)) + ")")
            params.extend(f",{kw}," for kw in keywords)

        if under_25:
            clauses.append(self._UNDER_25_SQL)

        if hide_blacklisted:
            clauses.append(
                "(company IS NULL OR company NOT IN "
                "(SELECT company FROM blacklisted_companies))"
            )

        if apply_type == 'unknown':
            clauses.append("apply_type IS NULL")
        elif apply_type in self.APPLY_FILTERS:
            clauses.append("apply_type = ?")
            params.append(apply_type)

        if source == LINKEDIN:
            clauses.append("source IS NULL")
        elif source in self.SOURCE_FILTERS:
            clauses.append("source = ?")
            params.append(source)

        if hide_aggregators:
            clauses.append(
                "(company IS NULL OR company NOT IN "
                "(SELECT company FROM aggregator_companies))"
            )

        # NULL and unranked values ("Not Applicable") are always kept by the
        # seniority check; the title check (see _connect_summary) still applies
        if hide_above_level:
            if self.ABOVE_TARGET_LEVELS:
                placeholders = ", ".join("?" * len(self.ABOVE_TARGET_LEVELS))
                clauses.append(
                    f"(seniority_level IS NULL OR seniority_level NOT IN ({placeholders}))")
                params.extend(self.ABOVE_TARGET_LEVELS)
            clauses.append("NOT title_above_level(title)")

        if applied == 'hide':
            clauses.append(f"NOT {self._APPLIED_SQL}")
        elif applied == 'only':
            clauses.append(self._APPLIED_SQL)

        return " WHERE " + " AND ".join(clauses), params

    def _connect_summary(self):
        """Connection for summary queries, with the SQL functions they use."""
        conn = sqlite3.connect(self.db_file)
        conn.create_function("title_above_level", 1,
                             lambda title: int(title_above_level(title)),
                             deterministic=True)
        return conn

    def get_job_summary(self, limit=None, unique=False, page=1, per_page=50,
                        sort=DEFAULT_SORT, direction=DEFAULT_DIRECTION,
                        **filters):
        """Get one page of the job summary view.

        filters: keyword arguments of _build_summary_filters (days defaults
        to 7). per_page=None disables pagination (all matching rows, or
        `limit`). Invalid sort/direction values fall back to date_time DESC.
        """
        conn = self._connect_summary()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        view_name = "job_summary_unique" if unique else "job_summary"
        where, params = self._build_summary_filters(**filters)

        if sort not in self.SORT_COLUMNS or direction not in self.SORT_DIRECTIONS:
            sort, direction = self.DEFAULT_SORT, self.DEFAULT_DIRECTION
        col = self.SORT_COLUMNS[sort]
        dir_sql = self.SORT_DIRECTIONS[direction]

        # NULLs always last; linkedin_job_id as tiebreaker keeps pages stable
        query = (f"SELECT * FROM {view_name} v{where}"
                 f" ORDER BY {col} IS NULL, {col} {dir_sql},"
                 f" linkedin_job_id {dir_sql}")

        if per_page is not None:
            page = max(1, int(page))
            query += " LIMIT ? OFFSET ?"
            params.extend([int(per_page), (page - 1) * int(per_page)])
        elif limit:
            query += " LIMIT ?"
            params.append(int(limit))

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def count_job_summary(self, unique=False, **filters):
        """Count rows of the job summary view matching the given filters."""
        conn = self._connect_summary()
        cursor = conn.cursor()

        view_name = "job_summary_unique" if unique else "job_summary"
        where, params = self._build_summary_filters(**filters)

        cursor.execute(f"SELECT COUNT(*) FROM {view_name} v{where}", params)
        total = cursor.fetchone()[0]
        conn.close()
        return total

    def get_employment_types(self):
        """Distinct non-empty job_posts.employment_type values, sorted."""
        conn = sqlite3.connect(self.db_file)
        rows = conn.execute(
            "SELECT DISTINCT employment_type FROM job_posts"
            " WHERE employment_type IS NOT NULL AND employment_type != ''"
            " ORDER BY employment_type").fetchall()
        conn.close()
        return [r[0] for r in rows]

    def get_description_snippets(self, job_ids, length=500):
        """{linkedin_job_id: first `length` chars of the description} for
        the given IDs (one page of results, kept out of the views)."""
        if not job_ids:
            return {}
        placeholders = ", ".join("?" * len(job_ids))
        conn = sqlite3.connect(self.db_file)
        rows = conn.execute(
            f"SELECT linkedin_job_id, SUBSTR(description, 1, ?) FROM job_posts"
            f" WHERE linkedin_job_id IN ({placeholders})",
            [int(length)] + list(job_ids)).fetchall()
        conn.close()
        return {r[0]: r[1] for r in rows if r[1]}

    def export_job_summary_csv(self, filepath=None, min_score=0, unique=True):
        """Export job summary to CSV file."""
        import csv

        if filepath is None:
            filename = 'job_summary_unique.csv' if unique else 'job_summary.csv'
            filepath = self.db_file.parent.parent / filename

        jobs = self.get_job_summary(min_score=min_score, unique=unique,
                                    per_page=None)

        if not jobs:
            print("No jobs to export")
            return None

        columns = [
            'linkedin_job_id', 'title', 'company', 'location',
            'date_time', 'applicant_count', 'weighted_score',
            'match_percentage', 'total_matches', 'matched_keywords',
            'apply_type', 'apply_url', 'seniority_level', 'source', 'job_url'
        ]

        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
            writer.writeheader()
            for job in jobs:
                writer.writerow(job)

        print(f"✅ Exported {len(jobs)} jobs to {filepath}")
        return filepath

    def add_blacklisted_company(self, company):
        """Add a company to the blacklist (idempotent)."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO blacklisted_companies (company) VALUES (?)",
            (company,)
        )
        conn.commit()
        conn.close()

    def remove_blacklisted_company(self, company):
        """Remove a company from the blacklist."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM blacklisted_companies WHERE company = ?",
            (company,)
        )
        conn.commit()
        conn.close()

    def get_blacklisted_companies(self):
        """Return a sorted list of blacklisted company names."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT company FROM blacklisted_companies ORDER BY company ASC"
        )
        rows = cursor.fetchall()
        conn.close()
        return [r[0] for r in rows]

    def job_post_exists(self, linkedin_job_id):
        """True if job_posts has a row for this ID."""
        conn = sqlite3.connect(self.db_file)
        row = conn.execute("SELECT 1 FROM job_posts WHERE linkedin_job_id = ?",
                           (linkedin_job_id,)).fetchone()
        conn.close()
        return row is not None

    def save_application(self, linkedin_job_id, applied_on, notes=None):
        """Mark a job as applied, or update its date/notes (upsert).

        applied_on: 'YYYY-MM-DD' (a local date picked by the user).
        """
        now = utc_now_iso()
        conn = sqlite3.connect(self.db_file)
        conn.execute("""
            INSERT INTO applications
                (linkedin_job_id, applied_on, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(linkedin_job_id) DO UPDATE SET
                applied_on = excluded.applied_on,
                notes = excluded.notes,
                updated_at = excluded.updated_at
        """, (linkedin_job_id, applied_on, notes, now, now))
        conn.commit()
        conn.close()

    def remove_application(self, linkedin_job_id):
        """Unmark a job as applied."""
        conn = sqlite3.connect(self.db_file)
        conn.execute("DELETE FROM applications WHERE linkedin_job_id = ?",
                     (linkedin_job_id,))
        conn.commit()
        conn.close()

    def get_applications(self):
        """All applications, most recently applied first."""
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT linkedin_job_id, applied_on, notes, created_at, updated_at"
            " FROM applications ORDER BY applied_on DESC, linkedin_job_id").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_application_status(self, jobs):
        """Application info for one page of summary rows.

        Returns {linkedin_job_id: {'applied_on', 'notes', 'similar'}}, only for
        jobs that are applied (similar=False) or share (title, company) with
        an applied job (similar=True, applied_on of that job).
        """
        conn = sqlite3.connect(self.db_file)
        own = {r[0]: (r[1], r[2]) for r in conn.execute(
            "SELECT linkedin_job_id, applied_on, notes FROM applications")}
        pairs = {}
        for title, company, applied_on in conn.execute(
                "SELECT s.title, s.company, a.applied_on FROM applications a"
                " JOIN job_searches s ON s.linkedin_job_id = a.linkedin_job_id"):
            if title is not None and company is not None:
                pairs[(title, company)] = max(applied_on, pairs.get((title, company), ''))
        conn.close()

        status = {}
        for job in jobs:
            job_id = job['linkedin_job_id']
            if job_id in own:
                applied_on, notes = own[job_id]
                status[job_id] = {'applied_on': applied_on, 'notes': notes, 'similar': False}
            elif (job.get('title'), job.get('company')) in pairs:
                status[job_id] = {'applied_on': pairs[(job['title'], job['company'])],
                                  'notes': None, 'similar': True}
        return status
