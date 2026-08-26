#!/usr/bin/env python3
"""
Telegram Alert - Envia alertas de ganho de dinheiro (bounties, pagamentos) via Telegram.

Usa TELEGRAM_BOT_TOKEN do .env e TELEGRAM_CHAT_ID (ou detecta automaticamente).

Uso:
    from tools.telegram_alert import send_alert
    send_alert("💰 Novo bounty: $500 em repo/example", parse_mode="HTML")

CLI:
    python3 tools/telegram_alert.py --setup    # Detecta e salva chat_id
    python3 tools/telegram_alert.py --test     # Envia mensagem de teste
    python3 tools/telegram_alert.py "Mensagem" # Envia mensagem direta
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

try:
    import requests
except ImportError:
    raise ImportError("requests nao instalado. Rode: pip install requests")

ROOT = Path("/Agentic")
ENV_PATH = ROOT / ".env"
CONFIG_PATH = ROOT / ".config" / "telegram_config.json"
LOG_PATH = ROOT / "logs" / "telegram_alert.log"


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")


def _load_env() -> dict:
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except (json.JSONDecodeError, KeyError):
            pass
    return {}


def _save_config(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2))


class TelegramAlert:
    """Cliente para enviar alertas via Telegram Bot API."""

    BASE_URL = "https://api.telegram.org/bot{token}/{method}"

    def __init__(self):
        self._env = _load_env()
        self._config = _load_config()
        self._token = self._env.get("TELEGRAM_BOT_TOKEN", "")
        self._chat_id = self._env.get("TELEGRAM_CHAT_ID") or self._config.get("chat_id")

        if not self._token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN ausente no .env")

    def _api(self, method: str, **kwargs) -> dict:
        url = self.BASE_URL.format(token=self._token, method=method)
        resp = requests.post(url, json=kwargs, timeout=15)
        if resp.status_code != 200:
            err = resp.text[:300]
            _log(f"Telegram API erro {resp.status_code}: {err}")
            raise RuntimeError(f"Telegram API {resp.status_code}: {err}")
        data = resp.json()
        if not data.get("ok"):
            desc = data.get("description", "Unknown error")
            _log(f"Telegram API falhou: {desc}")
            raise RuntimeError(f"Telegram API: {desc}")
        return data.get("result", {})

    def get_updates(self, offset: int = 0, limit: int = 10) -> list[dict]:
        """Obtem atualizacoes recentes (mensagens recebidas pelo bot)."""
        result = self._api("getUpdates", offset=offset, limit=limit)
        return result if isinstance(result, list) else []

    def setup_chat_id(self) -> str:
        """Detecta chat_id a partir da ultima mensagem enviada ao bot."""
        updates = self.get_updates(limit=5)
        if not updates:
            raise RuntimeError(
                "Nenhuma mensagem encontrada. Envie /start para o bot no Telegram primeiro."
            )
        # Pega o chat_id da ultima mensagem
        last = updates[-1]
        chat = last.get("message", {}).get("chat", {}) or last.get("callback_query", {}).get("message", {}).get("chat", {})
        chat_id = chat.get("id")
        if not chat_id:
            raise RuntimeError("Nao foi possivel extrair chat_id das atualizacoes.")

        self._chat_id = str(chat_id)
        self._config["chat_id"] = self._chat_id
        _save_config(self._config)
        _log(f"Chat ID configurado: {self._chat_id}")
        return self._chat_id

    def send_message(
        self,
        text: str,
        chat_id: Optional[str] = None,
        parse_mode: Optional[str] = None,
        disable_notification: bool = False,
    ) -> dict:
        """Envia mensagem de texto."""
        target = chat_id or self._chat_id
        if not target:
            raise RuntimeError(
                "chat_id nao configurado. Rode setup_chat_id() ou defina TELEGRAM_CHAT_ID no .env"
            )
        kwargs = {"chat_id": target, "text": text}
        if parse_mode:
            kwargs["parse_mode"] = parse_mode
        if disable_notification:
            kwargs["disable_notification"] = True
        result = self._api("sendMessage", **kwargs)
        _log(f"Mensagem enviada para {target}: {text[:80]}...")
        return result

    def send_alert(
        self,
        title: str,
        body: str = "",
        amount: Optional[float] = None,
        category: str = "info",
        url: Optional[str] = None,
    ) -> dict:
        """
        Envia alerta formatado sobre ganho de dinheiro.

        Args:
            title: Titulo do alerta
            body: Descricao adicional
            amount: Valor monetario (se aplicavel)
            category: Tipo de alerta (bounty, payment, merged, info)
            url: Link relacionado (PR, issue, etc)
        """
        icons = {
            "bounty": "🎯",
            "payment": "💰",
            "merged": "✅",
            "info": "ℹ️",
            "warning": "⚠️",
        }
        icon = icons.get(category, "📢")

        lines = [f"{icon} <b>{title}</b>"]
        if amount is not None:
            lines.append(f"💵 Valor: <code>${amount:.2f}</code>")
        if body:
            lines.append(f"\n{body}")
        if url:
            lines.append(f'\n🔗 <a href="{url}">Ver detalhes</a>')

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines.append(f"\n🕐 <i>{ts}</i>")

        text = "\n".join(lines)
        return self.send_message(text, parse_mode="HTML")

    def send_bounty_alert(self, repo: str, issue: int, amount: float, title: str, pr_url: Optional[str] = None) -> dict:
        """Alerta especifico para novo bounty ou PR submetido."""
        body = f"Repo: <code>{repo}</code>\nIssue: #{issue}\nTitulo: {title}"
        return self.send_alert(
            title=f"Bounty ${amount:.0f} - {repo}",
            body=body,
            amount=amount,
            category="bounty",
            url=pr_url,
        )

    def send_payment_alert(self, source: str, amount: float, details: str = "") -> dict:
        """Alerta especifico para pagamento recebido."""
        return self.send_alert(
            title=f"Pagamento Recebido - ${amount:.2f}",
            body=f"Fonte: {source}\n{details}" if details else f"Fonte: {source}",
            amount=amount,
            category="payment",
        )

    def send_pr_merged_alert(self, repo: str, pr_number: int, bounty: Optional[float] = None) -> dict:
        """Alerta quando um PR com bounty e mergeado."""
        body = f"Repo: <code>{repo}</code>\nPR: #{pr_number}"
        return self.send_alert(
            title=f"PR Mergeado - {repo}#{pr_number}",
            body=body,
            amount=bounty,
            category="merged",
            url=f"https://github.com/{repo}/pull/{pr_number}",
        )


# Funcoes de conveniencia module-level
_client: Optional[TelegramAlert] = None


def _get_client() -> TelegramAlert:
    global _client
    if _client is None:
        _client = TelegramAlert()
    return _client


def send_alert(title: str, body: str = "", amount: Optional[float] = None, category: str = "info", url: Optional[str] = None) -> dict:
    """Envia alerta formatado."""
    return _get_client().send_alert(title, body, amount, category, url)


def send_message(text: str, parse_mode: Optional[str] = None) -> dict:
    """Envia mensagem simples."""
    return _get_client().send_message(text, parse_mode=parse_mode)


def send_bounty_alert(repo: str, issue: int, amount: float, title: str, pr_url: Optional[str] = None) -> dict:
    """Envia alerta de bounty."""
    return _get_client().send_bounty_alert(repo, issue, amount, title, pr_url)


def send_payment_alert(source: str, amount: float, details: str = "") -> dict:
    """Envia alerta de pagamento."""
    return _get_client().send_payment_alert(source, amount, details)


def setup() -> str:
    """Configura chat_id automaticamente."""
    return _get_client().setup_chat_id()


def _cli():
    import argparse
    p = argparse.ArgumentParser(description="Telegram Alert CLI")
    p.add_argument("--setup", action="store_true", help="Detectar e salvar chat_id")
    p.add_argument("--test", action="store_true", help="Enviar mensagem de teste")
    p.add_argument("message", nargs="?", help="Mensagem para enviar")
    args = p.parse_args()

    client = TelegramAlert()

    if args.setup:
        chat_id = client.setup_chat_id()
        print(f"Chat ID configurado: {chat_id}")
        client.send_message("✅ Alertas de bounty configurados com sucesso!")
    elif args.test:
        client.send_alert(
            title="Teste de Alerta",
            body="Sistema de alertas Telegram funcionando corretamente.",
            amount=42.00,
            category="info",
        )
        print("Mensagem de teste enviada.")
    elif args.message:
        client.send_message(args.message)
        print("Mensagem enviada.")
    else:
        p.print_help()


if __name__ == "__main__":
    _cli()
