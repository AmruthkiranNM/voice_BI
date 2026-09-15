"""
Prediction Package — Time Resolution

Answers three questions generically, from the data rather than from phrasing:

  * which column carries the time axis,
  * what bucket size the history can actually support,
  * how far ahead "next quarter" or "the next 30 days" reaches.

Horizons are always resolved relative to the **latest valid date in the data**,
never to today's calendar. A dataset that ends in March 2022 forecasts forward
from March 2022, whichever year the question is asked in.

The horizon is also expressed in the frequency the history supports. "Next
year" against monthly history is twelve monthly periods, not one annual point:
aggregating fifteen months into two annual buckets leaves nothing to model and
silently compares a partial year against a whole one.
"""

from __future__ import annotations

import dataclasses
import logging
import re

import pandas as pd

from prediction.series_validation import normalize_frequency

logger = logging.getLogger(__name__)


#: Periods of each frequency in one of the next-coarser unit. Used to express a
#: horizon stated in one unit using the frequency the data supports.
PERIODS_PER_UNIT = {
    "days":     {"days": 1, "weeks": 7, "months": 30, "quarters": 91, "years": 365},
    "weeks":    {"weeks": 1, "months": 4, "quarters": 13, "years": 52},
    "months":   {"months": 1, "quarters": 3, "years": 12},
    "quarters": {"quarters": 1, "years": 4},
    "years":    {"years": 1},
}

_FREQ_ORDER = ["days", "weeks", "months", "quarters", "years"]

_UNIT_WORDS = {
    "day": "days", "days": "days", "daily": "days",
    "week": "weeks", "weeks": "weeks", "weekly": "weeks",
    "month": "months", "months": "months", "monthly": "months",
    "quarter": "quarters", "quarters": "quarters", "quarterly": "quarters",
    "year": "years", "years": "years", "yearly": "years", "annual": "years",
    "period": None, "periods": None,   # unit-less: adopt the data's frequency
}

_NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "eighteen": 18, "twenty": 20, "thirty": 30, "sixty": 60,
}


@dataclasses.dataclass
class TimeColumnProfile:
    """What a candidate time column looks like."""
    column: str
    n_parsed: int = 0
    parse_ratio: float = 0.0
    min_date: str | None = None
    max_date: str | None = None
    span_days: float = 0.0
    n_distinct: int = 0
    median_step_days: float = 0.0
    inferred_frequency: str = "months"
    is_monotonic: bool = False
    score: float = 0.0


@dataclasses.dataclass
class HorizonSpec:
    """A resolved forecast horizon."""
    periods: int = 0
    frequency: str = "months"
    requested_unit: str | None = None
    requested_count: int | None = None
    anchor: str | None = None          # last observed period the forecast starts from
    forecast_start: str | None = None
    forecast_end: str | None = None
    source: str = ""                   # how it was derived
    warnings: list[str] = dataclasses.field(default_factory=list)


# ──────────────────────────────────────────────────────────
# Time column detection
# ──────────────────────────────────────────────────────────

def profile_time_columns(df: pd.DataFrame, max_sample: int = 500) -> list[TimeColumnProfile]:
    """
    Profile every column that could serve as the time axis, best first.

    Scoring rewards what actually makes a column usable for forecasting: values
    that parse as dates, a wide span, many distinct points, and regular spacing.
    A name that looks temporal is a small bonus, never a requirement — a column
    called ``when_on`` or ``period_start`` is as valid as one called ``date``.
    """
    import warnings as _warnings

    profiles: list[TimeColumnProfile] = []

    for column in df.columns:
        series = df[column].dropna()
        if series.empty:
            continue

        is_datetime = pd.api.types.is_datetime64_any_dtype(df[column])
        if not is_datetime:
            # Bare numbers parse as epochs; that is not evidence of a date.
            if pd.api.types.is_numeric_dtype(series):
                continue
            sample = series.head(max_sample)
            try:
                with _warnings.catch_warnings():
                    _warnings.simplefilter("ignore")
                    parsed_sample = pd.to_datetime(sample, errors="coerce")
            except (ValueError, TypeError):
                continue
            ratio = float(parsed_sample.notna().mean())
            if ratio < 0.8:
                continue
        else:
            ratio = 1.0

        try:
            with _warnings.catch_warnings():
                _warnings.simplefilter("ignore")
                parsed = pd.to_datetime(series, errors="coerce").dropna()
        except (ValueError, TypeError):
            continue
        if parsed.empty:
            continue

        profile = TimeColumnProfile(column=column, n_parsed=int(len(parsed)), parse_ratio=ratio)
        profile.min_date = str(parsed.min())
        profile.max_date = str(parsed.max())
        profile.span_days = float((parsed.max() - parsed.min()).total_seconds() / 86400.0)
        profile.n_distinct = int(parsed.nunique())
        profile.is_monotonic = bool(parsed.is_monotonic_increasing)

        from prediction.series_validation import infer_frequency, median_step_days
        profile.median_step_days = median_step_days(parsed)
        profile.inferred_frequency = infer_frequency(parsed)

        score = 2.0 * ratio
        if profile.span_days > 0:
            score += 1.0
        if profile.n_distinct >= 10:
            score += 1.0
        if is_datetime:
            score += 1.0
        if re.search(r"date|time|day|month|year|period|when|stamp", column, re.IGNORECASE):
            score += 0.5
        profile.score = round(score, 3)
        profiles.append(profile)

    profiles.sort(key=lambda p: (-p.score, -p.span_days, p.column))
    return profiles


def select_time_column(
    df: pd.DataFrame,
    question: str = "",
    preferred: str | None = None,
) -> tuple[TimeColumnProfile | None, list[TimeColumnProfile]]:
    """
    Choose the time axis, preferring one the question actually names.

    A table with ``order_date`` and ``delivery_date`` has two valid axes, and
    which one is right depends on the question. Naming either one selects it;
    otherwise the best-scoring column wins.

    Returns (selected, all candidates).
    """
    candidates = profile_time_columns(df)
    if not candidates:
        return None, []

    if preferred:
        for candidate in candidates:
            if candidate.column.lower() == preferred.lower():
                return candidate, candidates

    if question:
        question_tokens = set(re.findall(r"[a-z0-9]+", question.lower()))
        best, best_overlap = None, 0
        for candidate in candidates:
            tokens = set(re.findall(r"[a-z0-9]+", candidate.column.lower()))
            overlap = len(tokens & question_tokens)
            # A bare "date" match is not a choice between two date columns.
            distinctive = tokens - {"date", "time", "at", "on", "the"}
            if overlap and distinctive & question_tokens and overlap > best_overlap:
                best, best_overlap = candidate, overlap
        if best is not None:
            logger.info("[Time] Question names '%s'; using it as the time axis.", best.column)
            return best, candidates

    return candidates[0], candidates


# ──────────────────────────────────────────────────────────
# Frequency
# ──────────────────────────────────────────────────────────

def _is_coarser(a: str, b: str) -> bool:
    return _FREQ_ORDER.index(a) > _FREQ_ORDER.index(b)


#: A series needs at least this many buckets to be worth modelling, and beyond
#: this many the buckets are finer than a business question usually wants.
MIN_USEFUL_PERIODS = 12
MAX_USEFUL_PERIODS = 200


def default_frequency(span_days: float, data_frequency: str) -> str:
    """
    Choose a reporting frequency when the question does not state one.

    Transactional records are almost always daily, but "daily" is rarely the
    resolution a business question wants — the raw sampling rate of the rows is
    not the same thing as the reporting period. Pick the coarsest bucket that
    still leaves enough periods to model, which lands on months for a year or
    two of daily transactions and on days for a dataset only weeks long.
    """
    data_frequency = normalize_frequency(data_frequency)
    if span_days <= 0:
        return data_frequency

    for frequency in reversed(_FREQ_ORDER):          # years → days
        if _is_coarser(data_frequency, frequency):
            continue                                  # finer than the records allow
        periods = span_days / PERIODS_PER_UNIT["days"][frequency]
        if MIN_USEFUL_PERIODS <= periods <= MAX_USEFUL_PERIODS:
            return frequency

    # Nothing sits in the comfortable band; take the coarsest that clears the
    # minimum, else fall back to the records' own granularity.
    for frequency in reversed(_FREQ_ORDER):
        if _is_coarser(data_frequency, frequency):
            continue
        if span_days / PERIODS_PER_UNIT["days"][frequency] >= MIN_USEFUL_PERIODS:
            return frequency
    return data_frequency


def resolve_frequency(
    requested: str | None,
    data_frequency: str,
    span_days: float = 0.0,
) -> tuple[str, list[str]]:
    """
    Settle the bucket size, honouring the question but bounded by the data.

    A request finer than the data supports (daily buckets over monthly records)
    would produce a series that is mostly empty, so it is widened to what the
    data can carry and the substitution is reported.
    """
    notes: list[str] = []
    data_frequency = normalize_frequency(data_frequency)

    if not requested:
        chosen = default_frequency(span_days, data_frequency)
        if chosen != data_frequency:
            notes.append(
                f"No reporting period was stated; using {chosen} buckets "
                f"({span_days:.0f} days of {data_frequency}-level records)."
            )
        return chosen, notes

    requested = normalize_frequency(requested)
    if _is_coarser(data_frequency, requested):
        notes.append(
            f"'{requested}' buckets were requested but the records are only "
            f"{data_frequency}-granular; using {data_frequency}."
        )
        return data_frequency, notes

    # Coarser than the data is fine — that is ordinary aggregation — but it
    # must still leave enough buckets to model. When it does not, fall back to
    # a sensible *reporting* period rather than to the raw sampling rate of the
    # rows: "next year" over 15 months of daily transactions means twelve
    # monthly periods, not 365 daily ones.
    if span_days:
        approx_periods = span_days / PERIODS_PER_UNIT["days"][requested]
        if approx_periods < 4:
            fallback = default_frequency(span_days, data_frequency)
            notes.append(
                f"{span_days:.0f} days of history gives fewer than 4 {requested} "
                f"buckets; reporting in {fallback} instead."
            )
            return fallback, notes

    return requested, notes


# ──────────────────────────────────────────────────────────
# Horizon
# ──────────────────────────────────────────────────────────

def parse_horizon_phrase(text: str) -> tuple[int | None, str | None]:
    """
    Extract a count and unit from natural language, without a phrase table.

    Handles "next 6 months", "the next three quarters", "over 30 days",
    "next year", "for 12 periods" and similar, by matching a number (digits or
    words) next to a time unit. Returns (count, unit); either may be None.
    """
    if not text:
        return None, None

    lowered = text.lower()
    unit_alt = "|".join(sorted(_UNIT_WORDS, key=len, reverse=True))
    number_alt = "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True))

    # "<number> <unit>", optionally preceded by next/coming/following/over/for.
    pattern = (
        rf"\b(?:next|coming|following|upcoming|over|for|in|within|ahead)?\s*"
        rf"(\d+|{number_alt})\s+({unit_alt})\b"
    )
    match = re.search(pattern, lowered)
    if match:
        raw_count, raw_unit = match.group(1), match.group(2)
        count = int(raw_count) if raw_count.isdigit() else _NUMBER_WORDS.get(raw_count)
        return count, _UNIT_WORDS.get(raw_unit)

    # A bare unit means one of it: "next quarter", "next year".
    bare = re.search(rf"\b(?:next|coming|following|upcoming)\s+({unit_alt})\b", lowered)
    if bare:
        return 1, _UNIT_WORDS.get(bare.group(1))

    return None, None


def resolve_horizon(
    question: str,
    frequency: str,
    last_period: pd.Timestamp | str | None,
    *,
    requested_periods: int | None = None,
    requested_unit: str | None = None,
    default_periods: int = 6,
) -> HorizonSpec:
    """
    Turn a stated horizon into a number of periods at the working frequency.

    "Next year" over monthly data becomes twelve monthly periods rather than a
    single annual bucket — same span, expressed at a resolution the history can
    actually support. The horizon always starts from the last observed period,
    so it is anchored to the data rather than to the current date.
    """
    frequency = normalize_frequency(frequency)
    spec = HorizonSpec(frequency=frequency)

    count, unit = requested_periods, requested_unit
    if count is None and unit is None:
        count, unit = parse_horizon_phrase(question)
        spec.source = "parsed_from_question" if count or unit else "default"
    else:
        spec.source = "explicit"

    spec.requested_count = count
    spec.requested_unit = unit

    if count is None and unit is None:
        spec.periods = default_periods
        spec.warnings.append(
            f"No horizon was stated; forecasting {default_periods} {frequency} ahead."
        )
    elif unit is None:
        # "next 8 periods" — periods of whatever the working frequency is.
        spec.periods = count or default_periods
    else:
        unit = normalize_frequency(unit)
        count = count or 1
        if unit == frequency:
            spec.periods = count
        elif _is_coarser(unit, frequency):
            # Express the coarser request at the working resolution.
            per = PERIODS_PER_UNIT.get(frequency, {}).get(unit)
            if per:
                spec.periods = count * per
                spec.warnings.append(
                    f"{count} {unit} expressed as {spec.periods} {frequency} periods, "
                    f"the resolution the history supports."
                )
            else:
                spec.periods = count
        else:
            # Finer than the working frequency: round up, never to zero.
            per = PERIODS_PER_UNIT.get(unit, {}).get(frequency)
            spec.periods = max(1, round(count / per)) if per else count
            spec.warnings.append(
                f"{count} {unit} rounded to {spec.periods} {frequency} period(s)."
            )

    spec.periods = max(1, int(spec.periods))

    if last_period is not None:
        anchor = pd.Timestamp(last_period)
        spec.anchor = str(anchor)
        offset = _offset_for(frequency)
        try:
            future = pd.date_range(start=anchor, periods=spec.periods + 1, freq=offset)[1:]
            spec.forecast_start = str(future[0])
            spec.forecast_end = str(future[-1])
        except Exception:  # pragma: no cover - exotic offsets
            pass

    return spec


def _offset_for(frequency: str) -> str:
    return {
        "days": "D", "weeks": "W", "months": "ME", "quarters": "QE", "years": "YE",
    }.get(normalize_frequency(frequency), "ME")
