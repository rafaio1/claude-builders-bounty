#!/bin/bash
# Validator Orchestrator
LOG="/Agentic/orchestrator/validator.log"
STATE="/Agentic/orchestrator/state.json"
CODEX_BIN="/root/.codex/packages/standalone/current/bin/codex"

echo "[$(date -u)] Validator Orchestrator Started" >> "$LOG"

ACCOUNT="validator"
PID_FILE="/Agentic/orchestrator/${ACCOUNT}.pid"

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "[$(date -u)] Agent $ACCOUNT already running (PID $(cat $PID_FILE))" >> "$LOG"
  exit 0
fi

GOAL="Você é o subagente VALIDATOR (Auditor). Seu objetivo é validar de forma independente as alegações e sucessos de TODOS os outros subagentes (bybit, binance, okx, bugbounty, pr_freelance, wise_liquidity).
Suas ferramentas principais incluem:
1. Leitura de Emails (Gmail) para confirmar payouts de bugbounty (HackerOne/Bugcrowd) e contratos freelance.
2. Leitura de PRs/MRs e issues no GitHub/GitLab para validar entregas de código.
3. Cross-check do state.json com as APIs reais das exchanges e contas Wise para confirmar saldos e trades.
Sempre que um agente alegar lucro, PR mergeado ou bug aceito, você deve buscar a prova documental/criptográfica.
Atualize o state.json adicionando campos de auditoria. Não execute trades nem cace bugs, apenas audite e valide."

echo "[$(date -u)] Spawning $ACCOUNT agent" >> "$LOG"

nohup script -qec "\"$CODEX_BIN\" \
  --dangerously-bypass-approvals-and-sandbox \
  -p fable-ultra \
  -c model_provider=\"ghostcli\" \
  -c model=\"claude-fable-5[1m]\" \
  -c model_reasoning_effort=\"ultra\" \
  \"$GOAL\"" \
  "/Agentic/orchestrator/${ACCOUNT}.log" > /dev/null 2>&1 &

echo $! > "$PID_FILE"
echo "[$(date -u)] Validator spawned with PID $!" >> "$LOG"
