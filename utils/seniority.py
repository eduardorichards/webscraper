"""Seniority level helpers for the "Hide above my level" filter."""
from config.settings import SENIORITY_ORDER


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
