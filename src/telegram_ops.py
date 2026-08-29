"""
Telegram Ops - Bidirectional task notifications with full access.
Complements telegram_gate.py (financial-only) with operational messaging.
"""
import json
import os
import time
import hashlib
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, Callable

try:
    import requests
except ImportError:
    requests = None

ROOT = Path("/Agentic")
LOG_FILE = ROOT / "logs" / "telegram_ops.log"
STATE_FILE = ROOT / "data" / "telegram_ops_state.json"
ENV_PATH = ROOT / ".env"

# Full access: no event type restrictions for ops channel
POLL_INTERVAL_SEC = 30


def _log(msg: str, level: str = "INFO") -> None:
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] [{level}] TG_OPS: {msg}"
    print(line, flush=True)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _load_env() -> dict:
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def _get_credentials() -> tuple:
    env = _load_env()
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    return token, chat_id


def send_message(text: str, parse_mode: str = "HTML", silent: bool = False) -> bool:
    """Send arbitrary message to configured Telegram chat. Full access - no filtering."""
    token, chat_id = _get_credentials()
    if not token or not chat_id:
        _log("BLOCKED: Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID", "ERROR")
        return False

    if requests is None:
        _log("requests library not available", "ERROR")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
        "disable_notification": silent,
    }

    for attempt in range(3):
        try:
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code == 200 and resp.json().get("ok"):
                _log(f"SENT: {text[:80]}...")
                return True
            elif resp.status_code == 429:
                retry_after = resp.json().get("parameters", {}).get("retry_after", 30)
                _log(f"Rate limited, waiting {retry_after}s", "WARN")
                time.sleep(retry_after)
                continue
            else:
                _log(f"HTTP {resp.status_code}: {resp.text[:200]}", "WARN")
        except Exception as e:
            _log(f"Request error (attempt {attempt+1}): {e}", "WARN")

        if attempt < 2:
            time.sleep((2 ** attempt) * 1.0)

    return False


def notify_task_complete(session_id: str, summary: str, status: str = "done") -> bool:
    """Notify that a Codex session/task has completed."""
    msg_lines = [
        "<b>✅ TAREFA CONCLUÍDA</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━",
        f"<b>Sessão:</b> <code>{session_id}</code>",
        f"<b>Status:</b> {status}",
        f"<b>Hora:</b> <i>{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</i>",
        "",
        f"{summary}",
        "",
        "<i>Responda a esta mensagem para enviar comandos ao agente.</i>",
        "━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    return send_message("\n".join(msg_lines))


def get_updates(offset: Optional[int] = None, limit: int = 20, timeout: int = 0) -> list:
    """Fetch incoming messages from Telegram. Returns list of update objects."""
    token, chat_id = _get_credentials()
    if not token:
        return []

    if requests is None:
        return []

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    params = {"timeout": timeout, "limit": limit}
    if offset is not None:
        params["offset"] = offset

    try:
        resp = requests.get(url, params=params, timeout=timeout + 10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("ok"):
                updates = []
                for u in data.get("result", []):
                    msg = u.get("message", {})
                    if str(msg.get("chat", {}).get("id")) == str(chat_id):
                        updates.append(u)
                return updates
    except Exception as e:
        _log(f"getUpdates error: {e}", "WARN")

    return []


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"last_update_id": 0, "pending_commands": []}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def poll_and_dispatch(handler: Optional[Callable[[str], None]] = None) -> list:
    """
    Poll for new messages and dispatch to handler.
    Returns list of new command texts received.
    Handler receives the raw text of each new message.
    """
    state = load_state()
    offset = state.get("last_update_id", 0) + 1 if state.get("last_update_id") else None

    updates = get_updates(offset=offset)
    new_commands = []

    for u in updates:
        update_id = u.get("update_id", 0)
        msg = u.get("message", {})
        text = msg.get("text", "").strip()

        if text:
            _log(f"RECV: {text[:100]}")
            new_commands.append(text)
            if handler:
                try:
                    handler(text)
                except Exception as e:
                    _log(f"Handler error: {e}", "ERROR")

        state["last_update_id"] = max(state.get("last_update_id", 0), update_id)

    save_state(state)
    return new_commands


def start_listener(handler: Optional[Callable[[str], None]] = None, daemon: bool = True) -> threading.Thread:
    """Start background polling thread for incoming Telegram commands."""
    def _loop():
        _log("Listener started")
        while True:
            try:
                poll_and_dispatch(handler)
            except Exception as e:
                _log(f"Poll loop error: {e}", "ERROR")
            time.sleep(POLL_INTERVAL_SEC)

    t = threading.Thread(target=_loop, daemon=daemon, name="tg-ops-listener")
    t.start()
    return t
