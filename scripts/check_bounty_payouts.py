#!/usr/bin/env python3
"""
Rotina de checagem de bounties pagos.
Verifica status dos PRs submetidos e detecta merges/pagamentos.
Notifica via arquivo de notificações para orquestramento.
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

LEDGER_PATH = Path("/Agentic/logs/bounty/ledger.json")
NOTIFICATIONS_PATH = Path("/Agentic/logs/bounty/notifications.json")
PAID_LOG_PATH = Path("/Agentic/logs/bounty/paid.json")


def load_ledger():
    with open(LEDGER_PATH, "r") as f:
        return json.load(f)


def save_notifications(notifications):
    NOTIFICATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if NOTIFICATIONS_PATH.exists():
        with open(NOTIFICATIONS_PATH, "r") as f:
            existing = json.load(f)
    existing.extend(notifications)
    with open(NOTIFICATIONS_PATH, "w") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)


def log_paid(entry):
    PAID_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    paid = []
    if PAID_LOG_PATH.exists():
        with open(PAID_LOG_PATH, "r") as f:
            paid = json.load(f)
    paid.append(entry)
    with open(PAID_LOG_PATH, "w") as f:
        json.dump(paid, f, indent=2, ensure_ascii=False)


def check_pr_status(repo, pr_number):
    """Retorna 'merged', 'open', 'closed' ou 'error'."""
    try:
        result = subprocess.run(
            ["gh", "pr", "view", str(pr_number), "--repo", repo, "--json", "state,mergedAt"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return "error"
        data = json.loads(result.stdout)
        if data.get("mergedAt"):
            return "merged"
        return data.get("state", "unknown").lower()
    except Exception:
        return "error"


def main():
    ledger = load_ledger()
    notifications = []
    updated_count = 0
    merged_count = 0

    for bounty in ledger.get("bounties", []):
        if bounty.get("status") in ("paid", "rejected"):
            continue

        pr_url = bounty.get("pr_url", "")
        if not pr_url:
            continue

        # Extrair número do PR da URL
        parts = pr_url.rstrip("/").split("/")
        if len(parts) < 2:
            continue
        try:
            pr_number = int(parts[-1])
        except ValueError:
            continue

        repo = bounty.get("repo", "")
        status = check_pr_status(repo, pr_number)

        if status == "merged" and bounty.get("status") != "merged":
            bounty["status"] = "merged"
            bounty["merged_at"] = datetime.now(timezone.utc).isoformat()
            updated_count += 1
            merged_count += 1

            notification = {
                "type": "bounty_merged",
                "repo": repo,
                "issue": bounty.get("issue"),
                "pr_url": pr_url,
                "title": bounty.get("title", ""),
                "estimated_bounty_usd": bounty.get("estimated_bounty_usd", 0),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": f"PR #{pr_number} MERGED em {repo}! Bounty estimado: ${bounty.get('estimated_bounty_usd', 0)}"
            }
            notifications.append(notification)
            print(f"[MERGED] {repo}#{bounty.get('issue')} PR#{pr_number} — ${bounty.get('estimated_bounty_usd', 0)}")

        elif status == "closed" and bounty.get("status") not in ("closed", "rejected"):
            bounty["status"] = "rejected"
            updated_count += 1
            notification = {
                "type": "bounty_rejected",
                "repo": repo,
                "issue": bounty.get("issue"),
                "pr_url": pr_url,
                "title": bounty.get("title", ""),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": f"PR #{pr_number} FECHADO sem merge em {repo}. Bounty rejeitado."
            }
            notifications.append(notification)
            print(f"[REJECTED] {repo}#{bounty.get('issue')} PR#{pr_number}")

    # Salvar ledger atualizado
    if updated_count > 0:
        with open(LEDGER_PATH, "w") as f:
            json.dump(ledger, f, indent=2, ensure_ascii=False)

    # Salvar notificações
    if notifications:
        save_notifications(notifications)

    # Resumo
    total_pending = sum(b.get("estimated_bounty_usd", 0) for b in ledger.get("bounties", []) if b.get("status") == "pr_submitted")
    total_merged = sum(b.get("estimated_bounty_usd", 0) for b in ledger.get("bounties", []) if b.get("status") == "merged")
    total_entries = len(ledger.get("bounties", []))

    print(f"\n=== RESUMO DA CHECAGEM ===")
    print(f"Total de bounties: {total_entries}")
    print(f"Merges detectados nesta rodada: {merged_count}")
    print(f"Pendente (pr_submitted): ${total_pending}")
    print(f"Merged (aguardando pagamento): ${total_merged}")
    print(f"Notificações geradas: {len(notifications)}")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")


if __name__ == "__main__":
    main()
