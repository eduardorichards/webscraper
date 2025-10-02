import json
import os
from datetime import datetime
from pathlib import Path

class JSONStorage:

    def __init__(self, base_path="data"):
        self.base_path = Path(base_path)
        self.searches_path = self.base_path
        
    def save_search_results(self, search_config, jobs, search_metadata=None):
        
        filename = self._generate_search_filename(search_config)
        filepath = self.searches_path / filename
    
        search_data = {
            "search_metadata": {
                "timestamp": datetime.now().isoformat(),
                "search_config": search_config.to_dict(),
                "total_jobs_found": len(jobs),
                "filename": filename,
                **(search_metadata or {})
            },
            "jobs": [self._job_to_dict(job) for job in jobs]
        }
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(search_data, f, indent=2, ensure_ascii=False)

            print(f"Search results saved: {filename}")
            print(f"Stored {len(jobs)} jobs")
            return str(filepath)
        except Exception as e:
            print(f"Error saving results: {e}")
            return None
    
    def _generate_search_filename(self, search_config):
        timestamp = datetime.now()
        date_str = timestamp.strftime("%Y-%m-%d")
        time_str = timestamp.strftime("%H%M%S")
    
        keywords = search_config.keywords or "nosearch"
        keywords_clean = keywords.replace(" ", "-").replace("/", "-") [:20]
        
        location = search_config.location or "anylocation"
        location_clean = location.replace(" ", "-").replace(",", "") [:15]
        
        exp_levels = search_config.experience_levels or []
        if exp_levels:
            exp_str = f"exp{'-'.join(map(str, sorted(exp_levels)))}"
        else:
            exp_str = "anyexp"
            
        remote_str = "remote" if search_config.remote else "any"
        
        filename = f"{date_str}_{keywords_clean}_{location_clean}_{exp_str}_{remote_str}_{time_str}.json"
        
        filename = "".join(c for c in filename if c.isalnum() or c in ".-_")

        return filename
    
    def _job_to_dict(self, job):
        """Convert Job object to dictionary for JSON storage"""
        return {
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "work_modality": job.work_modality,
            "posted_date": job.posted_date,
            "job_url": job.job_url,
            "scraped_at": datetime.now().isoformat()
        }
    
    
