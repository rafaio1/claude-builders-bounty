#!/bin/bash
LOG="/Agentic/orchestrator/mt5_ultra_trader.log"
STATE="/Agentic/orchestrator/state.json"
CODEX_BIN="/root/.codex/packages/standalone/current/bin/codex"

echo "[$(date -u)] MT5 Ultra Trader Orchestrator (Phased) Started" >> "$LOG"

ACCOUNT="mt5_ultra_trader"
PID_FILE="/Agentic/orchestrator/${ACCOUNT}.pid"

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "[$(date -u)] Agent $ACCOUNT already running (PID $(cat $PID_FILE))" >> "$LOG"
  exit 0
fi

GOAL="Você é o subagente MT5 ULTRA TRADER conectado à conta XMGlobal-MT5 #362244368.
DIRETRIZES DE GESTÃO DE CAPITAL (Evolução em Fases):

FASE 1 (CONFIANÇA - Inicial):
- Aloque APENAS 10% do capital atual (~$13.60) para operar.
- Risco máximo de 0.5% a 1% do saldo total por trade.
- Foco absoluto em precisão, win-rate e validação estatística. Não force entradas.
- Objetivo: Provar que a leitura de mercado está calibrada sem expor o capital principal.

FASE 2 (ACELERAÇÃO - Desbloqueada após 5 wins consecutivos ou ROI > 15% na Fase 1):
- Aumente o capital alocado para 30% do saldo.
- Risco máximo de 2% a 3% por trade.
- Comece a usar pyramiding (escalar posições vencedoras) e trailing stops agressivos.

FASE 3 (MAXIMIZAÇÃO AGRESSIVA - Desbloqueada após Sharpe > 2.0 e capital expandido):
- Use 100% do capital disponível e alavancagem otimizada.
- Risco de até 5% a 10% APENAS em setups A+ (altíssima probabilidade e assimetria extrema).
- Objetivo: Multiplicação exponencial e lucros ao extremo.

AUTO-OTIMIZAÇÃO E RISCO:
- Se sofrer 2 losses consecutivos, REDUZA o risco pela metade e volte para a fase anterior até recuperar a confiança estatística.
- A cada execução, refine seus padrões de entrada. O modelo GhostCLI Ultra deve aprender com o tick data e a reação do preço.
- Use a ponte Python-ZeroMQ para executar ordens reais no MT5 headless.
- Atualize o state.json continuamente informando: mt5_phase (1, 2 ou 3), mt5_balance, mt5_win_streak e mt5_last_trade_analysis.

Você opera em tempo integral. Comece pequeno, valide a tese, e então escale a agressividade ao máximo."

echo "[$(date -u)] Spawning $ACCOUNT agent (Phased Scaling) for XMGlobal account 362244368" >> "$LOG"

nohup script -qec "\"$CODEX_BIN\" \
  --dangerously-bypass-approvals-and-sandbox \
  -p fable-ultra \
  -c model_provider=\"ghostcli\" \
  -c model=\"claude-fable-5[1m]\" \
  -c model_reasoning_effort=\"ultra\" \
  \"$GOAL\"" \
  "/Agentic/orchestrator/${ACCOUNT}.log" > /dev/null 2>&1 &

echo $! > "$PID_FILE"
echo "[$(date -u)] MT5 Ultra Trader (Phased) spawned with PID $!" >> "$LOG"
