#!/bin/bash
set -euo pipefail

cd /Agentic/orchestrator
set -a
# shellcheck disable=SC1091
. /root/.automaton/bybit-murre.env
set +a

if ! python3 - <<'PY'
from trading_economic_guard import evaluate_live_trading

decision = evaluate_live_trading(exchange_name="bybit")
if not decision.allowed:
    print("TRADING_ECONOMIC_GUARD_BLOCKED:" + ";".join(decision.reasons))
    raise SystemExit(78)
PY
then
    printf '[%s] Watchdog: live start denied by economic guard\n' "$(date -u --iso-8601=seconds)" >> /Agentic/orchestrator/watchdog.log
    exit 0
fi

if ! tmux has-session -t bybit_spot 2>/dev/null; then
    tmux new-session -d -s bybit_spot "python3 -u subagent_trailing_unified.py bybit 2>&1 | tee -a bybit_spot_live.log"
    printf '[%s] Watchdog: Restarted bybit_spot\n' "$(date -u --iso-8601=seconds)" >> /Agentic/orchestrator/watchdog.log
fi
