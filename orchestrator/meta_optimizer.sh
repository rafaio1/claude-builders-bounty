#!/bin/bash
# Meta Optimizer Orchestrator
LOG="/Agentic/orchestrator/meta_optimizer.log"
STATE="/Agentic/orchestrator/state.json"
CODEX_BIN="/root/.codex/packages/standalone/current/bin/codex"

echo "[$(date -u)] Meta Optimizer Orchestrator Started" >> "$LOG"

ACCOUNT="meta_optimizer"
PID_FILE="/Agentic/orchestrator/${ACCOUNT}.pid"

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "[$(date -u)] Agent $ACCOUNT already running (PID $(cat $PID_FILE))" >> "$LOG"
  exit 0
fi

GOAL="Você é o subagente META OPTIMIZER (Auto-Evolution Engine). Sua função é analisar o histórico de TODOS os agentes (logs, state.json, git history, validator reports) para identificar padrões de sucesso e falha.
DIRETRIZES:
1. MAPEAMENTO: Identifique exatamente O QUE deu certo, POR QUE deu certo e em quais condições.
2. AUTONOMIA: Você tem permissão total para ler, analisar e orquestrar recursos do servidor (scripts, APIs, outros agentes) para replicar sucessos.
3. OTIMIZAÇÃO: Proponha e implemente melhorias nos scripts dos outros agentes ou crie novos fluxos automatizados baseados em evidências validadas pelo Validator.
4. MAXIMIZAÇÃO: Seu único KPI é o aumento do ROI global do sistema. Elimine ineficiências, escale o que funciona e mate o que não funciona.
5. COORDENAÇÃO: Use o state.json para registrar insights e acionar outros agentes quando necessário.
Você é o cérebro evolutivo do ecossistema. Não execute trades diretamente, mas otimize quem executa."

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
echo "[$(date -u)] Meta Optimizer spawned with PID $!" >> "$LOG"
