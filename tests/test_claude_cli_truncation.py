"""Tests for prompt truncation guard in claude_cli module."""

from __future__ import annotations

import pytest

from agentic.claude_cli import _MAX_PROMPT_CHARS, truncate_prompt


def test_truncate_prompt_returns_short_input_unchanged():
    short = "implement fix for token limit"
    assert truncate_prompt(short) == short


def test_truncate_prompt_truncates_over_limit():
    long_prompt = "x" * (_MAX_PROMPT_CHARS + 5000)
    result = truncate_prompt(long_prompt)
    assert len(result) <= _MAX_PROMPT_CHARS
    assert "[AVISO:" in result
    assert "truncado" in result


def test_truncate_prompt_preserves_prefix():
    prefix = "INSTRUÇÃO IMPORTANTE: " + "a" * 100
    long_prompt = prefix + "b" * (_MAX_PROMPT_CHARS + 1000)
    result = truncate_prompt(long_prompt)
    assert result.startswith(prefix)


def test_truncate_prompt_custom_limit():
    prompt = "abcdefghij"  # 10 chars
    result = truncate_prompt(prompt, limit=5)
    assert len(result) <= 5 + 200  # notice overhead
    assert "[AVISO:" in result


def test_truncate_prompt_non_string_returns_empty():
    assert truncate_prompt(None) == ""  # type: ignore[arg-type]
    assert truncate_prompt(123) == ""  # type: ignore[arg-type]


def test_truncate_prompt_exact_limit_unchanged():
    exact = "z" * _MAX_PROMPT_CHARS
    assert truncate_prompt(exact) == exact


def test_truncate_prompt_notice_contains_counts():
    long_prompt = "y" * (_MAX_PROMPT_CHARS + 2000)
    result = truncate_prompt(long_prompt)
    assert str(_MAX_PROMPT_CHARS) in result