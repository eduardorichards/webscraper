# LinkedIn Job Scraper

A Python application that scrapes job listings from LinkedIn based on configurable search parameters and stores results in a SQLite database.

## Features

- Search LinkedIn jobs by keywords, location, experience level, and work mode (remote/on-site)
- Batch searching with multiple predefined search templates
- SQLite storage with automatic duplicate prevention
- Optional JSON export for individual searches
- Configurable time filters (24h, 1 week, 1 month)

## Installation

1. Clone the repository
2. Install dependencies:
```bash
pip install -r requirements.txt
```
3. Optionally copy `.env.example` to `.env` and adjust (see [Environment configuration](#environment-configuration))

## Usage

### Run batch search (all templates)
```bash
python main.py
```

This executes all search templates defined in `config/settings.py` and saves results to the SQLite database.

### Run a single custom search
```python
from scraper import JobScraper, SearchConfig

config = SearchConfig(
    keywords="python developer",
    location="Argentina",
    experience_levels=[1, 2],  # 1=Internship, 2=Entry level
    remote=True,
    time_posted="24",  # Last 24 hours
    max_results=50
)

scraper = JobScraper()
jobs = scraper.search_jobs(config, save_results=True)

for job in jobs:
    print(f"{job.title} at {job.company}")
```

## Configuration

### Environment configuration

Environment-specific settings are read from environment variables, or from a `.env` file in
the project root (see `.env.example`). Without a `.env`, the defaults below apply.

| Variable | Default | Description |
|---|---|---|
| `PORT` | `5000` | Web app port (1–65535) |
| `HOST` | `0.0.0.0` | Web app bind address |
| `FLASK_DEBUG` | `false` | Flask debug mode; refused unless `HOST` is `127.0.0.1`, `localhost` or `::1` |
| `DEFAULT_PER_PAGE` | `50` | Default page size; one of 25, 50, 100, 200 |
| `DB_PATH` | `data/database/jobs_master.db` | SQLite database file |
| `LOG_DIR` | `data/logs` | Directory for `scraper.log`, `cron.log`, `scraper.lock` |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL` |
| `SCRAPE_MIN_DELAY` / `SCRAPE_MAX_DELAY` | `2` / `4` | Random delay (s) between job detail requests |
| `BATCH_SIZE` | `50` | Detail requests per batch before pausing |
| `BATCH_PAUSE` | `30` | Pause (s) between batches |
| `RETRY_DELAY` | `60` | Wait (s) before retrying after HTTP 429 |
| `MAX_RETRIES` | `3` | Max retries per job on HTTP 429 |
| `SEARCH_MIN_DELAY` / `SEARCH_MAX_DELAY` | `2` / `4` | Random delay (s) between search templates |

Relative `DB_PATH` / `LOG_DIR` resolve from the project root. Empty or unset variables use
the default; invalid values raise `ConfigError` at startup. Real environment variables take
precedence over `.env`. `.env` is read by python-dotenv, bash `source` (`run_scraper.sh`) and
systemd `EnvironmentFile`, so keep it to plain `KEY=value` lines: no quotes, no inline comments,
no `export`, no `$VAR` or `~`.

Search templates, experience levels and keywords are domain config and stay in `config/`.

### Search Templates

Edit `config/settings.py` to modify or add search templates:

```python
SEARCH_TEMPLATES = [
    {
        "name": "Python Developer Argentina",
        "keywords": "Python Developer",
        "location": "Argentina",
        "experience_levels": [1, 2],
        "remote": True,
        "time_posted": "24",
        "max_results": 100
    },
    # Add more templates...
]
```

### Experience Levels

| Code | Level |
|------|-------|
| 1 | Internship |
| 2 | Entry level |
| 3 | Associate |
| 4 | Mid-Senior level |
| 5 | Director |
| 6 | Executive |

### Time Filters

| Value | Period |
|-------|--------|
| `"24"` | Last 24 hours |
| `"1w"` | Last week |
| `"1m"` | Last month |

## Project Structure

```
Job Scraper/
├── main.py                 # Main entry point
├── config/
│   ├── settings.py         # Search templates and settings
│   └── storage_setting.py  # Storage paths
├── scraper/
│   ├── models/             # Data models (Job, SearchConfig)
│   ├── core/               # Scraper and URL builder
│   └── extractors/         # LinkedIn HTML parser
├── utils/
│   ├── sqlite_storage.py   # SQLite database handler
│   └── json_storage.py     # JSON file storage
└── data/
    └── database/           # SQLite database location
```

## Database

Jobs are stored in `data/database/jobs_master.db` with the following schema:

| Column | Description |
|--------|-------------|
| id | Auto-increment primary key |
| title | Job title |
| company | Company name |
| location | Job location |
| posted_date | When the job was posted |
| job_url | LinkedIn job URL (unique) |
| search_keywords | Keywords used in search |
| search_location | Location used in search |
| search_experience | Experience levels searched |
| search_remote | Whether remote filter was applied |

Duplicates are automatically prevented via the unique `job_url` constraint.

## Querying Results

```python
from utils.sqlite_storage import SQLiteStorage

storage = SQLiteStorage()
stats = storage.get_stats()

print(f"Total jobs: {stats['total_jobs']}")
print(f"Unique companies: {stats['unique_companies']}")
print(f"Unique locations: {stats['unique_locations']}")
```

## Keyword Analysis

Analyze stored jobs for keyword matches and rank by relevance:

```bash
# Edit main.py to call analyze_keywords() instead of multiple_search()
python main.py
```

Configure keywords in `config/keyword_settings.py`:
```python
DEFAULT_KEYWORDS = ["Python", "Java", "Docker", ...]
WEIGHTED_KEYWORDS = {"Python": 2.0, "Java": 2.5, ...}
```

## Export to CSV

Export analyzed jobs to CSV (deduplicated - removes duplicate remote postings):

```bash
python3 -c "from utils.sqlite_storage import SQLiteStorage; SQLiteStorage().export_job_summary_csv()"
```

Creates `data/job_summary_unique.csv` with columns:
- job_role, company, url, location, remote
- applicant_count, seniority_level
- total_matches, weighted_score, match_percentage

## SQL Views

Query directly in any SQLite tool:
```sql
SELECT * FROM job_summary_unique;  -- Deduplicated results
SELECT * FROM job_summary;          -- All results
```

## Known Limitations

- Maximum ~60 jobs per search (LinkedIn pagination not yet implemented)
- Only extracts data visible on search results page (not full job descriptions)
- No explicit rate limiting (use responsibly)

## Dependencies

- requests
- beautifulsoup4
- lxml
- pandas
- python-dotenv
- selenium (for future features)

## License

MIT
