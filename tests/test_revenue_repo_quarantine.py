"""Tests for durable fail-closed repository quarantine."""

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import build_pr_revenue_queue as queue_builder
from revenue_repo_quarantine import BLOCKED_SIGNALS, quarantine_pr


@pytest.mark.parametrize(
    "repo,number",
    [
        ("claude-builders-bounty/claude-builders-bounty", 3873),
        ("ClankerNation/OpenAgents", 5687),
        ("clankernation/openagents", 6120),
    ],
)
def test_quarantine_overrides_nominal_bounty_and_pr_signals(repo, number):
    record = quarantine_pr(
        {
            "repo": repo,
            "number": number,
            "url": f"https://github.com/{repo}/pull/{number}",
            "title": "nominal bounty attempt",
            "state": "OPEN",
            "mergedAt": None,
            "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN",
            "labels": ["bounty", "$9300"],
            "comments": ["/attempt", "/claim"],
            "author": "rafaio1",
        }
    )

    assert record is not None
    assert record["tier"] is None
    assert record["action"] == "quarantine_repository"
    assert record["monetizable"] is False
    assert record["monetizable_usd"] == 0.0
    assert record["receivable_confirmed"] is False
    assert set(record["blocked_signals"]) == set(BLOCKED_SIGNALS)
    assert record["reason"].startswith("repo_quarantined_zero_merged_")


def test_unlisted_repository_is_not_quarantined():
    assert quarantine_pr({"repo": "healthy/repo", "number": 1}) is None


def test_build_queue_preserves_quarantine_records_but_excludes_tiers(tmp_path, monkeypatch):
    repo = "claude-builders-bounty/claude-builders-bounty"
    key = f"{repo}#3873"
    inventory_path = tmp_path / "inventory.json"
    ledger_path = tmp_path / "ledger.json"
    payment_path = tmp_path / "payment.json"
    output_path = tmp_path / "queue.json"

    inventory_path.write_text(
        json.dumps(
            {
                "prs": {
                    key: {
                        "repo": repo,
                        "number": 3873,
                        "url": f"https://github.com/{repo}/pull/3873",
                        "title": "nominal bounty",
                        "state": "OPEN",
                        "mergedAt": None,
                        "author": "rafaio1",
                        "reviews_count": 4,
                        "ci_state": "SUCCESS",
                        "related_email_id": "attempt-email",
                    }
                }
            }
        )
    )
    ledger_path.write_text(
        json.dumps(
            {
                key: {
                    "value": 9300,
                    "currency": "USD",
                    "claim_status": "CLAIM_PENDING",
                    "payout_status": "PAYMENT_PENDING",
                    "claim_url": f"https://github.com/{repo}/issues/1",
                }
            }
        )
    )
    payment_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "pr_url": f"https://github.com/{repo}/pull/3873",
                        "amount": 9300,
                    }
                ]
            }
        )
    )

    monkeypatch.setattr(queue_builder, "INVENTORY_PATH", inventory_path)
    monkeypatch.setattr(queue_builder, "LEDGER_PATH", ledger_path)
    monkeypatch.setattr(queue_builder, "QUEUE_PATH", payment_path)
    monkeypatch.setattr(queue_builder, "OUTPUT_PATH", output_path)

    assert queue_builder.build_queue() == 0
    output = json.loads(output_path.read_text())

    assert output["tiers"] == {"A": [], "B": [], "C": []}
    assert output["metrics"]["quarantined"] == 1
    assert output["quarantine"]["count"] == 1
    assert output["quarantine"]["monetizable_usd"] == 0.0
    assert output["quarantine"]["items"][0]["key"] == key
    assert output["quarantine"]["items"][0]["monetizable_usd"] == 0.0
