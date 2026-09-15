"""
Evidence-grounded explanation layer for predictions.

A forecast can support four kinds of statement, and only the first three are
ever available from a sales table:

    OBSERVED DATA        what the data records happened
    FORECAST             what the model projects will happen
    MODEL INTERPRETATION how the projection relates to the record, and how well
                         the model validated
    CAUSAL CLAIM         *why* it happened

The fourth requires evidence this system does not have. Revenue by country and
month says nothing about consumer demand, marketing, pricing or competition,
so an explanation that offers those as reasons is inventing them — however
plausible it sounds, and however accurate the numbers around it are.

This module keeps the language model in its proper role: it phrases evidence it
is given, and every number and claim it produces is checked against that
evidence before the user sees it. When the check fails, the deterministic text
is returned instead. The model is never the source of a number.
"""

from __future__ import annotations

import logging
import re

from services.llm_service import call_llm

logger = logging.getLogger(__name__)


EVIDENCE_PROMPT = """You are a Business Advisor AI explaining a statistical forecast.

The user asked: "{message}"

Everything you are allowed to state is in the EVIDENCE block below. It was
computed deterministically by forecasting code — you must not recompute,
adjust, round differently, or add to it.

═══════════ EVIDENCE ═══════════
{evidence}
════════════════════════════════

WHAT YOU MAY SAY — these are supported:
  - OBSERVED: what the historical figures in the evidence show.
  - FORECAST: what the model projects, phrased as a projection
    ("the model projects", "the forecast for the period is", "is projected to").
  - MODEL INTERPRETATION: how the forecast compares with the historical
    baseline, which model was selected, and how it scored in validation.

WHAT YOU MUST NOT SAY — there is no evidence for any of it:
  - Any REASON, CAUSE or DRIVER for a number. The evidence contains quantities
    over time and nothing else: no consumer behaviour, demand, preferences,
    marketing, pricing, competition, seasonality rationale, economic conditions,
    supply, or market dynamics.
  - Never write "because", "due to", "driven by", "thanks to", "as a result of",
    "reflects growing/rising ...", or any equivalent causal phrasing.
  - Any number that does not appear in the EVIDENCE block.
  - Any entity, product, region or category not named in the EVIDENCE block.

If the user asks *why* something is expected, say plainly that the data shows
what is happening but does not establish why, then give the supporting figures
from the evidence (the historical pattern and the projection) as what the
projection is based on.

STYLE: 2-4 sentences, plain business English, **bold** for key figures.
Do not mention model internals beyond the model name and its validation score.

Write the explanation now:"""


# Generic causal connectives. This is a linguistic list, not a business one —
# it carries no assumption about the domain and would catch a fabricated cause
# for churn, headcount or defect rates just as readily as one for revenue.
_CAUSAL_PATTERNS = [
    r"\bbecause\b",
    r"\bdue to\b",
    r"\bdriven by\b",
    r"\bdrivers?\s+(?:of|are|is|include)\b",
    r"\bthanks to\b",
    r"\bas a result of\b",
    r"\bcaused by\b",
    r"\bowing to\b",
    r"\battributable to\b",
    r"\battributed to\b",
    r"\bstems? from\b",
    r"\bresult(?:s|ing)? from\b",
    r"\bthe reason (?:for|why|being)\b",
    r"\bexplains? why\b",
    r"\bleads? to\b",
    r"\bled to\b",
    r"\bleading to\b",
    r"\breflect(?:s|ing)? (?:growing|rising|increasing|strong|weak|declining)\b",
    r"\bfuel(?:s|led|ed|ling)?\s+by\b",
    r"\bon the back of\b",
    r"\bboosted by\b",
    r"\bsupported by (?:strong|growing|rising)\b",
]

# Small integers are ordinals, ranks, month counts and the like; requiring them
# to appear verbatim in the evidence would reject correct prose.
_SAFE_SMALL_INT_MAX = 31

# Relative tolerance when matching a quoted figure against the evidence, so
# "617,904" matches 617904.0 and "152.6%" matches 152.63.
_NUMERIC_TOLERANCE = 0.02


def find_causal_claims(text: str) -> list[str]:
    """Return the causal phrases present in a generated explanation."""
    found = []
    for pattern in _CAUSAL_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            found.append(match.group(0).strip())
    return found


def _numbers_in(text: str) -> list[float]:
    """Every numeric literal in a string, commas and currency symbols removed."""
    values = []
    for raw in re.findall(r"-?\d[\d,]*(?:\.\d+)?", text or ""):
        try:
            values.append(float(raw.replace(",", "")))
        except ValueError:
            continue
    return values


def find_ungrounded_numbers(text: str, evidence: str) -> list[float]:
    """
    Numbers in the explanation that do not appear in the evidence.

    A figure the model produced on its own is the clearest signal that it has
    started reasoning past its source, so it invalidates the explanation even
    when the surrounding prose reads well.
    """
    allowed = _numbers_in(evidence)
    ungrounded = []
    for value in _numbers_in(text):
        if abs(value) <= _SAFE_SMALL_INT_MAX and float(value).is_integer():
            continue
        if any(
            abs(value - candidate) <= _NUMERIC_TOLERANCE * max(abs(candidate), 1.0)
            for candidate in allowed
        ):
            continue
        ungrounded.append(value)
    return ungrounded


def verify(text: str, evidence: str) -> tuple[bool, list[str]]:
    """
    Check a generated explanation against its evidence.

    Returns (ok, problems).
    """
    problems = []
    for phrase in find_causal_claims(text):
        problems.append(f"unsupported causal claim: '{phrase}'")
    for value in find_ungrounded_numbers(text, evidence):
        problems.append(f"number not present in the evidence: {value:,.2f}")
    return (not problems), problems


def explain(
    message: str,
    evidence: str,
    fallback: str | None = None,
    *,
    max_attempts: int = 2,
) -> str:
    """
    Produce a natural-language explanation that is verifiably grounded.

    The model is asked to phrase the evidence. Its output is then checked for
    invented numbers and causal claims. A failed attempt is retried once with
    the specific problems named; if it still fails, the deterministic evidence
    text is returned verbatim. A plainer true answer beats a fluent invented
    one.
    """
    if not evidence or not evidence.strip():
        return fallback or "I don't have enough information to explain that."

    prompt = EVIDENCE_PROMPT.format(message=message, evidence=evidence)
    last_problems: list[str] = []

    for attempt in range(1, max_attempts + 1):
        try:
            text = call_llm(prompt, expect_json=False).strip()
        except Exception as exc:
            logger.warning("[Explanation] LLM call failed (%s); using deterministic text.", exc)
            return fallback or evidence

        ok, problems = verify(text, evidence)
        if ok:
            return text

        last_problems = problems
        logger.warning(
            "[Explanation] Attempt %d rejected: %s", attempt, "; ".join(problems),
        )
        if attempt < max_attempts:
            prompt = (
                EVIDENCE_PROMPT.format(message=message, evidence=evidence)
                + "\n\nYour previous answer was rejected for these reasons:\n"
                + "\n".join(f"  - {p}" for p in problems)
                + "\nRewrite it using ONLY the evidence above. State no causes, "
                  "and use no number that is not in the evidence."
            )

    logger.warning(
        "[Explanation] Falling back to deterministic text after %d attempts: %s",
        max_attempts, "; ".join(last_problems),
    )
    return fallback or evidence


def no_cause_available_note(target: str) -> str:
    """
    The standard, honest answer to a "why?" question about a forecast.

    Kept in one place so every agent answers it identically.
    """
    return (
        f"The data records {target} by period, so it can show *what* is projected "
        "and how that compares with the past, but it does not contain the "
        "information needed to establish *why* — that would require data on "
        "pricing, promotion, customer behaviour or market conditions, none of "
        "which is in this dataset."
    )
