"""Deterministic evidence and safety-contract tests for the Algora qualifier."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

import pytest

sys.path.insert(0, "/Agentic/tools")
import algora_bounty_qualifier as qualifier

NOW = datetime(2026, 8, 28, 18, 30, tzinfo=UTC)


def search_payload(*, repo: str = "acme/project", issue_number: int = 17) -> dict:
    return {
        "total_count": 1,
        "incomplete_results": False,
        "items": [
            {
                "repository_url": f"{qualifier.GITHUB_API_ROOT}/repos/{repo}",
                "url": f"{qualifier.GITHUB_API_ROOT}/repos/{repo}/issues/{issue_number}",
                "html_url": f"https://github.com/{repo}/issues/{issue_number}",
                "number": issue_number,
                "title": "Add bounded retry behavior with regression tests",
                "state": "open",
                "comments": 1,
                "updated_at": "2026-08-28T17:00:00+00:00",
            }
        ],
    }


def repo_payload(repo: str = "acme/project") -> dict:
    return {
        "node_id": f"repo:{repo}",
        "full_name": repo,
        "default_branch": "main",
        "archived": False,
        "disabled": False,
        "fork": False,
        "private": False,
        "created_at": "2020-01-01T00:00:00+00:00",
        "pushed_at": "2026-08-27T12:00:00+00:00",
        "license": {"spdx_id": "MIT"},
    }


def issue_payload(
    *, repo: str = "acme/project", issue_number: int = 17, comments: int = 1
) -> dict:
    return {
        "node_id": f"issue:{repo}:{issue_number}",
        "number": issue_number,
        "repository_url": f"{qualifier.GITHUB_API_ROOT}/repos/{repo}",
        "title": "Add bounded retry behavior with regression tests",
        "body": (
            "## Acceptance criteria\n"
            "The client must retry only transient failures, stop after four attempts, "
            "and return permanent failures immediately. The implementation should "
            "preserve the existing public API and must include deterministic behavior.\n"
            "- [ ] Add unit tests for transient and permanent failures.\n"
            "- [ ] Run the complete test suite and document the expected behavior."
        ),
        "state": "open",
        "state_reason": None,
        "locked": False,
        "assignees": [],
        "comments": comments,
        "author_association": "OWNER",
        "user": {"login": "maintainer"},
        "labels": [],
    }


def official_bounty_comment(
    amount: str = "250",
    *,
    sponsor: str = "acme",
    comment_id: int = 1,
    extra: str = "",
) -> dict:
    return {
        "id": comment_id,
        "html_url": (
            f"https://github.com/acme/project/issues/17#issuecomment-{comment_id}"
        ),
        "created_at": "2026-08-28T16:00:00+00:00",
        "updated_at": "2026-08-28T16:00:00+00:00",
        "user": {
            "id": qualifier.BOT_ID,
            "login": qualifier.BOT_LOGIN,
            "type": "Bot",
        },
        "body": (
            f"## 💎 ${amount} bounty by "
            f"[{sponsor}](https://algora.io/{sponsor})\n\n"
            f"{extra}"
        ),
    }


def board_document(*amounts: str) -> str:
    rendered_amounts = "".join(f"<div>${amount}</div>" for amount in amounts)
    return (
        '<section id="bounties-container" phx-value-tab="open">'
        "<table><tr><td>"
        '<a href="https://github.com/acme/project/issues/17">issue</a>'
        f"{rendered_amounts}"
        "</td></tr></table></section>"
    )


def fake_fetcher(
    *,
    comments: list[dict] | None = None,
    timeline: list[dict] | None = None,
    boards: dict[str, str] | None = None,
):
    issue_comments = comments if comments is not None else [official_bounty_comment()]
    issue_timeline = timeline if timeline is not None else []
    board_documents = boards if boards is not None else {"acme": board_document("250")}
    calls: list[tuple[str, dict | None]] = []
    board_calls: list[str] = []

    def fetch(endpoint: str, params=None):
        normalized_params = dict(params) if params is not None else None
        calls.append((endpoint, normalized_params))
        if endpoint == "rate_limit":
            return {
                "resources": {
                    "core": {"limit": 5000, "remaining": 4999, "reset": 2000000000},
                    "search": {"limit": 30, "remaining": 29, "reset": 2000000000},
                }
            }
        if endpoint == "repos/acme/project":
            return repo_payload()
        if endpoint == "repos/acme/project/issues/17":
            return issue_payload(comments=len(issue_comments))
        if endpoint == "repos/acme/project/issues/17/comments":
            assert normalized_params == {"per_page": 100}
            return issue_comments
        if endpoint == "repos/acme/project/issues/17/timeline":
            assert normalized_params == {"per_page": 100}
            return issue_timeline
        if endpoint == "repos/acme/project/git/trees/main":
            assert normalized_params == {"recursive": 1}
            return {
                "truncated": False,
                "tree": [
                    {"path": ".github/workflows/ci.yml"},
                    {"path": "LICENSE"},
                    {"path": "src/client.py"},
                    {"path": "tests/test_client.py"},
                ],
            }
        if endpoint == "repos/acme/project/pulls":
            assert normalized_params == {
                "state": "closed",
                "sort": "updated",
                "direction": "desc",
                "per_page": 20,
            }
            return [{"merged_at": "2026-08-27T12:00:00+00:00"}]
        raise AssertionError(f"unexpected endpoint: {endpoint}")

    def fetch_text(url: str) -> str:
        board_calls.append(url)
        sponsor = url.split("/")[-2]
        assert url == f"https://algora.io/{sponsor}/bounties"
        return board_documents[sponsor]

    return fetch, calls, fetch_text, board_calls


def candidate_from_search(payload: dict | None = None) -> dict:
    candidates, rejected = qualifier.parse_search(payload or search_payload())
    assert rejected == []
    assert len(candidates) == 1
    return candidates[0]


def test_candidate_can_qualify_but_never_become_actionable_or_revenue():
    fetch, calls, fetch_text, board_calls = fake_fetcher()
    result = qualifier.audit_candidate(
        candidate_from_search(), fetch, now=NOW, fetch_text=fetch_text
    )

    assert result["decision"] == "qualified"
    assert result["rejection_reasons"] == []
    assert result["gates"]["application_allowed"] is False
    assert result["gates"]["implementation_allowed"] is False
    assert result["gates"]["revenue_recognition_allowed"] is False
    assert result["gates"]["official_algora_bot_identity"] is True
    assert result["gates"]["canonical_algora_open_board"] is True
    assert result["financial_truth"] == {
        "face_value_usd": 250.0,
        "expected_revenue_usd": None,
        "receivable_usd": 0.0,
        "realized_revenue_usd": 0.0,
    }
    assert [endpoint for endpoint, _params in calls] == [
        "repos/acme/project",
        "repos/acme/project/issues/17",
        "repos/acme/project/issues/17/comments",
        "repos/acme/project/issues/17/timeline",
        "repos/acme/project/git/trees/main",
        "repos/acme/project/pulls",
    ]
    assert board_calls == ["https://algora.io/acme/bounties"]


def test_multiple_official_sponsors_are_summed_and_each_board_is_verified():
    comments = [
        official_bounty_comment("200", sponsor="acme", comment_id=1),
        official_bounty_comment("50", sponsor="second", comment_id=2),
    ]
    fetch, _calls, fetch_text, board_calls = fake_fetcher(
        comments=comments,
        boards={"acme": board_document("200"), "second": board_document("50")},
    )
    result = qualifier.audit_candidate(
        candidate_from_search(), fetch, now=NOW, fetch_text=fetch_text
    )

    assert result["decision"] == "qualified"
    assert result["financial_truth"]["face_value_usd"] == 250.0
    assert result["quality"]["active_bounty_component_count"] == 2
    assert len(result["evidence"]["canonical_board_results"]) == 2
    assert board_calls == [
        "https://algora.io/acme/bounties",
        "https://algora.io/second/bounties",
    ]


def test_attempt_rows_commands_linked_pr_and_ambiguous_board_amount_fail_closed():
    comments = [
        official_bounty_comment(
            extra=(
                "| 🟢 | active contributor |\n"
                "| 🔴 | inactive contributor |\n"
            )
        ),
        {
            "html_url": "https://github.com/acme/project/issues/17#issuecomment-3",
            "user": {"login": "contributor"},
            "created_at": "2026-08-28T17:30:00+00:00",
            "body": "/attempt #17\nI am working on this bounty.",
        },
    ]
    timeline = [
        {
            "event": "cross-referenced",
            "source": {
                "issue": {
                    "pull_request": {
                        "url": "https://api.github.com/repos/acme/project/pulls/22"
                    }
                }
            },
        }
    ]
    fetch, _calls, fetch_text, _board_calls = fake_fetcher(
        comments=comments,
        timeline=timeline,
        boards={"acme": board_document("250", "300")},
    )
    result = qualifier.audit_candidate(
        candidate_from_search(), fetch, now=NOW, fetch_text=fetch_text
    )

    assert result["decision"] == "rejected"
    assert (
        "canonical_algora_open_board_unavailable"
        in result["rejection_reasons"]
    )
    assert "algora_attempt_or_claim_activity_present" in result["rejection_reasons"]
    assert "linked_pull_request_activity_present" in result["rejection_reasons"]
    assert result["quality"]["pending_attempt_command_count"] == 1
    assert result["quality"]["active_attempt_table_row_count"] == 1
    assert result["quality"]["inactive_attempt_table_row_count"] == 1
    assert result["quality"]["linked_pull_request_event_count"] == 1
    assert result["financial_truth"]["face_value_usd"] == 250.0
    assert result["financial_truth"]["realized_revenue_usd"] == 0.0
    assert result["evidence"]["canonical_board_results"][0]["error_code"] == (
        "invalid_algora_board_row"
    )


def test_false_bot_identity_and_official_award_are_fail_closed():
    false_bot = official_bounty_comment()
    false_bot["user"] = {
        "id": qualifier.BOT_ID + 1,
        "login": qualifier.BOT_LOGIN,
        "type": "Bot",
    }
    fetch, _calls, fetch_text, board_calls = fake_fetcher(comments=[false_bot])
    identity_result = qualifier.audit_candidate(
        candidate_from_search(), fetch, now=NOW, fetch_text=fetch_text
    )
    assert identity_result["decision"] == "rejected"
    assert "official_algora_bot_identity_conflict" in identity_result["rejection_reasons"]
    assert "official_algora_active_bounty_not_proven" in identity_result["rejection_reasons"]
    assert board_calls == []

    award = {
        "id": 2,
        "html_url": "https://github.com/acme/project/issues/17#issuecomment-2",
        "created_at": "2026-08-28T17:00:00+00:00",
        "updated_at": "2026-08-28T17:00:00+00:00",
        "user": {
            "id": qualifier.BOT_ID,
            "login": qualifier.BOT_LOGIN,
            "type": "Bot",
        },
        "body": "@winner has been awarded **$250**",
    }
    fetch, _calls, fetch_text, _board_calls = fake_fetcher(
        comments=[official_bounty_comment(), award]
    )
    award_result = qualifier.audit_candidate(
        candidate_from_search(), fetch, now=NOW, fetch_text=fetch_text
    )
    assert award_result["decision"] == "rejected"
    assert "official_algora_bounty_already_awarded" in award_result["rejection_reasons"]
    assert award_result["quality"]["official_award_count"] == 1
    assert award_result["financial_truth"]["realized_revenue_usd"] == 0.0


def test_reward_action_link_is_a_pending_claim_and_never_an_award_or_revenue():
    comment = official_bounty_comment(
        extra=(
            "A claim is waiting for review: "
            "[Reward](https://console.algora.io/claims/claim_12345678)"
        )
    )
    fetch, _calls, fetch_text, _board_calls = fake_fetcher(comments=[comment])
    result = qualifier.audit_candidate(
        candidate_from_search(), fetch, now=NOW, fetch_text=fetch_text
    )

    assert result["decision"] == "rejected"
    assert "algora_attempt_or_claim_activity_present" in result["rejection_reasons"]
    assert result["gates"]["no_attempt_or_claim_activity"] is False
    assert result["quality"]["reward_action_link_count"] == 1
    assert result["quality"]["official_award_count"] == 0
    assert result["financial_truth"]["receivable_usd"] == 0.0
    assert result["financial_truth"]["realized_revenue_usd"] == 0.0


def test_malformed_attempt_table_row_blocks_candidate_fail_closed():
    comment = official_bounty_comment(
        extra="| 🟡 @contributor | unknown attempt state |\n"
    )
    fetch, _calls, fetch_text, _board_calls = fake_fetcher(comments=[comment])
    result = qualifier.audit_candidate(
        candidate_from_search(), fetch, now=NOW, fetch_text=fetch_text
    )

    assert result["decision"] == "rejected"
    assert "algora_attempt_or_claim_activity_present" in result["rejection_reasons"]
    assert result["quality"]["active_attempt_table_row_count"] == 0
    assert result["quality"]["inactive_attempt_table_row_count"] == 0
    assert result["quality"]["malformed_attempt_table_row_count"] == 1
    assert result["gates"]["no_attempt_or_claim_activity"] is False


def test_github_404_becomes_terminal_cached_rejection_and_is_reused():
    payload = search_payload()
    calls: list[str] = []

    def fetch(endpoint: str, params=None):
        del params
        calls.append(endpoint)
        if endpoint == "rate_limit":
            return {
                "resources": {
                    "core": {"limit": 5000, "remaining": 4999, "reset": 2000000000},
                    "search": {"limit": 30, "remaining": 29, "reset": 2000000000},
                }
            }
        raise qualifier.QualifierError("github_http_404", "resource missing")

    first, cache = qualifier.qualify_market(
        payload,
        {"entries": {}},
        fetch,
        now=NOW,
        run_id="first",
        fetch_text=lambda _url: pytest.fail("404 candidate must not fetch a board"),
    )
    second, _cache = qualifier.qualify_market(
        payload,
        cache,
        fetch,
        now=NOW,
        run_id="second",
        fetch_text=lambda _url: pytest.fail("cached candidate must not fetch a board"),
    )

    assert first["newly_audited_candidate_keys"]
    assert second["newly_audited_candidate_keys"] == []
    assert first["qualification_count"] == second["qualification_count"] == 1
    assert first["qualified_count"] == second["qualified_count"] == 0
    receipt = second["qualifications"][0]
    assert receipt["decision"] == "rejected"
    assert receipt["audit_error_code"] == "github_http_404"
    assert receipt["gates"]["application_allowed"] is False
    assert receipt["financial_truth"]["realized_revenue_usd"] == 0.0
    assert calls == ["rate_limit", "repos/acme/project", "rate_limit"]


@pytest.mark.parametrize(
    ("core_remaining", "search_remaining", "expected_code"),
    [
        (qualifier.MIN_CORE_RATE_REMAINING - 1, 29, "github_core_rate_budget_low"),
        (4999, qualifier.MIN_SEARCH_RATE_REMAINING - 1, "github_search_rate_budget_low"),
    ],
)
def test_low_rate_budget_fails_before_any_candidate_call(
    core_remaining: int, search_remaining: int, expected_code: str
):
    calls: list[str] = []

    def fetch(endpoint: str, params=None):
        del params
        calls.append(endpoint)
        assert endpoint == "rate_limit"
        return {
            "resources": {
                "core": {
                    "limit": 5000,
                    "remaining": core_remaining,
                    "reset": 2000000000,
                },
                "search": {
                    "limit": 30,
                    "remaining": search_remaining,
                    "reset": 2000000000,
                },
            }
        }

    with pytest.raises(qualifier.QualifierError) as error:
        qualifier.qualify_market(
            search_payload(),
            {"entries": {}},
            fetch,
            now=NOW,
            run_id="low-rate",
            fetch_text=lambda _url: pytest.fail("low rate must fail before board fetch"),
        )

    assert error.value.code == expected_code
    assert calls == ["rate_limit"]


@pytest.mark.skipif(os.name == "nt", reason="mode 0600 and os.fchmod are POSIX-only")
def test_atomic_output_is_private_mode_0600(tmp_path: Path):
    destination = tmp_path / "qualification.json"
    qualifier.atomic_json_write(destination, {"realized_revenue_usd": 0.0})

    assert json.loads(destination.read_text(encoding="utf-8")) == {
        "realized_revenue_usd": 0.0
    }
    if os.name != "nt":
        assert destination.stat().st_mode & 0o777 == 0o600


def test_external_transports_are_get_only_and_cannot_issue_writes(monkeypatch):
    captured: dict = {}

    class Completed:
        returncode = 0
        stdout = "{}"
        stderr = ""

    def fake_run(command, **kwargs):
        captured["command"] = list(command)
        captured["kwargs"] = kwargs
        return Completed()

    monkeypatch.setattr(qualifier.subprocess, "run", fake_run)
    assert qualifier.gh_get_json("repos/acme/project/issues/17/comments") == {}
    first_command = list(captured["command"])
    assert qualifier.gh_get_json("repos/acme/project/git/trees/feature%2Fmain") == {}
    with pytest.raises(qualifier.QualifierError) as invalid_escape:
        qualifier.gh_get_json("repos/acme/project/git/trees/feature%2Gmain")
    assert invalid_escape.value.code == "untrusted_github_endpoint"

    command = first_command
    method_index = command.index("-X") + 1
    assert command[method_index] == "GET"
    assert not {"POST", "PUT", "PATCH", "DELETE"}.intersection(command)
    assert captured["kwargs"]["check"] is False
    assert captured["kwargs"].get("shell", False) is False
    assert command[:5] == [
        "/usr/bin/gh",
        "api",
        "-X",
        "GET",
        "repos/acme/project/issues/17/comments",
    ]

    class BoardResponse:
        headers: ClassVar[dict[str, str]] = {
            "Content-Type": "text/html; charset=utf-8"
        }

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, maximum: int):
            assert maximum == qualifier.MAX_RESPONSE_BYTES + 1
            return board_document("250").encode("utf-8")

    def fake_urlopen(request, *, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return BoardResponse()

    monkeypatch.setattr(qualifier, "urlopen", fake_urlopen)
    assert "bounties-container" in qualifier.algora_get_text(
        "https://algora.io/acme/bounties"
    )
    assert captured["request"].get_method() == "GET"
    assert captured["request"].full_url == "https://algora.io/acme/bounties"
    assert captured["timeout"] == 25
