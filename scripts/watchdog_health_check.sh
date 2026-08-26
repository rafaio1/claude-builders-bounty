#!/bin/bash
# Watchdog Health Check - Idempotent reconciliation script
LOG="/Agentic/logs/payout_reconciliation.log"
MANIFEST="/Agentic/orchestrator/agent_manifest.json"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%S+00:00")

echo "[$TIMESTAMP][WATCHDOG] === Health Check Cycle Start ===" >> "$LOG"

# 1. Verify tmux sessions
TMUX_COUNT=$(tmux list-sessions 2>/dev/null | wc -l)
echo "[$TIMESTAMP][WATCHDOG] Tmux sessions active: $TMUX_COUNT" >> "$LOG"

# 2. Verify Bybit spot process in tmux
BYBIT_PID=$(tmux list-panes -t bybit_spot -F "#{pane_pid}" 2>/dev/null | head -1)
if [ -n "$BYBIT_PID" ]; then
    echo "[$TIMESTAMP][WATCHDOG] Bybit spot pane PID: $BYBIT_PID (alive)" >> "$LOG"
else
    echo "[$TIMESTAMP][WATCHDOG] ⚠️ Bybit spot pane not found!" >> "$LOG"
fi

# 3. Check payout monitor cron freshness
LAST_PAYOUT=$(tail -1 /Agentic/logs/payout_reconciliation.log 2>/dev/null | grep -oP '\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}' | head -1)
echo "[$TIMESTAMP][WATCHDOG] Last payout log entry: $LAST_PAYOUT" >> "$LOG"

# 4. Ledger consistency check
PENDING=$(python3 -c "import json; d=json.load(open('/Agentic/logs/bounty/ledger.json')); print(len([e for e in d.get('entries',[]) if e.get('status') in ('submitted','pending','open')]))" 2>/dev/null || echo "ERROR")
LIQUIDATED=$(python3 -c "import json; d=json.load(open('/Agentic/logs/bounty/ledger.json')); print(len([e for e in d.get('entries',[]) if e.get('status') in ('paid','liquidated','merged')]))" 2>/dev/null || echo "ERROR")
echo "[$TIMESTAMP][WATCHDOG] Ledger: pending=$PENDING, liquidated=$LIQUIDATED" >> "$LOG"

# 5. Telegram gate status
if [ "$LIQUIDATED" = "0" ] || [ "$LIQUIDATED" = "ERROR" ]; then
    echo "[$TIMESTAMP][WATCHDOG] Telegram: SILENT (no liquidated revenue)" >> "$LOG"
else
    echo "[$TIMESTAMP][WATCHDOG] Telegram: TRIGGER ELIGIBLE ($LIQUIDATED items)" >> "$LOG"
fi

echo "[$TIMESTAMP][WATCHDOG] === Health Check Cycle Complete ===" >> "$LOG"
