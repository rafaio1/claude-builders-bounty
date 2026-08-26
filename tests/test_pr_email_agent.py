#!/usr/bin/env python3
"""Tests for pr_email_agent classification logic."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from pr_email_agent import classify_message, needs_human_action, is_bot_success_only


def test_closed_trashed():
    action, trash = classify_message("CLOSED", "any content")
    assert action == "trash_closed"
    assert trash is True


def test_merged_trashed():
    action, trash = classify_message("MERGED", "any content")
    assert action == "trash_merged"
    assert trash is True


def test_open_human_review_kept():
    body = "Reviewer left comments: changes requested on line 42"
    action, trash = classify_message("OPEN", body)
    assert action == "keep_action_needed"
    assert trash is False


def test_open_bot_review_with_changes_kept():
    body = "greptile-apps[bot] review: found 3 issues, changes requested"
    action, trash = classify_message("OPEN", body)
    assert action == "keep_action_needed"
    assert trash is False


def test_open_bot_success_trashed():
    body = "github-actions[bot]: all checks passed successfully"
    action, trash = classify_message("OPEN", body)
    assert action == "trash_bot_success"
    assert trash is True


def test_open_cla_kept():
    body = "Please sign the CLA before we can merge"
    action, trash = classify_message("OPEN", body)
    assert action == "keep_action_needed"
    assert trash is False


def test_open_payment_kept():
    body = "Bounty payout pending for this PR"
    action, trash = classify_message("OPEN", body)
    assert action == "keep_action_needed"
    assert trash is False


def test_open_ambiguous_kept():
    body = "Thanks for contributing! We'll take a look soon."
    action, trash = classify_message("OPEN", body)
    assert action == "kept_ambiguous"
    assert trash is False


def test_idempotency_same_classification():
    body = "CI failure detected in build step"
    a1, t1 = classify_message("OPEN", body)
    a2, t2 = classify_message("OPEN", body)
    assert a1 == a2 == "keep_action_needed"
    assert t1 == t2 is False


def test_injection_not_executed():
    body = "'; rm -rf /; echo 'changes requested"
    action, trash = classify_message("OPEN", body)
    assert action == "keep_action_needed"
    assert trash is False


def test_protect_patterns_coverage():
    protected = [
        "action required from maintainer",
        "please authorize deployment",
        "invite sent to collaborator",
        "security vulnerability reported",
        "build failed on main branch",
        "question about implementation",
        "awaiting response from author",
        "@reviewer please review this",
        "contract terms need update",
        "reward approved for contributor",
    ]
    for phrase in protected:
        assert needs_human_action(phrase), f"Failed to protect: {phrase}"


def test_bot_success_patterns_specific():
    successes = [
        "vercel[bot] successfully deployed preview",
        "github-actions[bot] all checks passed",
        "codecov[bot] coverage report uploaded",
        "dependabot[bot] merged automatically",
    ]
    for phrase in successes:
        assert is_bot_success_only(phrase), f"Failed bot success: {phrase}"


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            print(f"FAIL {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR {t.__name__}: {e}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
