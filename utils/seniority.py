"""Seniority level helpers for the "Hide above my level" filter."""
import re

from config.settings import (ABOVE_LEVEL_TITLE_TERMS, SENIORITY_ORDER,
                             TARGET_LEVEL_TITLE_TERMS)


def levels_above(target_levels, order=SENIORITY_ORDER):
    """Return the levels in `order` ranked above the highest target level.

    Values outside `order` ("Not Applicable", NULL, anything unexpected) are
    never above the target. An empty target list hides nothing.

    Raises ValueError for a target level not in `order`.
    """
    unknown = [level for level in target_levels if level not in order]
    if unknown:
        raise ValueError(
            f"Unknown seniority level(s) {unknown}; expected one of {list(order)}")
    if not target_levels:
        return []
    highest = max(order.index(level) for level in target_levels)
    return list(order[highest + 1:])


def _word_regex(terms):
    return re.compile(r"\b(?:" + "|".join(terms) + r")\b", re.IGNORECASE)


_ABOVE_TITLE_RE = _word_regex(ABOVE_LEVEL_TITLE_TERMS)
_TARGET_TITLE_RE = _word_regex(TARGET_LEVEL_TITLE_TERMS)


def title_above_level(title):
    """True if the title names a level above mine ("Senior", "Tech Lead").

    A title that also names a target level ("Ssr", "Jr") is kept. NULL or
    empty titles are never above.
    """
    if not title:
        return False
    return bool(_ABOVE_TITLE_RE.search(title)) and not _TARGET_TITLE_RE.search(title)
