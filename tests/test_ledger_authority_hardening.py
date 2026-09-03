#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


HERE = Path(__file__).resolve().parent


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GATE_PATH = HERE / "agentic_ledger_proposal_gate.py"
VALIDATOR_PATH = HERE / "validate_financial_ledgers_semantic.py"
if not GATE_PATH.exists():
    GATE_PATH = Path("/usr/local/lib/agentic/agentic_ledger_proposal_gate.py")
if not VALIDATOR_PATH.exists():
    VALIDATOR_PATH = Path("/usr/local/lib/agentic/validate_financial_ledgers.py")

GATE = load_module("ledger_gate_hardening", GATE_PATH)
VALIDATOR = load_module("ledger_validator_hardening", VALIDATOR_PATH)


class LedgerAuthorityHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "Agentic"
        self.base = self.root / "data/aro"
        self.proposals = self.base / "proposals"
        self.authority = Path(self.temp.name) / "var/lib/agentic/ledger-authority"
        self.proposals.mkdir(parents=True)
        self.authority.mkdir(parents=True)
        self.ledger = self.base / "bounty_receive_ledger.json"
        self.realized = self.base / "realized_revenue_ledger.jsonl"
        self.original = (json.dumps({"schema_version": "1.0", "ledger_id": "test", "entries": []}, indent=2) + "\n").encode()
        self.ledger.write_bytes(self.original)
        self.realized.write_bytes(b"")
        self.environment = patch.dict(os.environ, {"AGENTIC_LEDGER_AUTHORITY_DIR": str(self.authority)})
        self.environment.start()

    def tearDown(self) -> None:
        self.environment.stop()
        self.temp.cleanup()

    def test_decoy_authority_in_writable_ingress_cannot_replace_secure_authority(self) -> None:
        GATE.snapshot(self.root, "test-bootstrap")
        malicious = b'{"schema_version":"1.0","entries":[{"status":"settled"}]}\n'
        self.ledger.write_bytes(malicious)

        # Simulate the old weakness: attacker changes canonical plus a matching
        # snapshot and manifest under the proposals ingress.  The hardened gate
        # must ignore all three decoys and restore from the external authority.
        (self.proposals / "authoritative_bounty_receive_ledger.json").write_bytes(malicious)
        (self.proposals / "authoritative_realized_revenue_ledger.jsonl").write_bytes(b"")
        (self.proposals / "authoritative_manifest.json").write_text(
            json.dumps(
                {
                    "bounty_receive_ledger_sha256": GATE.sha256_bytes(malicious),
                    "realized_revenue_ledger_sha256": GATE.sha256_bytes(b""),
                }
            ),
            encoding="utf-8",
        )

        incidents = GATE.restore_unauthorized_mutations(self.root)
        self.assertEqual(len(incidents), 1)
        self.assertEqual(self.ledger.read_bytes(), self.original)
        self.assertEqual(GATE.paths(self.root)["manifest"].parent, self.authority)

    def test_validator_checks_snapshot_bytes_not_only_manifest(self) -> None:
        GATE.snapshot(self.root, "test-bootstrap")
        (self.authority / "authoritative_bounty_receive_ledger.json").write_bytes(b"tampered\n")
        errors = VALIDATOR.validate_authoritative_manifest(self.root, self.ledger, self.realized)
        self.assertTrue(any("snapshot hash disagrees" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
