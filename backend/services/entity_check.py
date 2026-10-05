"""
Names in a question that the selected data does not contain.

"Predict revenue for Germany" over data with no Germany must not quietly drop
the word and forecast the overall total: the answer would look like a German
forecast. A capitalised name in the middle of a question that matches no
column, table or stored value is reported instead.
"""
from __future__ import annotations

import re

_CALENDAR = {
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december", "jan", "feb", "mar", "apr",
    "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec", "monday",
    "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
}

_MAX_VALUES = 500


def _known_words(tables: list[str]) -> set[str]:
    from services.database import get_low_cardinality_values, get_table_schema

    words: set[str] = set()
    for t in tables:
        words.update(re.findall(r"[a-z0-9]+", t.lower()))
        schema = get_table_schema(t)
        for c in schema:
            words.update(re.findall(r"[a-z0-9]+", c["column_name"].lower()))
        for values in get_low_cardinality_values(t, schema=schema, max_distinct=_MAX_VALUES).values():
            for v in values:
                words.update(re.findall(r"[a-z0-9]+", str(v).lower()))
    return words


def unknown_names(question: str, tables: list[str] | None) -> list[str]:
    """Capitalised mid-sentence names in ``question`` absent from ``tables``."""
    if not tables or not question:
        return []
    words = re.findall(r"[A-Za-z][A-Za-z'&-]*", question)
    if len(words) < 2:
        return []
    caps = [w for w in words[1:] if w[0].isupper()]
    # Title-Cased Questions carry no signal about which words are names.
    if len(caps) > len(words[1:]) / 2:
        return []

    known = _known_words(tables)
    found, run = [], []
    sentence_start = True
    for token in re.findall(r"[A-Za-z][A-Za-z'&-]*|[.!?]", question):
        if token in ".!?":
            sentence_start = True
            run = []
            continue
        is_name = (token[0].isupper() and not sentence_start and len(token) > 1
                   and token.lower() not in _CALENDAR and token != "I")
        sentence_start = False
        if not is_name:
            run = []
            continue
        parts = re.findall(r"[a-z0-9]+", token.lower())
        if all(p in known for p in parts):
            run = []
            continue
        if run and found and found[-1] == " ".join(run):
            run.append(token)
            found[-1] = " ".join(run)
        else:
            run = [token]
            found.append(token)
    return found
