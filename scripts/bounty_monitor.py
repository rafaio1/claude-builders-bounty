#!/usr/bin/env python3
"""
Bounty Monitor - Notifica SOMENTE payout confirmado e reconciliado via gate central
Gate fail-closed: apenas eventos financeiros realizados com evidencia externa
"""
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Garante import do gate central
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from telegram_gate import notify_payout_received  # noqa: E402

REPO_ROOT = Path("/Agentic")
LEDGER_PATH = REPO_ROOT / "logs/bounty/ledger.json"


def check_pr_status(repo, pr_number):
    """Check if PR is merged via gh cli"""
    try:
        result = subprocess.run(
            ["gh", "pr", "view", str(pr_number), "--repo", repo, "--json", "state,mergedAt,url"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception as e:
        print(f"GH error for {repo}#{pr_number}: {e}", file=sys.stderr)
    return None


def _make_event_id(entry: dict, pr_num: str) -> str:
    """Gera event_id deterministico para deduplicacao no gate."""
    raw = f"bounty_payout|{entry.get('repo','')}|{pr_num}|{entry.get('merged_at','')}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def main():
    if not LEDGER_PATH.exists():
        print("Ledger not found")
        sys.exit(1)

    data = json.loads(LEDGER_PATH.read_text())
    entries = data.get("entries", [])
    updated = False

    for entry in entries:
        if entry.get("status") != "pr_submitted":
            continue

        pr_url = entry.get("pr_url", "")
        if not pr_url or "/pull/" not in pr_url:
            continue

        repo = entry.get("repo", "")
        pr_num = pr_url.rstrip("/").split("/")[-1]

        pr_info = check_pr_status(repo, pr_num)
        if not pr_info:
            continue

        state = pr_info.get("state", "").upper()
        merged_at = pr_info.get("mergedAt")

        # APENAS payout confirmado e reconciliado passa pelo gate
        # MERGED sem payout confirmado eh silenciosamente ignorado
        payout_confirmed = entry.get("payout_confirmed") is True
        reconciliation = entry.get("reconciliation_status", "").lower()
        net_amount = float(entry.get("net_payout_usd", 0) or 0)

        if state == "MERGED" and merged_at and payout_confirmed and reconciliation == "confirmed" and net_amount > 0:
            entry["status"] = "merged"
            entry["merged_at"] = merged_at
            updated = True

            event_id = _make_event_id(entry, pr_num)
            gross = float(entry.get("gross_payout_usd", net_amount) or net_amount)
            fees = gross - net_amount

            result = notify_payout_received(
                process_id=f"bounty:{repo}:{pr_num}",
                event_id=event_id,
                source="bounty_monitor",
                external_reference=pr_url,
                occurred_at=merged_at,
                asset="USD",
                gross=gross,
                fees=fees,
                net=net_amount,
                currency="USD",
                reconciliation_status="confirmed",
            )
            print(f"PAYOUT_SENT: {repo}#{pr_num} net=${net_amount} gate={result}")
        else:
            # Atualiza status de merged/rejected SEM enviar Telegram
            if state == "MERGED" and merged_at:
                entry["status"] = "merged"
                entry["merged_at"] = merged_at
                updated = True
                print(f"MERGED_NO_PAYOUT: {repo}#{pr_num} (aguardando confirmacao)")
            elif state == "CLOSED" and not merged_at:
                entry["status"] = "closed_rejected"
                entry["closed_at"] = datetime.now(timezone.utc).isoformat()
                updated = True
                print(f"CLOSED: {repo}#{pr_num} (nao notificado)")

    if updated:
        data["entries"] = entries
        LEDGER_PATH.write_text(json.dumps(data, indent=2))
        print("Ledger updated")


if __name__ == "__main__":
    main()
