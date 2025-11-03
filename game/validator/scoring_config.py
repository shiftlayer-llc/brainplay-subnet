"""
Scoring configuration helpers and defaults.

Provides a human-readable interval constant and a parser that converts
values like "7 days", "24 hours", "90 minutes" into seconds.
"""

from __future__ import annotations

import re
from datetime import timedelta


# Default scoring window. Can be overridden via CLI: --scoring.interval
SCORING_INTERVAL = "3 days"

_UNITS = {
    "s": 1,
    "sec": 1,
    "secs": 1,
    "second": 1,
    "seconds": 1,
    "m": 60,
    "min": 60,
    "mins": 60,
    "minute": 60,
    "minutes": 60,
    "h": 3600,
    "hr": 3600,
    "hrs": 3600,
    "hour": 3600,
    "hours": 3600,
    "d": 86400,
    "day": 86400,
    "days": 86400,
    "w": 604800,
    "wk": 604800,
    "wks": 604800,
    "week": 604800,
    "weeks": 604800,
}


def parse_interval_to_seconds(text: str | None) -> int:
    """Parses a human-readable interval like "7 days" into seconds.

    Accepts forms like "90m", "24 hours", "1 week", "7d", case-insensitive.
    Defaults to days if no unit is specified.
    """
    if not text:
        return int(timedelta(days=7).total_seconds())
    t = text.strip().lower()
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*([a-z]*)\s*$", t)
    if not m:
        return int(timedelta(days=7).total_seconds())
    value = float(m.group(1))
    unit = m.group(2) or "days"
    factor = _UNITS.get(unit, _UNITS["days"])
    return int(value * factor)
