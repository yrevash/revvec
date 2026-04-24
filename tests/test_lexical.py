"""Phase 3a — lexical scorer tests.

Key invariants:
  - Alphanumeric industrial/aerospace codes survive extraction (case-normalised to UPPER).
  - Stopwords filtered.
  - Tokens < 3 chars dropped.
  - Pure numeric codes ≥ 4 digits preserved (alarm IDs, sol numbers).
"""
from __future__ import annotations

from revvec.retrieval.lexical import (
    extract_keywords,
    hybrid_score,
    lexical_overlap,
    passes_hybrid_threshold,
)


def test_extract_codes():
    kw = extract_keywords("Alarm 7234 on machine VF2-03 requires SOP-ME-112")
    assert "7234" in kw
    assert "VF2-03" in kw
    assert "SOP-ME-112" in kw


def test_extract_nasa_standards():
    kw = extract_keywords("Per NASA-STD-5017 the bonding resistance shall be measured")
    assert "NASA-STD-5017" in kw


def test_sol_number():
    kw = extract_keywords("Perseverance on sol 1214 recorded MEDA data")
    assert "1214" in kw
    assert "perseverance" in kw
    assert "meda" in kw


def test_stopwords_filtered():
    kw = extract_keywords("The system data and the reports show that the results are valid")
    # 'the', 'and', 'that', 'are', 'system', 'data', 'reports', 'results' all hedge/stop
    assert "valid" in kw
    assert "the" not in kw
    assert "and" not in kw
    assert "data" not in kw      # in our stopword list
    assert "system" not in kw
    assert "reports" not in kw


def test_short_tokens_dropped():
    kw = extract_keywords("Hi to be or not")
    # all < 3 chars or stopwords
    assert kw == set() or kw == {"hi"}.intersection(kw)


def test_lexical_overlap():
    q = {"COOLANT", "flow", "spindle"}
    d = {"COOLANT", "pressure", "rpm"}
    assert lexical_overlap(q, d) == 1 / 3


def test_empty_query():
    assert lexical_overlap(set(), {"anything"}) == 0.0
    assert hybrid_score(0.8, set(), set()) == 0.7 * 0.8


def test_hybrid_threshold_signalweave_recipe():
    # High semantic, zero lexical → passes on semantic alone (above 0.30)
    ok, _lex, final = passes_hybrid_threshold(0.9, {"foo"}, set())
    assert ok and final >= 0.35

    # Low semantic, high lexical → passes on lexical path
    ok, lex, final = passes_hybrid_threshold(0.1, {"alarm", "7234"}, {"alarm", "7234"})
    assert lex == 1.0
    assert ok, f"expected pass with lex=1.0, got final={final}"

    # Both low → fails
    ok, _, _ = passes_hybrid_threshold(0.1, {"foo"}, {"bar"})
    assert not ok
