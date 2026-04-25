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
    # since codes contain digits, they'd normally not match stopwords anyway ,
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
    """0.7 cosine + 0.3 keyword overlap. Kept for callers that already have
    pre-extracted keyword sets; new code should prefer bm25_scores()."""
    return semantic_weight * semantic + lexical_weight * lexical_overlap(query_keywords, doc_keywords)


# ─── BM25 stage 2 ────────────────────────────────────────────────────────────
# Real Okapi BM25 over the candidate pool returned by Actian stage 1.
# Tokenisation is industrial-code-aware: codes like SOP-ME-112 or sol 1214
# survive intact instead of being shredded by a naive tokenizer.

def tokenize_for_bm25(text: str) -> list[str]:
    """Tokenize while preserving industrial codes."""
    if not text:
        return []
    codes: list[str] = []
    for pat in _CODE_PATTERNS:
        for m in pat.finditer(text):
            codes.append(m.group(0).upper())
    normalised = re.sub(r"[^\w\s-]", " ", text.lower())
    words = [
        tok for tok in normalised.split()
        if len(tok) >= 3 and tok not in STOPWORDS and not any(c.isdigit() for c in tok)
    ]
    return codes + words


def bm25_scores(
    query_text: str,
    doc_texts: list[str],
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[float]:
    """Score every candidate doc against the query with Okapi BM25.
    Output is min-max normalised to [0, 1] so it combines cleanly with cosine."""
    if not query_text or not doc_texts:
        return [0.0] * len(doc_texts)
    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        q_kw = extract_keywords(query_text)
        return [lexical_overlap(q_kw, extract_keywords(d)) for d in doc_texts]
    tokenized = [tokenize_for_bm25(d) for d in doc_texts]
    if not any(tokenized):
        return [0.0] * len(doc_texts)
    bm25 = BM25Okapi(tokenized, k1=k1, b=b)
    raw = bm25.get_scores(tokenize_for_bm25(query_text))
    lo, hi = float(min(raw)), float(max(raw))
    if hi <= 0:
        return [0.0] * len(doc_texts)
    span = hi - lo if hi > lo else 1.0
    return [max(0.0, (float(s) - lo) / span) for s in raw]


# Stage 2 thresholds. Tuned on our golden query set.
SEMANTIC_MIN = 0.30
LEXICAL_MIN = 0.10
FINAL_MIN = 0.35


def passes_hybrid_threshold(
    semantic: float,
    query_keywords: set[str],
    doc_keywords: set[str],
) -> tuple[bool, float, float]:
    """Legacy keyword-overlap variant. Returns (passes, lex, final)."""
    lex = lexical_overlap(query_keywords, doc_keywords)
    final = 0.7 * semantic + 0.3 * lex
    passes = (semantic >= SEMANTIC_MIN or lex >= LEXICAL_MIN) and final >= FINAL_MIN
    return passes, lex, final


def passes_bm25_threshold(semantic: float, bm25: float) -> tuple[bool, float]:
    """BM25 variant. Returns (passes, final_score)."""
    final = 0.7 * semantic + 0.3 * bm25
    passes = (semantic >= SEMANTIC_MIN or bm25 >= LEXICAL_MIN) and final >= FINAL_MIN
    return passes, final
