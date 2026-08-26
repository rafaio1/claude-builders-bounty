#!/usr/bin/env python3
"""Telegram Alert System - Financial Events Only (Gate-Enforced)

This module now routes ALL Telegram notifications through src/telegram_gate.py.
Only confirmed, reconciled financial events are sent:
  - payout_received
  - trade_realized
  - transfer_confirmed

All heartbeats, opportunities, paper trades, scans, and status reports are blocked.
"""
import sys
import os
import json
import time
from datetime import datetime, timezone
from pathlib import Path

# Add src to path for gate import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

try:
    from telegram_gate import send_financial_event, notify_trade_realized, _log as gate_log
except ImportError as e:
    print(f"[FATAL] Cannot import telegram_gate: {e}", flush=True)
    sys.exit(1)

LEDGER_FILE = '/Agentic/ledger.jsonl'
STATE_FILES = ['/Agentic/orchestrator/v22_state.json']
SENT_TRACKER = '/Agentic/logs/telegram_gate_sent_trades.json'

def log(msg):
    ts = datetime.now(timezone.utc).strftime('%H:%M:%S')
    print(f"[{ts}] TG_ALERTS: {msg}", flush=True)

def load_sent_ids():
    if os.path.exists(SENT_TRACKER):
        try:
            with open(SENT_TRACKER, 'r') as f:
                return set(json.load(f).get('sent_event_ids', []))
        except Exception:
            pass
    return set()

def save_sent_ids(ids):
    os.makedirs(os.path.dirname(SENT_TRACKER), exist_ok=True)
    trimmed = sorted(list(ids))[-5000:]
    with open(SENT_TRACKER, 'w') as f:
        json.dump({'sent_event_ids': trimmed}, f, indent=2)

def check_and_send_realized_trades():
    """Scan ledger for new realized LIVE trades and send via gate."""
    sent_ids = load_sent_ids()
    new_sends = 0
    
    if not os.path.exists(LEDGER_FILE):
        return 0
    
    try:
        with open(LEDGER_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    # ONLY send for LIVE mode realized trades with net != 0
                    if entry.get('mode') != 'LIVE':
                        continue
                    if entry.get('net_pnl') is None or float(entry['net_pnl']) == 0:
                        continue
                    
                    # Generate deterministic event_id from trade data
                    ts = entry.get('ts', '')
                    symbol = entry.get('symbol', 'UNKNOWN')
                    net = entry.get('net_pnl', 0)
                    event_id = f"trade:{symbol}:{ts}:{net}"
                    
                    if event_id in sent_ids:
                        continue
                    
                    # Send through gate (validates schema internally)
                    success = notify_trade_realized(
                        process_id=f"grid-{entry.get('strategy', 'unknown')}",
                        source=entry.get('exchange', 'bybit'),
                        external_reference=f"{symbol}-{ts[:19]}",
                        asset=symbol.split('/')[0] if '/' in symbol else symbol,
                        gross=float(entry.get('gross_pnl', net)),
                        fees=float(entry.get('fees_usdt', 0)),
                        net=float(net),
                        currency='USDT',
                        event_id=event_id,
                        dry_run=False
                    )
                    
                    if success:
                        sent_ids.add(event_id)
                        new_sends += 1
                        log(f"SENT realized trade: {symbol} net={net:+.6f}")
                        
                except Exception as e:
                    continue
    except Exception as e:
        log(f"Ledger scan error: {e}")
    
    if new_sends > 0:
        save_sent_ids(sent_ids)
    
    return new_sends

def main():
    """Main loop: only sends confirmed financial events via gate."""
    log("Telegram Financial Alerts starting (gate-enforced)...")
    log("ONLY realized trades, payouts, and transfers will be sent.")
    log("Heartbeats, opportunities, and paper trades are BLOCKED.")
    
    while True:
        try:
            sent = check_and_send_realized_trades()
            if sent > 0:
                log(f"Sent {sent} new financial event(s)")
            time.sleep(30)
        except KeyboardInterrupt:
            log("Shutting down...")
            break
        except Exception as e:
            log(f"Main loop error: {e}")
            time.sleep(30)

if __name__ == '__main__':
    main()
