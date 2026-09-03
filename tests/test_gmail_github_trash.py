#!/usr/bin/env python3
"""Tests for Gmail GitHub-TRASH backfill v2 correctness."""
import json, os, sys, tempfile
sys.path.insert(0, '/Agentic/scripts')

def test_intent_without_applied_is_retriable():
    """Intent-only receipts must be retried on next run.
    load_receipts_by_phase returns (intent_ids, applied_ids)."""
    from gmail_github_trash_backfill import load_receipts_by_phase
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        f.write(json.dumps({"message_id": "test1", "phase": "intent"}) + "\n")
        f.write(json.dumps({"message_id": "test2", "phase": "applied"}) + "\n")
        f.write(json.dumps({"message_id": "test3", "phase": "intent"}) + "\n")
        path = f.name
    
    import gmail_github_trash_backfill as mod
    original = mod.RECEIPTS_PATH
    try:
        from pathlib import Path
        mod.RECEIPTS_PATH = Path(path)
        intent_ids, applied_ids = load_receipts_by_phase()
        assert "test2" in applied_ids, "applied receipt must be recognized"
        assert "test1" not in applied_ids, "intent-only must NOT block retry"
        assert "test3" not in applied_ids, "intent-only must NOT block retry"
        assert "test1" in intent_ids, "intent-only must be in intent set"
        print("PASS: intent_without_applied_is_retriable")
    finally:
        mod.RECEIPTS_PATH = original
        os.unlink(path)

def test_financial_signal_included_in_trash():
    """GitHub messages with financial_signal=true ARE eligible for TRASH."""
    from gmail_github_trash_backfill import is_eligible
    # is_eligible checks authentication dict, not top-level dkim_pass
    decision = {
        "message_id": "fin1",
        "rule_version": "gmail-inbox-v1",
        "status": "classified_untrusted_input",
        "content_fingerprint": "abc123",
        "sender_domain": "github.com",
        "authentication": {"dkim_pass": True, "dmarc_pass": False},
        "financial_signal": True,
        "security_signal": True,
    }
    assert is_eligible(decision), "Financial signal must NOT exclude GitHub message from TRASH"
    print("PASS: financial_signal_included_in_trash")

def test_non_github_excluded():
    """Non-github.com senders are NEVER eligible."""
    from gmail_github_trash_backfill import is_eligible
    for domain in ["gitlab.com", "gmail.com", "fake-github.com", ""]:
        decision = {
            "message_id": f"x_{domain}",
            "rule_version": "gmail-inbox-v1",
            "status": "classified_untrusted_input",
            "content_fingerprint": "fp",
            "sender_domain": domain,
            "authentication": {"dkim_pass": True, "dmarc_pass": False},
        }
        assert not is_eligible(decision), f"Domain '{domain}' must be excluded"
    print("PASS: non_github_excluded")

def test_auth_gate_required():
    """GitHub domain without DKIM/DMARC pass is NEVER eligible."""
    from gmail_github_trash_backfill import is_eligible
    decision = {
        "message_id": "noauth1",
        "rule_version": "gmail-inbox-v1",
        "status": "classified_untrusted_input",
        "content_fingerprint": "fp",
        "sender_domain": "github.com",
        "authentication": {"dkim_pass": False, "dmarc_pass": False},
    }
    assert not is_eligible(decision), "Missing DKIM+DMARC must exclude"
    print("PASS: auth_gate_required")

if __name__ == "__main__":
    test_intent_without_applied_is_retriable()
    test_financial_signal_included_in_trash()
    test_non_github_excluded()
    test_auth_gate_required()
    print("\nAll 4 tests PASSED")
