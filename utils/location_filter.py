"""Location filter for ATS postings: keep jobs open to Argentina / LATAM.

Rules, in order:
1. Keep if any location mentions an allowlisted term (whole words,
   case- and accent-insensitive): Argentina, Buenos Aires, LATAM, Latin
   America, Americas, AMER, Anywhere, Worldwide, Global... ("Anywhere in
   the United States" counts as the United States)
2. Keep a bare "Remote" (or no location at all on a remote posting) unless
   the description restricts it to the US ("US-based", "authorized to work
   in the United States", ...).
3. Drop everything else: cities and countries outside the allowlist,
   "Remote - US", "Canada", "Remote, Poland"...
"""
import re
import unicodedata

ALLOWED_TERMS = (
    "argentina", "buenos aires", "caba", "capital federal",
    "latam", "latin america", "latinoamerica", "south america", "americas", "amer",
    "anywhere", "worldwide", "global",
)
_ALLOWED_RE = re.compile(r"\b(%s)\b" % "|".join(re.escape(t) for t in ALLOWED_TERMS))
# "Anywhere in the United States" / "Anywhere in Ireland" name a country:
# only the place after "in" is checked
_ANYWHERE_IN_RE = re.compile(r"\banywhere\s+in\b")

# A location that says only "remote", without a place
BARE_REMOTE = {"remote", "fully remote", "remote only", "100% remote"}

_US = r"(?:the\s+)?(?:us|u\.s\.?|usa|united\s+states(?:\s+of\s+america)?)"
US_ONLY_PATTERNS = (
    r"based\s+in\s+" + _US + r"(?![a-z])",
    r"\b(?:us|u\.s\.?)[\s-]+based\b",
    r"\b(?:us|u\.s\.?|usa)\s+only\b",
    r"\bunited\s+states\s+only\b",
    r"\b(?:authorized|authorised|eligible)\s+to\s+work\s+in\s+" + _US + r"(?![a-z])",
    r"\bmust\s+(?:reside|live|be\s+located)\s+in\s+" + _US + r"(?![a-z])",
)
_US_ONLY_RE = re.compile("|".join(US_ONLY_PATTERNS), re.IGNORECASE)


def _normalize(text):
    """Lowercase without accents ("Latinoamérica" → "latinoamerica")."""
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def allowed_location(text):
    """True if `text` mentions an allowlisted term."""
    return bool(_ALLOWED_RE.search(_ANYWHERE_IN_RE.sub(" ", _normalize(text))))


def is_us_only(description):
    """True if the description restricts the job to people in the US."""
    return bool(_US_ONLY_RE.search(description or ""))


def _is_bare_remote(locations, is_remote):
    names = [_normalize(loc).strip(" .-") for loc in locations if loc and loc.strip()]
    if not names:
        return bool(is_remote)
    return all(name in BARE_REMOTE for name in names)


def check_location(locations, description=None, is_remote=False):
    """(keep, reason) for a posting with these location strings."""
    locations = [loc for loc in locations if loc]
    if any(allowed_location(loc) for loc in locations):
        return True, "allowed location"
    if _is_bare_remote(locations, is_remote):
        if is_us_only(description):
            return False, "remote, US only"
        return True, "remote, no country"
    return False, "location not allowed"
