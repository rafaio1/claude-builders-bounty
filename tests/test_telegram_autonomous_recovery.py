#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("telegram_bridge.py")
if not MODULE_PATH.exists():
    MODULE_PATH = Path(__file__).resolve().parents[1] / "telegram_bridge.py"
if not MODULE_PATH.exists():
    MODULE_PATH = Path("/usr/local/lib/agentic/telegram_bridge.py")
SPEC = importlib.util.spec_from_file_location("telegram_bridge_autonomous_test", MODULE_PATH)
assert SPEC and SPEC.loader
BRIDGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BRIDGE)


class TelegramAutonomousRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.saved = {
            name: getattr(BRIDGE, name)
            for name in (
                "ROOT", "STATE_FILE", "RECOVERY_OUTBOX", "EMAIL_OUTBOX", "INBOX_FILE",
                "COMMAND_LOCK_FILE", "TG_CHAT", "TG_USER", "TG_USERNAME", "send_text",
            )
        }
        BRIDGE.ROOT = self.root
        BRIDGE.STATE_FILE = self.root / "telegram-state.json"
        BRIDGE.RECOVERY_OUTBOX = self.root / "notifications.jsonl"
        BRIDGE.EMAIL_OUTBOX = self.root / "emails.jsonl"
        BRIDGE.INBOX_FILE = self.root / "commands.jsonl"
        BRIDGE.COMMAND_LOCK_FILE = self.root / "commands.lock"
        BRIDGE.TG_CHAT = "100"
        BRIDGE.TG_USER = "100"
        BRIDGE.TG_USERNAME = "rafaio1"

    def tearDown(self) -> None:
        for name, value in self.saved.items():
            setattr(BRIDGE, name, value)
        self.temp.cleanup()

    def test_only_wallet_creation_receipt_payment_receipt_and_evidence_backed_hard_block_are_sent(self) -> None:
        sent: list[str] = []
        BRIDGE.send_text = lambda message: sent.append(message) or True
        base = {
            "schema_version": 1,
            "created_at": "2026-09-01T00:00:00Z",
            "action_required": False,
            "human_action": "none",
            "informational": True,
            "autonomous_recovery": True,
            "ledger_id": "abc",
            "bounty_key": "github|example/project|1",
            "status": "submitted",
            "asset": "USD",
            "amount": 10,
            "network": None,
            "receive_address": None,
            "blockers": [],
            "recovery_steps": ["O monitor autonomo consulta a fonte publica."],
            "alert_class": "silent_pending",
            "terminal_blocked": False,
        }
        wallet_received = {
            **base,
            "ledger_id": "wallet",
            "status": "wallet_received",
            "asset": "RTC",
            "amount": 5,
            "network": "rustchain-native",
            "receive_address": "RTC-public",
            "txid": "a" * 64,
            "wallet_history_url": "https://rustchain.org/wallet/history?miner_id=RTC-public",
            "alert_class": "wallet_received",
        }
        hard_block = {
            **base,
            "ledger_id": "hard",
            "alert_class": "hard_block",
            "terminal_blocked": True,
            "blockers": [{"type": "blocked_inactive_issue", "evidence": {"source_url": "https://github.com/example/project/issues/1"}}],
        }
        wallet_recovery_ready = {
            "schema_version": 2,
            "notice_id": "b" * 64,
            "event_type": "wallet_recovery_ready",
            "alert_class": "wallet_recovery_ready",
            "created_at": "2026-09-01T00:00:00Z",
            "action_required": False,
            "human_action": "none",
            "informational": True,
            "autonomous_recovery": True,
            "terminal_blocked": False,
            "blockers": [],
            "wallet_id": "rtc_native",
            "rail_id": "rtc_native",
            "role": "client_receive_self_custody",
            "status": "inbound_monitoring",
            "asset": "RTC",
            "network": "rustchain-native",
            "receive_address": "RTC-public",
            "receive_ready": True,
            "recovery_status": "verified_encrypted_server_local",
            "recovery_bundle_fingerprint": "c" * 64,
            "recovery_instructions": ["restaurar localmente", "rederivar endereco", "retomar monitor"],
            "delivery_channels": ["telegram", "email"],
            "delivery_policy": "required_idempotent",
        }
        route_options_pending = {
            **wallet_recovery_ready,
            "notice_id": "d" * 64,
            "event_type": "route_options_pending",
            "alert_class": "route_options_pending",
            "status": "route_pending",
            "route_status": "route_pending",
            "never_rejects_bounty": True,
            "reason_codes": ["route_not_end_to_end_verified", "exchange_destination_unverified", "wise_offramp_unverified"],
            "route_options": [{
                "option_id": "verified-route-candidate",
                "stages": ["self_custody", "swap", "exchange", "fiat", "Wise"],
                "evidence_required": ["official_support"],
                "cost_inputs_required": ["all_fees"],
                "risks": ["liquidity"],
            }],
            "evidence": {"status": "not_end_to_end_verified", "wallet_registry_fingerprint": "e" * 64, "wallet_audit_fingerprint": "f" * 64},
            "execution_enabled": False,
            "execution_policy": "automatic_only_after_all_technical_legal_destination_asset_network_and_fee_gates",
            "settlement_policy": "never_before_wise_confirmation_and_reconciliation",
        }
        rows = [base, wallet_recovery_ready, route_options_pending, wallet_received, hard_block, {**base, "ledger_id": "old", "action_required": True}]
        BRIDGE.RECOVERY_OUTBOX.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        state = {"seen_notifications": []}
        BRIDGE.scan_recovery(state)
        self.assertEqual(len(sent), 4)
        self.assertIn("CARTEIRA AUTOCUSTODIA E RECUPERACAO PRONTAS", sent[0])
        self.assertIn("ROTA AUTONOMA ATE WISE AINDA PENDENTE", sent[1])
        self.assertIn("RECEBIMENTO EM CARTEIRA AUTOCUSTODIA CONFIRMADO", sent[2])
        self.assertIn("TRAVA REAL DE BOUNTY", sent[3])
        self.assertTrue(all("Acao humana: nenhuma" in item for item in sent))
        self.assertEqual(len(state["seen_notifications"]), 4)
        self.assertEqual(len(state["suppressed_notifications"]), 2)
        emails = [json.loads(line) for line in BRIDGE.EMAIL_OUTBOX.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(emails), 4)
        self.assertTrue(all("Acao humana: nenhuma" in item["body"] for item in emails))

    def test_allowlisted_policy_commands_are_authorized_processed_and_acked_idempotently(self) -> None:
        rows = [
            {
                "correlation_id": "first",
                "update_id": 869013124,
                "message_id": 1779,
                "chat_id": "100",
                "sender_id": "100",
                "sender_username": "rafaio1",
                "processed": False,
                "execution_authorized": False,
            },
            {
                "correlation_id": "untrusted",
                "update_id": 869013125,
                "message_id": 1781,
                "chat_id": "999",
                "sender_id": "999",
                "sender_username": "attacker",
                "processed": False,
                "execution_authorized": True,
            },
        ]
        BRIDGE.INBOX_FILE.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        pending = BRIDGE.reconcile_policy_commands()
        self.assertEqual(pending, ["first"])
        updated = [json.loads(line) for line in BRIDGE.INBOX_FILE.read_text(encoding="utf-8").splitlines()]
        self.assertTrue(updated[0]["execution_authorized"])
        self.assertTrue(updated[0]["processed"])
        self.assertEqual(updated[0]["processing_result"], "autonomous_recovery_policy_applied")
        self.assertFalse(updated[1]["execution_authorized"])
        self.assertFalse(updated[1]["processed"])
        BRIDGE.mark_policy_acknowledged(pending)
        self.assertEqual(BRIDGE.reconcile_policy_commands(), [])

    def test_rule_v5_declares_route_recovery_receipt_payment_hard_block_and_command_channels(self) -> None:
        rule_path = Path(__file__).with_name("telegram_gate_rule.json")
        if not rule_path.exists():
            rule_path = Path(__file__).resolve().parents[1] / "telegram_gate_rule.json"
        if not rule_path.exists():
            rule_path = Path("/Agentic/state/telegram_gate_rule.json")
        if not rule_path.exists():
            self.skipTest("production policy is only present on the server")
        rule = json.loads(rule_path.read_text(encoding="utf-8"))
        self.assertEqual(rule["version"], 5)
        recovery = rule["channels"]["wallet_recovery_ready"]
        self.assertEqual(recovery["delivery_channels"], ["telegram", "email"])
        self.assertTrue(recovery["forbids_custody_credentials_or_encrypted_payload"])
        self.assertTrue(recovery["deduplicated_by_stable_notice_id"])
        route = rule["channels"]["route_options_pending"]
        self.assertTrue(route["requires_evidence_cost_and_risk_fields"])
        self.assertTrue(route["never_rejects_eligible_bounty"])
        self.assertTrue(route["never_implies_settlement"])
        received = rule["channels"]["wallet_received"]
        self.assertIs(received["action_required"], False)
        self.assertEqual(received["human_action"], "none")
        self.assertTrue(received["requires_transaction_id"])
        hard_block = rule["channels"]["hard_block"]
        self.assertTrue(hard_block["requires_terminal_blocked"])
        self.assertIn("bybit_asset_unsupported", hard_block["excluded_reasons"])
        commands = rule["channels"]["commands"]
        self.assertEqual(commands["authorization"], "exact_chat_sender_and_username_allowlist")
        self.assertEqual(rule["fail_mode"], "closed")


if __name__ == "__main__":
    unittest.main()
