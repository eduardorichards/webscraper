# LinkedIn Job Scraper - Claude Code Context

## Project Overview
A Python-based LinkedIn job scraper that searches for job listings, extracts data, stores results in SQLite, and ranks jobs by keyword matching. Designed for tracking junior developer positions in Argentina and Latin America.

## Quick Start
```bash
# Run batch job search
python main.py

# Analyze stored jobs for keyword matches (edit main.py __main__ block)
# Change to: analyze_keywords()
```

## Project Structure
```
Job Scraper/
├── main.py                      # Entry point - multiple_search() or analyze_keywords()
├── web_app.py                   # Flask web interface for viewing results
├── config/
│   ├── settings.py              # Search templates, headers, mappings
│   └── keyword_settings.py      # Keyword matching & rate limiting config
├── scraper/
│   ├── models/
│   │   ├── job.py               # Job data model
│   │   ├── search_config.py     # Search parameters model
│   │   ├── keyword_config.py    # Keyword matching config
│   │   └── match_result.py      # Match result model
│   ├── core/
│   │   ├── scraper.py           # JobScraper - search orchestration
│   │   ├── url_builder.py       # LinkedInURLBuilder - URL construction
│   │   ├── detail_scraper.py    # DetailScraper - job page scraping
│   │   └── keyword_matcher.py   # KeywordMatcher - analysis orchestrator
│   ├── extractors/
│   │   └── linkedin_extractor.py # LinkedInExtractor - search page parsing
│   └── analyzers/
│       └── keyword_analyzer.py  # KeywordAnalyzer - regex matching
├── utils/
│   └── sqlite_storage.py        # SQLiteStorage class
├── data/
│   └── database/jobs_master.db  # SQLite database
└── tests/
    └── test_scraper.py          # Unit tests
```

## Key Classes

### Models
- **`Job`**: Represents a job listing with title, company, location, posted_date, job_url
- **`SearchConfig`**: Search parameters - keywords, location, time_posted, remote, experience_levels, max_results
- **`KeywordConfig`**: Keywords to match with optional weights for scoring
- **`MatchResult`**: Stores keyword match analysis results per job

### Core
- **`JobScraper`**: Main search orchestrator - builds URLs, fetches search pages, extracts job cards
- **`DetailScraper`**: Scrapes individual job pages for descriptions, applicant counts
- **`KeywordMatcher`**: Orchestrates keyword analysis workflow
- **`LinkedInURLBuilder`**: Builds LinkedIn search URLs
- **`LinkedInExtractor`**: Parses LinkedIn search results HTML

### Analyzers
- **`KeywordAnalyzer`**: Regex-based keyword matching with weighted scoring

### Storage
- **`SQLiteStorage`**: Primary storage with jobs and job_analyses tables

## Data Flow

### Job Search Flow
```
main.py → multiple_search()
  → For each SEARCH_TEMPLATE:
    → JobScraper.search_jobs(config)
      → LinkedInURLBuilder.build_url()
      → requests.get(url)
      → LinkedInExtractor.extract_jobs(soup)
      → SQLiteStorage.append_jobs(jobs)
```

### Keyword Analysis Flow
```
main.py → analyze_keywords()
  → KeywordMatcher.analyze_jobs()
    → SQLiteStorage.get_jobs_without_analysis()
    → For each job:
      → DetailScraper.scrape_job_details(url)  [2-4s delay]
      → KeywordAnalyzer.analyze(description)
      → SQLiteStorage.save_job_analysis()
    → Sort by weighted_score
    → Display ranked results
```

## Configuration

### Search Templates (`config/settings.py`)
12 predefined searches in `SEARCH_TEMPLATES` list with:
- `keywords`, `location`, `experience_levels`, `remote`, `time_posted`, `max_results`

### Keyword Settings (`config/keyword_settings.py`)
```python
SCRAPE_MIN_DELAY = 2      # seconds
SCRAPE_MAX_DELAY = 4      # seconds
BATCH_SIZE = 50           # pause every N jobs
BATCH_PAUSE = 30          # seconds between batches
DEFAULT_KEYWORDS = [...]  # default keywords to match
WEIGHTED_KEYWORDS = {...} # keyword weights for scoring
```

### Experience Level Codes
```
1: Internship, 2: Entry level, 3: Associate,
4: Mid-Senior, 5: Director, 6: Executive
```

## Database Schema

### jobs table
```sql
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT, company TEXT, location TEXT, posted_date TEXT,
    job_url TEXT UNIQUE,
    search_keywords TEXT, search_location TEXT,
    search_experience TEXT, search_remote TEXT
)
```

### job_analyses table
```sql
CREATE TABLE job_analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    job_name TEXT,
    company TEXT,
    job_url TEXT,
    description TEXT,
    applicant_count INTEGER,
    employment_type TEXT,
    job_function TEXT,
    total_matches INTEGER,
    weighted_score REAL,
    matched_keywords TEXT,
    match_percentage REAL,
    analyzed_at TIMESTAMP,
    scrape_status TEXT,
    FOREIGN KEY (job_id) REFERENCES jobs(id),
    UNIQUE(job_id)
)
```

## LinkedIn HTML Selectors

### Search Results Page
- Job card: `div.job-search-card`
- Title: `h3.base-search-card__title`
- Company: `h4.base-search-card__subtitle`
- Location: `span.job-search-card__location`
- URL: `a.job-card-container__link`

### Job Detail Page
- Description: `div.show-more-less-html__markup`
- Applicants: `span.num-applicants__caption`
- Criteria: `li.description__job-criteria-item`

## SQL Views

### job_summary
Combined view of jobs + analysis data with all fields.

### job_summary_unique
Deduplicated view - removes duplicate remote job postings (same title + company).
Keeps the one with lowest applicant count.

```sql
-- Query deduplicated results
SELECT * FROM job_summary_unique;

-- Query all results (with duplicates)
SELECT * FROM job_summary;
```

## Common Tasks

### Export to CSV (one-liner)
```bash
python3 -c "from utils.sqlite_storage import SQLiteStorage; SQLiteStorage().export_job_summary_csv()"
```
Creates `data/job_summary_unique.csv` with deduplicated results.

### Run keyword analysis on stored jobs
```python
from main import analyze_keywords

# With default keywords (from config/keyword_settings.py)
results = analyze_keywords()

# With custom keywords
results = analyze_keywords(
    keywords=["Python", "Django", "Docker"],
    weights={"Python": 2.0, "Django": 1.5},
    top_n=20
)
```

### Get job summary (Python)
```python
from utils.sqlite_storage import SQLiteStorage
storage = SQLiteStorage()

# Get deduplicated results
jobs = storage.get_job_summary(unique=True)

# Get all results (with duplicates)
jobs = storage.get_job_summary(unique=False)

# Export to CSV
storage.export_job_summary_csv()  # Deduplicated by default
storage.export_job_summary_csv(unique=False)  # All results
```

### Get ranked jobs from database
```python
from scraper import KeywordMatcher, KeywordConfig
from utils.sqlite_storage import SQLiteStorage

keyword_config = KeywordConfig(keywords=["Python", "Django"])
storage = SQLiteStorage()
matcher = KeywordMatcher(storage, keyword_config)

# Get top jobs by score
top_jobs = matcher.get_ranked_jobs(min_score=5, limit=20)
```

### Query analysis statistics
```python
from utils.sqlite_storage import SQLiteStorage

storage = SQLiteStorage()
stats = storage.get_analysis_stats()
print(f"Analyzed: {stats['total_analyzed']}, Avg score: {stats['avg_score']:.1f}")
```

## Rate Limiting
- 2-4 second random delays between requests
- 30 second pause every 50 jobs
- Retry with 60s wait on 429 errors
- User-agent rotation
- ~10-12 minutes for 200 jobs

## Known Limitations
1. **Max ~60 jobs per search**: LinkedIn pagination not yet implemented
2. **Rate limiting**: May get blocked if running too frequently

## Dependencies
- `requests` - HTTP requests
- `beautifulsoup4` - HTML parsing
- `lxml` - Parser backend
- `flask` - Web interface
- `sqlite3` - Database (built-in)

## File Locations
- Database: `data/database/jobs_master.db`
