"""Timestamp helpers shared by the scraper and storage."""
from datetime import datetime, timezone

# UTC ISO-8601 with seconds and a Z suffix, e.g. 2026-10-07T22:11:34Z.
# Same format as job_posts.date_time, so values compare as text.
ISO_UTC_FORMAT = '%Y-%m-%dT%H:%M:%SZ'


def utc_now_iso():
    """Return the current UTC time as an ISO-8601 string (seconds, Z suffix)."""
    return datetime.now(timezone.utc).strftime(ISO_UTC_FORMAT)
