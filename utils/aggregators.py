"""Load the hand-checked aggregator company list (config/aggregators.json)."""
import json
from pathlib import Path

AGGREGATORS_FILE = Path(__file__).resolve().parent.parent / "config" / "aggregators.json"


def load_aggregators(path=None):
    """Return [(company, category, reason)] from the aggregator data file.

    Raises ValueError if the file is malformed: an entry without a company,
    a category not declared in "categories", or a duplicated company.
    """
    path = Path(path) if path is not None else AGGREGATORS_FILE
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    categories = data.get("categories") or {}
    entries = []
    seen = set()
    for item in data.get("companies") or []:
        company = (item.get("company") or "").strip()
        category = item.get("category")
        if not company:
            raise ValueError(f"{path}: aggregator entry without a company: {item!r}")
        if category not in categories:
            raise ValueError(f"{path}: unknown category {category!r} for {company!r}")
        if company in seen:
            raise ValueError(f"{path}: duplicated company {company!r}")
        seen.add(company)
        entries.append((company, category, item.get("reason")))
    return entries
