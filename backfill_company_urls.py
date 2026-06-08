"""
Backfill company_url for jobs already in the database.

Strategy:
- Groups jobs by company name (hit each company only once)
- Scrapes ONE job URL per unique company to find its LinkedIn profile URL
- Updates ALL jobs from that company in one query
- Safe to re-run: skips companies that already have a URL
"""

import sqlite3
import time
import random
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from config.keyword_settings import USER_AGENTS

DB_PATH = Path(__file__).resolve().parent / 'data' / 'database' / 'jobs_master.db'

MIN_DELAY = 5
MAX_DELAY = 10
BATCH_SIZE = 15
BATCH_PAUSE = 90  # seconds — going slow, no hurry


def get_headers():
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
    }


def is_job_expired(soup):
    """Return True if LinkedIn redirected away from the job detail page."""
    # A valid job page has a topcard with job details
    has_job_detail = bool(
        soup.select_one('div.top-card-layout') or
        soup.select_one('section.top-card-layout') or
        soup.select_one('div.show-more-less-html__markup') or
        soup.select_one('h1.top-card-layout__title')
    )
    if has_job_detail:
        return False
    # No job detail elements found — it's a redirect or error page
    return True


def extract_company_url(soup):
    """Extract company LinkedIn profile URL using only specific selectors."""
    selectors = [
        'a.topcard__org-name-link',
        'a[data-tracking-control-name*="org-name"]',
        'a[data-tracking-control-name*="company"]',
    ]
    for selector in selectors:
        elem = soup.select_one(selector)
        if elem:
            href = elem.get('href', '')
            if '/company/' in href:
                parsed = urlparse(href)
                return urlunparse(('https', 'www.linkedin.com', parsed.path, '', '', ''))
    return None


def get_companies_to_fill(conn):
    """
    Returns distinct companies still missing company_url,
    ordered by most jobs first (biggest bang per request).
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT company, MIN(job_url) AS sample_job_url, COUNT(*) AS job_count
        FROM jobs
        WHERE company_url IS NULL
          AND company IS NOT NULL
          AND job_url IS NOT NULL
        GROUP BY company
        ORDER BY job_count DESC
    """)
    return cursor.fetchall()


def update_company(conn, company, company_url):
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE jobs SET company_url = ? WHERE company = ?",
        (company_url, company)
    )
    conn.commit()
    return cursor.rowcount


def normalize_url(url):
    """Force www.linkedin.com instead of country-specific domains."""
    parsed = urlparse(url)
    return urlunparse(parsed._replace(netloc='www.linkedin.com'))


def scrape_with_retry(job_url, max_retries=3):
    job_url = normalize_url(job_url)
    for attempt in range(max_retries):
        try:
            resp = requests.get(job_url, headers=get_headers(), timeout=15)
            if resp.status_code == 429:
                wait = 60 * (attempt + 1)
                print(f"  ⚠️  Rate limited. Waiting {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return BeautifulSoup(resp.content, 'html.parser')
        except requests.RequestException as e:
            print(f"  ❌ Request error (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(15)
    return None


def main():
    conn = sqlite3.connect(DB_PATH)

    companies = get_companies_to_fill(conn)
    total = len(companies)

    if total == 0:
        print("✅ All companies already have company_url. Nothing to do.")
        conn.close()
        return

    print(f"Found {total} companies without company_url")
    print(f"Delays: {MIN_DELAY}-{MAX_DELAY}s per request, {BATCH_PAUSE}s pause every {BATCH_SIZE} companies\n")

    found = 0
    not_found = 0

    for i, (company, sample_url, job_count) in enumerate(companies, 1):
        print(f"[{i}/{total}] {company} ({job_count} jobs)")

        # Reuse URL already known for this company from a newer job
        cursor = conn.cursor()
        cursor.execute(
            "SELECT company_url FROM jobs WHERE company = ? AND company_url IS NOT NULL LIMIT 1",
            (company,)
        )
        row = cursor.fetchone()
        if row:
            updated = update_company(conn, company, row[0])
            print(f"  ♻️  Reused existing: {row[0]} — updated {updated} row(s)")
            found += 1
            continue

        print(f"  Scraping: {sample_url[:80]}")

        soup = scrape_with_retry(sample_url)
        if soup is None:
            print("  ❌ Failed to fetch page, skipping")
            not_found += 1
        elif is_job_expired(soup):
            print("  ⏭️  Job expired/unavailable — skipping")
            not_found += 1
        else:
            company_url = extract_company_url(soup)
            if company_url:
                updated = update_company(conn, company, company_url)
                print(f"  ✅ {company_url} — updated {updated} row(s)")
                found += 1
            else:
                print("  ⚠️  No company URL found on this page")
                not_found += 1

        # Rate limiting
        if i < total:
            if i % BATCH_SIZE == 0:
                print(f"\n⏸️  Batch of {BATCH_SIZE} done. Pausing {BATCH_PAUSE}s...\n")
                time.sleep(BATCH_PAUSE)
            else:
                delay = random.uniform(MIN_DELAY, MAX_DELAY)
                time.sleep(delay)

    conn.close()
    print(f"\n{'='*50}")
    print(f"Done. Found: {found} | Not found: {not_found} | Total: {total}")


if __name__ == '__main__':
    main()
