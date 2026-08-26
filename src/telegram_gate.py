"""
Central Telegram Financial Gate - Fail-Closed

ONLY allows sending messages for confirmed, reconciled financial events.
Blocks all heartbeats, scans, opportunities, paper trades, and potential revenue.
"""
import json
import os
import time
import random
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

try:
    import requests
except ImportError:
    requests = None

ROOT = Path("/Agentic")
DEDUP_FILE = ROOT / "logs" / "telegram_gate_dedup.json"
LOG_FILE = ROOT / "logs" / "telegram_gate.log"
CONFIG_PATH = ROOT / ".config" / "telegram_config.json"
ENV_PATH = ROOT / ".env"

# Strict allowlist of event types
ALLOWED_EVENT_TYPES = {
    "payout_received",
    "trade_realized",
    "transfer_confirmed"
}

REQUIRED_FIELDS = [
    "event_id", "process_id", "event_type", "source", 
    "external_reference", "occurred_at", "asset", 
    "gross", "fees", "net", "currency", "reconciliation_status"
]

def _log(msg: str, level: str = "INFO") -> None:
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] [{level}] TG_GATE: {msg}"
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

def _load_dedup() -> set:
    if DEDUP_FILE.exists():
        try:
            data = json.loads(DEDUP_FILE.read_text())
            return set(data.get("seen_ids", []))
        except Exception:
            pass
    return set()

def _save_dedup(seen_ids: set) -> None:
    DEDUP_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Keep only last 10000 IDs to prevent unbounded growth
    trimmed = sorted(list(seen_ids))[-10000:]
    DEDUP_FILE.write_text(json.dumps({"seen_ids": trimmed}, indent=2))

def _get_token_and_chat() -> tuple:
    env = _load_env()
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if not chat_id and CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text())
            chat_id = cfg.get("chat_id", "")
        except Exception:
            pass
    
    return token, chat_id

def validate_event(event: Dict[str, Any]) -> tuple:
    """
    Validate event against strict financial-only schema.
    Returns (is_valid: bool, reason: str)
    """
    if not isinstance(event, dict):
        return False, "Event must be a dict"
    
    # Check required fields
    for field in REQUIRED_FIELDS:
        if field not in event or event[field] is None or str(event[field]).strip() == "":
            return False, f"Missing required field: {field}"
    
    # Check event_type allowlist
    if event["event_type"] not in ALLOWED_EVENT_TYPES:
        return False, f"Blocked event_type: {event['event_type']}. Allowed: {ALLOWED_EVENT_TYPES}"
    
    # Check reconciliation_status
    if event["reconciliation_status"] != "confirmed":
        return False, f"Reconciliation status must be 'confirmed', got: {event['reconciliation_status']}"
    
    # Check net != 0
    try:
        net_val = float(event["net"])
        if net_val == 0:
            return False, "Net value cannot be zero"
    except (ValueError, TypeError):
        return False, "Net value must be numeric"
    
    # Check external_reference is not empty/generic
    ref = str(event["external_reference"]).strip()
    if len(ref) < 3 or ref.lower() in ("none", "null", "n/a", "test"):
        return False, "Invalid external_reference"
    
    return True, "OK"

def send_financial_event(event: Dict[str, Any], dry_run: bool = False) -> bool:
    """
    Send a validated financial event to Telegram.
    Returns True if sent successfully, False otherwise.
    """
    # Validate
    is_valid, reason = validate_event(event)
    if not is_valid:
        _log(f"REJECTED: {reason} | event_type={event.get('event_type', '?')} | id={event.get('event_id', '?')}", "WARN")
        return False
    
    # Deduplication check
    seen_ids = _load_dedup()
    eid = str(event["event_id"])
    if eid in seen_ids:
        _log(f"DUPLICATE: event_id={eid} already sent", "WARN")
        return False
    
    # Get credentials
    token, chat_id = _get_token_and_chat()
    if not token or not chat_id:
        _log("BLOCKED: Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID", "ERROR")
        return False
    
    # Format message
    msg = format_financial_message(event)
    
    if dry_run:
        _log(f"DRY_RUN: Would send to {chat_id}: {msg[:100]}...")
        return True
    
    # Send with backoff
    success = _send_with_backoff(token, chat_id, msg)
    
    if success:
        seen_ids.add(eid)
        _save_dedup(seen_ids)
        _log(f"SENT: {event['event_type']} | net={event['net']} {event['currency']} | id={eid}")
    else:
        _log(f"SEND_FAILED: event_id={eid}", "ERROR")
    
    return success

def format_financial_message(event: Dict[str, Any]) -> str:
    """Format financial event into concise Telegram HTML message."""
    type_labels = {
        "payout_received": "💰 PAYOUT RECEBIDO",
        "trade_realized": "📈 TRADE REALIZADO",
        "transfer_confirmed": "🔄 TRANSFERÊNCIA CONFIRMADA"
    }
    label = type_labels.get(event["event_type"], event["event_type"].upper())
    
    gross = float(event["gross"])
    fees = float(event["fees"])
    net = float(event["net"])
    
    sign = "+" if net > 0 else ""
    
    lines = [
        f"<b>{label}</b>",
        f"━━━━━━━━━━━━━━━━━━━━━━━",
        f"<b>Processo:</b> <code>{event['process_id']}</code>",
        f"<b>Fonte:</b> {event['source']}",
        f"<b>Ref:</b> <code>{event['external_reference']}</code>",
        f"",
        f"<b>Bruto:</b> <code>{sign}{gross:.4f} {event['currency']}</code>",
        f"<b>Taxas:</b> <code>-{abs(fees):.4f} {event['currency']}</code>",
        f"<b>Líquido:</b> <code>{sign}{net:.4f} {event['currency']}</code>",
        f"",
        f"<i>{event['occurred_at']}</i>",
        f"━━━━━━━━━━━━━━━━━━━━━━━"
    ]
    
    return "\n".join(lines)

def _send_with_backoff(token: str, chat_id: str, text: str, max_retries: int = 3) -> bool:
    """Send message with exponential backoff and jitter."""
    if requests is None:
        _log("requests library not available", "ERROR")
        return False
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    
    for attempt in range(max_retries):
        try:
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    return True
                _log(f"API returned ok=false: {data.get('description')}", "WARN")
            elif resp.status_code == 429:
                # Rate limited - wait longer
                retry_after = resp.json().get("parameters", {}).get("retry_after", 30)
                _log(f"Rate limited, waiting {retry_after}s", "WARN")
                time.sleep(retry_after)
                continue
            else:
                _log(f"HTTP {resp.status_code}: {resp.text[:200]}", "WARN")
        except Exception as e:
            _log(f"Request error (attempt {attempt+1}): {e}", "WARN")
        
        if attempt < max_retries - 1:
            # Exponential backoff with jitter
            base_delay = (2 ** attempt) * 1.0
            jitter = random.uniform(0, 0.5)
            delay = base_delay + jitter
            _log(f"Retrying in {delay:.1f}s...")
            time.sleep(delay)
    
    return False

# Convenience functions for allowed event types
def notify_payout_received(
    process_id: str,
    source: str,
    external_reference: str,
    asset: str,
    gross: float,
    fees: float,
    net: float,
    currency: str = "USDT",
    event_id: Optional[str] = None,
    dry_run: bool = False
) -> bool:
    """Notify about a confirmed payout received."""
    if event_id is None:
        event_id = hashlib.sha256(f"payout:{process_id}:{external_reference}:{net}".encode()).hexdigest()[:16]
    
    return send_financial_event({
        "event_id": event_id,
        "process_id": process_id,
        "event_type": "payout_received",
        "source": source,
        "external_reference": external_reference,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "asset": asset,
        "gross": gross,
        "fees": fees,
        "net": net,
        "currency": currency,
        "reconciliation_status": "confirmed"
    }, dry_run=dry_run)

def notify_trade_realized(
    process_id: str,
    source: str,
    external_reference: str,
    asset: str,
    gross: float,
    fees: float,
    net: float,
    currency: str = "USDT",
    event_id: Optional[str] = None,
    dry_run: bool = False
) -> bool:
    """Notify about a realized trade with confirmed PnL."""
    if event_id is None:
        event_id = hashlib.sha256(f"trade:{process_id}:{external_reference}:{net}".encode()).hexdigest()[:16]
    
    return send_financial_event({
        "event_id": event_id,
        "process_id": process_id,
        "event_type": "trade_realized",
        "source": source,
        "external_reference": external_reference,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "asset": asset,
        "gross": gross,
        "fees": fees,
        "net": net,
        "currency": currency,
        "reconciliation_status": "confirmed"
    }, dry_run=dry_run)

def notify_transfer_confirmed(
    process_id: str,
    source: str,
    external_reference: str,
    asset: str,
    gross: float,
    fees: float,
    net: float,
    currency: str = "USDT",
    event_id: Optional[str] = None,
    dry_run: bool = False
) -> bool:
    """Notify about a confirmed transfer."""
    if event_id is None:
        event_id = hashlib.sha256(f"transfer:{process_id}:{external_reference}:{net}".encode()).hexdigest()[:16]
    
    return send_financial_event({
        "event_id": event_id,
        "process_id": process_id,
        "event_type": "transfer_confirmed",
        "source": source,
        "external_reference": external_reference,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "asset": asset,
        "gross": gross,
        "fees": fees,
        "net": net,
        "currency": currency,
        "reconciliation_status": "confirmed"
    }, dry_run=dry_run)
