"""Read public ATS job boards (Greenhouse, Lever, Ashby) and normalize postings.

Each board is one GET returning every open posting with its description, so
no per-job requests are needed. `fetch_board()` returns `AtsJob`s; parsing
helpers are separate so tests can feed saved JSON.
"""
import html
import logging
import re
from datetime import datetime, timezone
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from utils.job_keys import ASHBY, GREENHOUSE, LEVER, make_key

logger = logging.getLogger(__name__)

TIMEOUT = 15
USER_AGENT = "job-scraper/1.0 (personal job search; reads public job board APIs)"

# Also serves EU-hosted boards (job-boards.eu.greenhouse.io); there is no
# boards-api.eu.greenhouse.io host (no DNS record, checked 2026-11-17)
GREENHOUSE_BASE_URL = "https://boards-api.greenhouse.io"
LEVER_BASE_URL = "https://api.lever.co"
ASHBY_BASE_URL = "https://api.ashbyhq.com"

# Employment types as LinkedIn names them, so the UI filter groups them
_EMPLOYMENT_TYPES = {
    "fulltime": "Full-time", "parttime": "Part-time",
    "contract": "Contract", "contractor": "Contract", "freelance": "Contract",
    "intern": "Internship", "internship": "Internship",
    "temporary": "Temporary", "temp": "Temporary",
}


class AtsError(Exception):
    """A board could not be read (HTTP error, timeout, unexpected payload)."""


class AtsJob:
    """One posting from an ATS board, normalized across sources."""

    __slots__ = ("key", "source", "slug", "company", "title", "locations",
                 "description", "job_url", "apply_url", "posted_at",
                 "employment_type", "remote")

    def __init__(self, key, source, slug, company, title, locations, description,
                 job_url, apply_url=None, posted_at=None, employment_type=None,
                 remote=False):
        self.key = key
        self.source = source
        self.slug = slug
        self.company = company
        self.title = title
        self.locations = locations          # List[str], primary first
        self.description = description      # plain text
        self.job_url = job_url
        self.apply_url = apply_url
        self.posted_at = posted_at          # UTC ISO-8601 ('...Z') or None
        self.employment_type = employment_type
        self.remote = remote

    @property
    def location_raw(self):
        """All locations joined, as stored in job_searches.location."""
        return "; ".join(self.locations)

    def __repr__(self):
        return "AtsJob(%r, %r)" % (self.key, self.title)


def html_to_text(markup):
    """Plain text of an HTML fragment, one line per block, blank lines collapsed."""
    if not markup:
        return ""
    text = BeautifulSoup(markup, "lxml").get_text("\n")
    lines = [line.strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def to_utc_iso(value):
    """'2026-07-22T13:38:40-04:00', '...Z', '....327+00:00' or epoch ms →
    '2026-07-22T17:38:40Z'. None for missing or unparseable values."""
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)
        else:
            text = str(value).strip()
            if text.isdigit():
                return to_utc_iso(int(text))
            # fromisoformat (3.8) wants +00:00 and 3 or 6 fractional digits
            text = re.sub(r"[Zz]$", "+00:00", text)
            text = re.sub(r"\.\d+", "", text, count=1)
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_employment_type(value):
    """'FullTime' / 'Full Time' / 'Contract | Remote' → LinkedIn's name
    ('Full-time', 'Contract'); None for anything else.

    Lever's commitment is free text ("RDD | Argentina", "Global | LATAM"),
    so unknown values are dropped rather than added to the UI filter.
    """
    if not value:
        return None
    first = str(value).split("|", 1)[0]
    return _EMPLOYMENT_TYPES.get(re.sub(r"[^a-z]", "", first.lower()))


def _unique(values):
    """Non-empty stripped strings, first occurrence kept."""
    result = []
    for value in values:
        value = (value or "").strip() if isinstance(value, str) else ""
        if value and value not in result:
            result.append(value)
    return result


def parse_greenhouse(data, company, slug):
    """AtsJobs from a Greenhouse /jobs?content=true response."""
    jobs = []
    for item in data.get("jobs") or []:
        location = (item.get("location") or {}).get("name")
        offices = item.get("offices") or []
        locations = _unique([location] + [o.get("location") for o in offices]
                            + [o.get("name") for o in offices])
        posted = item.get("first_published") or item.get("updated_at")
        url = item.get("absolute_url")
        jobs.append(AtsJob(
            key=make_key(GREENHOUSE, slug, item["id"]),
            source=GREENHOUSE, slug=slug, company=company,
            title=(item.get("title") or "").strip(),
            locations=locations,
            # content is HTML-escaped HTML
            description=html_to_text(html.unescape(item.get("content") or "")),
            job_url=url, apply_url=url,
            posted_at=to_utc_iso(posted),
            remote=any("remote" in loc.lower() for loc in locations),
        ))
    return jobs


def parse_lever(data, company, slug):
    """AtsJobs from a Lever /v0/postings/{slug}?mode=json response (a list)."""
    jobs = []
    for item in data or []:
        categories = item.get("categories") or {}
        locations = _unique([categories.get("location")]
                            + list(categories.get("allLocations") or []))
        # Lever's ISO country code; postings in e.g. "Capital Federal" have "AR"
        if item.get("country") == "AR" and "Argentina" not in locations:
            locations.append("Argentina")
        parts = [item.get("descriptionPlain") or ""]
        for section in item.get("lists") or []:
            parts.append(((section.get("text") or "").strip() + "\n"
                          + html_to_text(section.get("content"))).strip())
        parts.append(item.get("additionalPlain") or "")
        workplace = (item.get("workplaceType") or "").lower()
        jobs.append(AtsJob(
            key=make_key(LEVER, slug, item["id"]),
            source=LEVER, slug=slug, company=company,
            title=(item.get("text") or "").strip(),
            locations=locations,
            description="\n\n".join(p.strip() for p in parts if p and p.strip()),
            job_url=item.get("hostedUrl"),
            apply_url=item.get("applyUrl") or item.get("hostedUrl"),
            posted_at=to_utc_iso(item.get("createdAt")),
            employment_type=normalize_employment_type(categories.get("commitment")),
            remote=workplace == "remote",
        ))
    return jobs


def parse_ashby(data, company, slug):
    """AtsJobs from an Ashby /posting-api/job-board/{slug} response.

    Unlisted postings (isListed false) are skipped.
    """
    jobs = []
    for item in data.get("jobs") or []:
        if item.get("isListed") is False:
            continue
        locations = _unique([item.get("location")]
                            + [s.get("location") for s in item.get("secondaryLocations") or []])
        workplace = (item.get("workplaceType") or "").lower()
        jobs.append(AtsJob(
            key=make_key(ASHBY, slug, item["id"]),
            source=ASHBY, slug=slug, company=company,
            title=(item.get("title") or "").strip(),
            locations=locations,
            description=(item.get("descriptionPlain") or "").strip(),
            job_url=item.get("jobUrl"),
            apply_url=item.get("applyUrl") or item.get("jobUrl"),
            posted_at=to_utc_iso(item.get("publishedAt")),
            employment_type=normalize_employment_type(item.get("employmentType")),
            remote=bool(item.get("isRemote")) or workplace == "remote",
        ))
    return jobs


PARSERS = {GREENHOUSE: parse_greenhouse, LEVER: parse_lever, ASHBY: parse_ashby}


def board_url(ats, slug):
    """API URL of a company's job board."""
    if ats == GREENHOUSE:
        return "%s/v1/boards/%s/jobs?content=true" % (GREENHOUSE_BASE_URL, slug)
    if ats == LEVER:
        return "%s/v0/postings/%s?mode=json" % (LEVER_BASE_URL, slug)
    if ats == ASHBY:
        return "%s/posting-api/job-board/%s?includeCompensation=true" % (ASHBY_BASE_URL, slug)
    raise ValueError("unknown ATS: %r" % (ats,))


def fetch_board(company, session=None):
    # type: (dict, Optional[requests.Session]) -> List[AtsJob]
    """Fetch and parse one company's board.

    company: a row of the companies table (name, ats, slug).
    Raises AtsError on HTTP errors (including 404), timeouts and payloads
    that can't be parsed. An empty board returns [].
    """
    url = board_url(company["ats"], company["slug"])
    getter = session or requests
    try:
        response = getter.get(url, timeout=TIMEOUT, headers={
            "User-Agent": USER_AGENT, "Accept": "application/json"})
    except requests.RequestException as e:
        raise AtsError("request failed: %s" % e)
    if response.status_code != 200:
        raise AtsError("HTTP %d" % response.status_code)
    try:
        data = response.json()
        return PARSERS[company["ats"]](data, company["name"], company["slug"])
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        raise AtsError("unexpected response: %s: %s" % (type(e).__name__, e))
