"""Single source of truth for search normalisation.

Called at INDEX time (``import_pipeline.build_fts`` writes the normalised
columns on ``medicine_fts``) and at QUERY time (``search.py``), so the two can
never drift — a value normalised for storage is byte-compared against the very
same formula applied to the query.

Why this exists
---------------
The original search normalised every one of 25,405 candidate rows in Python on
every keystroke (six ``re.sub`` passes each) and could not use an index, because
the stored text was not normalised. That is what made typing feel slow
(263–365 ms for a single character). Normalising once at import time turns each
runtime comparison into a plain string operation and lets SQLite drive the
prefix narrowing through a covering index.
"""
from __future__ import annotations

import re

# Bangla digits ০-৯ -> ASCII, so "৫০০" and "500" are the same query.
BN_MAP = str.maketrans("\u09e6\u09e7\u09e8\u09e9\u09ea\u09eb\u09ec\u09ed\u09ee\u09ef", "0123456789")

_NON_WORD = re.compile(r"[^0-9a-z\u0980-\u09ff]+")
_WS = re.compile(r"\s+")

# High sentinel for a prefix range scan: everything that starts with ``q`` is
# < ``q + \uffff`` under BINARY collation, so ``>= q AND < q+\uffff`` is exactly
# ``LIKE 'q%'`` but index-usable (LIKE cannot use a BINARY index in SQLite).
PREFIX_HIGH = "\uffff"


def norm(value: str | None) -> str:
    """Lower-case, fold Bangla digits, collapse punctuation/space. Never None."""
    if not value:
        return ""
    text = str(value).translate(BN_MAP).lower()
    text = _NON_WORD.sub(" ", text)
    return _WS.sub(" ", text).strip()


def first_token(value: str | None) -> str:
    """First normalised word: 'Napa Extend' -> 'napa'."""
    n = norm(value)
    return n.split(" ", 1)[0] if n else ""


def prefix_high(q: str) -> str:
    return q + PREFIX_HIGH
