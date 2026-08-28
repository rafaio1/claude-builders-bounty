"""Tests for the complete, evidence-gated GitHub PR inventory."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import github_pr_inventory as inventory


def _comment(
    body: str,
    *,
    login: str = "maintainer",
    association: str = "OWNER",
    timestamp: str = "2026-08-28T10:00:00Z",
):
    return {
        "author": {"login": login},
        "authorAssociation": association,
        "bodyText": body,
        "createdAt": timestamp,
        "url": "https://github.com/org/repo/pull/1#issuecomment-1",
    }


def _review(
    state: str,
    body: str = "",
    *,
    association: str = "MEMBER",
    timestamp: str = "2026-08-28T10:00:00Z",
):
    return {
        "author": {"login": "reviewer"},
        "authorAssociation": association,
        "state": state,
        "bodyText": body,
        "submittedAt": timestamp,
        "url": "https://github.com/org/repo/pull/1#pullrequestreview-1",
    }


def _pr(**overrides):
    base = {
        "id": "PR_1",
        "number": 1,
        "title": "Implement feature",
        "url": "https://github.com/org/repo/pull/1",
        "state": "OPEN",
        "isDraft": False,
        "createdAt": "2026-08-27T10:00:00Z",
        "updatedAt": "2026-08-28T10:00:00Z",
        "closedAt": None,
        "mergedAt": None,
        "bodyText": "",
        "reviewDecision": None,
        "author": {"login": "rafaio1"},
        "repository": {
            "nameWithOwner": "org/repo",
            "isArchived": False,
            "isFork": False,
            "pushedAt": "2026-08-28T10:00:00Z",
            "updatedAt": "2026-08-28T10:00:00Z",
        },
        "comments": {"nodes": []},
        "reviews": {"nodes": []},
        "closingIssuesReferences": {"nodes": []},
    }
    base.update(overrides)
    return base


def test_author_self_claim_is_not_payment_evidence():
    pr = _pr(bodyText="I am claiming this $500 bounty and expect payment.")
    result = inventory.classify_pr(pr)
    assert result["author_self_claim_ignored"] is True
    assert result["payment_promise"]["authoritative"] is False
    assert result["classification"] == "ordinary_open"


def test_platform_bot_comment_is_authoritative_promise_not_revenue():
    pr = _pr(
        comments={
            "nodes": [
                _comment(
                    "Algora bounty: $75 USD for the accepted implementation.",
                    login="algora-pbc",
                    association="NONE",
                )
            ]
        }
    )
    result = inventory.classify_pr(pr)
    assert result["payment_promise"]["authoritative"] is True
    assert result["classification"] == "payment_validation_required"
    assert result["realized_revenue"] is False


def test_later_owner_no_bounty_overrides_old_promise():
    pr = _pr(
        comments={
            "nodes": [
                _comment("Bounty payment is $100 USD.", timestamp="2026-08-27T10:00:00Z"),
                _comment(
                    "There is no bounty or monetary reward for this contribution.",
                    timestamp="2026-08-28T10:00:00Z",
                ),
            ]
        }
    )
    result = inventory.classify_pr(pr)
    assert result["payment_promise"]["authoritative"] is False
    assert result["payment_promise"]["negated"] is True
    assert result["classification"] == "ordinary_open"


def test_merged_with_maintainer_promise_becomes_settlement_followup():
    pr = _pr(
        state="MERGED",
        mergedAt="2026-08-28T10:00:00Z",
        closedAt="2026-08-28T10:00:00Z",
        comments={"nodes": [_comment("We will pay a $250 bounty after merge.")]},
    )
    result = inventory.classify_pr(pr)
    assert result["classification"] == "settlement_validation_required"
    assert result["realized_revenue"] is False


def test_open_approved_with_promise_becomes_merge_followup():
    pr = _pr(
        reviewDecision="APPROVED",
        comments={"nodes": [_comment("This accepted bounty pays 125 USDT.")]},
        reviews={"nodes": [_review("APPROVED", "Looks good.")]},
    )
    result = inventory.classify_pr(pr)
    assert result["formal_approval"]["present"] is True
    assert result["classification"] == "merge_followup"


def test_open_maintainer_change_request_is_technical_followup_without_payment():
    pr = _pr(reviews={"nodes": [_review("CHANGES_REQUESTED", "Please add tests.")]})
    result = inventory.classify_pr(pr)
    assert result["classification"] == "technical_followup"
    assert result["payment_promise"]["authoritative"] is False


def test_own_owner_comment_cannot_create_payment_signal():
    pr = _pr(
        comments={
            "nodes": [
                _comment(
                    "This PR earns a $500 bounty.",
                    login="rafaio1",
                    association="OWNER",
                )
            ]
        }
    )
    result = inventory.classify_pr(pr)
    assert result["payment_promise"]["authoritative"] is False
    assert result["classification"] == "ordinary_open"


def test_issue_spec_is_not_pr_feedback():
    pr = _pr(
        closingIssuesReferences={
            "nodes": [
                {
                    "author": {"login": "maintainer"},
                    "authorAssociation": "OWNER",
                    "bodyText": "Please add tests and update the parser.",
                    "createdAt": "2026-08-27T09:00:00Z",
                    "lastEditedAt": None,
                    "url": "https://github.com/org/repo/issues/1",
                    "comments": {"nodes": []},
                }
            ]
        }
    )
    result = inventory.classify_pr(pr)
    assert result["actionable_feedback"]["present"] is False
    assert result["classification"] == "ordinary_open"


def test_positive_approved_review_does_not_become_technical_followup():
    pr = _pr(
        reviewDecision="APPROVED",
        reviews={
            "nodes": [
                _review("APPROVED", "Tests look good; no changes needed.")
            ]
        },
    )
    result = inventory.classify_pr(pr)
    assert result["formal_approval"]["present"] is True
    assert result["actionable_feedback"]["present"] is False
    assert result["classification"] == "ordinary_open"


def test_not_eligible_for_bounty_is_never_payment_signal():
    pr = _pr(
        comments={"nodes": [_comment("This PR isn't eligible for the $100 bounty.")]}
    )
    result = inventory.classify_pr(pr)
    assert result["payment_promise"]["authoritative"] is False
    assert result["payment_promise"]["negated"] is True


def test_truncated_evidence_window_cannot_promote_payment():
    pr = _pr(
        comments={
            "totalCount": 21,
            "nodes": [_comment("We will pay a $100 bounty after merge.")],
        }
    )
    result = inventory.classify_pr(pr)
    assert result["evidence_coverage"]["complete"] is False
    assert result["payment_promise"]["authoritative"] is False
    assert result["payment_promise"]["ambiguous_truncated"] is True
    assert result["classification"] == "evidence_review_required"


def test_truncated_window_without_visible_promise_still_enters_review_queue():
    pr = _pr(comments={"totalCount": 21, "nodes": [_comment("Thanks.")]})
    result = inventory.classify_pr(pr)
    assert result["evidence_coverage"]["complete"] is False
    assert result["classification"] == "evidence_review_required"


def test_later_duplicate_is_not_a_technical_followup():
    pr = _pr(
        comments={
            "nodes": [
                _comment(
                    "Tests pass, but this is a later duplicate. Another PR is the primary payout candidate."
                )
            ]
        }
    )
    result = inventory.classify_pr(pr)
    assert result["terminal_rejection"]["present"] is True
    assert result["actionable_feedback"]["present"] is False
    assert result["classification"] == "rejected_or_duplicate"


def test_thanks_for_update_is_not_actionable():
    pr = _pr(comments={"nodes": [_comment("Thanks for the update!")]})
    result = inventory.classify_pr(pr)
    assert result["actionable_feedback"]["present"] is False
    assert result["classification"] == "ordinary_open"


def test_chinese_maintainer_request_is_actionable():
    pr = _pr(comments={"nodes": [_comment("实现基本正确，缺的是第五条，测试。请添加测试代码。") ]})
    result = inventory.classify_pr(pr)
    assert result["actionable_feedback"]["present"] is True
    assert result["classification"] == "technical_followup"


def test_later_change_request_overrides_approval_and_payment():
    pr = _pr(
        reviewDecision="CHANGES_REQUESTED",
        comments={
            "nodes": [
                _comment("We will pay a $100 bounty after acceptance.", timestamp="2026-08-28T10:00:00Z")
            ]
        },
        reviews={
            "nodes": [
                _review("APPROVED", "Looks good.", timestamp="2026-08-28T10:30:00Z"),
                _review("CHANGES_REQUESTED", "Please add tests.", timestamp="2026-08-28T11:00:00Z"),
            ]
        },
    )
    result = inventory.classify_pr(pr)
    assert result["classification"] == "technical_followup"


def test_later_rejection_overrides_approval_and_payment():
    pr = _pr(
        reviewDecision="APPROVED",
        comments={
            "nodes": [
                _comment("We will pay a $100 bounty after acceptance.", timestamp="2026-08-28T10:00:00Z"),
                _comment("This is a later duplicate submission; another candidate was selected.", timestamp="2026-08-28T12:00:00Z"),
            ]
        },
        reviews={"nodes": [_review("APPROVED", "Looks good.", timestamp="2026-08-28T11:00:00Z")]},
    )
    result = inventory.classify_pr(pr)
    assert result["classification"] == "rejected_or_duplicate"


def test_later_payment_and_approval_supersede_old_rejection():
    pr = _pr(
        reviewDecision="APPROVED",
        comments={
            "nodes": [
                _comment("This was a duplicate submission.", timestamp="2026-08-28T08:00:00Z"),
                _comment("We will pay a $100 bounty after acceptance.", timestamp="2026-08-28T10:00:00Z"),
            ]
        },
        reviews={"nodes": [_review("APPROVED", "Accepted.", timestamp="2026-08-28T11:00:00Z")]},
    )
    result = inventory.classify_pr(pr)
    assert result["classification"] == "merge_followup"


def test_source_hash_changes_when_classification_changes():
    queries = [{"partition": "open", "reported_count": 1, "collected_count": 1, "pages": 1}]
    first = {"org/repo#1": {"classification": "ordinary_open", "url": "u"}}
    second = {"org/repo#1": {"classification": "technical_followup", "url": "u"}}
    assert inventory.inventory_source_hash("rafaio1", queries, first) != inventory.inventory_source_hash("rafaio1", queries, second)


def test_build_inventory_retries_one_drift():
    expected = ({"ok": True}, {"ok": True})
    with patch.object(
        inventory,
        "_build_inventory_once",
        side_effect=[inventory.InventoryDriftError("drift"), expected],
    ) as builder, patch.object(inventory.time, "sleep") as sleeper:
        assert inventory.build_inventory("rafaio1") == expected
    assert builder.call_count == 2
    sleeper.assert_called_once_with(2)


def test_collect_partition_paginates_and_requires_exact_count():
    first = {
        "data": {
            "search": {
                "issueCount": 2,
                "pageInfo": {"hasNextPage": True, "endCursor": "next"},
                "nodes": [_pr(number=1)],
            }
        }
    }
    second = {
        "data": {
            "search": {
                "issueCount": 2,
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [_pr(number=2, url="https://github.com/org/repo/pull/2")],
            }
        }
    }
    with patch.object(inventory, "run_graphql", side_effect=[first, second]) as mocked:
        nodes, count, pages = inventory.collect_partition("is:pr author:rafaio1 is:open")
    assert len(nodes) == count == 2
    assert pages == 2
    assert mocked.call_args_list[0].args[1] is None
    assert mocked.call_args_list[1].args[1] == "next"


def test_collect_partition_fails_closed_on_count_mismatch():
    response = {
        "data": {
            "search": {
                "issueCount": 2,
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [_pr(number=1)],
            }
        }
    }
    with patch.object(inventory, "run_graphql", return_value=response), pytest.raises(
        inventory.InventoryError, match="incomplete"
    ):
        inventory.collect_partition("is:pr author:rafaio1 is:open")


def test_query_partitions_are_disjoint_and_avoid_single_search_cap():
    queries = [template for _, template in inventory.QUERY_PARTITIONS]
    assert any("is:merged" in query for query in queries)
    assert any("is:open" in query for query in queries)
    assert any("is:closed -is:merged" in query for query in queries)
    assert len(queries) == 3


def test_graphql_retries_bounded_transient_cli_failure():
    failed = inventory.subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="temporary upstream error"
    )
    succeeded = inventory.subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout='{"data":{"search":{"issueCount":0}}}',
        stderr="",
    )
    with patch.object(inventory.subprocess, "run", side_effect=[failed, succeeded]) as mocked, \
         patch.object(inventory.time, "sleep") as sleeper:
        response = inventory.run_graphql("is:pr author:rafaio1 is:open", None)
    assert response["data"]["search"]["issueCount"] == 0
    assert mocked.call_count == 2
    sleeper.assert_called_once_with(1)
