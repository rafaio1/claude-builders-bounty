#!/usr/bin/env python3
"""Deterministic tests for Revenue Control Plane."""
import json
import os
import sys
import tempfile
from pathlib import Path

# Ensure tools is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import revenue_control_plane as rcp


def make_item(merged=False, evidence=None, status="OPEN", reason=""):
    return {
        "canonical_key": "test/repo#1",
        "url": "https://github.com/test/repo/pull/1",
        "merged": merged,
        "api_merged": merged,
        "bounty_evidence": evidence,
        "status": status,
        "classification_reason": reason,
    }


def test_tier_a_rejects_list_evidence():
    item = make_item(merged=True, evidence=["bounty_repo", "title_signal"])
    assert not rcp.is_tier_a_payable(item), "List evidence must fail closed"


def test_tier_a_rejects_null_evidence():
    item = make_item(merged=True, evidence=None)
    assert not rcp.is_tier_a_payable(item), "Null evidence must fail closed"


def test_tier_a_rejects_unmerged():
    evidence = {"amount": 500, "url": "https://example.com/bounty", "claim_path": "/claim"}
    item = make_item(merged=False, evidence=evidence)
    assert not rcp.is_tier_a_payable(item), "Unmerged PR must not be Tier A"


def test_tier_a_rejects_missing_claim_path():
    evidence = {"amount": 500, "url": "https://example.com/bounty"}
    item = make_item(merged=True, evidence=evidence)
    assert not rcp.is_tier_a_payable(item), "Missing claim_path must fail"


def test_tier_a_rejects_honeypot():
    evidence = {"amount": 500, "url": "https://example.com/bounty", "claim_path": "/claim"}
    item = make_item(merged=True, evidence=evidence, status="NOT_BOUNTY", reason="SATIRICAL_HONEYPOT_PI_IMPOSSIBLE")
    assert not rcp.is_tier_a_payable(item), "Honeypot/satire must be rejected"


def test_tier_a_accepts_valid():
    evidence = {"amount": 1000, "url": "https://example.com/bounty", "claim_path": "/claim"}
    item = make_item(merged=True, evidence=evidence)
    assert rcp.is_tier_a_payable(item), "Valid Tier A item should pass"


def test_ev_per_hour_zero_for_spam():
    evidence = {"amount": 1000, "url": "https://example.com/bounty", "claim_path": "/claim"}
    item = make_item(merged=True, evidence=evidence, reason="SPAM_BOT")
    assert rcp.compute_ev_per_hour(item) == 0.0


def test_ev_per_hour_positive_for_valid():
    evidence = {"amount": 1000, "url": "https://example.com/bounty", "claim_path": "/claim"}
    item = make_item(merged=True, evidence=evidence)
    ev = rcp.compute_ev_per_hour(item)
    assert ev > 0, f"EV should be positive for valid item, got {ev}"
    assert ev == 10.0, f"1000/100h should be 10.0, got {ev}"


def test_build_work_orders_max_three():
    queue = []
    for i in range(10):
        evidence = {"amount": 100 * (i + 1), "url": f"https://example.com/{i}", "claim_path": "/claim"}
        queue.append({
            "canonical_key": f"test/repo#{i}",
            "url": f"https://github.com/test/repo/pull/{i}",
            "merged": True,
            "api_merged": True,
            "bounty_evidence": evidence,
            "status": "OPEN",
            "classification_reason": "",
        })
    orders = rcp.build_work_orders(queue, max_orders=3)
    assert len(orders) <= 3, f"Should cap at 3 orders, got {len(orders)}"
    # Should pick highest EV first
    assert orders[0]["bounty_amount"] == 1000


def test_build_work_orders_empty_for_no_tier_a():
    queue = [make_item(merged=False, evidence=["list"]), make_item(merged=True, evidence=None)]
    orders = rcp.build_work_orders(queue)
    assert len(orders) == 0, "No Tier A items should produce empty work orders"


def test_reconcile_ledger_groups_by_currency(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    entries = [
        {"provider": "wise", "transaction_id": "t1", "currency": "USD", "gross": 100, "fee": 5, "net": 95},
        {"provider": "bybit", "transaction_id": "t2", "currency": "USDT", "gross": 200, "fee": 2, "net": 198},
        {"provider": "wise", "transaction_id": "t3", "currency": "USD", "gross": 50, "fee": 3, "net": 47},
    ]
    with open(ledger, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    
    original = rcp.LEDGER_FILE
    try:
        rcp.LEDGER_FILE = ledger
        result = rcp.reconcile_ledger()
    finally:
        rcp.LEDGER_FILE = original
    
    assert result["entries"] == 3
    assert "USD" in result["total_by_currency"]
    assert "USDT" in result["total_by_currency"]
    assert abs(result["total_by_currency"]["USD"] - 142.0) < 0.001
    assert abs(result["total_by_currency"]["USDT"] - 198.0) < 0.001
    # Must NOT sum across currencies
    total_sum = sum(result["total_by_currency"].values())
    assert abs(total_sum - 340.0) < 0.001


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
