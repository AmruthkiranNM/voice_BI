"""
Prediction Package — Intent Markers

Deterministic, domain-free tests for whether a question is about the future.

These are linguistic markers, not a catalogue of questions: they carry no
knowledge of countries, products or revenue, and behave the same on a dataset
about shipments or patients. They give the router a fast, offline answer, and
give the configuration resolver a fallback for when interpretation is
unavailable.
"""

from __future__ import annotations

import re

#: Future tense, expectation, and projection language.
#: Note the deliberate omission of "may": as a modal it is a future marker,
#: but as a month name it appears in ordinary historical questions ("revenue
#: in May"), and misreading those as forecasts is the worse error. "Might",
#: "could" and "would" carry the same modal sense without the collision.
FUTURE_MARKERS = re.compile(
    r"\b(will|won't|shall|going to|about to|might|could|would|"
    r"expect\w*|anticipat\w*|likely|unlikely|probabl\w*|"
    r"forecast\w*|predict\w*|project(?:ed|ion|ions)?|"
    r"future|upcoming|next|ahead|soon|outlook|trajectory|"
    r"remain|stay|continue|persist)\b",
    re.IGNORECASE,
)

#: Named prediction tasks that are predictive regardless of tense. "Risk" in
#: any of its usual constructions is a model output, not a recorded fact —
#: a dataset stores what happened, not how risky something is.
TASK_MARKERS = re.compile(
    r"\b(churn\w*|attrition|retention|propensity|likelihood|estimate\w*|"
    r"(?:high|low|elevated|increased|greatest|at)[- ]risk|"
    r"risk\s+(?:of|score|level|band|group)|"
    r"scor\w+\s+(?:for|by)\s+risk)\b",
    re.IGNORECASE,
)

#: Past-tense markers. Present so an explicitly historical question is not
#: pulled into the prediction pipeline by an incidental "next".
PAST_MARKERS = re.compile(
    r"\b(was|were|had|did|last (?:year|month|quarter|week)|"
    r"previous|prior|historical\w*|so far|to date|yesterday)\b",
    re.IGNORECASE,
)


def is_predictive_question(question: str) -> tuple[bool, str]:
    """
    Whether a question asks about the future. Returns (verdict, reason).

    A named prediction task settles it outright. Otherwise future language
    decides, unless the question is also explicitly framed in the past, in
    which case the historical reading wins — "what were sales last month"
    should not become a forecast because it contains the word "last".
    """
    text = question or ""

    task = TASK_MARKERS.search(text)
    if task:
        return True, f"names a prediction task ('{task.group(0)}')"

    future = FUTURE_MARKERS.search(text)
    if not future:
        return False, "no future or prediction language"

    past = PAST_MARKERS.search(text)
    if past and not re.search(r"\b(will|forecast\w*|predict\w*|next|expect\w*)\b",
                              text, re.IGNORECASE):
        return False, f"framed in the past ('{past.group(0)}')"

    return True, f"future language ('{future.group(0)}')"
