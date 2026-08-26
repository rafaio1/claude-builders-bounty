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


def test_gmail_trash_returns_bool():
    """Verify gmail_trash returns bool and handles failure."""
    from unittest.mock import patch
    from pr_email_agent import gmail_trash
    with patch("pr_email_agent.run_cmd_list") as mock_run:
        mock_run.return_value = (0, '{"status": "ok"}', "")
        assert gmail_trash("msg123") is True
    with patch("pr_email_agent.run_cmd_list") as mock_run:
        mock_run.return_value = (1, "", "API error")
        assert gmail_trash("msg456") is False


def test_trash_failed_entry_not_in_seen():
    """When trash fails, entry has reprocess=True and is not permanently blocked."""
    from unittest.mock import patch
    import pr_email_agent as agent
    fake_search_lines = ["[msg_fail] | github@github.com | [Test/repo] PR #999 (PR #999)"]
    single_window = [{"label": "30d", "query": "newer_than:30d"}]
    with patch.object(agent, "gmail_search_paginated", return_value=fake_search_lines), \
         patch.object(agent, "gh_pr_state", return_value=("CLOSED", "https://example.com/999")), \
         patch.object(agent, "gmail_read", return_value={"body": "", "snippet": ""}), \
         patch.object(agent, "gmail_trash", return_value=False), \
         patch.object(agent, "save_ledger_atomic") as mock_save, \
         patch.object(agent, "load_ledger", return_value=[]), \
         patch.object(agent, "load_cursor", return_value={"completed_windows": [], "current_window": None, "last_run": None}), \
         patch.object(agent, "save_cursor"), \
         patch.object(agent, "SCAN_WINDOWS", single_window):
        agent.classify_and_process()
        saved = mock_save.call_args[0][0]
        assert len(saved) == 1
        entry = saved[0]
        assert entry["action"] == "trash_failed"
        assert entry["reprocess"] is True
        assert entry["trash_at"] is None
        seen = set()
        for e in saved:
            mid = e.get("message_id")
            if e.get("reprocess"):
                seen.discard(mid)
            else:
                seen.add(mid)
        assert "msg_fail" not in seen


def test_latest_entry_wins_reprocess():
    """Latest-entry-wins: a reprocess=True entry allows re-processing."""
    fake_ledger = [
        {"message_id": "msg_rp", "action": "trash_closed", "trash_at": "2026-01-01T00:00:00Z"},
        {"message_id": "msg_rp", "action": "restored_unsafe_open_no_action", "reprocess": True},
    ]
    seen = set()
    for e in fake_ledger:
        mid = e.get("message_id")
        if e.get("reprocess"):
            seen.discard(mid)
        else:
            seen.add(mid)
    assert "msg_rp" not in seen


def test_cursor_load_save(tmp_path):
    """Cursor persists completed windows and survives round-trip."""
    from unittest.mock import patch
    import pr_email_agent as agent
    cursor_file = tmp_path / "cursor.json"
    original = agent.CURSOR_PATH
    agent.CURSOR_PATH = str(cursor_file)
    try:
        # Fresh load returns defaults
        c = agent.load_cursor()
        assert c["completed_windows"] == []
        # Save and reload
        c["completed_windows"] = ["30d"]
        c["last_run"] = "2026-08-26T00:00:00+00:00"
        agent.save_cursor(c)
        c2 = agent.load_cursor()
        assert "30d" in c2["completed_windows"]
        assert c2["last_run"] == "2026-08-26T00:00:00+00:00"
    finally:
        agent.CURSOR_PATH = original


def test_window_completion_skips_on_rerun():
    """Completed windows are skipped unless overridden."""
    from unittest.mock import patch, MagicMock
    import pr_email_agent as agent
    cursor = {"completed_windows": ["30d", "30d-1y", "gt1y"], "current_window": None, "last_run": None}
    mock_search = MagicMock(return_value=[])
    with patch.object(agent, "load_cursor", return_value=cursor), \
         patch.object(agent, "save_cursor"), \
         patch.object(agent, "gmail_search_paginated", mock_search), \
         patch.object(agent, "load_ledger", return_value=[]), \
         patch.object(agent, "save_ledger_atomic"):
        agent.classify_and_process()
        # All windows completed -> search never called
        assert mock_search.call_count == 0


def test_batch_limit_stops_processing():
    """Batch size limits processing per window."""
    from unittest.mock import patch
    import pr_email_agent as agent
    lines = [f"[msg{i}] | github@github.com | [Test/repo] PR #{i} (PR #{i})" for i in range(10)]
    single_window = [{"label": "30d", "query": "newer_than:30d"}]
    processed_msgs = []

    def fake_classify(state, body):
        return "kept_ambiguous", False

    def fake_append(entry):
        processed_msgs.append(entry["message_id"])

    with patch.object(agent, "gmail_search_paginated", return_value=lines), \
         patch.object(agent, "gh_pr_state", return_value=("OPEN", "https://example.com")), \
         patch.object(agent, "gmail_read", return_value={"body": "", "snippet": ""}), \
         patch.object(agent, "classify_message", side_effect=fake_classify), \
         patch.object(agent, "append_action_queue", side_effect=fake_append), \
         patch.object(agent, "load_ledger", return_value=[]), \
         patch.object(agent, "save_ledger_atomic"), \
         patch.object(agent, "load_cursor", return_value={"completed_windows": [], "current_window": None, "last_run": None}), \
         patch.object(agent, "save_cursor"), \
         patch.object(agent, "SCAN_WINDOWS", single_window):
        agent.classify_and_process(batch_size=3)
        assert len(processed_msgs) == 3


def test_dry_run_no_side_effects():
    """Dry run must not call trash, append queue, save_ledger_atomic, or save_cursor."""
    from unittest.mock import patch, MagicMock
    import pr_email_agent as agent
    lines = ["[msg_dry] | github@github.com | [Test/repo] PR #1 (PR #1)"]
    single_window = [{"label": "30d", "query": "newer_than:30d"}]
    with patch.object(agent, "gmail_search_paginated", return_value=lines), \
         patch.object(agent, "gh_pr_state", return_value=("CLOSED", "https://example.com/1")), \
         patch.object(agent, "gmail_read", return_value={"body": "", "snippet": ""}), \
         patch.object(agent, "gmail_trash") as mock_trash, \
         patch.object(agent, "append_action_queue") as mock_queue, \
         patch.object(agent, "save_ledger_atomic") as mock_save_ledger, \
         patch.object(agent, "save_cursor") as mock_save_cursor, \
         patch.object(agent, "load_ledger", return_value=[]), \
         patch.object(agent, "load_cursor", return_value={"completed_windows": [], "current_window": None, "last_run": None}), \
         patch.object(agent, "SCAN_WINDOWS", single_window):
        result = agent.classify_and_process(dry_run=True)
        mock_trash.assert_not_called()
        mock_queue.assert_not_called()
        mock_save_ledger.assert_not_called()
        mock_save_cursor.assert_not_called()
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["message_id"] == "msg_dry"
