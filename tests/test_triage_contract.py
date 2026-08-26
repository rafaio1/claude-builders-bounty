"""Regression tests for triage JSON contract and extract_json robustness."""
import sys, os, json, pytest
sys.path.insert(0, "/Agentic/scripts")

# We need to test extract_json and the triage validation logic
from bounty_engine import extract_json

class TestExtractJson:
    def test_pure_json_array(self):
        raw = '[{"url":"https://github.com/a/b/issues/1","title":"Fix bug","estimated_hours":1,"confidence_score":0.9,"reason":"test"}]'
        result = extract_json(raw)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["url"] == "https://github.com/a/b/issues/1"

    def test_markdown_fenced_json(self):
        raw = 'Here is the selection:\n```json\n[{"url":"https://github.com/a/b/issues/2","title":"Typo","estimated_hours":0.5,"confidence_score":0.8,"reason":"simple"}]\n```\nDone.'
        result = extract_json(raw)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["url"] == "https://github.com/a/b/issues/2"

    def test_prose_before_after_json(self):
        raw = 'Based on the candidates, I select:\n[{"url":"https://github.com/x/y/issues/3","title":"CI fail","estimated_hours":2,"confidence_score":0.7,"reason":"clear error"}]\nThese are the best targets.'
        result = extract_json(raw)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_empty_string_returns_none(self):
        assert extract_json("") is None
        assert extract_json(None) is None

    def test_no_json_returns_none(self):
        assert extract_json("This is just plain text with no JSON at all.") is None

    def test_malformed_json_returns_none(self):
        assert extract_json('{"url": "missing bracket"') is None

    def test_dict_with_files_to_change(self):
        raw = '{"files_to_change": [{"path": "src/main.py", "action": "modify", "content": "print(1)"}], "branch_name": "fix/test"}'
        result = extract_json(raw)
        assert isinstance(result, dict)
        assert "files_to_change" in result

    def test_ansi_codes_stripped(self):
        raw = '\x1b[32m[{"url":"https://github.com/a/b/issues/4","title":"Green","estimated_hours":1,"confidence_score":0.5,"reason":"ansi"}]\x1b[0m'
        result = extract_json(raw)
        assert isinstance(result, list)
        assert len(result) == 1


class TestTriageSchemaContract:
    """Validate that triage output conforms to the expected schema."""

    REQUIRED_KEYS = {"url", "title", "estimated_hours", "confidence_score", "reason"}

    def _validate_selection(self, item):
        assert isinstance(item, dict), f"Selection item must be dict, got {type(item)}"
        missing = self.REQUIRED_KEYS - set(item.keys())
        assert not missing, f"Missing required keys: {missing}"
        assert isinstance(item["url"], str) and item["url"].startswith("http"), \
            f"url must be a valid URL string, got: {item['url']!r}"
        assert isinstance(item["title"], str) and len(item["title"]) > 0, \
            "title must be a non-empty string"
        assert isinstance(item["estimated_hours"], (int, float)) and item["estimated_hours"] >= 0, \
            f"estimated_hours must be a non-negative number, got: {item['estimated_hours']!r}"
        assert isinstance(item["confidence_score"], (int, float)) and 0 <= item["confidence_score"] <= 1, \
            f"confidence_score must be between 0 and 1, got: {item['confidence_score']!r}"
        assert isinstance(item["reason"], str) and len(item["reason"]) > 0, \
            "reason must be a non-empty string"

    def test_valid_selection_passes(self):
        item = {
            "url": "https://github.com/org/repo/issues/10",
            "title": "Fix null pointer in parser",
            "estimated_hours": 1.5,
            "confidence_score": 0.85,
            "reason": "Clear stack trace and failing test"
        }
        self._validate_selection(item)

    def test_missing_key_fails(self):
        item = {"url": "https://github.com/org/repo/issues/10", "title": "Fix"}
        with pytest.raises(AssertionError, match="Missing required keys"):
            self._validate_selection(item)

    def test_invalid_url_fails(self):
        item = {
            "url": "not-a-url",
            "title": "Fix",
            "estimated_hours": 1,
            "confidence_score": 0.5,
            "reason": "test"
        }
        with pytest.raises(AssertionError, match="url must be a valid URL"):
            self._validate_selection(item)

    def test_confidence_out_of_range_fails(self):
        item = {
            "url": "https://github.com/org/repo/issues/10",
            "title": "Fix",
            "estimated_hours": 1,
            "confidence_score": 1.5,
            "reason": "test"
        }
        with pytest.raises(AssertionError, match="confidence_score must be between 0 and 1"):
            self._validate_selection(item)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
