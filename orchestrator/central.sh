#!/bin/bash
LOG="/Agentic/orchestrator/central.log"
STATE="/Agentic/orchestrator/state.json"
CODEX_BIN="/root/.codex/packages/standalone/current/bin/codex"

echo "[$(date -u)] Central Orchestrator Started" >> "$LOG"

if [ ! -f "$STATE" ]; then
  echo '{"target_usd":20000000,"accounts":["wise","bybit","binance"],"status":"initializing"}' > "$STATE"
fi

spawn_agent() {
  local ACCOUNT=$1
  local GOAL=$2
  local PID_FILE="/Agentic/orchestrator/${ACCOUNT}.pid"
  
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "[$(date -u)] Agent $ACCOUNT already running (PID $(cat $PID_FILE))" >> "$LOG"
    return 0
  fi

  echo "[$(date -u)] Spawning $ACCOUNT agent with goal: $GOAL" >> "$LOG"
  
  nohup script -qec "\"$CODEX_BIN\" \
    --dangerously-bypass-approvals-and-sandbox \
    -p fable-ultra \
    -c model_provider=\"ghostcli\" \
    -c model=\"claude-fable-5[1m]\" \
    -c model_reasoning_effort=\"ultra\" \
    \"Você é o subagente especializado em $ACCOUNT. Seu objetivo é maximizar capital na conta $ACCOUNT como parte da meta global de 20M USD. Coordene-se via /Agentic/orchestrator/state.json. Não concorra com outros subagentes. Reporte progresso a cada ação. Goal específico: $GOAL\"" \
    "/Agentic/orchestrator/${ACCOUNT}.log" > /dev/null 2>&1 &
  
  echo $! > "$PID_FILE"
}

 # Financial Trading Agents (Futures/Perpetuals Focus)
 spawn_agent "bybit_futures" "Trading de futuros perpétuos na ByBit com alavancagem otimizada. Foco em multiplicação agressiva de capital via contratos USDT-M. Meta parcial: 8M USD."
 spawn_agent "binance_futures" "Trading de futuros COIN-M e USDT-M na Binance. Estratégias de funding rate arbitrage e momentum. Meta parcial: 8M USD."
 spawn_agent "okx_futures" "Futuros perpétuos e opções na OKX. Foco em volatilidade e hedge cross-exchange. Meta parcial: 4M USD."
 
 # Revenue Generation Agents (Non-Trading)
 spawn_agent "bugbounty" "Caça automatizada de bugs em programas públicos (HackerOne/Bugcrowd). Foco em vulnerabilidades críticas e altas recompensas. Meta parcial: 2M USD."
 spawn_agent "pr_freelance" "Execução de tarefas de programação e automação sob demanda. Aceitar contratos high-ticket e entregar com velocidade máxima. Meta parcial: 1M USD."
 spawn_agent "wise_liquidity" "Arbitragem fiat-crypto e gestão de fluxo para financiar operações futures. Meta parcial: suporte aos traders."

echo "[$(date -u)] All agents orchestrated. Monitoring..." >> "$LOG"
