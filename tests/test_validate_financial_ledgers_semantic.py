#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


VALIDATOR_PATH = Path(__file__).with_name("validate_financial_ledgers_semantic.py")
RECONCILER_PATH = Path(__file__).with_name("agentic_rustchain_reconcile.py")
if not VALIDATOR_PATH.exists():
    VALIDATOR_PATH = Path("/usr/local/lib/agentic/validate_financial_ledgers.py")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = load_module("semantic_validator", VALIDATOR_PATH)
RECONCILER_TESTS = load_module("reconciler_tests", Path(__file__).with_name("test_agentic_rustchain_reconcile.py"))
RECONCILER = RECONCILER_TESTS.MODULE


class ValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        ledger = self.root / "data/aro/bounty_receive_ledger.json"
        ledger.parent.mkdir(parents=True)
        ledger.write_text(json.dumps({"schema_version": "1.0", "ledger_id": "test", "updated_at": "2026-09-01T14:00:00Z", "entries": []}), encoding="utf-8")
        (self.root / "data/aro/realized_revenue_ledger.jsonl").write_text("", encoding="utf-8")
        RECONCILER.reconcile(self.root, RECONCILER_TESTS.fixture_evidence(), now="2026-09-01T14:00:00+00:00")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_valid_canonical_artifacts(self) -> None:
        errors = VALIDATOR.validate(
            self.root,
            now=datetime(2026, 9, 1, 14, 5, tzinfo=timezone.utc),
            report_max_age_seconds=0,
        )
        self.assertEqual(errors, [])

    def test_future_report_fails_closed(self) -> None:
        reports = self.root / "logs/capital_cycles"
        reports.mkdir(parents=True)
        report = reports / "future.json"
        report.write_text(json.dumps({"timestamp": "2026-09-01T15:00:00Z", "financial_state": {"realized_revenue_usd": 0}}), encoding="utf-8")
        now_epoch = datetime(2026, 9, 1, 14, 5, tzinfo=timezone.utc).timestamp()
        os.utime(report, (now_epoch, now_epoch))
        errors = VALIDATOR.validate(
            self.root,
            now=datetime(2026, 9, 1, 14, 5, tzinfo=timezone.utc),
            report_max_age_seconds=1200,
        )
        self.assertTrue(any("future timestamp" in error for error in errors))

    def test_inconsistent_summary_fails_closed(self) -> None:
        reports = self.root / "logs/capital_cycles"
        reports.mkdir(parents=True)
        report = reports / "summary.json"
        report.write_text(json.dumps({"timestamp": "2026-09-01T14:05:00Z", "ledger": {"total_entries": 46}}), encoding="utf-8")
        ledger_path = self.root / "data/aro/bounty_receive_ledger.json"
        ledger_mtime = datetime(2026, 9, 1, 14, 4, 50, tzinfo=timezone.utc).timestamp()
        os.utime(ledger_path, (ledger_mtime, ledger_mtime))
        os.utime(report, (ledger_mtime + 1, ledger_mtime + 1))
        errors = VALIDATOR.validate(
            self.root,
            now=datetime(2026, 9, 1, 14, 5, tzinfo=timezone.utc),
            report_max_age_seconds=10**9,
        )
        self.assertTrue(any("total_entries=46 disagrees" in error for error in errors))

    def test_wallet_receipt_requires_exact_public_transactions(self) -> None:
        ledger_path = self.root / "data/aro/bounty_receive_ledger.json"
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        rustchain = next(row for row in ledger["entries"] if row.get("bounty_key") == "github|Scottcjn/Rustchain|8295")
        rustchain["txids"] = []
        rustchain["txid"] = None
        ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
        errors = VALIDATOR.validate(
            self.root,
            now=datetime(2026, 9, 1, 14, 5, tzinfo=timezone.utc),
            report_max_age_seconds=0,
        )
        self.assertTrue(any("wallet_received without positive amount and valid transaction ids" in error for error in errors), errors)
        self.assertTrue(any("transaction evidence count is invalid" in error for error in errors), errors)

    def test_exchange_unavailability_cannot_replace_conversion_pending(self) -> None:
        ledger_path = self.root / "data/aro/bounty_receive_ledger.json"
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        rustchain = next(row for row in ledger["entries"] if row.get("bounty_key") == "github|Scottcjn/Rustchain|8289")
        rustchain["bybit_route_status"] = "blocked_bybit_unsupported_asset"
        ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
        errors = VALIDATOR.validate(
            self.root,
            now=datetime(2026, 9, 1, 14, 5, tzinfo=timezone.utc),
            report_max_age_seconds=0,
        )
        self.assertTrue(any("canonical RustChain semantics disagree" in error for error in errors), errors)

    def test_sidecar_requires_14_rtc_three_receipts_six_transactions_and_zero_settlement(self) -> None:
        sidecar_path = self.root / "data/aro/rustchain_reconciliation.json"
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        sidecar["wallet_received_total"]["transaction_count"] = 5
        sidecar["settled_total"]["amount"] = 14
        sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
        errors = VALIDATOR.validate(
            self.root,
            now=datetime(2026, 9, 1, 14, 5, tzinfo=timezone.utc),
            report_max_age_seconds=0,
        )
        self.assertTrue(any("wallet-received sidecar total disagrees" in error for error in errors), errors)
        self.assertTrue(any("incorrectly reports settlement" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
