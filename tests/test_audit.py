"""Audit hash-chain tests — verify() must detect any tampering.

Covers:
  1. Empty log verifies OK.
  2. Normal append produces a chain that verifies.
  3. Byte-level tamper (edit any field) breaks the chain.
  4. Row deletion breaks the chain (prev_hash of next row no longer matches).
  5. Row insertion breaks the chain (hash doesn't match).
  6. Re-ordering rows breaks the chain.
"""
from __future__ import annotations

import json
from pathlib import Path

from revvec.audit.chain import AuditAgent


def test_empty_log_verifies(tmp_path: Path) -> None:
    a = AuditAgent(tmp_path)
    ok, n, _ = a.verify()
    assert ok and n == 0


def test_append_and_verify(tmp_path: Path) -> None:
    a = AuditAgent(tmp_path)
    for i in range(7):
        a.record({"action": "query", "i": i, "persona": "maintenance"})
    ok, n, err = a.verify()
    assert ok, err
    assert n == 7


def test_tamper_edit_field(tmp_path: Path) -> None:
    a = AuditAgent(tmp_path)
    for i in range(3):
        a.record({"action": "query", "i": i})

    p = a._current_path()
    lines = p.read_text().splitlines()
    row = json.loads(lines[1])
    row["action"] = "TAMPERED"
    lines[1] = json.dumps(row)
    p.write_text("\n".join(lines) + "\n")

    # Use a fresh agent so the in-memory last_hash doesn't shortcut verify
    a2 = AuditAgent(tmp_path)
    ok, _, err = a2.verify()
    assert not ok
    assert "mismatch" in err.lower() or "tamper" in err.lower()


def test_tamper_delete_row(tmp_path: Path) -> None:
    a = AuditAgent(tmp_path)
    for i in range(4):
        a.record({"action": "query", "i": i})
    p = a._current_path()
    lines = p.read_text().splitlines()
    del lines[2]
    p.write_text("\n".join(lines) + "\n")

    a2 = AuditAgent(tmp_path)
    ok, _, _ = a2.verify()
    assert not ok


def test_tamper_insert_row(tmp_path: Path) -> None:
    a = AuditAgent(tmp_path)
    for i in range(4):
        a.record({"action": "query", "i": i})
    p = a._current_path()
    lines = p.read_text().splitlines()
    fake = {
        "action": "query",
        "i": 99,
        "ts_ms": 123,
        "prev_hash": "0" * 64,
        "row_hash": "1" * 64,
    }
    lines.insert(2, json.dumps(fake))
    p.write_text("\n".join(lines) + "\n")

    a2 = AuditAgent(tmp_path)
    ok, _, _ = a2.verify()
    assert not ok


def test_tamper_reorder(tmp_path: Path) -> None:
    a = AuditAgent(tmp_path)
    for i in range(5):
        a.record({"action": "query", "i": i})
    p = a._current_path()
    lines = p.read_text().splitlines()
    lines[1], lines[3] = lines[3], lines[1]
    p.write_text("\n".join(lines) + "\n")

    a2 = AuditAgent(tmp_path)
    ok, _, _ = a2.verify()
    assert not ok
