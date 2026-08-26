#!/usr/bin/env python3
"""
Telegram Alert Bot para notificações de ganho de dinheiro.
Lê notificações do orquestrador de bounties e envia via Telegram.

Configuração:
  - Defina TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID no .env ou variáveis de ambiente
  - Rode manualmente ou via cron após o bounty_orchestrator.py

Uso:
  python3 /Agentic/scripts/telegram_alerts.py [--test]
"""
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

NOTIFICATIONS_PATH = Path("/Agentic/logs/bounty/notifications.json")
SENT_LOG_PATH = Path("/Agentic/logs/bounty/telegram_sent.json")
ENV_PATH = Path("/Agentic/.env")


def load_env():
    """Carrega variáveis do .env sem sobrescrever env vars existentes."""
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def get_telegram_config():
    """Retorna (bot_token, chat_id) ou (None, None) se não configurado."""
    load_env()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return None, None
    return token, chat_id


def send_telegram_message(token: str, chat_id: str, text: str) -> bool:
    """Envia mensagem via Telegram Bot API. Retorna True se sucesso."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                return True
            print(f"[WARN] Telegram API retornou ok=false: {result}")
            return False
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[ERROR] Telegram HTTP {e.code}: {body}")
        return False
    except Exception as e:
        print(f"[ERROR] Falha ao enviar Telegram: {e}")
        return False


def load_notifications():
    """Carrega notificações pendentes."""
    if not NOTIFICATIONS_PATH.exists():
        return []
    with open(NOTIFICATIONS_PATH, "r") as f:
        return json.load(f)


def load_sent_log():
    """Carrega IDs de notificações já enviadas."""
    if not SENT_LOG_PATH.exists():
        return set()
    with open(SENT_LOG_PATH, "r") as f:
        data = json.load(f)
    return set(data.get("sent_keys", []))


def save_sent_log(sent_keys: set):
    """Persiste IDs de notificações enviadas."""
    SENT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SENT_LOG_PATH, "w") as f:
        json.dump({"sent_keys": sorted(sent_keys)}, f, indent=2)


def notification_key(n: dict) -> str:
    """Gera chave única para deduplicação."""
    return f"{n.get('type','')}:{n.get('repo','')}:{n.get('issue','')}:{n.get('timestamp','')}"


def format_bounty_merged(n: dict) -> str:
    """Formata notificação de merge para Telegram."""
    usd = n.get("estimated_bounty_usd", 0)
    return (
        f"✅ *BOUNTY MERGED!*\n\n"
        f"📦 `{n.get('repo', '')}` #{n.get('issue', '')}\n"
        f"💰 *${usd}* estimado\n"
        f"🔗 [PR]({n.get('pr_url', '')})\n\n"
        f"_Aguardando pagamento..._"
    )


def format_bounty_rejected(n: dict) -> str:
    """Formata notificação de rejeição para Telegram."""
    return (
        f"❌ *Bounty Rejeitado*\n\n"
        f"📦 `{n.get('repo', '')}` #{n.get('issue', '')}\n"
        f"🔗 [PR]({n.get('pr_url', '')})\n\n"
        f"_PR fechado sem merge._"
    )


def format_summary(notifications: list) -> str:
    """Formata resumo consolidado quando há múltiplas notificações."""
    merged = [n for n in notifications if n.get("type") == "bounty_merged"]
    rejected = [n for n in notifications if n.get("type") == "bounty_rejected"]
    total_usd = sum(n.get("estimated_bounty_usd", 0) for n in merged)

    lines = [f"📬 *Resumo de Bounties* ({len(notifications)} novas)\n"]

    if merged:
        lines.append(f"✅ *{len(merged)} merge(s)* — ${total_usd} estimado:")
        for n in merged[:5]:
            lines.append(f"  • `{n['repo']}#{n['issue']}` — ${n.get('estimated_bounty_usd', 0)}")
        if len(merged) > 5:
            lines.append(f"  ... e mais {len(merged) - 5}")
        lines.append("")

    if rejected:
        lines.append(f"❌ *{len(rejected)} rejeitado(s)*:")
        for n in rejected[:3]:
            lines.append(f"  • `{n['repo']}#{n['issue']}`")
        if len(rejected) > 3:
            lines.append(f"  ... e mais {len(rejected) - 3}")

    return "\n".join(lines)


def main():
    test_mode = "--test" in sys.argv

    token, chat_id = get_telegram_config()
    if not token or not chat_id:
        print("[WARN] TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID não configurados.")
        print("       Adicione ao /Agentic/.env ou exporte como variáveis de ambiente.")
        print("       Exemplo:")
        print("         TELEGRAM_BOT_TOKEN=123456:ABC-DEF")
        print("         TELEGRAM_CHAT_ID=-1001234567890")
        if test_mode:
            print("\n[TEST] Enviando mensagem de teste com config mock...")
            print("[SKIP] Sem credenciais reais, pulando envio.")
        return

    if test_mode:
        print("[TEST] Enviando mensagem de teste...")
        ok = send_telegram_message(token, chat_id, "🤖 *Bot de Bounties Online*\n\n_Conectado e pronto para alertas._")
        print(f"[TEST] Resultado: {'OK' if ok else 'FALHA'}")
        return

    # Carregar notificações e log de enviados
    notifications = load_notifications()
    sent_keys = load_sent_log()

    # Filtrar apenas não-enviadas
    pending = [n for n in notifications if notification_key(n) not in sent_keys]

    if not pending:
        print("Nenhuma notificação pendente para enviar.")
        return

    print(f"Enviando {len(pending)} notificação(ões)...")

    # Se muitas notificações, enviar resumo primeiro
    if len(pending) >= 5:
        summary = format_summary(pending)
        if send_telegram_message(token, chat_id, summary):
            print("  ✅ Resumo enviado")
        else:
            print("  ❌ Falha ao enviar resumo")

    # Enviar individuais (limitar a 10 por execução para evitar rate limit)
    sent_count = 0
    for n in pending[:10]:
        key = notification_key(n)
        ntype = n.get("type", "")

        if ntype == "bounty_merged":
            msg = format_bounty_merged(n)
        elif ntype == "bounty_rejected":
            msg = format_bounty_rejected(n)
        else:
            msg = f"📢 {n.get('message', json.dumps(n, ensure_ascii=False))}"

        if send_telegram_message(token, chat_id, msg):
            sent_keys.add(key)
            sent_count += 1
            print(f"  ✅ {ntype}: {n.get('repo','')}#{n.get('issue','')}")
        else:
            print(f"  ❌ {ntype}: {n.get('repo','')}#{n.get('issue','')}")

    save_sent_log(sent_keys)
    print(f"\nEnviadas: {sent_count}/{len(pending)}")


if __name__ == "__main__":
    main()
