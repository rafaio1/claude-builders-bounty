import json
import os
import sys
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add tools to path
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import revenue_reconciler as rr

@pytest.fixture
def temp_workspace(tmp_path):
    """Create isolated workspace for tests."""
    data_dir = tmp_path / "data" / "aro"
    data_dir.mkdir(parents=True)
    
    # Override paths
    rr.WORKDIR = tmp_path
    rr.QUEUE_FILE = data_dir / "approved_pr_payment_queue.json"
    rr.REALIZED_LEDGER = data_dir / "realized_revenue_ledger.jsonl"
    rr.CHECKPOINT_FILE = data_dir / "reconciler_checkpoint.json"
    rr.LOCK_FILE = data_dir / "reconciler.lock"
    
    yield tmp_path, data_dir

def test_fake_bounty_rejected(temp_workspace):
    """Bounties without Tier A fields must be rejected in fast path."""
    tmp_path, data_dir = temp_workspace
    queue = [
        {
            "canonical_key": "fake/repo#1",
            "github_merged": True,
            "status": "PENDING",
            "bounty_evidence": {
                "official_reward_url": None,
                "official_value": 100,
                "eligibility_confirmed": True,
                "claim_path_verified": False
            }
        }
    ]
    rr.save_json(rr.QUEUE_FILE, queue)
    
    decision, reason = rr.classify_item_fast(queue[0])
    assert decision == "INCOMPLETE_EVIDENCE"
    assert reason == "missing_tier_a_fields"

def test_duplicate_settlement_rejected(temp_workspace):
    """Same provider+tx_id must not be recorded twice."""
    tmp_path, data_dir = temp_workspace
    
    entry = {
        "provider": "wise",
        "transaction_id": "TRX-123",
        "timestamp": "2026-08-27T00:00:00Z",
        "currency": "USD",
        "gross": 100.0,
        "fee": 2.0,
        "net": 98.0
    }
    
    assert rr.append_ledger(entry) == True
    assert rr.append_ledger(entry) == False  # Duplicate
    
    with open(rr.REALIZED_LEDGER) as f:
        lines = [l for l in f if l.strip()]
    assert len(lines) == 1

def test_fee_math_validation(temp_workspace):
    """Net must equal gross - fee within tolerance."""
    tmp_path, data_dir = temp_workspace
    
    bad_entry = {
        "provider": "bybit",
        "transaction_id": "TRX-BAD",
        "timestamp": "2026-08-27T00:00:00Z",
        "currency": "USDT",
        "gross": 100.0,
        "fee": 5.0,
        "net": 90.0  # Wrong: should be 95.0
    }
    
    assert rr.append_ledger(bad_entry) == False

def test_valid_settlement_recorded(temp_workspace):
    """Valid settlement with correct math must be recorded."""
    tmp_path, data_dir = temp_workspace
    
    entry = {
        "provider": "binance",
        "transaction_id": "TRX-OK",
        "timestamp": "2026-08-27T12:00:00Z",
        "currency": "USDT",
        "gross": 500.0,
        "fee": 1.5,
        "net": 498.5
    }
    
    assert rr.append_ledger(entry) == True
    
    with open(rr.REALIZED_LEDGER) as f:
        recorded = json.loads(f.readline())
    
    assert recorded["provider"] == "binance"
    assert recorded["transaction_id"] == "TRX-OK"
    assert recorded["net"] == 498.5
    assert "recorded_at" in recorded

def test_audit_completes_under_60s(temp_workspace):
    """Audit must finish quickly even with empty/small queue."""
    tmp_path, data_dir = temp_workspace
    rr.save_json(rr.QUEUE_FILE, [])
    
    import time
    start = time.time()
    report = rr.audit(max_api_calls=5)
    elapsed = time.time() - start
    
    assert elapsed < 60.0
    assert report["stats"]["total"] == 0
    assert report["elapsed_seconds"] < 60.0

def test_bybit_floor_is_five():
    """Bybit minimum balance must be 5.0, not 2.975."""
    assert rr.BYBIT_MIN_BALANCE == 5.0
    assert rr.BYBIT_MIN_BALANCE >= 5.0

def test_bounty_evidence_list_fails_closed(temp_workspace):
    """bounty_evidence as list must not raise AttributeError."""
    tmp_path, data_dir = temp_workspace
    item = {
        "canonical_key": "test/repo#1",
        "github_merged": True,
        "status": "PENDING",
        "bounty_evidence": ["not", "a", "dict"]
    }
    decision, reason = rr.classify_item_fast(item)
    assert decision == "INCOMPLETE_EVIDENCE"
    assert reason == "bounty_evidence_not_dict"

def test_bounty_evidence_none_fails_closed(temp_workspace):
    """bounty_evidence as None must not raise AttributeError."""
    tmp_path, data_dir = temp_workspace
    item = {
        "canonical_key": "test/repo#2",
        "github_merged": True,
        "status": "PENDING",
        "bounty_evidence": None
    }
    decision, reason = rr.classify_item_fast(item)
    assert decision == "INCOMPLETE_EVIDENCE"
    assert reason == "bounty_evidence_not_dict"

def test_provider_allowlist_enforced(temp_workspace):
    """Unknown provider must be rejected."""
    tmp_path, data_dir = temp_workspace
    entry = {
        "provider": "sketchy_bank",
        "transaction_id": "TRX-X",
        "timestamp": "2026-08-27T00:00:00Z",
        "currency": "USD",
        "gross": 100.0,
        "fee": 1.0,
        "net": 99.0
    }
    valid, reason = rr.validate_settlement(entry)
    assert valid == False
    assert "provider_not_allowed" in reason

def test_empty_transaction_id_rejected(temp_workspace):
    """Whitespace-only or empty tx_id must be rejected."""
    tmp_path, data_dir = temp_workspace
    entry = {
        "provider": "wise",
        "transaction_id": "   ",
        "timestamp": "2026-08-27T00:00:00Z",
        "currency": "USD",
        "gross": 100.0,
        "fee": 1.0,
        "net": 99.0
    }
    valid, reason = rr.validate_settlement(entry)
    assert valid == False
    assert reason == "empty_transaction_id"

def test_negative_gross_rejected(temp_workspace):
    """Gross must be positive."""
    tmp_path, data_dir = temp_workspace
    entry = {
        "provider": "wise",
        "transaction_id": "TRX-NEG",
        "timestamp": "2026-08-27T00:00:00Z",
        "currency": "USD",
        "gross": -10.0,
        "fee": 0.0,
        "net": -10.0
    }
    valid, reason = rr.validate_settlement(entry)
    assert valid == False
    assert reason == "gross_must_be_positive"

def test_negative_fee_rejected(temp_workspace):
    """Fee must be non-negative."""
    tmp_path, data_dir = temp_workspace
    entry = {
        "provider": "wise",
        "transaction_id": "TRX-NEGFEE",
        "timestamp": "2026-08-27T00:00:00Z",
        "currency": "USD",
        "gross": 100.0,
        "fee": -5.0,
        "net": 105.0
    }
    valid, reason = rr.validate_settlement(entry)
    assert valid == False
    assert reason == "fee_must_be_nonnegative"

def test_status_groups_by_currency(temp_workspace):
    """Status must not sum different currencies together."""
    tmp_path, data_dir = temp_workspace
    
    entries = [
        {"provider": "wise", "transaction_id": "T1", "timestamp": "2026-08-27T00:00:00Z", "currency": "USD", "gross": 100, "fee": 1, "net": 99},
        {"provider": "binance", "transaction_id": "T2", "timestamp": "2026-08-27T00:00:00Z", "currency": "USDT", "gross": 200, "fee": 2, "net": 198},
        {"provider": "wise", "transaction_id": "T3", "timestamp": "2026-08-27T00:00:00Z", "currency": "USD", "gross": 50, "fee": 0.5, "net": 49.5},
    ]
    for e in entries:
        rr.append_ledger(e)
    
    # Capture status output
    import io
    from contextlib import redirect_stdout
    f = io.StringIO()
    with redirect_stdout(f):
        rr.status()
    output = json.loads(f.getvalue())
    
    totals = output["total_realized_net_by_currency"]
    assert "USD" in totals
    assert "USDT" in totals
    assert abs(totals["USD"] - 148.5) < 0.01
    assert abs(totals["USDT"] - 198.0) < 0.01
    # Must NOT have a single combined total
    assert "total_realized_net" not in output

def test_max_api_calls_capped():
    """MAX_API_CALLS must be <= 20."""
    assert rr.MAX_API_CALLS <= 20

def test_audit_hard_deadline_below_60():
    """AUDIT_HARD_DEADLINE must be < 60."""
    assert rr.AUDIT_HARD_DEADLINE < 60
