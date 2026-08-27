"""Fail-closed handling for unaffiliated GitHub slash-attempt notifications."""

import sys
from pathlib import Path
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))

import pr_email_agent as agent


def test_unaffiliated_slash_attempt_is_non_actionable_and_never_trashed():
    for state in ("OPEN", "CLOSED", "MERGED"):
        action, trash = agent.classify_message(
            state,
            "zhaog100 commented:\n/attempt",
            author_association="NONE",
        )
        assert action == agent.UNAFFILIATED_ATTEMPT_ACTION
        assert trash is False


def test_affiliated_or_unverified_attempt_keeps_safe_ambiguous_default():
    assert agent.classify_message("OPEN", "\n/attempt", "MEMBER") == (
        "kept_ambiguous",
        False,
    )
    assert agent.classify_message("OPEN", "\n/attempt", None) == (
        "kept_ambiguous",
        False,
    )


def test_association_resolver_is_read_only_and_fail_closed():
    with patch.object(
        agent,
        "run_cmd_list",
        return_value=(0, "CONTRIBUTOR\nNONE", ""),
    ) as run:
        assert agent.github_latest_slash_attempt_association("org/repo", 12) == "NONE"
    command = run.call_args.args[0]
    assert command[:3] == ["gh", "api", "--paginate"]
    assert "comments?per_page=100" in command[3]

    with patch.object(agent, "run_cmd_list", return_value=(1, "", "denied")):
        assert agent.github_latest_slash_attempt_association("org/repo", 12) is None


def test_non_actionable_attempt_is_recorded_without_queue_or_mutation():
    search_lines = [
        "[msg_attempt] | notifications@github.com | [Test/repo] update (PR #9)"
    ]
    windows = [{"label": "30d", "query": "newer_than:30d"}]
    cursor = {
        "completed_windows": [],
        "verified_completed_windows": [],
        "current_window": None,
        "last_run": None,
    }

    with patch.object(agent, "gmail_search_paginated", return_value=search_lines), \
         patch.object(agent, "gh_pr_state", return_value=("OPEN", "https://github.com/Test/repo/pull/9")), \
         patch.object(agent, "gmail_read", return_value={"body": "/attempt", "snippet": ""}), \
         patch.object(agent, "github_latest_slash_attempt_association", return_value="NONE"), \
         patch.object(agent, "gmail_trash") as trash, \
         patch.object(agent, "append_action_queue") as queue, \
         patch.object(agent, "load_ledger", return_value=[]), \
         patch.object(agent, "save_ledger_atomic") as save_ledger, \
         patch.object(agent, "load_cursor", return_value=cursor), \
         patch.object(agent, "save_cursor"), \
         patch.object(agent, "SCAN_WINDOWS", windows):
        agent.classify_and_process()

    trash.assert_not_called()
    queue.assert_not_called()
    saved = save_ledger.call_args.args[0]
    assert len(saved) == 1
    assert saved[0]["action"] == agent.UNAFFILIATED_ATTEMPT_ACTION
    assert saved[0]["author_association"] == "NONE"
    assert saved[0]["trash_at"] is None
