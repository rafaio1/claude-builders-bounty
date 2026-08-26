#!/usr/bin/env python3
"""
Orquestrador de Bounties: checagem + expurgo + notificação consolidada.
Projetado para rodar via cron ou manualmente.
Uso: python3 /Agentic/scripts/bounty_orchestrator.py [--notify]
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

NOTIFICATIONS_PATH = Path("/Agentic/logs/bounty/notifications.json")
STATE_PATH = Path("/Agentic/state/orchestrator.json")
CLEANUP_SCRIPT = Path("/Agentic/scripts/cleanup_workspace.sh")
PAYOUT_SCRIPT = Path("/Agentic/scripts/check_bounty_payouts.py")


def load_state():
    if STATE_PATH.exists():
        with open(STATE_PATH, "r") as f:
            return json.load(f)
    return {"last_run": None, "total_notifications_sent": 0}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def run_cleanup():
    """Executa rotina de expurgo."""
    if not CLEANUP_SCRIPT.exists():
        print("[WARN] cleanup_workspace.sh não encontrado, pulando expurgo.")
        return False
    try:
        result = subprocess.run(
            ["bash", str(CLEANUP_SCRIPT)],
            capture_output=True, text=True, timeout=120
        )
        print(result.stdout)
        if result.returncode != 0:
            print(f"[WARN] Expurgo retornou código {result.returncode}")
            print(result.stderr)
        return True
    except Exception as e:
        print(f"[ERROR] Falha no expurgo: {e}")
        return False


def run_payout_check():
    """Executa checagem de bounties pagos."""
    if not PAYOUT_SCRIPT.exists():
        print("[WARN] check_bounty_payouts.py não encontrado.")
        return False
    try:
        result = subprocess.run(
            [sys.executable, str(PAYOUT_SCRIPT)],
            capture_output=True, text=True, timeout=120
        )
        print(result.stdout)
        if result.returncode != 0:
            print(f"[WARN] Checagem retornou código {result.returncode}")
            print(result.stderr)
        return True
    except Exception as e:
        print(f"[ERROR] Falha na checagem: {e}")
        return False


def get_pending_notifications():
    """Retorna notificações não lidas."""
    if not NOTIFICATIONS_PATH.exists():
        return []
    with open(NOTIFICATIONS_PATH, "r") as f:
        return json.load(f)


def format_notification_summary(notifications):
    """Formata resumo legível das notificações."""
    if not notifications:
        return "Nenhuma notificação pendente."

    lines = [f"📬 {len(notifications)} notificação(ões) pendente(s):\n"]
    merged = [n for n in notifications if n.get("type") == "bounty_merged"]
    rejected = [n for n in notifications if n.get("type") == "bounty_rejected"]

    if merged:
        total_usd = sum(n.get("estimated_bounty_usd", 0) for n in merged)
        lines.append(f"✅ MERGES ({len(merged)}):")
        for n in merged:
            lines.append(f"   • {n['repo']}#{n['issue']} — ${n.get('estimated_bounty_usd', 0)}")
            lines.append(f"     {n['pr_url']}")
        lines.append(f"   Total estimado: ${total_usd}\n")

    if rejected:
        lines.append(f"❌ REJEITADOS ({len(rejected)}):")
        for n in rejected:
            lines.append(f"   • {n['repo']}#{n['issue']}")
            lines.append(f"     {n['pr_url']}\n")

    return "\n".join(lines)


def main():
    notify_mode = "--notify" in sys.argv
    state = load_state()

    print(f"=== ORQUESTRADOR DE BOUNTIES ===")
    print(f"Iniciado: {datetime.now(timezone.utc).isoformat()}")
    print(f"Última execução: {state.get('last_run', 'nunca')}\n")

    # Passo 1: Expurgo
    print("--- [1/3] EXPURGO ---")
    run_cleanup()

    # Passo 2: Checagem de pagamentos
    print("\n--- [2/3] CHECAGEM DE PAGAMENTOS ---")
    run_payout_check()

    # Passo 3: Notificações
    print("\n--- [3/3] NOTIFICAÇÕES ---")
    notifications = get_pending_notifications()
    summary = format_notification_summary(notifications)
    print(summary)

    # Atualizar estado
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    state["total_notifications_sent"] += len(notifications)
    save_state(state)

    # Se --notify, escrever arquivo de alerta para o agente ler
    if notify_mode and notifications:
        alert_path = Path("/Agentic/logs/bounty/alert.txt")
        alert_path.parent.mkdir(parents=True, exist_ok=True)
        with open(alert_path, "w") as f:
            f.write(f"ALERT: {len(notifications)} bounty notification(s) at {state['last_run']}\n")
            f.write(summary)
        print(f"\n⚠️  Alerta escrito em {alert_path}")

    print(f"\n=== ORQUESTRADOR CONCLUÍDO ===")


if __name__ == "__main__":
    main()
