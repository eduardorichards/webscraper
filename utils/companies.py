"""Load the curated ATS company list (config/companies.json)."""
import json
import re
from pathlib import Path

from utils.job_keys import ATS_SOURCES

COMPANIES_FILE = Path(__file__).resolve().parent.parent / "config" / "companies.json"
_SLUG_RE = re.compile(r"[A-Za-z0-9._-]+")


def load_companies(path=None):
    """Return a list of company dicts from the companies data file.

    Each dict has name, ats, slug, priority, hires_in_ar, notes and
    active (bool, default True); missing optional fields are None.

    Raises ValueError if the file is malformed: an entry without a name, an
    unknown ats, an invalid slug, or a duplicated name or
    (ats, slug) board.
    """
    path = Path(path) if path is not None else COMPANIES_FILE
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    entries = []
    names = set()
    boards = set()
    for item in data.get("companies") or []:
        name = (item.get("name") or "").strip()
        ats = item.get("ats")
        slug = (item.get("slug") or "").strip()
        if not name:
            raise ValueError(f"{path}: company entry without a name: {item!r}")
        if ats not in ATS_SOURCES:
            raise ValueError(f"{path}: unknown ats {ats!r} for {name!r}")
        if not _SLUG_RE.fullmatch(slug):
            raise ValueError(f"{path}: invalid slug {slug!r} for {name!r}")
        if name in names:
            raise ValueError(f"{path}: duplicated company {name!r}")
        if (ats, slug) in boards:
            raise ValueError(f"{path}: duplicated board {ats}:{slug}")
        names.add(name)
        boards.add((ats, slug))
        entries.append({
            "name": name, "ats": ats, "slug": slug,
            "priority": item.get("priority"), "hires_in_ar": item.get("hires_in_ar"),
            "notes": item.get("notes"), "active": bool(item.get("active", True)),
        })
    return entries
