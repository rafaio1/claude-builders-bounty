"""
Tests for Telegram Financial Gate - Fail-Closed Validation

Covers:
- Allowed: payout_received, trade_realized with valid evidence
- Rejected: paper trades, potential bounties, PR opened, waiting state,
  duplicate event_id, missing external_reference, net=0, unconfirmed reconciliation
"""
import sys
import os
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timezone

# Add src to path
sys.path.insert(0, str(Path("/Agentic/src")))

from telegram_gate import validate_event, send_financial_event, _load_dedup, _save_dedup, DEDUP_FILE


def make_valid_event(**overrides):
    """Create a valid financial event for testing."""
    base = {
        "event_id": "test-event-001",
        "process_id": "bounty-immunefi-123",
        "event_type": "payout_received",
        "source": "immunefi",
        "external_reference": "TX-ABC123DEF456",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "asset": "USDC",
        "gross": 500.00,
        "fees": 5.00,
        "net": 495.00,
        "currency": "USDC",
        "reconciliation_status": "confirmed"
    }
    base.update(overrides)
    return base


class TestValidateEvent:
    """Test schema validation logic."""
    
    def test_valid_payout(self):
        event = make_valid_event()
        is_valid, reason = validate_event(event)
        assert is_valid, f"Valid payout rejected: {reason}"
    
    def test_valid_trade_realized(self):
        event = make_valid_event(
            event_type="trade_realized",
            process_id="grid-v22-xrp",
            source="bybit",
            external_reference="ORDER-789XYZ",
            asset="XRP",
            gross=12.50,
            fees=0.05,
            net=12.45,
            currency="USDT"
        )
        is_valid, reason = validate_event(event)
        assert is_valid, f"Valid trade rejected: {reason}"
    
    def test_valid_transfer_confirmed(self):
        event = make_valid_event(
            event_type="transfer_confirmed",
            process_id="wise-withdrawal-456",
            source="wise",
            external_reference="WISE-TX-999",
            asset="USD",
            gross=1000.00,
            fees=10.00,
            net=990.00,
            currency="USD"
        )
        is_valid, reason = validate_event(event)
        assert is_valid, f"Valid transfer rejected: {reason}"
    
    def test_reject_paper_trade(self):
        event = make_valid_event(event_type="paper_trade")
        is_valid, reason = validate_event(event)
        assert not is_valid, "Paper trade should be rejected"
        assert "Blocked event_type" in reason
    
    def test_reject_potential_bounty(self):
        event = make_valid_event(event_type="potential_bounty")
        is_valid, reason = validate_event(event)
        assert not is_valid, "Potential bounty should be rejected"
    
    def test_reject_pr_opened(self):
        event = make_valid_event(event_type="pr_opened")
        is_valid, reason = validate_event(event)
        assert not is_valid, "PR opened should be rejected"
    
    def test_reject_waiting_state(self):
        event = make_valid_event(event_type="waiting_monitoring")
        is_valid, reason = validate_event(event)
        assert not is_valid, "Waiting state should be rejected"
    
    def test_reject_heartbeat(self):
        event = make_valid_event(event_type="heartbeat")
        is_valid, reason = validate_event(event)
        assert not is_valid, "Heartbeat should be rejected"
    
    def test_reject_scan_result(self):
        event = make_valid_event(event_type="scan_result")
        is_valid, reason = validate_event(event)
        assert not is_valid, "Scan result should be rejected"
    
    def test_reject_opportunity(self):
        event = make_valid_event(event_type="grid_opportunity")
        is_valid, reason = validate_event(event)
        assert not is_valid, "Opportunity should be rejected"
    
    def test_reject_net_zero(self):
        event = make_valid_event(net=0)
        is_valid, reason = validate_event(event)
        assert not is_valid, "Net=0 should be rejected"
        assert "zero" in reason.lower()
    
    def test_reject_missing_external_reference(self):
        event = make_valid_event(external_reference="")
        is_valid, reason = validate_event(event)
        assert not is_valid, "Empty external_reference should be rejected"
    
    def test_reject_generic_external_reference(self):
        for bad_ref in ["none", "null", "n/a", "test", "N/A"]:
            event = make_valid_event(external_reference=bad_ref)
            is_valid, reason = validate_event(event)
            assert not is_valid, f"Generic ref '{bad_ref}' should be rejected"
    
    def test_reject_unconfirmed_reconciliation(self):
        event = make_valid_event(reconciliation_status="pending")
        is_valid, reason = validate_event(event)
        assert not is_valid, "Unconfirmed reconciliation should be rejected"
        assert "confirmed" in reason.lower()
    
    def test_reject_missing_required_field(self):
        for field in ["event_id", "process_id", "event_type", "source", 
                      "external_reference", "occurred_at", "asset", 
                      "gross", "fees", "net", "currency", "reconciliation_status"]:
            event = make_valid_event()
            del event[field]
            is_valid, reason = validate_event(event)
            assert not is_valid, f"Missing {field} should be rejected"
            assert field in reason
    
    def test_reject_non_dict(self):
        is_valid, reason = validate_event("not a dict")
        assert not is_valid
        
        is_valid, reason = validate_event(None)
        assert not is_valid


class TestDeduplication:
    """Test persistent deduplication logic."""
    
    def setup_method(self):
        """Clean dedup file before each test."""
        if DEDUP_FILE.exists():
            DEDUP_FILE.unlink()
    
    def test_duplicate_rejected(self):
        # First send should work (dry_run to avoid actual API call)
        event = make_valid_event(event_id="dedup-test-001")
        result1 = send_financial_event(event, dry_run=True)
        assert result1, "First send should succeed"
        
        # Manually add to dedup (simulating successful send)
        seen = _load_dedup()
        seen.add("dedup-test-001")
        _save_dedup(seen)
        
        # Second send with same ID should be rejected
        result2 = send_financial_event(event, dry_run=True)
        assert not result2, "Duplicate event_id should be rejected"
    
    def test_different_ids_allowed(self):
        event1 = make_valid_event(event_id="unique-001")
        event2 = make_valid_event(event_id="unique-002")
        
        result1 = send_financial_event(event1, dry_run=True)
        result2 = send_financial_event(event2, dry_run=True)
        
        assert result1 and result2, "Different event_ids should both pass"


class TestDryRun:
    """Test dry-run mode doesn't send real messages."""
    
    def test_dry_run_returns_true_for_valid(self):
        event = make_valid_event()
        result = send_financial_event(event, dry_run=True)
        assert result, "Dry run should return True for valid events"
    
    def test_dry_run_returns_false_for_invalid(self):
        event = make_valid_event(event_type="invalid_type")
        result = send_financial_event(event, dry_run=True)
        assert not result, "Dry run should return False for invalid events"


def run_tests():
    """Run all tests and report results."""
    import traceback
    
    test_classes = [TestValidateEvent, TestDeduplication, TestDryRun]
    total = 0
    passed = 0
    failed = []
    
    for cls in test_classes:
        instance = cls()
        methods = [m for m in dir(instance) if m.startswith("test_")]
        
        for method_name in methods:
            total += 1
            try:
                if hasattr(instance, "setup_method"):
                    instance.setup_method()
                getattr(instance, method_name)()
                passed += 1
                print(f"  ✅ {cls.__name__}.{method_name}")
            except AssertionError as e:
                failed.append((f"{cls.__name__}.{method_name}", str(e)))
                print(f"  ❌ {cls.__name__}.{method_name}: {e}")
            except Exception as e:
                failed.append((f"{cls.__name__}.{method_name}", f"Exception: {e}"))
                print(f"  💥 {cls.__name__}.{method_name}: {e}")
                traceback.print_exc()
    
    print(f"\n{'='*60}")
    print(f"Results: {passed}/{total} passed")
    if failed:
        print(f"\nFailed tests:")
        for name, err in failed:
            print(f"  - {name}: {err}")
        return 1
    else:
        print("All tests passed! ✅")
        return 0


if __name__ == "__main__":
    sys.exit(run_tests())
