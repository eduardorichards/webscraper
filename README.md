# LinkedIn Job Scraper

[![CI](https://github.com/eduardorichards/webscraper/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/eduardorichards/webscraper/actions/workflows/ci.yml)

A Python application that scrapes job listings from LinkedIn based on configurable search parameters and stores results in a SQLite database.

## Features

- Search LinkedIn jobs by keywords, location, experience level, and work mode (remote/on-site)
- Batch searching with multiple predefined search templates
- SQLite storage with automatic duplicate prevention
- Optional JSON export for individual searches
- Configurable time filters (24h, 1 week, 1 month)
- Detects the application type (LinkedIn Easy Apply vs external) of each job; the web UI
  shows it in an "Apply" column and can filter by it (Easy Apply / External / Unknown)
- Follows "See more jobs" result pages (up to `SEARCH_MAX_PAGES` per search)
- Web UI filters, on by default: "Hide aggregators" (job boards, talent marketplaces, mass
  reposters from `config/aggregators.json`) and "Hide above my level" (seniority above
  `TARGET_SENIORITY_LEVELS`). Aggregator jobs are not detail-scraped at all.
- Web UI results page: text search (title/company), employment type, score range, min match %,
  matched keywords, "Under 25 applicants", active filters as removable chips, expandable rows
  with seniority / employment type / industries / description excerpt, and dark mode (follows
  the OS setting). All filters are GET params, so any view can be bookmarked.
- Application tracking: mark a job as applied (date + optional notes) from the results page;
  the "Applied" filter (default "Hide applied") also covers postings with the same title and
  company
- Shortlist API (`GET /api/shortlist`): JSON list of the best recent jobs to apply to now
- Scores record the keyword config they were computed with (`scoring_version`);
  `scripts/rescore_jobs.py` re-scores stored jobs without re-fetching

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
| `SEARCH_MIN_DELAY` / `SEARCH_MAX_DELAY` | `2` / `4` | Random delay (s) between search templates and between result pages |
| `SEARCH_MAX_PAGES` | `4` | Result pages per search template (1–100): first page + "See more jobs" pages |

Relative `DB_PATH` / `LOG_DIR` resolve from the project root. Empty or unset variables use
the default; invalid values raise `ConfigError` at startup. Real environment variables take
precedence over `.env`. `.env` is read by python-dotenv, bash `source` (`run_scraper.sh`) and
systemd `EnvironmentFile`, so keep it to plain `KEY=value` lines: no quotes, no inline comments,
no `export`, no `$VAR` or `~`.

Search templates, experience levels, target seniority levels, keywords and the aggregator list
are domain config and stay in `config/`.

### Pagination

The search page shows up to 60 jobs. When it's full, the scraper requests the next pages from
LinkedIn's guest "See more jobs" endpoint
(`jobs-guest/jobs/api/seeMoreJobPostings/search?<same params>&start=<jobs so far>`, 10 jobs per
page), with the `SEARCH_*_DELAY` delay before each page and the same 429 retries as detail
pages (`RETRY_DELAY`, `MAX_RETRIES`). It stops at a short page, a page with only already-seen
jobs, the template's `max_results`, or `SEARCH_MAX_PAGES`. Each page is saved as it arrives.
`search_runs.pages_fetched` and `hit_page_limit` (1 = stopped at `SEARCH_MAX_PAGES` with more
results left; a warning is logged) record what happened.

### Seniority ("Hide above my level")

LinkedIn no longer enforces the experience-level search filter (`f_E`), so many results are
Mid-Senior. `TARGET_SENIORITY_LEVELS` in `config/settings.py` (default: Internship, Entry level,
Associate) sets your levels; the web UI hides jobs whose `seniority_level` ranks above the
highest of them (Internship < Entry level < Associate < Mid-Senior level < Director <
Executive). Jobs with no seniority or "Not Applicable" are always shown. Nothing is deleted.

### Aggregators

`config/aggregators.json` lists companies that aren't the actual employer (job boards and
feeds, AI-training/talent marketplaces, mass multi-country reposters), each with a `category`
and `reason`. It's synced into the `aggregator_companies` table on every `SQLiteStorage()`
init (added, updated and removed to match the file). Their jobs:
- are hidden by the web UI's "Hide aggregators" filter (on by default), and
- are not detail-scraped: the search hit is stored, but the job page is never fetched, so
  they have no `job_posts` row and don't appear in the UI even with the filter off.
  Each analysis logs `Skipped N detail fetches for aggregator companies`.

This list is separate from the manual blacklist (`blacklisted_companies`, managed in the UI).

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
│   ├── env.py              # Environment config (env vars / .env)
│   ├── settings.py         # Search templates and settings
│   ├── keyword_settings.py # Keywords and weights
│   └── aggregators.json    # Aggregator companies (category, reason)
├── scraper/
│   ├── models/             # Data models (Job, SearchConfig)
│   ├── core/               # Scraper and URL builder
│   └── extractors/         # LinkedIn HTML parser
├── scripts/
│   ├── backfill_apply_type.py  # One-off apply_type backfill
│   └── rescore_jobs.py     # Re-score stored jobs with the current keywords
├── utils/
│   ├── sqlite_storage.py   # SQLite database handler
│   ├── aggregators.py      # Loads config/aggregators.json
│   └── seniority.py        # "Above my level" rule
└── data/
    └── database/           # SQLite database location
```

## Database

Jobs are stored in SQLite at `data/database/jobs_master.db` (`DB_PATH`). The schema is created
and migrated automatically whenever `SQLiteStorage()` is instantiated: new tables and columns
are added in place, existing data is kept, and running it again does nothing.

All timestamps are UTC ISO-8601 text with seconds and a `Z` suffix, e.g. `2026-10-07T22:11:34Z`
(except `applications.applied_on`, a plain `YYYY-MM-DD` date picked by the user).

| Table | One row per | Main columns |
|-------|-------------|--------------|
| `search_runs` | search template execution | `template_name`, `keywords`, `location`, `started_at`, `finished_at`, `jobs_found`, `new_jobs`, `status` (`ok` / `error`), `error`, `pages_fetched`, `hit_page_limit` |
| `job_searches` | search result (a job found by a search; the same job can appear many times) | `linkedin_job_id`, `title`, `company`, `location`, `company_url`, `search_*`, `scraped_at`, `search_run_id` |
| `job_posts` | job (details from the job page + keyword analysis) | `linkedin_job_id` (unique), `description`, `applicant_count`, `applicant_count_qualifier`, `apply_type`, `apply_url`, `seniority_level`, `date_time`, `scraped_at`, `weighted_score`, `matched_keywords`, `scoring_version`, ... |
| `blacklisted_companies` | company hidden in the web UI | `company`, `added_at` |
| `aggregator_companies` | aggregator company (synced from `config/aggregators.json`) | `company`, `category`, `reason` |
| `applications` | job I applied to (managed in the UI) | `linkedin_job_id` (primary key), `applied_on`, `notes`, `created_at`, `updated_at` |

- `search_runs.new_jobs` counts jobs whose `linkedin_job_id` was not in `job_searches` before
  that run. A run with `status` NULL was interrupted before finishing.
- `scraped_at` is NULL on rows saved before it was introduced; it is not backfilled.
- `applicant_count_qualifier`: LinkedIn shows bounds instead of exact counts to logged-out
  visitors. `"Be among the first 25 applicants"` is stored as `25` / `under` (fewer than 25),
  `"Over 200 applicants"` as `200` / `over`, and an exact `"87 applicants"` as `87` / NULL.
  Historical rows with `applicant_count = 25` and no qualifier most likely mean "under 25".
- `apply_type`: `easy_apply`, `external`, or NULL (unknown: job closed, fetch failed, no
  marker on the page, or analyzed before this column existed; existing rows are not
  backfilled; see "Backfill apply_type" below). `apply_url` is meant for the external target, but logged-out job pages don't
  expose it, so it is currently always NULL and the UI shows "External" without a link.
- `linkedin_job_id` is taken from the card's `data-entity-urn` (or the end of the
  `/jobs/view/` URL) and must be exactly 10 digits; other cards are skipped and logged. Older
  rows may contain junk IDs (shorter, or numbers taken from titles); they are kept.
- `job_function` is NULL since ~2026-10-01: LinkedIn removed "Job function" from logged-out
  job pages (they now list only seniority, employment type and industries).
- `search_runs.pages_fetched` / `hit_page_limit` and `job_posts.scoring_version` are NULL on
  rows written before they existed.
- Closed jobs: LinkedIn redirects an expired job page to a search page
  (`trk=expired_jd_redirect`). The analysis then saves the job like a failed fetch (no
  description, `scraped_at` NULL, `apply_type` NULL) so it isn't analyzed again.

Recent search runs:
```sql
SELECT template_name, started_at, jobs_found, new_jobs, pages_fetched, hit_page_limit,
       status, error
FROM search_runs ORDER BY id DESC LIMIT 24;
```

## Querying Results

```python
from utils.sqlite_storage import SQLiteStorage

storage = SQLiteStorage()
stats = storage.get_stats()

print(f"Total jobs: {stats['total_jobs']}")
print(f"Unique companies: {stats['unique_companies']}")
print(f"Unique locations: {stats['unique_locations']}")
```

## Shortlist API

`GET /api/shortlist` returns the best jobs to apply to right now, as JSON, ordered by
`weighted_score` (highest first).

| Param | Default | Accepted values |
|---|---|---|
| `since` | `2h` | `<N>h` or `<N>d` (1h to 365d): `date_time` (when the job was analyzed) within that window |
| `min_score` | `25` | number >= 0 |
| `limit` | `10` | integer 1–100 |
| `apply` | `external` | `external`, `easy_apply` or `all` (`all` includes unknown apply type) |

Empty or missing params use the default. Any invalid value returns **400** with every bad
param listed: `{"error": "invalid parameters", "invalid": {"limit": "..."}}`.

Always applied (not configurable): hide blacklisted companies, hide aggregators, hide jobs
above my level, and hide applied jobs, including postings with the same title and company as
an applied job. Uses the deduplicated `job_summary_unique` view, like the web UI.

```bash
curl 'http://localhost:5000/api/shortlist?since=6h&min_score=30&limit=5'
```

```json
{
  "params": {"since": "6h", "min_score": 30.0, "limit": 5, "apply": "external"},
  "total": 12,
  "count": 5,
  "jobs": [{
    "linkedin_job_id": "4123456789",
    "title": "Junior Python Developer",
    "company": "Acme",
    "location": "Buenos Aires, Argentina",
    "date_time": "2026-11-14T10:00:00Z",
    "weighted_score": 42.0,
    "match_percentage": 30.0,
    "matched_keywords": ["Python", "Django"],
    "seniority_level": "Entry level",
    "employment_type": "Full-time",
    "apply_type": "external",
    "applicant_count": 25,
    "applicant_count_qualifier": "under",
    "job_url": "https://www.linkedin.com/jobs/view/4123456789/"
  }]
}
```

- `total` counts all matches before `limit`; `count` is the number of jobs returned.
- `applicant_count_qualifier` is `under`, `over` or `null` (exact). A historical `25` with a
  `null` qualifier most likely means "under 25".

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

Each score stores `scoring_version`, a 12-character hash of the keyword list, their weights,
case sensitivity and a scorer version (`SCORER_VERSION` in `scraper/models/keyword_config.py`,
bumped when the matching logic changes). Scores with different versions aren't comparable.
Failed or closed fetches have no version.

### Re-score stored jobs

After changing keywords or weights, re-score stored descriptions (no requests to LinkedIn):
```bash
python -m scripts.rescore_jobs --dry-run   # how many rows would change
python -m scripts.rescore_jobs             # rows with an old or NULL scoring_version
python -m scripts.rescore_jobs --all       # every row with a description
```
It updates only `total_matches`, `weighted_score`, `matched_keywords`, `match_percentage` and
`scoring_version`, in batches of 500, and skips rows without a description. Re-running it is a
no-op. ~100k rows take about 2–3 minutes.

## Backfill apply_type (one-off)
`scripts/backfill_apply_type.py` re-fetches the job page of recently analyzed rows with
`apply_type IS NULL` and sets only `apply_type` / `apply_url` (never description, scores or
other columns). It sends requests to LinkedIn: run it sparingly.
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
- Closed jobs, pages without a marker and failed fetches stay NULL, so every run re-fetches
  them (bounded by `--since` / `--limit`).
- Stops after 5 consecutive failed fetches (exit 1): `DetailScraper` doesn't wait after
  non-429 errors, so a block would otherwise mean back-to-back requests.
- Lock: takes `LOG_DIR/scraper.lock` with `run_scraper.sh`'s PID format. If a live process
  holds it, it exits 1 with a message; a stale lock is replaced. While the backfill runs,
  the hourly cron run skips (300 jobs ≈ 20 min). `--dry-run` doesn't take the lock.
- Logs progress to `scraper.log` + stdout and ends with
  `Summary: easy_apply=… / external=… / closed=… / unknown=… / errors=…`.

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

## CI/CD

GitHub Actions (`.github/workflows/ci.yml`) runs on every pull request and every push to `main`:

1. **test**: installs `requirements.txt` on Python 3.8 (the server's version) and runs
   `python -m unittest discover -s tests -t .`. Tests use temporary databases, never the real one.
2. **deploy** (pushes to `main` only, after tests pass, in the `production` environment):
   - The runner joins the tailnet as an **ephemeral Tailscale node** tagged `tag:ci`, using an
     OAuth client. The server is not exposed to the internet.
   - It opens an SSH connection with a dedicated deploy key and sends no command. The server's
     `authorized_keys` **forces** that key to run `deploy.sh`, so the key cannot do anything else.
   - **`deploy.sh`** runs `git pull --ff-only`, reinstalls dependencies only if
     `requirements.txt` changed, restarts `job-scraper-web`, and runs a **health check**
     (`curl` on `http://localhost:$PORT/`, `PORT` read from `.env`, default 5000). A failed
     check fails the workflow. It prints the deployed short commit hash.

Deploys never overlap (concurrency group `deploy`, queued rather than cancelled). Pull requests,
including those from forks, only run tests and get no secrets. Actions are pinned to commit
SHAs, and Dependabot (`.github/dependabot.yml`) proposes updates weekly.

### Required secrets

Stored in the `production` environment (Settings → Environments → production):

| Secret | Description |
|---|---|
| `TS_OAUTH_CLIENT_ID` | Tailscale OAuth client ID |
| `TS_OAUTH_SECRET` | Tailscale OAuth client secret |
| `DEPLOY_SSH_KEY` | Private key of the dedicated deploy key pair |
| `DEPLOY_HOST` | Server's Tailscale hostname or IP |
| `DEPLOY_USER` | SSH user on the server |

### One-time server setup

1. **sudoers**: let the deploy user restart the web app without a password, and nothing else
   (`sudo visudo -f /etc/sudoers.d/job-scraper-deploy`):
   ```
   edu ALL=(root) NOPASSWD: /usr/bin/systemctl restart job-scraper-web
   ```
2. **Deploy key**: generate a key pair used only for deploys (`ssh-keygen -t ed25519 -f deploy_key -N ""`),
   store the private key as `DEPLOY_SSH_KEY`, and add the public key to `~/.ssh/authorized_keys`
   on the server as a single line:
   ```
   command="/home/edu/job-scraper/deploy.sh",restrict ssh-ed25519 AAAA... github-actions-deploy
   ```
   `restrict` disables port forwarding, agent forwarding, X11 and PTY allocation.
3. **Tailscale**:
   - Define `tag:ci` in the tailnet policy file (`tagOwners`).
   - Create an OAuth client (trust credential) with only the **`auth_keys` write** scope,
     limited to `tag:ci`. Store its ID and secret as `TS_OAUTH_CLIENT_ID` / `TS_OAUTH_SECRET`.

### Recommended hardening

Not configured yet:

- **Tailscale ACL**: allow `tag:ci` to reach only the server on port 22, e.g.
  ```json
  "grants": [{ "src": ["tag:ci"], "dst": ["<server>"], "ip": ["tcp:22"] }]
  ```
- **Deployment branch rule**: restrict the `production` environment to the `main` branch
  (Settings → Environments → production → Deployment branches).
- **Source restriction on the deploy key**: prefix the `authorized_keys` line with
  `from="100.64.0.0/10",` so the key only works from Tailscale addresses.
- **Host key pinning**: every runner is new, so `StrictHostKeyChecking=accept-new` trusts
  whatever host key the server presents on first contact. Tailscale already authenticates the
  connection to the node, but for strict checking store the server's `ssh-keyscan` output as a
  `DEPLOY_KNOWN_HOSTS` secret, write it to the known_hosts file, and switch to
  `StrictHostKeyChecking=yes`.

### Manual deploy (fallback)

If the workflow is unavailable, on the server:
```bash
cd /home/edu/job-scraper && ./deploy.sh
```

## Known Limitations

- At most 60 + 10 × (`SEARCH_MAX_PAGES` − 1) jobs per search and run (90 by default)
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
