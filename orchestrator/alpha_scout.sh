#!/bin/bash
# Alpha Scout Orchestrator
LOG="/Agentic/orchestrator/alpha_scout.log"
STATE="/Agentic/orchestrator/state.json"
CODEX_BIN="/root/.codex/packages/standalone/current/bin/codex"

echo "[$(date -u)] Alpha Scout Orchestrator Started" >> "$LOG"

ACCOUNT="alpha_scout"
PID_FILE="/Agentic/orchestrator/${ACCOUNT}.pid"

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "[$(date -u)] Agent $ACCOUNT already running (PID $(cat $PID_FILE))" >> "$LOG"
  exit 0
fi

GOAL="Você é o subagente ALPHA SCOUT. Seu ciclo de vida é estrito:
1. PROSPECÇÃO: Busque novas oportunidades de alta assimetria (crypto, arb, ineficiências).
2. VALIDAÇÃO PAPER: Teste a estratégia em modo simulação/paper. Não use capital real ainda.
3. SOLICITAÇÃO: Se validado com sucesso (>60% winrate ou Sharpe > 1.5), atualize o state.json solicitando capital da conta 'wise_liquidity'.
4. EXECUÇÃO REAL: Ao receber capital da Wise, execute a estratégia com gestão de risco rigorosa.
5. REPAGAMENTO: Assim que atingir lucro alvo ou stop, devolva o capital principal + lucros para 'wise_liquidity' e volte ao passo 1.
6. AUTONOMIA: Quando tiver capital próprio acumulado, use-o prioritariamente. Use Wise apenas como alavancagem temporária.
Coordene-se EXCLUSIVAMENTE via /Agentic/orchestrator/state.json. Meta: Maximizar ROI com risco controlado."

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
echo "[$(date -u)] Alpha Scout spawned with PID $!" >> "$LOG"
