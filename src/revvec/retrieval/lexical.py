"""Lexical scorer for Stage 2 of three-tier hybrid retrieval.

The point: embedding models have never seen industrial and aerospace codes
like VF2-03, SOP-ME-112, NASA-STD-5017, sol 1214, Alarm 7234, or CTQ-241C.
Pure semantic search on a query containing one of those codes returns
high-semantic-similarity but wrong-code documents. The lexical overlap signal
rescues this.

Algorithm:
  1. Extract alphanumeric codes intact (regex: letter+digit tokens, optionally
     hyphenated).
  2. Normalise the rest: lowercase, strip punctuation, tokenize on whitespace.
  3. Drop tokens < 3 chars or in an aerospace/manufacturing stopword list.
  4. Union of (codes, regular tokens) = the keyword set.

Overlap scoring follows the SignalWeave-tested recipe: the keyword-match
fraction is computed against the QUERY's keyword set (so a query with rare
codes is weighted appropriately).
"""
from __future__ import annotations

import re
from typing import Iterable


# Regex for alphanumeric industrial/aerospace codes:
# A token with at least one letter AND at least one digit, optionally hyphenated.
# Matches: VF2-03, SOP-ME-112, NASA-STD-5017, CTQ-241C, Alarm7234, sol1214, 7234
# Also matches pure-digit runs of ≥ 4 chars (alarm codes, sol numbers).
_CODE_PATTERNS = [
    # mixed alphanumeric (letter+digit, possibly hyphenated)
    re.compile(r"\b[A-Za-z]+[0-9]+[A-Za-z0-9-]*\b"),
    re.compile(r"\b[A-Za-z]+(?:-[A-Za-z0-9]+)+\b"),
    re.compile(r"\b[0-9]+[A-Za-z]+[A-Za-z0-9-]*\b"),
    # pure-digit codes ≥ 4 digits (alarm IDs, sol numbers, part IDs)
    re.compile(r"\b[0-9]{4,}\b"),
]

# Aerospace + manufacturing stopwords (in addition to standard English stopwords).
STOPWORDS: frozenset[str] = frozenset({
    # standard English
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "have", "has", "had", "been", "being", "will", "would", "could", "should",
    "may", "might", "must", "can", "cannot", "not", "but", "nor", "yet",
    "you", "your", "yours", "they", "them", "their", "its",
    # manufacturing / aerospace hedge-words
    "data", "system", "systems", "component", "components", "report", "reports",
    "analysis", "design", "process", "method", "methods", "using", "used",
    "study", "studies", "result", "results", "figure", "table",
    "paper", "papers", "section", "reference", "references",
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "based", "due", "given", "shall", "such", "many", "also", "new", "test", "tests",
    "part", "parts", "time", "times",
})


def extract_keywords(text: str) -> set[str]:
    """Return a set of retrievable keywords from free text.

    Preserves alphanumeric industrial codes (case-normalised to UPPER) and
    pulls out regular content words (case-normalised to lower, stopwords
    stripped, length >= 3).
    """
    if not text:
        return set()

    # Pass 1: alphanumeric codes
    codes: set[str] = set()
    remaining_spans: list[tuple[int, int]] = [(0, len(text))]
    for pat in _CODE_PATTERNS:
        for m in pat.finditer(text):
            codes.add(m.group(0).upper())

    # Pass 2: remaining words (codes stay in the string but will be re-tokenised;
    # since codes contain digits, they'd normally not match stopwords anyway —
    # we UPPER them in the code-set so when we then lowercase + filter we
    # don't double-count them).
    normalised = re.sub(r"[^\w\s-]", " ", text.lower())
    tokens = {
        tok for tok in normalised.split()
        if len(tok) >= 3 and tok not in STOPWORDS and not any(c.isdigit() for c in tok)
    }

    return codes | tokens


def lexical_overlap(query_keywords: set[str], doc_keywords: set[str]) -> float:
    """Fraction of query keywords present in the document's keyword set."""
    if not query_keywords:
        return 0.0
    overlap = query_keywords & doc_keywords
    return len(overlap) / len(query_keywords)


def hybrid_score(
    semantic: float,
    query_keywords: set[str],
    doc_keywords: set[str],
    *,
    semantic_weight: float = 0.7,
    lexical_weight: float = 0.3,
) -> float:
    """0.7 · semantic + 0.3 · lexical (SignalWeave-tested recipe)."""
    return semantic_weight * semantic + lexical_weight * lexical_overlap(query_keywords, doc_keywords)


# Thresholds used by RetrievalAgent's Stage-2 filter (SignalWeave-borrowed defaults).
SEMANTIC_MIN = 0.30
LEXICAL_MIN = 0.10
FINAL_MIN = 0.35


def passes_hybrid_threshold(
    semantic: float,
    query_keywords: set[str],
    doc_keywords: set[str],
) -> tuple[bool, float, float]:
    """Return (passes, lexical_score, final_score) for a (semantic, q_kw, d_kw)."""
    lex = lexical_overlap(query_keywords, doc_keywords)
    final = 0.7 * semantic + 0.3 * lex
    passes = (semantic >= SEMANTIC_MIN or lex >= LEXICAL_MIN) and final >= FINAL_MIN
    return passes, lex, final
