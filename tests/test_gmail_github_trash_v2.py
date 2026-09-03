#!/usr/bin/env python3
"""Atomicity tests for gmail_github_trash_v2.py

Tests:
1. Intent without applied must be retried (crash between intent write and batchModify)
2. Financial/security signals in GitHub emails must be preserved, never trashed
3. Non-GitHub senders must never be touched
4. Already-applied messages must be skipped idempotently
5. DKIM/DMARC failure must prevent trash even if sender looks like GitHub
"""
import json, sys, tempfile, hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch, call
from datetime import datetime, timezone

# Add scripts to path
sys.path.insert(0, str(Path("/Agentic/scripts")))
import gmail_github_trash_v2 as gtv


def make_msg(msg_id, sender, subject="", snippet="", dkim_pass=True):
    """Create a mock Gmail message metadata structure."""
    auth_val = "dkim=pass dmarc=pass" if dkim_pass else "dkim=fail dmarc=fail"
    return {
        "id": msg_id,
        "snippet": snippet,
        "payload": {
            "headers": [
                {"name": "From", "value": sender},
                {"name": "Subject", "value": subject},
                {"name": "Authentication-Results", "value": auth_val},
            ]
        }
    }


def test_intent_without_applied_is_retried():
    """If receipt has intent but no applied, process_message must retry batchModify."""
    with tempfile.TemporaryDirectory() as td:
        receipt_path = Path(td) / "receipts.jsonl"
        # Write an intent-only receipt (simulates crash after intent, before batchModify)
        with open(receipt_path, "w") as f:
            f.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "msg_id": "msg_crash_001",
                "status": "intent",
                "reason": "pending_batch_modify",
                "rule_version": "gmail-inbox-v1",
                "content_fingerprint": "abc123",
                "sender_domain": "github.com"
            }) + "\n")

        # Mock service
        mock_service = MagicMock()
        mock_msg = make_msg("msg_crash_001", "notifications@github.com", "PR merged", "no financial signal")
        mock_service.users().messages().get.return_value.execute.return_value = mock_msg
        mock_service.users().messages().batchModify.return_value.execute.return_value = {}

        with patch.object(gtv, "RECEIPT_PATH", receipt_path):
            result = gtv.process_message(mock_service, "msg_crash_001")

        assert result == "applied", f"Expected 'applied' for intent-only receipt, got '{result}'"
        # Verify batchModify was called (retry happened)
        mock_service.users().messages().batchModify.assert_called_once()
        # Verify applied receipt was written
        lines = receipt_path.read_text().strip().split("\n")
        statuses = [json.loads(l)["status"] for l in lines]
        assert "applied" in statuses, f"Missing 'applied' receipt. Statuses: {statuses}"
        print("PASS: test_intent_without_applied_is_retried")


def test_financial_signal_preserved():
    """GitHub email with bounty/claim/payout keyword must be preserved, not trashed."""
    with tempfile.TemporaryDirectory() as td:
        receipt_path = Path(td) / "receipts.jsonl"
        mock_service = MagicMock()
        mock_msg = make_msg("msg_fin_001", "notifications@github.com",
                           "Bounty claim approved", "payout of $500 confirmed")
        mock_service.users().messages().get.return_value.execute.return_value = mock_msg

        with patch.object(gtv, "RECEIPT_PATH", receipt_path):
            result = gtv.process_message(mock_service, "msg_fin_001")

        assert "preserved" in result, f"Expected preserved, got '{result}'"
        # batchModify must NOT have been called
        mock_service.users().messages().batchModify.assert_not_called()
        # Receipt must say classified_preserved
        line = json.loads(receipt_path.read_text().strip())
        assert line["status"] == "classified_preserved"
        print("PASS: test_financial_signal_preserved")


def test_non_github_sender_untouched():
    """Non-GitHub sender must never be trashed or have batchModify called."""
    with tempfile.TemporaryDirectory() as td:
        receipt_path = Path(td) / "receipts.jsonl"
        mock_service = MagicMock()
        mock_msg = make_msg("msg_other_001", "alice@example.com", "Hello", "just chatting")
        mock_service.users().messages().get.return_value.execute.return_value = mock_msg

        with patch.object(gtv, "RECEIPT_PATH", receipt_path):
            result = gtv.process_message(mock_service, "msg_other_001")

        assert "not_github" in result, f"Expected not_github, got '{result}'"
        mock_service.users().messages().batchModify.assert_not_called()
        line = json.loads(receipt_path.read_text().strip())
        assert line["status"] == "classified_untrusted_input"
        print("PASS: test_non_github_sender_untouched")


def test_already_applied_skipped():
    """Message with existing applied receipt must be skipped without API calls."""
    with tempfile.TemporaryDirectory() as td:
        receipt_path = Path(td) / "receipts.jsonl"
        with open(receipt_path, "w") as f:
            f.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "msg_id": "msg_done_001",
                "status": "applied",
                "reason": "trashed_after_intent",
                "rule_version": "gmail-inbox-v1",
                "content_fingerprint": "xyz789",
                "sender_domain": "github.com"
            }) + "\n")

        mock_service = MagicMock()

        with patch.object(gtv, "RECEIPT_PATH", receipt_path):
            result = gtv.process_message(mock_service, "msg_done_001")

        assert "skipped_already_applied" in result, f"Expected skipped, got '{result}'"
        # No API calls at all
        mock_service.users().messages().get.assert_not_called()
        mock_service.users().messages().batchModify.assert_not_called()
        print("PASS: test_already_applied_skipped")


def test_dkim_fail_prevents_trash():
    """GitHub-looking sender with failed DKIM/DMARC must not be trashed."""
    with tempfile.TemporaryDirectory() as td:
        receipt_path = Path(td) / "receipts.jsonl"
        mock_service = MagicMock()
        mock_msg = make_msg("msg_spoof_001", "notifications@github.com",
                           "Account security alert", "verify your wallet", dkim_pass=False)
        mock_service.users().messages().get.return_value.execute.return_value = mock_msg

        with patch.object(gtv, "RECEIPT_PATH", receipt_path):
            result = gtv.process_message(mock_service, "msg_spoof_001")

        assert "not_github" in result, f"Expected not_github (dkim fail), got '{result}'"
        mock_service.users().messages().batchModify.assert_not_called()
        line = json.loads(receipt_path.read_text().strip())
        assert line["status"] == "classified_untrusted_input"
        assert line["reason"] == "dkim_dmarc_fail"
        print("PASS: test_dkim_fail_prevents_trash")


if __name__ == "__main__":
    test_intent_without_applied_is_retried()
    test_financial_signal_preserved()
    test_non_github_sender_untouched()
    test_already_applied_skipped()
    test_dkim_fail_prevents_trash()
    print("\nALL 5 TESTS PASSED")
