"""
Time Context Service

What period the user's data actually covers, and what "today" means to it.

"Last quarter" only means something relative to a clock, and the clock the
user's data runs on is not the wall clock: an uploaded extract can end months
or years before today. Anchoring relative periods to the real date is how a
question like "top products last quarter" ends up filtering to a window the
data has never contained, and returning nothing.

Coverage is derived from the schema, never from column names, so it works on
any uploaded dataset. The anchor is a value, not a call to ``datetime.now()``,
so the behaviour is deterministic and testable.
"""

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date

logger = logging.getLogger(__name__)

#: Coverage rarely changes within a session, and profiling costs a table scan.
_CACHE: dict[tuple, tuple[float, "TimeCoverage"]] = {}
_TTL_SECONDS = 300


@dataclass
class TimeCoverage:
    """The span of time the scoped tables describe."""
    min_date: str | None = None
    max_date: str | None = None
    #: {table: [time column names, best first]}
    columns: dict[str, list[str]] = field(default_factory=dict)

    @property
    def known(self) -> bool:
        return bool(self.min_date and self.max_date)

    @property
    def anchor(self) -> str | None:
        """
        The date relative expressions should be read against.

        The latest date in the data: it is what the user means by "now" when
        they are looking at an extract that stopped being updated.
        """
        return self.max_date

    def describe(self) -> str:
        if not self.known:
            return "The data has no usable date column."
        return f"{self.min_date} to {self.max_date}"


def _date_only(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:10] if len(text) >= 10 else text or None


def coverage(tables: list[str] | None = None) -> TimeCoverage:
    """
    The widest date span across ``tables``, with the time columns that carry it.

    Candidate columns come from the same profiler the prediction engine uses,
    so a column called ``when_on`` counts exactly as much as one called
    ``date``. Failure is never fatal: an unprofilable table simply contributes
    no coverage.
    """
    from services.database import get_all_table_names, get_database_path

    names = list(tables) if tables else get_all_table_names()
    if not names:
        return TimeCoverage()

    key = (get_database_path(), tuple(sorted(names)))
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < _TTL_SECONDS:
        return hit[1]

    from prediction.profiler import build_profile

    result = TimeCoverage()
    for table in names:
        try:
            profile = build_profile(table)
        except Exception as exc:
            logger.debug("[TimeContext] Could not profile %s: %s", table, exc)
            continue

        for candidate in profile.time_columns:
            lo, hi = _date_only(candidate.min_date), _date_only(candidate.max_date)
            if not lo or not hi:
                continue
            result.columns.setdefault(table, []).append(candidate.column)
            if result.min_date is None or lo < result.min_date:
                result.min_date = lo
            if result.max_date is None or hi > result.max_date:
                result.max_date = hi

    _CACHE[key] = (time.time(), result)
    logger.info(
        "[TimeContext] Coverage for %s: %s (time columns: %s)",
        names, result.describe(), result.columns or "none",
    )
    return result


def years_outside(text: str, cov: TimeCoverage) -> list[int]:
    """Calendar years named in ``text`` that the data does not reach at all."""
    if not cov.known:
        return []
    lo, hi = int(cov.min_date[:4]), int(cov.max_date[:4])
    named = sorted({int(y) for y in re.findall(r"\b(1[89]\d\d|2\d\d\d)\b", text or "")})
    return [y for y in named if y < lo or y > hi]


def named_periods(anchor: str) -> list[tuple[str, str, str]]:
    """
    Literal [start, end) windows for the periods people name, anchored to a date.

    These are computed here rather than left to the SQL writer because SQLite's
    date arithmetic has two traps that silently produce nothing: subtracting a
    month from a month-end overflows (2022-03-31 '-1 month' is 2022-03-03), and
    'end of month' is not a modifier at all, so it returns NULL and empties the
    whole predicate.

    Returns (label, start_inclusive, end_exclusive).
    """
    y, m, d = (int(x) for x in str(anchor)[:10].split("-"))
    _ = date(y, m, d)          # reject an unparseable anchor early

    def month_start(year: int, month: int) -> date:
        year += (month - 1) // 12
        month = (month - 1) % 12 + 1
        return date(year, month, 1)

    this_month = month_start(y, m)
    quarter_first_month = m - (m - 1) % 3
    this_quarter = month_start(y, quarter_first_month)
    last_quarter = month_start(y, quarter_first_month - 3)

    iso = lambda x: x.isoformat()
    return [
        ("this month", iso(this_month), iso(month_start(y, m + 1))),
        ("last month", iso(month_start(y, m - 1)), iso(this_month)),
        ("this quarter", iso(this_quarter),
         iso(month_start(this_quarter.year, this_quarter.month + 3))),
        ("last quarter", iso(last_quarter), iso(this_quarter)),
        ("this year", iso(date(y, 1, 1)), iso(date(y + 1, 1, 1))),
        ("last year", iso(date(y - 1, 1, 1)), iso(date(y, 1, 1))),
    ]


def prompt_block(cov: TimeCoverage) -> str:
    """
    The coverage, phrased for a SQL-writing prompt.

    It states the anchor date rather than leaving the model to use the wall
    clock, and lists the windows literally so no SQLite date arithmetic is
    needed to hit them.
    """
    if not cov.known:
        return ("DATA COVERAGE: this dataset has no usable date column, so do "
                "not add any date filter.")

    columns = ", ".join(
        f"{table}.{col}" for table, cols in cov.columns.items() for col in cols
    )
    windows = "\n".join(
        f"    {label}: >= '{start}' AND < '{end}'"
        for label, start, end in named_periods(cov.max_date)
    )
    return (
        f"DATA COVERAGE: the data runs from {cov.min_date} to {cov.max_date} "
        f"(date columns: {columns}).\n"
        f"- Treat {cov.max_date} as TODAY. The data stops there; the real "
        f"calendar date is irrelevant to this database.\n"
        f"- Never use date('now'), CURRENT_DATE or strftime(..., 'now'): they "
        f"resolve to the real date, which is outside the data, so the query "
        f"would return nothing.\n"
        f"- Use these exact windows when the question names a period. Each is "
        f"[start, end): filter with >= start AND < end.\n{windows}\n"
        f"- For a rolling window use date('{cov.max_date}', '-30 days') style "
        f"arithmetic. Never use the modifier 'end of month': SQLite has no such "
        f"modifier and it makes the whole condition NULL, matching no rows."
    )


def invalidate() -> None:
    """Forget cached coverage, e.g. after an upload changes the data."""
    _CACHE.clear()
