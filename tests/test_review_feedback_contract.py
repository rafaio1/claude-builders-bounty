"""Contrato estruturado de review_feedback: parse, serialização e restrição de escopo."""

from __future__ import annotations

import pytest

from agentic.improve import (
    parse_review_feedback,
    structured_review_feedback,
)


def test_parse_structured_dict() -> None:
    raw = {
        "verdict": "reject",
        "reason": "escopo alargado para loop.py",
        "files": ["src/agentic/improve.py", "tests/test_improve.py"],
    }
    parsed = parse_review_feedback(raw)
    assert parsed["verdict"] == "reject"
    assert parsed["reason"] == "escopo alargado para loop.py"
    assert parsed["files"] == ["src/agentic/improve.py", "tests/test_improve.py"]


def test_parse_freeform_text_extracts_files() -> None:
    text = (
        "reject — o develop alterou src/agentic/loop.py fora do parecer; "
        "corrija apenas src/agentic/improve.py e tests/test_improve.py"
    )
    parsed = parse_review_feedback(text)
    assert parsed["verdict"] == "reject"
    assert "loop.py" in parsed["reason"] or "fora do parecer" in parsed["reason"]
    assert "src/agentic/improve.py" in parsed["files"]
    assert "tests/test_improve.py" in parsed["files"]


def test_parse_empty_returns_reject() -> None:
    parsed = parse_review_feedback("")
    assert parsed == {"verdict": "reject", "reason": "", "files": []}


def test_parse_none_returns_reject() -> None:
    parsed = parse_review_feedback(None)
    assert parsed == {"verdict": "reject", "reason": "", "files": []}


def test_structured_serialization_includes_files() -> None:
    raw = {
        "verdict": "reject",
        "reason": "motivo X",
        "files": ["src/agentic/improve.py"],
    }
    serialized = structured_review_feedback(raw)
    assert serialized.startswith("reject:")
    assert "motivo X" in serialized
    assert "arquivos=src/agentic/improve.py" in serialized


def test_structured_serialization_without_files() -> None:
    raw = {"verdict": "approve", "reason": "ok"}
    serialized = structured_review_feedback(raw)
    assert serialized == "approve: ok"


def test_parse_normalizes_paths() -> None:
    raw = {
        "verdict": "reject",
        "reason": "paths sujos",
        "files": [".\\src\\agentic\\improve.py", "./tests/test_improve.py"],
    }
    parsed = parse_review_feedback(raw)
    assert parsed["files"] == ["src/agentic/improve.py", "tests/test_improve.py"]


def test_parse_approve_prefix() -> None:
    parsed = parse_review_feedback("approve — tudo certo")
    assert parsed["verdict"] == "approve"


def test_parse_reject_prefix() -> None:
    parsed = parse_review_feedback("reject: motivo Y")
    assert parsed["verdict"] == "reject"
    assert parsed["reason"] == "motivo Y"