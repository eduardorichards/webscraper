"""SQLite storage for job search results with duplicate prevention"""
import sqlite3
from pathlib import Path


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
        print(f"✅ SQLite database ready at: {self.db_file}")
    
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