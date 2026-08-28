"""Safety and evidence-contract tests for the Drips GitHub qualifier."""

from __future__ import annotations

import base64
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.error import URLError
from urllib.parse import urlparse

import pytest

sys.path.insert(0, "/Agentic/tools")
import drips_github_qualifier as qualifier

NOW = datetime(2026, 8, 28, 16, 20, tzinfo=UTC)


def candidate(*, repo: str = "acme/project", issue_number: int = 7) -> dict:
    return {
        "id": f"drips:{repo}:{issue_number}",
        "drips_issue_id": f"00000000-0000-4000-8000-{issue_number:012d}",
        "repo": repo,
        "issue_number": issue_number,
        "title": "Add bounded retry behavior with tests",
        "points": 200,
        "complexity": "large",
        "pending_applications_count": 0,
        "github_updated_at": "2026-08-28T16:00:00Z",
        "wave_id": "22222222-2222-4222-8222-222222222222",
    }


def drips_snapshot(rows: list[dict] | None = None) -> tuple[dict, dict]:
    payload = {
        "schema_version": "1.0",
        "run_id": "drips-run",
        "source_hash": "drips-source",
        "generated_at": NOW.isoformat(),
        "valid_until": (NOW + timedelta(minutes=10)).isoformat(),
        "active_wave": {
            "id": "22222222-2222-4222-8222-222222222222",
            "end_at": "2026-08-31T12:00:00Z",
        },
        "scan": {"drips_detail_evidence_complete": True},
        "financial_truth": {"realized_revenue_usd": 0.0},
        "candidates": list(rows if rows is not None else [candidate()]),
    }
    manifest = {
        "status": "complete",
        "run_id": payload["run_id"],
        "source_hash": payload["source_hash"],
    }
    return payload, manifest


def repo_payload(repo: str = "acme/project", *, license_spdx: str | None = "MIT") -> dict:
    return {
        "node_id": f"repo:{repo}",
        "full_name": repo,
        "default_branch": "main",
        "archived": False,
        "disabled": False,
        "fork": False,
        "private": False,
        "pushed_at": "2026-08-28T15:00:00Z",
        "license": {"spdx_id": license_spdx} if license_spdx else None,
    }


def issue_payload(repo: str = "acme/project", issue_number: int = 7) -> dict:
    return {
        "node_id": f"issue:{repo}:{issue_number}",
        "number": issue_number,
        "repository_url": f"{qualifier.GITHUB_API_ROOT}/repos/{repo}",
        "title": "Add bounded retry behavior with tests",
        "body": (
            "## Acceptance Criteria\n"
            "The client in `src/client.py` must retry only transient failures. "
            "It should stop after four attempts and preserve permanent failures.\n"
            "- [ ] Add unit tests under `tests/test_client.py`.\n"
            "- [ ] Run `pytest tests/test_client.py` and document expected behavior."
        ),
        "state": "open",
        "state_reason": None,
        "locked": False,
        "assignees": [],
        "comments": 0,
        "labels": [{"name": "200-points"}],
        "user": {"login": "maintainer"},
        "updated_at": "2026-08-28T16:00:00Z",
    }


def tree_payload(*, missing_path: bool = False, include_package_json: bool = False) -> dict:
    paths = [
        ".github/workflows/ci.yml",
        "LICENSE",
        "tests",
        "tests/test_client.py",
    ]
    if not missing_path:
        paths.append("src")
        paths.append("src/client.py")
    if include_package_json:
        paths.append("package.json")
    return {"truncated": False, "tree": [{"path": path} for path in paths]}


def pulls_payload(*, merged: bool = True) -> list[dict]:
    return [{"merged_at": "2026-08-27T12:00:00Z" if merged else None}]


def fake_fetcher(
    rows: list[dict],
    *,
    rate_remaining: int = 60,
    missing_path: bool = False,
    merged: bool = True,
    application_comment: bool = False,
    package_license: str | None = None,
):
    calls: list[str] = []
    by_repo = {row["repo"]: row for row in rows}

    def fetch(url: str):
        calls.append(url)
        parsed = urlparse(url)
        if parsed.path == "/rate_limit":
            return {
                "resources": {
                    "core": {"limit": 60, "remaining": rate_remaining, "reset": 2000000000}
                }
            }
        parts = parsed.path.strip("/").split("/")
        assert parts[0] == "repos"
        repo = f"{parts[1]}/{parts[2]}"
        row = by_repo[repo]
        if len(parts) == 3:
            return repo_payload(repo, license_spdx=None if package_license else "MIT")
        if parts[3] == "issues" and len(parts) == 5:
            value = issue_payload(repo, row["issue_number"])
            if application_comment:
                value["comments"] = 1
            return value
        if parts[3] == "issues" and parts[5] == "comments":
            return (
                [{"body": "<!-- wave:application-id=abc -->"}]
                if application_comment
                else []
            )
        if parts[3] == "issues" and parts[5] == "timeline":
            return []
        if parts[3:5] == ["git", "trees"]:
            return tree_payload(
                missing_path=missing_path,
                include_package_json=package_license is not None,
            )
        if parts[3] == "contents" and parts[4] == "package.json":
            encoded = base64.b64encode(
                json.dumps({"name": "project", "license": package_license}).encode()
            ).decode()
            return {
                "type": "file",
                "path": "package.json",
                "encoding": "base64",
                "size": len(base64.b64decode(encoded)),
                "content": encoded,
            }
        if parts[3] == "pulls":
            return pulls_payload(merged=merged)
        raise AssertionError(url)

    return fetch, calls


def test_drips_snapshot_requires_matching_fresh_complete_evidence():
    payload, manifest = drips_snapshot()
    qualifier.validate_drips_snapshot(payload, manifest, now=NOW)
    payload["valid_until"] = NOW.isoformat()
    with pytest.raises(qualifier.QualifierError) as error:
        qualifier.validate_drips_snapshot(payload, manifest, now=NOW)
    assert error.value.code == "drips_snapshot_stale"


def test_candidate_can_qualify_but_never_become_actionable_or_revenue():
    row = candidate()
    fetch, calls = fake_fetcher([row])
    result = qualifier.audit_candidate(
        row,
        fetch,
        now=NOW,
        drips_source_hash="drips-source",
        wave_end_at="2026-08-31T12:00:00Z",
    )
    assert result["decision"] == "qualified"
    assert result["score"] >= qualifier.MIN_SCORE
    assert result["gates"]["application_allowed"] is False
    assert result["gates"]["implementation_allowed"] is False
    assert result["gates"]["automation_eligible"] is False
    assert result["financial_truth"]["points_value_usd"] is None
    assert result["financial_truth"]["realized_revenue_usd"] == 0.0
    assert len(calls) == 6


def test_root_package_spdx_license_is_accepted_when_github_license_is_null():
    row = candidate()
    fetch, calls = fake_fetcher([row], package_license="ISC")
    result = qualifier.audit_candidate(
        row,
        fetch,
        now=NOW,
        drips_source_hash="drips-source",
        wave_end_at="2026-08-31T12:00:00Z",
    )
    assert result["decision"] == "qualified"
    assert result["gates"]["license_present"] is True
    assert result["evidence"]["license_spdx"] == "ISC"
    assert result["evidence"]["license_source"] == "root_package_json"
    assert result["quality"]["license_warning"] == "missing_license_file"
    assert result["evidence"]["package_manifest_api_url"].endswith(
        "/contents/package.json?ref=main"
    )
    assert len(calls) == 7


def test_missing_referenced_path_and_no_merged_history_reject():
    row = candidate()
    fetch, _calls = fake_fetcher([row], missing_path=True, merged=False)
    result = qualifier.audit_candidate(
        row,
        fetch,
        now=NOW,
        drips_source_hash="drips-source",
        wave_end_at="2026-08-31T12:00:00Z",
    )
    assert result["decision"] == "rejected"
    assert "referenced_repository_paths_missing" in result["rejection_reasons"]
    assert "recent_merged_pr_history_missing" in result["rejection_reasons"]


def test_trivial_scope_is_rejected_even_with_high_points():
    row = candidate()
    fetch, _calls = fake_fetcher([row])

    def trivial(url: str):
        value = fetch(url)
        if urlparse(url).path.endswith(f"/issues/{row['issue_number']}"):
            value = dict(value)
            value["title"] = "Remove commented-out and dead code repo-wide"
        return value

    result = qualifier.audit_candidate(
        row,
        trivial,
        now=NOW,
        drips_source_hash="drips-source",
        wave_end_at="2026-08-31T12:00:00Z",
    )
    assert result["decision"] == "rejected"
    assert "scope_appears_trivial_or_inflated" in result["rejection_reasons"]


def test_application_comment_and_points_label_mismatch_reject():
    row = candidate()
    fetch, _calls = fake_fetcher([row], application_comment=True)

    def mismatch(url: str):
        value = fetch(url)
        if urlparse(url).path.endswith(f"/issues/{row['issue_number']}"):
            value = dict(value)
            value["labels"] = [{"name": "100-points"}]
        return value

    result = qualifier.audit_candidate(
        row,
        mismatch,
        now=NOW,
        drips_source_hash="drips-source",
        wave_end_at="2026-08-31T12:00:00Z",
    )
    assert result["decision"] == "rejected"
    assert "github_application_comment_present" in result["rejection_reasons"]
    assert "drips_github_points_mismatch" in result["rejection_reasons"]


def test_market_audits_only_one_new_candidate_and_reuses_fresh_cache():
    first = candidate()
    second = candidate(repo="acme/second", issue_number=8)
    payload, manifest = drips_snapshot([first, second])
    fetch, calls = fake_fetcher([first, second])
    output1, cache1 = qualifier.qualify_market(
        payload,
        manifest,
        {"entries": {}},
        fetch,
        now=NOW,
        run_id="run-1",
    )
    assert output1["qualification_count"] == 1
    assert output1["qualified_count"] == 1
    assert len(calls) == 7  # one rate check plus six candidate reads

    output2, cache2 = qualifier.qualify_market(
        payload,
        manifest,
        cache1,
        fetch,
        now=NOW + timedelta(minutes=1),
        run_id="run-2",
    )
    assert output2["qualification_count"] == 2
    assert output2["qualified_count"] == 2
    assert len(calls) == 14
    assert len(cache2["entries"]) == 2


def test_low_public_rate_budget_fails_before_candidate_reads():
    payload, manifest = drips_snapshot()
    fetch, calls = fake_fetcher(payload["candidates"], rate_remaining=3)
    with pytest.raises(qualifier.QualifierError) as error:
        qualifier.qualify_market(
            payload,
            manifest,
            {"entries": {}},
            fetch,
            now=NOW,
        )
    assert error.value.code == "github_rate_budget_low"
    assert len(calls) == 1


def test_token_is_read_from_existing_gh_config_without_subprocess(tmp_path, monkeypatch):
    config = tmp_path / "gh"
    config.mkdir()
    (config / "hosts.yml").write_text(
        "github.com:\n  oauth_token: gho_abcdefghijklmnopqrstuvwxyz123456\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GH_CONFIG_DIR", str(config))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN_FILE", raising=False)
    monkeypatch.setattr(
        qualifier.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("gh subprocess should not be called"),
    )
    assert qualifier.resolve_github_token() == "gho_abcdefghijklmnopqrstuvwxyz123456"


class FakeResponse:
    status = 200

    def __init__(self, payload: dict, *, final_url: str):
        self.raw = json.dumps(payload).encode()
        self.final_url = final_url
        self.headers = {"Content-Type": "application/json; charset=utf-8"}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return self.final_url

    def getcode(self):
        return self.status

    def read(self, _limit: int):
        return self.raw


def test_http_retry_is_bounded_and_redirect_is_rejected(monkeypatch):
    url = f"{qualifier.GITHUB_API_ROOT}/rate_limit"
    calls = []

    def flaky(_request, timeout):
        calls.append(timeout)
        if len(calls) < qualifier.MAX_HTTP_ATTEMPTS:
            raise URLError("temporary")
        return FakeResponse({"ok": True}, final_url=url)

    monkeypatch.setattr(qualifier, "urlopen", flaky)
    monkeypatch.setattr(qualifier.time, "sleep", lambda _seconds: None)
    assert qualifier.http_get_json(url) == {"ok": True}
    assert len(calls) == qualifier.MAX_HTTP_ATTEMPTS

    monkeypatch.setattr(
        qualifier,
        "urlopen",
        lambda _request, timeout: FakeResponse(
            {"ok": True}, final_url="https://evil.example/rate_limit"
        ),
    )
    with pytest.raises(qualifier.QualifierError) as error:
        qualifier.http_get_json(url)
    assert error.value.code == "untrusted_github_redirect"


def test_atomic_write_is_private(tmp_path: Path):
    path = tmp_path / "qualification.json"
    qualifier.atomic_json_write(path, {"status": "complete"})
    assert json.loads(path.read_text()) == {"status": "complete"}
    assert os.stat(path).st_mode & 0o777 == 0o600


def test_main_writes_matching_manifest(monkeypatch, tmp_path: Path):
    drips_path = tmp_path / "drips.json"
    drips_manifest_path = tmp_path / "drips-success.json"
    output_path = tmp_path / "output.json"
    manifest_path = tmp_path / "success.json"
    cache_path = tmp_path / "cache.json"
    payload, manifest = drips_snapshot()
    drips_path.write_text(json.dumps(payload))
    drips_manifest_path.write_text(json.dumps(manifest))
    fetch, _calls = fake_fetcher(payload["candidates"])
    monkeypatch.setattr(qualifier, "http_get_json", fetch)
    monkeypatch.setattr(
        qualifier,
        "parse_args",
        lambda: SimpleNamespace(
            drips=str(drips_path),
            drips_manifest=str(drips_manifest_path),
            output=str(output_path),
            manifest=str(manifest_path),
            cache=str(cache_path),
        ),
    )
    monkeypatch.setattr(qualifier, "iso_now", lambda: NOW.isoformat())
    monkeypatch.setattr(qualifier, "utc_now", lambda: NOW)
    assert qualifier.main() == 0
    saved = json.loads(output_path.read_text())
    success = json.loads(manifest_path.read_text())
    assert success["status"] == "complete"
    assert success["run_id"] == saved["run_id"]
    assert success["source_hash"] == saved["source_hash"]
    assert success["application_allowed"] is False
    assert success["realized_revenue_usd"] == 0.0


def test_source_contains_no_external_write_methods():
    source = Path(qualifier.__file__).read_text(encoding="utf-8").casefold()
    assert 'method="post"' not in source
    assert 'method="patch"' not in source
    assert 'method="delete"' not in source
