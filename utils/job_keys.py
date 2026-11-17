"""Job keys stored in the `linkedin_job_id` column, for every source.

LinkedIn jobs keep their numeric ID. Jobs from ATS boards use a prefixed
key, `<source>:<board slug>:<posting id>` (e.g. `lever:redbee:f035d332-...`),
so they can never collide with a LinkedIn ID. `job_searches.source` stores
the same source name (NULL = LinkedIn).
"""
import re

LINKEDIN = "linkedin"
GREENHOUSE = "greenhouse"
LEVER = "lever"
ASHBY = "ashby"
ATS_SOURCES = (GREENHOUSE, LEVER, ASHBY)
SOURCES = (LINKEDIN,) + ATS_SOURCES
SOURCE_LABELS = {LINKEDIN: "LinkedIn", GREENHOUSE: "Greenhouse", LEVER: "Lever",
                 ASHBY: "Ashby"}

LINKEDIN_JOB_BASE_URL = "https://www.linkedin.com/jobs/view/"

_LINKEDIN_ID_RE = re.compile(r"[0-9]+")  # ASCII only (str.isdigit accepts '３')
_ATS_KEY_RE = re.compile(r"(%s):[A-Za-z0-9._-]+:[A-Za-z0-9_-]+" % "|".join(ATS_SOURCES))
# SQL condition, same rule as is_linkedin_key(): the key in column `col`
# has no source prefix (keys of other sources always contain ':').
LINKEDIN_KEY_SQL = "instr({col}, ':') = 0"


def make_key(source, slug, posting_id):
    """Key for an ATS posting: '<source>:<slug>:<posting id>'."""
    if source not in ATS_SOURCES:
        raise ValueError("unknown ATS source: %r" % (source,))
    key = "%s:%s:%s" % (source, slug, posting_id)
    if not _ATS_KEY_RE.fullmatch(key):
        raise ValueError("invalid job key: %r" % (key,))
    return key


def is_linkedin_key(key):
    """True for a LinkedIn job ID, i.e. a key without a source prefix.

    Historical junk IDs (short numbers) count as LinkedIn too: they came
    from LinkedIn search pages.
    """
    return bool(key) and ":" not in str(key)


def is_valid_key(key):
    """True for a numeric LinkedIn ID or a well-formed ATS key."""
    key = str(key or "")
    return bool(_LINKEDIN_ID_RE.fullmatch(key) or _ATS_KEY_RE.fullmatch(key))


def source_of(key):
    """'linkedin' / 'greenhouse' / 'lever' / 'ashby', or None if malformed."""
    key = str(key or "")
    if is_linkedin_key(key):
        return LINKEDIN
    if _ATS_KEY_RE.fullmatch(key):
        return key.split(":", 1)[0]
    return None


def job_url_for(key, stored_url=None):
    """Posting URL: built from the ID for LinkedIn, the stored URL otherwise.

    Returns None for a non-LinkedIn key without a stored http(s) URL.
    """
    if is_linkedin_key(key):
        return "%s%s/" % (LINKEDIN_JOB_BASE_URL, key)
    if stored_url and str(stored_url).startswith(("http://", "https://")):
        return stored_url
    return None
