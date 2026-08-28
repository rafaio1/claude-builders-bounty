"""Evidence and safety-contract tests for the Opire bounty qualifier."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import pytest

sys.path.insert(0, "/Agentic/tools")
import opire_bounty_qualifier as qualifier

NOW = datetime(2026, 8, 28, 17, 30, tzinfo=UTC)


def reward(
    *,
    reward_id: str = "01TESTREWARD",
    repo: str = "acme/project",
    issue_number: int = 7,
    cents: int = 25_000,
) -> dict:
    return {
        "id": reward_id,
        "title": "Add bounded retry behavior with regression tests",
        "url": f"https://github.com/{repo}/issues/{issue_number}",
        "platform": "GitHub",
        "featuredBy": None,
        "claimerUsers": [],
        "tryingUsers": [],
        "programmingLanguages": ["Python"],
        "createdAt": 1787935000000,
        "pendingPrice": {"value": cents, "unit": "USD_CENT"},
        "organization": {"name": repo.split("/", 1)[0]},
        "project": {
            "url": f"https://github.com/{repo}",
            "name": repo.split("/", 1)[1],
            "isPublic": True,
            "isBotInstalled": True,
        },
    }


def repo_payload(repo: str = "acme/project", *, new: bool = False) -> dict:
    return {
        "node_id": f"repo:{repo}",
        "full_name": repo,
        "default_branch": "main",
        "archived": False,
        "disabled": False,
        "fork": False,
        "private": False,
        "created_at": "2026-08-20T00:00:00Z" if new else "2020-01-01T00:00:00Z",
        "pushed_at": "2026-08-27T12:00:00Z",
        "license": {"spdx_id": "MIT"},
    }


def issue_payload(repo: str = "acme/project", issue_number: int = 7) -> dict:
    return {
        "node_id": f"issue:{repo}:{issue_number}",
        "number": issue_number,
        "repository_url": f"{qualifier.GITHUB_API_ROOT}/repos/{repo}",
        "title": "Add bounded retry behavior with regression tests",
        "body": (
            "## Acceptance criteria\n"
            "The client in src/client.py must retry only transient failures and stop "
            "after four attempts. Permanent errors should be returned immediately.\n"
            "- [ ] Add unit tests for transient and permanent failures.\n"
            "- [ ] Run pytest and document the expected behavior."
        ),
        "state": "open",
        "state_reason": None,
        "locked": False,
        "assignees": [],
        "comments": 0,
        "author_association": "OWNER",
        "user": {"login": "maintainer"},
    }


def fake_fetcher(
    rows: list[dict],
    *,
    command_comment: bool = False,
    linked_pr: bool = False,
    new_repo: bool = False,
):
    candidates, _ = qualifier.parse_opire_rewards(rows)
    by_repo = {row["repo"]: row for row in candidates}
    calls: list[str] = []

    def fetch(url: str):
        calls.append(url)
        parsed = urlparse(url)
        if parsed.path == "/rate_limit":
            return {
                "resources": {
                    "core": {"limit": 5000, "remaining": 4999, "reset": 2000000000}
                }
            }
        parts = parsed.path.strip("/").split("/")
        assert parts[0] == "repos"
        repo = f"{parts[1]}/{parts[2]}"
        row = by_repo[repo]
        if len(parts) == 3:
            return repo_payload(repo, new=new_repo)
        if parts[3] == "issues" and len(parts) == 5:
            value = issue_payload(repo, row["issue_number"])
            if command_comment:
                value["comments"] = 1
            return value
        if parts[3] == "issues" and parts[5] == "comments":
            return [{"body": "/try #7\nI will implement this."}] if command_comment else []
        if parts[3] == "issues" and parts[5] == "timeline":
            return (
                [
                    {
                        "event": "cross-referenced",
                        "source": {"issue": {"pull_request": {"url": "https://api.github/x"}}},
                    }
                ]
                if linked_pr
                else []
            )
        if parts[3:5] == ["git", "trees"]:
            return {
                "truncated": False,
                "tree": [
                    {"path": ".github/workflows/ci.yml"},
                    {"path": "LICENSE"},
                    {"path": "src/client.py"},
                    {"path": "tests/test_client.py"},
                ],
            }
        if parts[3] == "pulls":
            return [{"merged_at": "2026-08-27T12:00:00Z"}]
        raise AssertionError(url)

    return fetch, calls


def test_parse_opire_requires_official_usd_issue_and_zero_competition():
    valid = reward()
    claimed = reward(reward_id="claimed", issue_number=8)
    claimed["tryingUsers"] = [{"login": "someone"}]
    wrong_unit = reward(reward_id="wrong-unit", issue_number=9)
    wrong_unit["pendingPrice"]["unit"] = "POINTS"
    candidates, rejected = qualifier.parse_opire_rewards([valid, claimed, wrong_unit])
    assert len(candidates) == 1
    assert candidates[0]["face_value_usd"] == 250.0
    assert len(rejected) == 2
    assert any("opire_trying_users_not_zero" in row["reasons"] for row in rejected)
    assert any("invalid_usd_price" in row["reasons"] for row in rejected)


def test_candidate_can_qualify_but_never_become_actionable_or_revenue():
    rows = [reward()]
    candidate, _ = qualifier.parse_opire_rewards(rows)
    fetch, calls = fake_fetcher(rows)
    result = qualifier.audit_candidate(candidate[0], fetch, now=NOW)
    assert result["decision"] == "qualified"
    assert result["gates"]["application_allowed"] is False
    assert result["gates"]["implementation_allowed"] is False
    assert result["gates"]["revenue_recognition_allowed"] is False
    assert result["financial_truth"] == {
        "face_value_usd": 250.0,
        "expected_revenue_usd": None,
        "receivable_usd": 0.0,
        "realized_revenue_usd": 0.0,
    }
    assert len(calls) == 6


def test_attempt_comment_and_linked_pr_reject_even_when_source_says_nobody():
    rows = [reward()]
    candidate, _ = qualifier.parse_opire_rewards(rows)
    fetch, _ = fake_fetcher(rows, command_comment=True, linked_pr=True)
    result = qualifier.audit_candidate(candidate[0], fetch, now=NOW)
    assert result["decision"] == "rejected"
    assert "opire_attempt_or_claim_comment_present" in result["rejection_reasons"]
    assert "linked_pull_request_activity_present" in result["rejection_reasons"]


def test_new_repository_and_implausible_reward_are_fail_closed():
    rows = [reward(cents=126_253_000)]
    candidate, _ = qualifier.parse_opire_rewards(rows)
    fetch, _ = fake_fetcher(rows, new_repo=True)
    result = qualifier.audit_candidate(candidate[0], fetch, now=NOW)
    assert result["decision"] == "rejected"
    assert "repository_too_new_for_payout_confidence" in result["rejection_reasons"]
    assert "bounty_value_requires_manual_fraud_review" in result["rejection_reasons"]


def test_market_audits_one_new_candidate_and_reuses_cache():
    rows = [reward(), reward(reward_id="second", repo="acme/second", issue_number=8)]
    fetch, calls = fake_fetcher(rows)
    output1, cache1 = qualifier.qualify_market(
        rows,
        {"entries": {}},
        fetch,
        now=NOW,
        run_id="run-1",
        github_authenticated=True,
    )
    assert len(output1["newly_audited_candidate_keys"]) == 1
    assert output1["qualification_count"] == 1
    assert output1["audit_policy"]["github_authenticated"] is True
    first_call_count = len(calls)
    output2, _cache2 = qualifier.qualify_market(
        rows,
        cache1,
        fetch,
        now=NOW,
        run_id="run-2",
        github_authenticated=True,
    )
    assert len(output2["newly_audited_candidate_keys"]) == 1
    assert output2["qualification_count"] == 2
    assert len(calls) == first_call_count + 7


def test_low_rate_budget_fails_before_candidate_calls():
    rows = [reward()]

    def fetch(url: str):
        assert urlparse(url).path == "/rate_limit"
        return {
            "resources": {
                "core": {"limit": 60, "remaining": 10, "reset": 2000000000}
            }
        }

    with pytest.raises(qualifier.QualifierError) as error:
        qualifier.qualify_market(rows, {"entries": {}}, fetch, now=NOW)
    assert error.value.code == "github_rate_budget_low"


def test_deleted_issue_is_cached_as_rejection_instead_of_stalling_queue():
    rows = [reward()]

    def fetch(url: str):
        if urlparse(url).path == "/rate_limit":
            return {
                "resources": {
                    "core": {"limit": 5000, "remaining": 4999, "reset": 2000000000}
                }
            }
        raise qualifier.QualifierError("api_http_410", "resource deleted")

    output, cache = qualifier.qualify_market(
        rows,
        {"entries": {}},
        fetch,
        now=NOW,
        run_id="deleted-run",
    )
    assert output["qualification_count"] == 1
    assert output["qualified_count"] == 0
    receipt = output["qualifications"][0]
    assert receipt["decision"] == "rejected"
    assert receipt["audit_error_code"] == "api_http_410"
    assert receipt["financial_truth"]["realized_revenue_usd"] == 0.0
    assert len(cache["entries"]) == 1


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


def test_atomic_output_is_private(tmp_path: Path):
    path = tmp_path / "result.json"
    qualifier.atomic_json_write(path, {"secret": False})
    assert json.loads(path.read_text()) == {"secret": False}
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600
