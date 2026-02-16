"""SQLite storage for job search results with duplicate prevention."""
import sqlite3
import json
from pathlib import Path
from datetime import datetime


class SQLiteStorage:
    def __init__(self, db_file=None):
        if db_file is None:
            # Save to a directory inside the project: data/database
            project_root = Path(__file__).resolve().parent.parent  # Go to the project root
            data_folder = project_root / 'data' / 'database'
            data_folder.mkdir(parents=True, exist_ok=True)  # Ensure the directory exists
            db_file = data_folder / 'jobs_master.db'
        
        self.db_file = Path(db_file)
        self.table_name = 'jobs'
        self._ensure_db_exists()
    
    def _ensure_db_exists(self):
        """Create SQLite database and table if it doesn't exist"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # Create table if it doesn't exist
        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            company TEXT,
            location TEXT,
            posted_date TEXT,
            job_url TEXT UNIQUE,
            search_keywords TEXT,
            search_location TEXT,
            search_experience TEXT,
            search_remote TEXT
        )
        """)
        
        conn.commit()
        conn.close()

        # Also ensure job_analyses table exists
        self._ensure_analyses_table_exists()
        print(f"✅ SQLite database ready at: {self.db_file}")

    def _ensure_analyses_table_exists(self):
        """Create job_analyses table if it doesn't exist."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS job_analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            description TEXT,
            applicant_count INTEGER,
            seniority_level TEXT,
            employment_type TEXT,
            job_function TEXT,
            industries TEXT,
            keyword_matches TEXT,
            total_matches INTEGER,
            weighted_score REAL,
            matched_keywords TEXT,
            match_percentage REAL,
            search_keywords TEXT,
            analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            scrape_status TEXT DEFAULT 'pending',
            FOREIGN KEY (job_id) REFERENCES jobs(id),
            UNIQUE(job_id, search_keywords)
        )
        """)

        # Create index for faster queries
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_job_analyses_score
        ON job_analyses(weighted_score DESC)
        """)
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_job_analyses_job_id
        ON job_analyses(job_id)
        """)

        # Create view for easy querying of combined job + analysis data
        cursor.execute("DROP VIEW IF EXISTS job_summary")
        cursor.execute("""
        CREATE VIEW job_summary AS
        SELECT
            j.title AS job_role,
            j.company,
            j.job_url AS url,
            j.location,
            j.search_remote AS remote,
            ja.applicant_count,
            ja.seniority_level,
            ja.total_matches,
            ja.weighted_score,
            ja.match_percentage,
            ja.matched_keywords,
            ja.analyzed_at
        FROM jobs j
        INNER JOIN job_analyses ja ON j.id = ja.job_id
        ORDER BY ja.weighted_score DESC
        """)

        # Create deduplicated view - keeps max 2 per (job_role, company)
        # Keeps the ones with lowest applicant count
        cursor.execute("DROP VIEW IF EXISTS job_summary_unique")
        cursor.execute("""
        CREATE VIEW job_summary_unique AS
        SELECT job_role, company, url, location, remote,
               applicant_count, seniority_level, total_matches,
               weighted_score, match_percentage, matched_keywords, analyzed_at
        FROM (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY job_role, company
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
    
    def append_jobs(self, jobs, search_config):
        """Insert new jobs into the database, avoiding duplicates"""
        if not jobs:
            print("No jobs to append to SQLite database")
            return
        
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        new_jobs = []
        duplicate_by_url = 0
        
        for job in jobs:
            try:
                # Insert job into the database
                cursor.execute(f"""
                INSERT INTO {self.table_name} (
                    title, company, location, posted_date, job_url,
                    search_keywords, search_location, search_experience, search_remote
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    job.title,
                    job.company,
                    job.location,
                    job.posted_date,
                    job.job_url,
                    search_config.keywords,
                    search_config.location,
                    ','.join(map(str, search_config.experience_levels)) if search_config.experience_levels else '',
                    'Yes' if search_config.remote else 'No'
                ))
                new_jobs.append(job)
            except sqlite3.IntegrityError:
                # Duplicate job_url, skip
                duplicate_by_url += 1
                continue
        
        conn.commit()
        conn.close()
        
        print(f"✅ Added {len(new_jobs)} new jobs to SQLite database")
        if duplicate_by_url > 0:
            print(f"⚠️  Skipped {duplicate_by_url} duplicate jobs by URL")
    
    def get_total_jobs(self):
        """Get total number of jobs in the database"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute(f"SELECT COUNT(*) FROM {self.table_name}")
        total_jobs = cursor.fetchone()[0]
        
        conn.close()
        return total_jobs
    
    def get_stats(self):
        """Get statistics about stored jobs"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute(f"SELECT COUNT(*) FROM {self.table_name}")
        total_jobs = cursor.fetchone()[0]
        
        cursor.execute(f"SELECT COUNT(DISTINCT company) FROM {self.table_name}")
        unique_companies = cursor.fetchone()[0]
        
        cursor.execute(f"SELECT COUNT(DISTINCT location) FROM {self.table_name}")
        unique_locations = cursor.fetchone()[0]
        
        conn.close()
        return {
            'total_jobs': total_jobs,
            'unique_companies': unique_companies,
            'unique_locations': unique_locations,
            'file_path': self.db_file
        }

    def get_all_jobs(self):
        """Get all jobs from the database."""
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(f"SELECT * FROM {self.table_name}")
        rows = cursor.fetchall()

        conn.close()
        return [dict(row) for row in rows]

    def get_jobs_by_ids(self, job_ids):
        """Get jobs by their IDs."""
        if not job_ids:
            return []

        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        placeholders = ','.join('?' * len(job_ids))
        cursor.execute(
            f"SELECT * FROM {self.table_name} WHERE id IN ({placeholders})",
            job_ids
        )
        rows = cursor.fetchall()

        conn.close()
        return [dict(row) for row in rows]

    def get_jobs_without_analysis(self, search_keywords=None):
        """
        Get jobs that haven't been analyzed yet.
        Returns max 2 jobs per (title, company) pair to avoid analyzing excessive duplicates.

        Args:
            search_keywords: Optional - only get jobs not analyzed with these specific keywords
        """
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if search_keywords:
            cursor.execute(f"""
                WITH ranked_jobs AS (
                    SELECT j.*,
                        ROW_NUMBER() OVER (
                            PARTITION BY j.title, j.company
                            ORDER BY j.id ASC
                        ) as row_num
                    FROM {self.table_name} j
                )
                SELECT rj.id, rj.title, rj.company, rj.location, rj.posted_date,
                       rj.job_url, rj.search_keywords, rj.search_location,
                       rj.search_experience, rj.search_remote
                FROM ranked_jobs rj
                LEFT JOIN job_analyses ja
                    ON rj.id = ja.job_id AND ja.search_keywords = ?
                WHERE rj.row_num <= 2
                  AND ja.id IS NULL
                ORDER BY rj.id ASC
            """, (search_keywords,))
        else:
            cursor.execute(f"""
                WITH ranked_jobs AS (
                    SELECT j.*,
                        ROW_NUMBER() OVER (
                            PARTITION BY j.title, j.company
                            ORDER BY j.id ASC
                        ) as row_num
                    FROM {self.table_name} j
                )
                SELECT rj.id, rj.title, rj.company, rj.location, rj.posted_date,
                       rj.job_url, rj.search_keywords, rj.search_location,
                       rj.search_experience, rj.search_remote
                FROM ranked_jobs rj
                LEFT JOIN job_analyses ja ON rj.id = ja.job_id
                WHERE rj.row_num <= 2
                  AND ja.id IS NULL
                ORDER BY rj.id ASC
            """)

        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def save_job_analysis(self, match_result, keyword_config):
        """
        Save or update job analysis results.

        Args:
            match_result: MatchResult instance with analysis data
            keyword_config: KeywordConfig instance used for analysis
        """
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        search_keywords = keyword_config.get_keywords_string()
        keyword_matches_json = json.dumps(match_result.keyword_matches)
        matched_keywords_str = ','.join(match_result.matched_keywords)

        cursor.execute("""
            INSERT OR REPLACE INTO job_analyses (
                job_id, description, applicant_count, seniority_level,
                employment_type, job_function, industries,
                keyword_matches, total_matches, weighted_score,
                matched_keywords, match_percentage, search_keywords,
                analyzed_at, scrape_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            match_result.job_id,
            match_result.description,
            match_result.applicant_count,
            match_result.seniority_level,
            match_result.employment_type,
            match_result.job_function,
            match_result.industries,
            keyword_matches_json,
            match_result.total_matches,
            match_result.weighted_score,
            matched_keywords_str,
            match_result.match_percentage,
            search_keywords,
            datetime.now().isoformat(),
            match_result.scrape_status
        ))

        conn.commit()
        conn.close()

    def get_analyzed_jobs(self, search_keywords=None, min_score=0, min_keywords=0,
                          order_by='weighted_score DESC', limit=None):
        """
        Get analyzed jobs with optional filtering.

        Args:
            search_keywords: Filter by specific keyword set used for analysis
            min_score: Minimum weighted score threshold
            min_keywords: Minimum number of matched keywords
            order_by: SQL ORDER BY clause
            limit: Maximum number of results

        Returns:
            List of dicts with job and analysis data
        """
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = f"""
            SELECT
                j.id, j.title, j.company, j.location, j.posted_date, j.job_url,
                ja.description, ja.applicant_count, ja.seniority_level,
                ja.employment_type, ja.keyword_matches, ja.total_matches,
                ja.weighted_score, ja.matched_keywords, ja.match_percentage,
                ja.analyzed_at, ja.scrape_status
            FROM {self.table_name} j
            INNER JOIN job_analyses ja ON j.id = ja.job_id
            WHERE ja.weighted_score >= ?
        """
        params = [min_score]

        if search_keywords:
            query += " AND ja.search_keywords = ?"
            params.append(search_keywords)

        if min_keywords > 0:
            # Count matched keywords by comma-separated length
            query += f" AND (LENGTH(ja.matched_keywords) - LENGTH(REPLACE(ja.matched_keywords, ',', '')) + 1) >= ?"
            params.append(min_keywords)

        query += f" ORDER BY {order_by}"

        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query, params)
        rows = cursor.fetchall()

        conn.close()

        # Parse JSON fields
        results = []
        for row in rows:
            result = dict(row)
            if result.get('keyword_matches'):
                result['keyword_matches'] = json.loads(result['keyword_matches'])
            if result.get('matched_keywords'):
                result['matched_keywords'] = result['matched_keywords'].split(',')
            results.append(result)

        return results

    def get_analysis_stats(self, search_keywords=None):
        """Get statistics about analyzed jobs."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        if search_keywords:
            cursor.execute("""
                SELECT
                    COUNT(*) as total_analyzed,
                    AVG(weighted_score) as avg_score,
                    MAX(weighted_score) as max_score,
                    AVG(match_percentage) as avg_match_pct
                FROM job_analyses
                WHERE search_keywords = ?
            """, (search_keywords,))
        else:
            cursor.execute("""
                SELECT
                    COUNT(*) as total_analyzed,
                    AVG(weighted_score) as avg_score,
                    MAX(weighted_score) as max_score,
                    AVG(match_percentage) as avg_match_pct
                FROM job_analyses
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
        """
        Get job summary from the combined view.

        Returns jobs with: job_role, company, url, location, remote,
        applicant_count, seniority_level, total_matches, weighted_score,
        match_percentage, matched_keywords

        Args:
            min_score: Minimum weighted score threshold
            limit: Maximum number of results
            unique: If True, use deduplicated view (removes duplicate remote postings)

        Returns:
            List of dicts with combined job + analysis data
        """
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

        results = []
        for row in rows:
            result = dict(row)
            # Parse matched_keywords if present
            if result.get('matched_keywords'):
                result['matched_keywords'] = result['matched_keywords'].split(',')
            results.append(result)

        return results

    def export_job_summary_csv(self, filepath=None, min_score=0, unique=True):
        """
        Export job summary to CSV file.

        Args:
            filepath: Path for CSV file (default: data/job_summary.csv)
            min_score: Minimum weighted score threshold
            unique: If True, remove duplicate remote job postings (default: True)
        """
        import csv

        if filepath is None:
            filename = 'job_summary_unique.csv' if unique else 'job_summary.csv'
            filepath = self.db_file.parent.parent / filename

        jobs = self.get_job_summary(min_score=min_score, unique=unique)

        if not jobs:
            print("No jobs to export")
            return None

        # Define column order
        columns = [
            'job_role', 'company', 'url', 'location', 'remote',
            'applicant_count', 'seniority_level', 'total_matches',
            'weighted_score', 'match_percentage', 'matched_keywords'
        ]

        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
            writer.writeheader()
            for job in jobs:
                # Convert matched_keywords list to string for CSV
                if isinstance(job.get('matched_keywords'), list):
                    job['matched_keywords'] = ', '.join(job['matched_keywords'])
                writer.writerow(job)

        print(f"✅ Exported {len(jobs)} jobs to {filepath}")
        return filepath