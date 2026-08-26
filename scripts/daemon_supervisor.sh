#!/bin/bash
# Daemon Supervisor - Keeps critical revenue agents alive
LOG="/Agentic/logs/supervisor.log"
SCRIPTS="/Agentic/scripts"

declare -A DAEMONS=(
  ["high_ticket_sniper"]="high_ticket_sniper.py"
  ["bounty_engine"]="bounty_engine.py"
  ["autonomous_executor"]="autonomous_executor.py"
  ["airdrop_farmer"]="airdrop_farmer.py"
  ["polymarket_bot"]="polymarket_bot.py"
)

while true; do
  for name in "${!DAEMONS[@]}"; do
    script="${DAEMONS[$name]}"
    if ! pgrep -f "python3.*$script" > /dev/null; then
      echo "[$(date -u +%FT%T)] RESTARTING $name ($script)" >> "$LOG"
      cd "$SCRIPTS" && nohup python3 "$script" >> "/Agentic/logs/${name}.log" 2>&1 &
      sleep 1
    fi
  done
  sleep 30
done
