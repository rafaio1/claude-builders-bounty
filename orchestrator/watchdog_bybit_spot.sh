#!/bin/bash
if ! tmux has-session -t bybit_spot 2>/dev/null; then
    cd /Agentic/orchestrator
    tmux new-session -d -s bybit_spot "python3 -u subagent_trailing_unified.py bybit 2>&1 | tee -a bybit_spot_live.log"
    echo "[$(date -u)] Watchdog: Restarted bybit_spot" >> /Agentic/orchestrator/watchdog.log
fi
