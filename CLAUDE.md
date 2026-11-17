# LinkedIn Job Scraper - Claude Code Context

## Project Overview
A Python-based LinkedIn job scraper that searches for job listings, extracts data, stores results in SQLite, and ranks jobs by keyword matching. Designed for tracking junior developer positions in Argentina and Latin America. A second collector reads the public Greenhouse / Lever / Ashby job boards of a curated company list into the same tables (see "ATS sources").

## Quick Start
```bash
# Run full pipeline: search + keyword analysis
python main.py
```
`main.py` calls `setup_logging()`, then runs `multiple_search()` followed by `analyze_keywords()` in sequence. Logs go to both stdout and `data/logs/scraper.log`.

```bash
# ATS boards only (Greenhouse / Lever / Ashby, config/companies.json); no LinkedIn requests
python main.py --source ats
```
`--source linkedin` is the default (the pipeline above, unchanged). Meant to run daily from
cron via `run_scraper.sh --source ats` (see "Cron").

## Development Notes

- The DB can be large (~100k jobs, ~490 MB in production). Any feature that lists jobs must be paginated/limited; never render the full table.
- All code, comments, UI text, docs and commit messages must be in English.
- Do not run the scraper (`main.py`) unless explicitly asked — it hits LinkedIn and can get the IP blocked.
- Pushing to `main` deploys to production automatically (see "Server Deployment"). Do not push
  unless explicitly asked, and never SSH into the server.
- The server runs Python 3.8: code must stay 3.8 compatible. No `X | Y` type unions, no
  built-in generics like `list[int]` / `dict[str, int]` in annotations (use `typing.List` etc.),
  no `str.removeprefix` / `removesuffix`, no `zoneinfo`, no `match` statements. CI runs the tests
  on 3.8.
- Environment-specific config (ports, paths, log level, rate limits) lives in `config/env.py`,
  read from environment variables / `.env` (template: `.env.example`). Domain config (search
  templates, mappings, headers, keywords) stays in `config/settings.py` and
  `config/keyword_settings.py` — don't move it to env. With no `.env`, defaults match the
  previous hardcoded values.

### Environment variables
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
| `SEARCH_MIN_DELAY` / `SEARCH_MAX_DELAY` | `2` / `4` | Random delay (s) between search templates and between result pages |
| `SEARCH_MAX_PAGES` | `4` | Result pages per search template (1–100): first page + "See more jobs" pages |
| `ATS_MIN_DELAY` / `ATS_MAX_DELAY` | `1` / `2` | Random delay (s) between companies with `--source ats` |

Relative `DB_PATH` / `LOG_DIR` resolve from the project root. Empty or unset variables use
the default; invalid values raise `ConfigError` at startup. Real environment variables take
precedence over `.env`. `.env` is read by python-dotenv, bash `source` (`run_scraper.sh`) and
systemd `EnvironmentFile`, so keep it to plain `KEY=value` lines: no quotes, no inline comments,
no `export`, no `$VAR` or `~`.

## Project Structure
```
Job Scraper/
├── main.py                      # Entry point - search + analysis pipeline; --source ats
├── web_app.py                   # Flask web interface for viewing results
├── run_scraper.sh               # Cron wrapper (lock file, virtualenv, logging)
├── deploy.sh                    # Server-side deploy (SSH forced command from CI)
├── job-scraper-web.service      # systemd unit for Flask web app
├── .env.example                 # Documented environment variables (copy to .env)
├── .github/
│   ├── workflows/ci.yml         # CI: tests on 3.8; deploy on push to main
│   └── dependabot.yml           # Weekly GitHub Actions updates
├── config/
│   ├── env.py                   # Environment config (env vars / .env, validated)
│   ├── settings.py              # Search templates, headers, mappings, seniority targets
│   ├── keyword_settings.py      # Keywords, weights, user agents
│   ├── aggregators.json         # Aggregator companies (category, reason)
│   └── companies.json           # ATS boards to read (name, ats, slug, ...)
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
│   ├── analyzers/
│   │   └── keyword_analyzer.py  # KeywordAnalyzer - regex matching
│   └── sources/
│       ├── ats_client.py        # fetch_board(), parse_greenhouse/lever/ashby() → AtsJob
│       └── ats_collector.py     # collect_ats(): runs, location filter, store + score
├── scripts/
│   ├── backfill_apply_type.py   # One-off apply_type backfill (fetches LinkedIn)
│   └── rescore_jobs.py          # Re-score stored descriptions (no fetching)
├── utils/
│   ├── sqlite_storage.py        # SQLiteStorage class (schema + migrations)
│   ├── aggregators.py           # load_aggregators() for config/aggregators.json
│   ├── companies.py             # load_companies() for config/companies.json
│   ├── job_keys.py              # Job keys per source, source_of(), job_url_for()
│   ├── location_filter.py       # check_location() for ATS postings (AR / LATAM)
│   ├── seniority.py             # levels_above() for "Hide above my level"
│   └── time_utils.py            # utc_now_iso() timestamp helper
├── data/
│   ├── database/jobs_master.db  # SQLite database
│   └── logs/                    # scraper.log, cron.log, scraper.lock
└── tests/
    ├── test_scraper.py          # Unit tests
    ├── test_sqlite_storage.py   # Storage tests
    ├── test_migrations.py       # Schema migration idempotency
    ├── test_search_runs.py      # search_runs tracking (HTTP mocked)
    ├── test_search_templates.py # SEARCH_TEMPLATES structure (AR/LATAM pairs, levels, no OR)
    ├── test_keyword_settings.py # Weight keys match keywords; no case-insensitive duplicates
    ├── test_applicant_parsing.py # Applicant caption parsing
    ├── test_apply_detection.py  # Apply type / closed-job detection (uses fixtures/)
    ├── test_web_app.py          # Web UI filters, chips, presentation, applications API
    │                            # (Flask test client)
    ├── test_backfill_apply_type.py # Backfill selection, no-overwrite, lock (HTTP mocked)
    ├── test_pagination.py       # "See more jobs" pagination, 429, search_runs pages (HTTP mocked)
    ├── test_job_ids.py          # 10-digit job ID extraction/validation
    ├── test_job_criteria.py     # Criteria parsing on a current job page (no job function)
    ├── test_aggregators.py      # Aggregator file, table sync, detail-fetch skip
    ├── test_shortlist.py        # /api/shortlist params, fixed filters, ordering, limit
    ├── test_seniority.py        # "Above my level" rule
    ├── test_scoring_version.py  # scoring_version hash, rescore script
    ├── test_job_keys.py         # Key format, source_of(), job_url_for()
    ├── test_location_filter.py  # Allowlist, bare "Remote" vs US-only descriptions
    ├── test_ats_client.py       # Greenhouse/Lever/Ashby parsing, dates, fetch errors
    ├── test_companies.py        # companies.json validation, table sync keeps check stats
    ├── test_ats_collector.py    # Collection into the DB, runs, skips; LinkedIn flow,
    │                            # web UI, applications, shortlist, backfill with ATS keys
    ├── fixtures/                # Trimmed logged-out pages: job pages (easy apply, external,
    │                            # criteria), search page, "See more jobs" page; trimmed
    │                            # Greenhouse / Lever / Ashby board responses (*.json)
    ├── test_run_scraper.py      # Cron wrapper: argument forwarding, log lines, shared lock
    └── test_env.py              # config/env.py tests
```

## Key Classes

### Models
- **`Job`**: Represents a job listing with title, company, location, posted_date, job_url
- **`SearchConfig`**: Search parameters - keywords, location, time_posted, remote, experience_levels, max_results
- **`KeywordConfig`**: Keywords to match with optional weights for scoring
- **`MatchResult`**: Stores keyword match analysis results per job; `job_url` is built from
  the key (LinkedIn) or `source_url` (other sources)

### Core
- **`JobScraper`**: Main search orchestrator - builds URLs, fetches the search page and "See more
  jobs" pages, extracts job cards; per-run stats in `last_jobs_found`, `last_new_jobs`,
  `last_pages_fetched`, `last_hit_page_limit`
- **`DetailScraper`**: Scrapes individual job pages for descriptions, applicant counts
- **`KeywordMatcher`**: Orchestrates keyword analysis workflow; skips aggregator companies
- **`LinkedInURLBuilder`**: Builds LinkedIn search URLs (`build_url`) and "See more jobs" URLs
  (`build_see_more_url(config, start)`)
- **`LinkedInExtractor`**: Parses LinkedIn search results HTML

### Analyzers
- **`KeywordAnalyzer`**: Regex-based keyword matching with weighted scoring

### Storage
- **`SQLiteStorage`**: Primary storage (`search_runs`, `job_searches`, `job_posts`,
  `blacklisted_companies`, `aggregator_companies`, `applications`, `companies`); creates and
  migrates the schema and syncs the aggregator and company lists on init

### ATS sources (`scraper/sources/`)
- **`AtsJob`**: normalized posting (key, source, slug, company, title, locations,
  description, job_url, apply_url, posted_at, employment_type, remote)
- **`fetch_board(company)`**: one GET per board; raises `AtsError` on HTTP errors, timeouts
  and bad payloads; an empty board returns `[]`
- **`collect_ats(storage, keyword_config)`**: per company, run → filter → store → score

## Data Flow

### Job Search Flow
```
main.py → multiple_search()
  → For each SEARCH_TEMPLATE:
    → SQLiteStorage.start_search_run()          [search_runs row, status NULL]
    → JobScraper.search_jobs(config, search_run_id, raise_errors=True)
      → for each page (at most SEARCH_MAX_PAGES):
        → page 1: LinkedInURLBuilder.build_url()
          later:  sleep(SEARCH_*_DELAY); build_see_more_url(config, start=cards so far)
        → requests.get(url)                     [429 → wait RETRY_DELAY, MAX_RETRIES times]
        → LinkedInExtractor.extract_jobs(soup)  [skips cards without a 10-digit ID]
        → SQLiteStorage.append_jobs(jobs, ...)  [IDs already seen this run dropped]
        → stop if: short page (< 60 first / < 10 later), only repeated IDs, max_results
    → SQLiteStorage.finish_search_run()         [status 'ok', or 'error' + message;
                                                 pages_fetched, hit_page_limit]
```

### ATS Collection Flow
```
main.py --source ats → collect_ats_jobs() → collect_ats(storage, keyword_config)
  → for each active row of companies (data-file order), ATS_*_DELAY between companies:
    → start_search_run("ats:<ats>:<slug>", "ats", slug)
    → fetch_board(company)                      [15 s timeout; AtsError → run 'error']
    → for each posting: check_location()        [dropped: not stored]
      → skip if the key is in job_searches or job_posts (never re-scored)
      → add_ats_job()                           [job_searches row: source, job_url]
      → aggregator company: stop here (no job_posts row, like LinkedIn)
      → score_job() + save_job_analysis()       [apply_type 'external', posted_at]
    → finish_search_run(jobs_found=postings returned, new_jobs=stored, pages_fetched=1)
    → mark_company_checked(name, postings returned; 0 on errors)
```

### Keyword Analysis Flow
```
main.py → analyze_keywords(since=<pipeline start>)
  → KeywordMatcher.analyze_jobs(since)
    → SQLiteStorage.get_jobs_without_analysis() [LinkedIn IDs only; excludes aggregator_companies]
    → log "Skipped N detail fetches for aggregator companies"
                                                [count_skipped_aggregator_jobs(since)]
    → For each job:
      → DetailScraper.scrape_job_details(url)  [2-4s delay; parse_applicant_text(),
                                                parse_apply_type(); {'closed': True} if expired]
      → KeywordAnalyzer.analyze(description)
      → MatchResult.calculate_score()           [sets scoring_version]
      → SQLiteStorage.save_job_analysis()
    → Sort by weighted_score
    → Display ranked results
```

## Configuration

### Search Templates (`config/settings.py`)
24 searches in `SEARCH_TEMPLATES`, built by `_search_pair(group, keywords)`: each group runs
twice, `"<Group> AR"` (location Argentina, `remote` False) and `"<Group> LATAM"` (Latin America,
`remote` True). List order = priority (`multiple_search()` runs them top to bottom):

| Tier | Groups (one keyword each) |
|---|---|
| 1 | Java, QA Automation, Automatizador, AI Engineer, LLM, Backend |
| 2 | Python, AWS, Playwright |
| 3 | Fullstack, Software Developer, DevOps |

- One term per template, no quotes: the logged-out search doesn't honor `OR` (2026-11-17:
  `"QA Automation" OR SDET` → 4,000+ results vs 7,000+ for `SDET` alone). Its matching is fuzzy,
  so a term also surfaces close variants (`SDET` → "QA Automation" titles), which is why
  Spring Boot, SDET, Test Automation, Selenium, Serverless, etc. have no template of their own.
- `experience_levels` `[1, 2, 3]` (matches `TARGET_SENIORITY_LEVELS`; LinkedIn barely enforces it)
- `time_posted` is `"2h"`, twice the hourly cron interval, so consecutive runs overlap (see "Cron")
- `max_results` (250) caps the whole run across pages
- Worst case per run: 24 × `SEARCH_MAX_PAGES` (4) = 96 search requests, ~7 min of search
  delays; most templates return < 60 cards in two hours, so usually ~24–30. Detail requests are
  separate (one per new job).
- Covered by `tests/test_search_templates.py`.

### Pagination (`config/settings.py`)
- `LINKEDIN_SEE_MORE_URL`: guest endpoint behind "See more jobs"
  (`jobs-guest/jobs/api/seeMoreJobPostings/search`): same query params as the search page plus
  `start=<cards already shown>`; returns bare `<li>` job cards with the same markup. Verified
  on 2026-11-14 (search page 60 cards, `start=60` → next 10, no overlap).
- `SEARCH_FIRST_PAGE_SIZE = 60`, `SEARCH_MORE_PAGE_SIZE = 10`: a page with fewer cards is the
  last one. If LinkedIn shrinks them, pagination just stops early.
- `hit_page_limit = 1` means the last allowed page was still full: results were left
  unfetched (logged as a warning). Raise `SEARCH_MAX_PAGES` if it's frequent.

### Seniority (`config/settings.py`)
- LinkedIn no longer enforces `f_E` (~52% of results are Mid-Senior since Aug 2026).
- `SENIORITY_ORDER` (from `EXPERIENCE_LEVELS`) ranks `job_posts.seniority_level` values;
  `TARGET_SENIORITY_LEVELS` (default Internship, Entry level, Associate) are mine.
- `levels_above()` (`utils/seniority.py`) → `SQLiteStorage.ABOVE_TARGET_LEVELS`; the
  `hide_above_level` filter hides those. NULL, "Not Applicable" and unknown values are never
  hidden. Computed at query time, nothing stored or deleted. An unknown target name raises
  `ValueError` at import.
- The same filter also hides by title (`title_above_level()`, registered as a SQLite function
  in `SQLiteStorage._connect_summary()`): whole-word, case-insensitive match of
  `ABOVE_LEVEL_TITLE_TERMS` (Senior/Sr/Lead/Director/Head/Staff/Principal/Architect/Manager
  and Spanish equivalents), unless the title also matches `TARGET_LEVEL_TITLE_TERMS`
  (Jr/Junior/Ssr/Semi-senior/Trainee/Intern/Pasante). Applies to the web UI and `/api/shortlist`.

### Aggregators (`config/aggregators.json`)
- Hand-checked list from the market analysis: `categories` (`job_board`,
  `talent_marketplace`, `mass_reposter`) and `companies` (`company`, `category`, `reason`),
  matched by exact company name. Industry/name-pattern rules were deliberately left out.
- Don't import from `analysis/` (it's moving to its own repo); edit the JSON instead.

### ATS sources (`config/companies.json`)
- Entries: `name` (stored as `job_searches.company`, so blacklist/aggregator matching uses
  it), `ats` (`greenhouse` / `lever` / `ashby`), `slug`, optional `priority`,
  `hires_in_ar`, `notes`, `active` (default true). Synced into `companies` on every init.
- APIs (public, no auth; User-Agent `ats_client.USER_AGENT`):
  - Greenhouse `https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true`:
    `content` is HTML-escaped HTML; posted = `first_published`, else `updated_at`;
    locations = `location.name` + `offices[].location` + `offices[].name`. Also serves
    EU-hosted boards (Valtech); `boards-api.eu.greenhouse.io` doesn't resolve (2026-11-17).
  - Lever `https://api.lever.co/v0/postings/{slug}?mode=json`: description =
    `descriptionPlain` + `lists[]` (header + HTML stripped) + `additionalPlain`; posted =
    `createdAt` (ms); locations = `categories.location` + `allLocations`, plus "Argentina"
    when `country` is `AR`.
  - Ashby `https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true`:
    locations = `location` + `secondaryLocations[].location`; unlisted postings skipped.
- `employment_type` is mapped to LinkedIn's names (`Full-time`, `Part-time`, `Contract`,
  `Internship`, `Temporary`); anything else (Lever's free-text commitments) → NULL.
- Location filter (`utils/location_filter.py`), first match wins:
  1. any location matches the allowlist (whole words, case/accent-insensitive): Argentina,
     Buenos Aires, CABA, Capital Federal, LATAM, Latin America, Latinoamérica, South
     America, Americas, AMER, Anywhere, Worldwide, Global ("Anywhere in X" counts as X) → keep;
  2. bare "Remote" (or no location on a remote posting) → keep unless the description is
     US-only ("based in the US", "US-based", "U.S. only", "authorized to work in the United
     States", "must reside in the US"...);
  3. anything else (other countries/cities, "Remote - US") → drop, not stored.
- A board that suddenly returns 404 or an empty list may have moved to another ATS: check the
  company's careers page for the board it embeds (2026-11-17: Webflow and Stensul had moved
  from Greenhouse to Ashby, same slugs). The `ats:<ats>:<slug>` runs keep the history.

### Keyword Settings (`config/keyword_settings.py`)
```python
USER_AGENTS = [...]       # user-agent rotation pool
DEFAULT_KEYWORDS = [...]  # default keywords to match
WEIGHTED_KEYWORDS = {...} # keyword weights for scoring
```

### Experience Level Codes
```
1: Internship, 2: Entry level, 3: Associate,
4: Mid-Senior, 5: Director, 6: Executive
```

## Database Schema

Defined in `SQLiteStorage._ensure_db_exists()` (`utils/sqlite_storage.py`), which runs on
every `SQLiteStorage()` init inside one `BEGIN IMMEDIATE` transaction. Tables are
`CREATE TABLE IF NOT EXISTS`; views are dropped and recreated each time. `job_searches` and
`job_posts` are joined by `linkedin_job_id` (no foreign key).

### Migrations
Schema changes must be idempotent and lossless, added to `_create_schema()`:
- New columns: `_add_column_if_missing(cursor, table, column, definition)` (checks
  `PRAGMA table_info`, then `ALTER TABLE ... ADD COLUMN`; returns `True` if it added the column).
  Existing rows get NULL; don't backfill with made-up values.
- One-time data fixes: run them only inside `if self._add_column_if_missing(...):` for the column
  they introduce, so they never re-run on rows written later.
- Covered by `tests/test_migrations.py` (legacy DB → migrate twice → same data).

- Aggregator list: `_sync_aggregators()` runs on every init, after the migrations; it
  inserts/updates/deletes `aggregator_companies` rows to match `config/aggregators.json`
  (`SQLiteStorage(aggregators_file=...)` overrides the path, used by tests).

### search_runs table
One row per search template execution in `main.multiple_search()`.
```sql
CREATE TABLE search_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_name TEXT,                -- template "name"
    keywords TEXT,
    location TEXT,
    started_at TEXT,                   -- UTC ISO-8601
    finished_at TEXT,                  -- UTC ISO-8601; NULL = interrupted
    jobs_found INTEGER,                -- jobs extracted from the search page
    new_jobs INTEGER,                  -- linkedin_job_ids not in job_searches before this run
    status TEXT CHECK (status IN ('ok', 'error')),  -- NULL = interrupted
    error TEXT,                        -- exception message when status = 'error'
    pages_fetched INTEGER,             -- result pages fetched; NULL before pagination
    hit_page_limit INTEGER             -- 1 = stopped at SEARCH_MAX_PAGES with a full last page
)
```

### job_searches table
One row per search hit — the same `linkedin_job_id` can appear many times (once per
search template that found it). ATS jobs get one row (first collection), with
`search_keywords = 'ats'` and `search_location = <slug>`.
```sql
CREATE TABLE job_searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    linkedin_job_id TEXT,              -- NOT unique
    title TEXT,
    company TEXT,
    location TEXT,
    company_url TEXT,
    search_keywords TEXT,
    search_location TEXT,
    search_experience TEXT,
    search_remote TEXT,
    scraped_at TEXT,                   -- UTC, when the search page was fetched (NULL on old rows)
    search_run_id INTEGER REFERENCES search_runs(id),  -- NULL on old rows
    source TEXT,                       -- NULL = LinkedIn; 'greenhouse' | 'lever' | 'ashby'
    job_url TEXT                       -- posting URL for non-LinkedIn jobs; NULL for LinkedIn
)
-- INDEX idx_job_searches_linkedin_id ON job_searches(linkedin_job_id)
-- INDEX idx_job_searches_run         ON job_searches(search_run_id)
```

### job_posts table
One row per job: details scraped from the job page plus keyword analysis results.
```sql
CREATE TABLE job_posts (
    linkedin_job_id TEXT UNIQUE NOT NULL,
    description TEXT,
    applicant_count INTEGER,
    date_time TIMESTAMP,               -- when analysis ran (set even if the fetch failed)
    total_matches INTEGER,
    weighted_score REAL,
    matched_keywords TEXT,
    match_percentage REAL,
    employment_type TEXT,
    job_function TEXT,
    seniority_level TEXT,
    industries TEXT,
    scraped_at TEXT,                   -- UTC, when details were fetched; NULL if the fetch failed or old row
    applicant_count_qualifier TEXT,    -- 'under' | 'over' | NULL (exact)
    apply_type TEXT,                   -- 'easy_apply' | 'external' | NULL (unknown)
    apply_url TEXT,                    -- external apply URL; currently always NULL (see below)
    scoring_version TEXT,              -- KeywordConfig.scoring_version() of the score; NULL if
                                       -- scored before versioning or nothing scored
    posted_at TEXT                     -- posting date from the source (ATS jobs); NULL for LinkedIn
)
-- INDEX idx_job_posts_score    ON job_posts(weighted_score DESC)
-- INDEX idx_job_posts_datetime ON job_posts(date_time DESC)
-- INDEX idx_job_posts_employment_type ON job_posts(employment_type)  -- employment type options
```

### Applicant count
Logged-out LinkedIn shows bounds, not exact counts, at both ends.
`parse_applicant_text()` in `detail_scraper.py` returns `(count, qualifier)`:

| Caption (`.num-applicants__caption`) | applicant_count | applicant_count_qualifier |
|---|---|---|
| "Be among the first 25 applicants" / "…primeros 25…" | 25 | `under` (fewer than 25) |
| "Over 200 applicants" / "Más de 200…" | 200 | `over` (more than 200) |
| "87 applicants" | 87 | NULL (exact) |

Historical data (before the qualifier column existed):
- The old parser stored "Over 200" as `201`. The migration rewrites those rows once (when it
  adds the qualifier column) to `200` / `over` — 2,800 rows in a local DB copy on 2026-11-14.
- The old parser stored "Be among the first N" as `25` with no qualifier, indistinguishable
  from an exact 25. **Historical `applicant_count = 25` with NULL qualifier most likely means
  "under 25"** (~82% of `job_posts` rows in a local DB copy on 2026-11-14). The migration leaves
  them untouched.
- When sorting/filtering by applicants, treat `25`+NULL like `25`+`under`.

### Application type
Logged-out job pages show an "Apply" button for both types; there is no visible "Easy Apply"
label. `parse_apply_type()` in `detail_scraper.py` reads LinkedIn's tracking names on the
apply controls (verified against logged-in pages on 2026-11-14):

| Marker (`data-tracking-control-name`) | apply_type |
|---|---|
| `public_jobs_apply-link-onsite` (Apply button) | `easy_apply` |
| `public_jobs_apply-link-offsite_...` (sign-in modal) | `external` |
| neither, both, or a "No longer accepting applications" notice | NULL |

- Unknown/closed must never become `easy_apply`.
- The external target URL is not exposed to logged-out visitors, so `apply_url` is saved as
  NULL. The column and UI link are kept for when it can be extracted.
- Closed jobs: `is_closed_job_url()` flags a fetch whose final URL has `trk=expired_jd_redirect`
  or no `/jobs/view/` in its path (LinkedIn redirects expired jobs to a search page).
  `scrape_job_details()` returns `{'closed': True}` and `KeywordMatcher` saves the row like a
  failed fetch (no description, `scraped_at` NULL, `apply_type` NULL).
- These are tracking names, not a public contract: if LinkedIn changes them, detection falls
  back to NULL. Re-check against `tests/fixtures/` and a live page.
- Migration doesn't backfill; `scripts/backfill_apply_type.py` can fill recent rows (see
  "Common Tasks"). Web UI filter: `?apply=easy_apply|external|unknown`
  (`unknown` = `apply_type IS NULL`, which includes all rows analyzed before the column existed).

### Job keys (`utils/job_keys.py`)
`linkedin_job_id` is the job key for every source (not renamed). LinkedIn keys are the
numeric ID; ATS keys are `greenhouse:{slug}:{id}`, `lever:{slug}:{id}`, `ashby:{slug}:{id}`.
Use the helpers instead of parsing keys: `is_linkedin_key()` (no `:`; SQL:
`LINKEDIN_KEY_SQL`), `source_of()`, `is_valid_key()` (API validation), `make_key()`,
`job_url_for(key, stored_url)` (LinkedIn URL from the ID, else `job_searches.job_url`).
Anything that fetches LinkedIn (`_PENDING_JOBS_SQL`, `backfill_apply_type.py`) only selects
LinkedIn keys.

### Job IDs
`LinkedInExtractor` takes `linkedin_job_id` from the card's `data-entity-urn`
(`urn:li:jobPosting:<id>`), falling back to the **last** number of the `/jobs/view/` path
(slugs can contain numbers from the title, e.g. "Somewhere" spam). It must be exactly 10
digits (`is_valid_job_id()`); other cards are skipped with a warning (title + href) but still
count toward `last_card_count` for pagination. Historical junk IDs (2,996 shorter than 9
digits, 67 of 9/11/13 digits from titles) are left in the DB.

### job_function
NULL since ~2026-10-01: LinkedIn removed the "Job function" criteria item from logged-out job
pages (checked on two live pages on 2026-11-14; they list only Seniority level, Employment type,
Industries). Not a parser bug; the parser still reads it if it comes back
(`tests/test_job_criteria.py`).

### Scoring
`weighted_score` = Σ weight × min(count, `MAX_SCORED_MATCHES`) over the keywords
(`KeywordConfig.keyword_score()`, cap 2 since `SCORER_VERSION` 2): presence matters, repetition
doesn't. `total_matches` keeps the raw counts. Keywords in `config/keyword_settings.py` follow the
CV (Java/Spring Boot, QA automation, AWS, AI); AWS services are weighted low (AWS 6, Lambda /
Serverless 3, DynamoDB / ECS / S3 2) so an AWS-heavy posting can't stack them. On a local copy
(2026-11-17) the change moved the distribution from median 11 / p90 54 / max 571 to median 12 /
p90 53 / max 200.

### Score versioning
`KeywordConfig.scoring_version()` = first 12 hex chars of SHA-256 over canonical JSON of
`SCORER_VERSION`, `case_sensitive` and `{keyword: float(weight)}` for the configured keywords
(order and weights of unlisted keywords don't matter). Bump `SCORER_VERSION` in
`scraper/models/keyword_config.py` when `KeywordAnalyzer.analyze` or
`MatchResult.calculate_score` changes. Compare/rank scores only within one version; use
`scripts/rescore_jobs.py` to bring old rows to the current one.

### blacklisted_companies table
Companies hidden in the web UI (managed via `/api/blacklist`). Matched by exact
`company` string.
```sql
CREATE TABLE blacklisted_companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT UNIQUE NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

### aggregator_companies table
Synced from `config/aggregators.json` on every init; separate from the manual blacklist.
```sql
CREATE TABLE aggregator_companies (
    company TEXT PRIMARY KEY,
    category TEXT NOT NULL,            -- job_board | talent_marketplace | mass_reposter
    reason TEXT
)
```
- Web UI: `hide_aggregators` filter (on by default).
- Detail scraping: `get_jobs_without_analysis()` excludes them (`exclude_aggregators=True`),
  so their search hits are stored but the job page is never fetched and they get no
  `job_posts` row (so they don't appear in the UI even with the filter off).
  `count_skipped_aggregator_jobs(since)` counts pending ones first seen at/after `since`.

### companies table
Synced from `config/companies.json` on every init (inserts/updates config fields, deletes
unlisted companies); the sync never touches `last_checked_at` / `last_job_count`.
```sql
CREATE TABLE companies (
    name TEXT PRIMARY KEY,
    ats TEXT NOT NULL,                 -- greenhouse | lever | ashby
    slug TEXT NOT NULL,
    priority TEXT,
    hires_in_ar TEXT,
    notes TEXT,
    active INTEGER DEFAULT 1,
    last_checked_at TEXT,              -- UTC ISO-8601, last board read (also on errors)
    last_job_count INTEGER             -- postings returned (before the location filter); 0 on errors
)
```

### applications table
Jobs I applied to, managed via `/api/applications` (GET list; POST upsert
`{linkedin_job_id, applied_on?, notes?}`; DELETE `{linkedin_job_id}`; the key is a numeric
LinkedIn ID or an ATS key). POST requires an
existing `job_posts` row (404 otherwise), `applied_on` as `YYYY-MM-DD` (default: server's
today; the UI sends the browser's local date) and notes up to 2,000 characters.
```sql
CREATE TABLE applications (
    linkedin_job_id TEXT PRIMARY KEY,
    applied_on TEXT NOT NULL,          -- YYYY-MM-DD, a local date picked by the user (not UTC)
    notes TEXT,
    created_at TEXT,                   -- UTC ISO-8601
    updated_at TEXT                    -- UTC ISO-8601
)
```
- Web UI filter `applied=hide|only|all` (default `hide`). `hide`/`only` match the job itself
  **and** any posting with the same `(title, company)` as an applied job, because
  `job_summary_unique` keeps up to 2 postings per pair (`SQLiteStorage._APPLIED_SQL`).
  Those twins show a "✓ Similar" button.

### Views
- **`job_summary`**: `job_posts INNER JOIN job_searches` on `linkedin_job_id`, `GROUP BY
  linkedin_job_id` (one row per job). Columns: `linkedin_job_id, title, company, location,
  date_time, applicant_count, weighted_score, match_percentage, total_matches,
  matched_keywords, apply_type, apply_url, seniority_level, applicant_count_qualifier,
  employment_type, industries, source, job_url`. `date_time` is
  `COALESCE(posted_at, date_time)`: the posting date for ATS jobs (so a first collection
  doesn't show months-old postings as new), analysis time for LinkedIn. `description` is deliberately left out (it would be carried
  through the window function); the UI fetches `SUBSTR(description, 1, 500)` for the current
  page only (`get_description_snippets()`).
- **`job_summary_unique`**: same columns; keeps at most 2 rows per `(title, company)`,
  preferring the lowest non-NULL `applicant_count` (`ROW_NUMBER()` window). This is what
  the web app uses. Because of the window function, any query on it scans the whole view
  (~0.35 s on ~100k jobs).

### Timestamp format
`job_posts.date_time` / `posted_at`, all `scraped_at` columns and the `search_runs` timestamps are stored as
UTC ISO-8601 text with seconds and a `Z` suffix, e.g. `2026-10-07T22:11:34Z` (may be NULL).
Generate them with `utils.time_utils.utc_now_iso()`. Compare against them with the same format:
```sql
date_time >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-7 days')
```
The web UI shows it as relative time ("3h ago") with the local time on hover.
Exception: `applications.applied_on` is a plain `YYYY-MM-DD` local date.

## Web UI (`web_app.py`, `templates/index.html`)
- Server-side pagination; every filter is a GET param (bookmarkable). `get_job_summary()` /
  `count_job_summary()` take the filters as keyword arguments of
  `SQLiteStorage._build_summary_filters()` (`days` defaults to 7); the view is aliased `v`.

| Param | Filter |
|---|---|
| `q` | title or company contains (case-insensitive; `%` / `_` literal) |
| `days` (`7`/`14`/`30`/`all`), `hours` | posted within |
| `location` | location contains |
| `min_score`, `max_score`, `min_match` | score range, min match % |
| `emp` (repeated) | employment type, any of (options: distinct values in the DB) |
| `kw` (repeated) | `matched_keywords` contains any of (exact item; options: `DEFAULT_KEYWORDS`) |
| `under25=1` | `applicant_count < 25`, or `25` with qualifier `under` or NULL (historical) |
| `apply` | `easy_apply` / `external` / `unknown` |
| `applied` | `hide` (default) / `only` / `all` (see "applications table") |
| `source` | `linkedin` (`source IS NULL`) / `greenhouse` / `lever` / `ashby` |
| `hide_blacklisted`, `hide_aggregators`, `hide_above_level` | on (`1`) by default |
| `sort`, `dir`, `page`, `per_page` | sorting / pagination |

- Checkboxes are paired with a hidden `0` input; the last value wins, absent = default.
- Active filters that differ from the defaults are shown as chips; each links to the same URL
  with that filter reset. "Clear filters" keeps only `sort`, `dir`, `per_page`.
- Score badge: `SCORE_BADGE_THRESHOLDS` in `web_app.py` (≥50 strong, ≥25 good, ≥10 fair,
  else low; from the 2026-11-14 distribution: median 10, p75 25, p90 47). Revisit after
  rescoring production.
- Applicants: `<25` for `under` and for historical `25` + NULL; `>200` for `over`.
- `GET /api/shortlist` (`api_shortlist()`): JSON of the best jobs to apply to now. Params:
  `since` (`<N>h`/`<N>d`, 1h–365d, default `2h`; maps to the `hours`/`days` filter),
  `min_score` (≥ 0, default 29; keeps the 14-day shortlist size of
  the pre-cap default 25), `limit` (1–100, default 10), `apply`
  (`external` default / `easy_apply` / `all`). Empty = default; any invalid value → 400 with
  `{"error", "invalid": {param: message}}`. Fixed: `hide_blacklisted`, `hide_aggregators`,
  `hide_above_level`, `applied='hide'`; `job_summary_unique` sorted by `weighted_score` desc.
  Response: `params` (effective), `total` (before limit), `count`, `jobs` (fields in
  `SHORTLIST_FIELDS`, `matched_keywords` as a list, plus `source` and `job_url`
  (`job_url_for()`: `https://www.linkedin.com/jobs/view/<id>/` or the stored ATS URL)).
- "View" links and the Source column use `job_link()` / `source_label()` (template globals).
- Styling: Pico CSS, no `data-theme` (follows the OS light/dark setting). Use Pico variables
  (`--pico-*`) for every color, never hex/rgb (`test_no_light_theme_or_hardcoded_colors`).
  Below 1100px the Location, Source and Match columns are hidden (all in the expanded row).
  No overflow wrapper around the table, which would break the sticky header.

## LinkedIn HTML Selectors

### Search Results Page
- Job card: `div.job-search-card`
- Title: `h3.base-search-card__title`
- Company: `h4.base-search-card__subtitle`
- Location: `span.job-search-card__location`
- Job ID: `data-entity-urn` on the card (`urn:li:jobPosting:<10 digits>`); fallback: first
  `a[href*="/jobs/view/"]` (now `a.base-card__full-link`), last number of the path
- "See more jobs" button: `button.infinite-scroller__show-more-button` (loads
  `LINKEDIN_SEE_MORE_URL`)

### Job Detail Page
- Description: `div.show-more-less-html__markup`
- Applicants: `span.num-applicants__caption`
- Criteria: `li.description__job-criteria-item` (`h3.description__job-criteria-subheader` +
  `span.description__job-criteria-text`); currently Seniority level, Employment type, Industries
- Apply type: `[data-tracking-control-name]` containing `apply-link-onsite` / `apply-link-offsite`
  (see "Application type")

## SQL Views

### job_summary
Combined view of jobs + analysis data with all fields.

### job_summary_unique
Deduplicated view - removes duplicate remote job postings (same title + company).
Keeps at most 2 per (title, company), preferring the lowest applicant count.

```sql
-- Query deduplicated results
SELECT * FROM job_summary_unique;

-- Query all results (with duplicates)
SELECT * FROM job_summary;
```

## Common Tasks

### Backfill apply_type (one-off)
`scripts/backfill_apply_type.py` re-fetches the job page of recently analyzed rows with
`apply_type IS NULL` and sets only `apply_type` / `apply_url` (never description, scores or
other columns). It hits LinkedIn, so don't run it unless asked.
```bash
python -m scripts.backfill_apply_type --dry-run                # list what would be fetched
python -m scripts.backfill_apply_type                          # last 3 days, up to 300 jobs
python -m scripts.backfill_apply_type --since 12h --min-score 5 --limit 50
```
- Selection: `apply_type IS NULL`, `date_time` within `--since` (`<N>d` / `<N>h`, default
  `3d`), `weighted_score >= --min-score` (default 0), numeric IDs of at least 10 digits,
  newest first, at most `--limit` (default 300).
- Uses `DetailScraper` as is (headers, delays, batch pauses, 429 retries). Each update is
  written immediately with `WHERE apply_type IS NULL`, so it never overwrites a value.
- LinkedIn keys only (numeric); ATS jobs are saved with `apply_type = 'external'`.
- Closed jobs, pages without a marker and failed fetches stay NULL, so every run re-fetches
  them (bounded by `--since` / `--limit`).
- Stops after 5 consecutive failed fetches (exit 1): `DetailScraper` doesn't wait after
  non-429 errors, so a block would otherwise mean back-to-back requests.
- Lock: takes `LOG_DIR/scraper.lock` with `run_scraper.sh`'s PID format. If a live process
  holds it, it exits 1 with a message; a stale lock is replaced. While the backfill runs,
  the hourly cron run skips (300 jobs ≈ 20 min). `--dry-run` doesn't take the lock.
- Logs progress to `scraper.log` + stdout and ends with
  `Summary: easy_apply=… / external=… / closed=… / unknown=… / errors=…`.

### Re-score stored jobs (no fetching)
`scripts/rescore_jobs.py` recomputes `total_matches`, `weighted_score`, `matched_keywords`,
`match_percentage` and `scoring_version` from `job_posts.description` with the current
`DEFAULT_KEYWORDS` / `WEIGHTED_KEYWORDS`. Doesn't contact LinkedIn, doesn't take the lock.
```bash
python -m scripts.rescore_jobs --dry-run   # count rows with an old/NULL version
python -m scripts.rescore_jobs             # re-score them (batches of 500, one transaction each)
python -m scripts.rescore_jobs --all --limit 1000
```
- Rows without a description (failed/closed fetches) are skipped and keep a NULL version.
- ATS jobs are re-scored too (their description comes from the board API).
- Idempotent: a second run finds nothing to do. ~100k rows ≈ 2–3 min (local copy, 2026-11-14).

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
Defaults below; all configurable via env (`SCRAPE_*_DELAY`, `BATCH_*`, `RETRY_DELAY`,
`MAX_RETRIES`, `SEARCH_*_DELAY`).
- 2-4 second random delays between requests (and between search templates and result pages)
- Search pages: same 429 retries, 15 s timeout; aggregator jobs are never detail-fetched
- 30 second pause every 50 jobs
- Retry with 60s wait on 429 errors (max 3 retries)
- User-agent rotation
- ~10-12 minutes for 200 jobs

## Logging
Paths below are under `LOG_DIR` (default `data/logs`); level set by `LOG_LEVEL`.
- `data/logs/scraper.log` — `RotatingFileHandler`, 5 MB max, 7 backups. Also mirrors to stdout.
- `data/logs/cron.log` — stdout/stderr captured from cron runs via `run_scraper.sh`
- `data/logs/scraper.lock` — PID lock file to prevent overlapping cron runs

## Known Limitations
1. **Jobs per search**: at most 60 + 10 × (`SEARCH_MAX_PAGES` − 1) per run (90 by default)
2. **Rate limiting**: May get blocked if running too frequently
3. **`job_function`**: not available on logged-out pages since ~2026-10-01
4. **No outage alerting** yet (no alert when no `search_runs` row is `ok` for N hours)

## Dependencies
- `requests` - HTTP requests
- `beautifulsoup4` - HTML parsing
- `lxml` - Parser backend
- `flask` - Web interface
- `python-dotenv` - Loads `.env`
- `sqlite3` - Database (built-in)

## File Locations
- Database: `data/database/jobs_master.db` (`DB_PATH`)
- Logs: `data/logs/`

## Server Deployment

### Automated deploy (CI/CD)
Every push to `main` runs `.github/workflows/ci.yml`:
1. **test** — Python 3.8, `pip install -r requirements.txt`, `python -m unittest discover -s tests -t .`.
   Tests must not need the real DB.
2. **deploy** (push to `main` only, after tests, `production` environment, never concurrent) —
   joins the tailnet as an ephemeral `tag:ci` node, SSHes with `DEPLOY_SSH_KEY`, and the
   server's `authorized_keys` forces that key to run `deploy.sh` (no remote command is sent).
3. **`deploy.sh`** — `git pull --ff-only`, `venv/bin/pip install -r requirements.txt` only if it
   changed, `sudo -n systemctl restart job-scraper-web`, health check on
   `http://localhost:$PORT/` (`PORT` from `.env`, default 5000), prints the deployed short hash.
   It must not depend on arguments or `SSH_ORIGINAL_COMMAND`, and its body stays inside `main()`
   because `git pull` can rewrite the running script.

Secrets (`production` environment): `TS_OAUTH_CLIENT_ID`, `TS_OAUTH_SECRET`, `DEPLOY_SSH_KEY`,
`DEPLOY_HOST`, `DEPLOY_USER`. Pass them to `run:` scripts via `env:`, never inline `${{ }}`, and
never hardcode hostnames, IPs or usernames in the workflow. Actions are pinned to commit SHAs
(Dependabot updates them). One-time server setup (sudoers, forced-command key, Tailscale) is in
the README "CI/CD" section.

### Manual deploy (fallback)
If CI is unavailable, push from the local machine and run the same script on the server:
```bash
# Local
git push origin main

# Server
cd /home/edu/job-scraper && ./deploy.sh
# or fully manual:
git pull --ff-only && venv/bin/pip install -r requirements.txt && sudo systemctl restart job-scraper-web
```

### Server setup (first time)
```bash
git clone <repo-url> /home/edu/job-scraper
cd /home/edu/job-scraper
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
mkdir -p data/database data/logs
cp .env.example .env   # optional; edit to override defaults
```

### Cron (hourly scraper, daily ATS boards)
```bash
crontab -e
# Add:
0 * * * * /home/edu/job-scraper/run_scraper.sh
# ATS boards (Greenhouse / Lever / Ashby), once a day:
45 6 * * * /home/edu/job-scraper/run_scraper.sh --source ats
```
`run_scraper.sh` loads `.env` (if present), activates the virtualenv, acquires a PID lock, runs
`main.py "$@"` (its arguments are forwarded), and logs to `$LOG_DIR/cron.log`. The start, finish
and skip lines include the arguments, e.g. `Starting scraper run (--source ats)`; runs without
arguments log as before.

LinkedIn and ATS runs share `scraper.lock`, so they never write to SQLite at the same time:
whichever starts while the other holds the lock logs `Scraper already running (PID …),
skipping run (…)` and exits. Schedule the ATS run away from `:00` (an hourly LinkedIn run
usually takes several minutes; `:45` leaves room). A skipped ATS run waits for the next day,
so check `cron.log` for `skipping run (--source ats)`. An ATS run takes ~1 min (18 boards,
1–2 s apart), so it rarely makes the hourly run skip. Covered by `tests/test_run_scraper.py`
(fake `main.py`, no network).

The searches use `time_posted="2h"`, twice the cron interval. With `"1h"` there was no overlap,
so a posting was missed whenever a template's next run started more than an hour after its last
one (random delays, 429 waits), a run was skipped because the previous one (or the backfill)
held the lock, or LinkedIn indexed a posting late. The overlap costs no detail requests
(`get_jobs_without_analysis()` only returns IDs without a `job_posts` row), but each repeat hit
adds a `job_searches` row (~2.85 rows per job before the change, 428k rows / 83 MB locally).
Two consecutive skipped runs can still leave a gap.

### systemd (Flask web app)
```bash
sudo cp /home/edu/job-scraper/job-scraper-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable job-scraper-web
sudo systemctl start job-scraper-web
```
The unit reads `/home/edu/job-scraper/.env` via `EnvironmentFile=-` (optional). Restart the service after editing `.env`.

### Note on data directory
`data/` is gitignored — the database and logs are local per machine. Create `data/database/` and `data/logs/` manually on the server after cloning.
