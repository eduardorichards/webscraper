"""SQLite storage for job search results with duplicate prevention."""
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

LINKEDIN_JOB_BASE_URL = "https://www.linkedin.com/jobs/view/"


class SQLiteStorage:
    def __init__(self, db_file=None):
        if db_file is None:
            project_root = Path(__file__).resolve().parent.parent
            data_folder = project_root / 'data' / 'database'
            data_folder.mkdir(parents=True, exist_ok=True)
            db_file = data_folder / 'jobs_master.db'

        self.db_file = Path(db_file)
        self._ensure_db_exists()

    def _ensure_db_exists(self):
        """Create SQLite database and tables if they don't exist."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

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

        # Indexes
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_job_searches_linkedin_id
        ON job_searches(linkedin_job_id)
        """)
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_job_posts_score
        ON job_posts(weighted_score DESC)
        """)

        # View: combined job data for display
        cursor.execute("DROP VIEW IF EXISTS job_summary")
        cursor.execute("""
        CREATE VIEW job_summary AS
        SELECT
            jp.linkedin_job_id,
            js.title,
            js.company,
            js.location,
            jp.date_time,
            jp.applicant_count,
            jp.weighted_score,
            jp.match_percentage,
            jp.total_matches,
            jp.matched_keywords
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
               total_matches, matched_keywords
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

        conn.commit()
        conn.close()
        print(f"✅ SQLite database ready at: {self.db_file}")

    def append_jobs(self, jobs, search_config):
        """Insert search results into job_searches table."""
        if not jobs:
            print("No jobs to append to SQLite database")
            return

        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        added = 0
        for job in jobs:
            cursor.execute("""
            INSERT INTO job_searches (
                linkedin_job_id, title, company, location, company_url,
                search_keywords, search_location, search_experience, search_remote
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job.linkedin_job_id,
                job.title,
                job.company,
                job.location,
                job.company_url,
                search_config.keywords,
                search_config.location,
                ','.join(map(str, search_config.experience_levels)) if search_config.experience_levels else '',
                'Yes' if search_config.remote else 'No'
            ))
            added += 1

        conn.commit()
        conn.close()

        print(f"✅ Added {added} search results to SQLite database")

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

    def get_jobs_without_analysis(self):
        """
        Get distinct linkedin_job_ids that haven't been analyzed yet.
        Returns max 2 per (title, company) pair to avoid analyzing excessive duplicates.
        """
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            WITH unique_jobs AS (
                SELECT linkedin_job_id, title, company,
                    ROW_NUMBER() OVER (
                        PARTITION BY title, company
                        ORDER BY id ASC
                    ) as row_num
                FROM job_searches
                GROUP BY linkedin_job_id
            )
            SELECT uj.linkedin_job_id, uj.title, uj.company
            FROM unique_jobs uj
            LEFT JOIN job_posts jp ON uj.linkedin_job_id = jp.linkedin_job_id
            WHERE uj.row_num <= 2
              AND jp.linkedin_job_id IS NULL
            ORDER BY uj.linkedin_job_id ASC
        """)

        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def save_job_analysis(self, match_result):
        """Save or update job post analysis results."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        matched_keywords_str = ','.join(match_result.matched_keywords)

        cursor.execute("""
            INSERT OR REPLACE INTO job_posts (
                linkedin_job_id, description, applicant_count, date_time,
                total_matches, weighted_score, matched_keywords, match_percentage,
                employment_type, job_function, seniority_level, industries
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                jp.matched_keywords, jp.match_percentage
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

    def get_job_summary(self, min_score=0, limit=None, unique=False):
        """Get job summary from the combined view."""
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        view_name = "job_summary_unique" if unique else "job_summary"
        query = f"SELECT * FROM {view_name} WHERE weighted_score >= ?"
        params = [min_score]

        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def export_job_summary_csv(self, filepath=None, min_score=0, unique=True):
        """Export job summary to CSV file."""
        import csv

        if filepath is None:
            filename = 'job_summary_unique.csv' if unique else 'job_summary.csv'
            filepath = self.db_file.parent.parent / filename

        jobs = self.get_job_summary(min_score=min_score, unique=unique)

        if not jobs:
            print("No jobs to export")
            return None

        columns = [
            'linkedin_job_id', 'title', 'company', 'location',
            'date_time', 'applicant_count', 'weighted_score',
            'match_percentage', 'total_matches', 'matched_keywords'
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
