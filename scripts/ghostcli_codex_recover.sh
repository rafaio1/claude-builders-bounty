#!/bin/bash
# Wait for GhostCLI inference to recover, then nudge all Codex tmux agents.
set -euo pipefail
KEY=$(grep -oP '^GHOSTCLI_API_KEY=\K.*' /root/ApiFable/.env | head -1)
LOG=/Agentic/logs/ghostcli_recover.log
mkdir -p /Agentic/logs
echo "[$(date -u)] recover watcher start" | tee -a "$LOG"

healthy() {
  code=$(curl -sS --max-time 45 "https://ghostcli.dev/v1/chat/completions" \
    -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
    -d '{"model":"claude-sonnet-5","messages":[{"role":"user","content":"Reply PONG"}],"max_tokens":8}' \
    -o /tmp/gc_recover.json -w '%{http_code}' || echo 000)
  if [ "$code" = "200" ] && grep -q 'choices\|message\|content\|PONG\|pong' /tmp/gc_recover.json 2>/dev/null; then
    return 0
  fi
  # also accept any 200 with choices
  if [ "$code" = "200" ] && grep -q 'choices\|output_text\|message' /tmp/gc_recover.json 2>/dev/null; then
    return 0
  fi
  echo "[$(date -u)] still down HTTP=$code body=$(head -c 100 /tmp/gc_recover.json 2>/dev/null)" | tee -a "$LOG"
  return 1
}

for i in $(seq 1 120); do
  if healthy; then
    echo "[$(date -u)] GhostCLI healthy — nudging Codex agents" | tee -a "$LOG"
    break
  fi
  sleep 30
  if [ "$i" -eq 120 ]; then
    echo "[$(date -u)] give up after 60m" | tee -a "$LOG"
    exit 1
  fi
done

nudge() {
  local s="$1" msg="$2"
  tmux has-session -t "$s" 2>/dev/null || return 0
  tmux send-keys -t "$s:0.0" Escape C-u 2>/dev/null || true
  sleep 0.4
  tmux send-keys -t "$s:0.0" "$msg" Enter
  echo "[$(date -u)] nudged $s" | tee -a "$LOG"
}

nudge codex_bybit_futures 'GhostCLI voltou. Continue: diagnostique saldo/permissoes Bybit e execute a melhor acao disponivel agora. Meta capital -> Wise.'
nudge codex_binance_futures 'GhostCLI voltou. Continue trading Binance agora: diagnostique saldo e execute. Meta capital -> Wise \$2M.'
nudge codex_okx_futures 'GhostCLI voltou. Continue OKX futures/options agora. Meta 4M parcial; capital final Wise.'
nudge codex_bugbounty 'GhostCLI voltou. Continue bug bounty/PRs pagos agora; registre no ledger.'
nudge codex_pr_freelance 'GhostCLI voltou. Continue high-ticket bounty/PR agora (>\$500).'
nudge codex_wise_liquidity 'GhostCLI voltou. Continue arb fiat-crypto / bridge Wise agora.'

# Interrupt long backoff on orca pts if possible (best-effort)
for pts in 90 91 95; do
  if [ -w "/dev/pts/$pts" ]; then
    printf '\033' > "/dev/pts/$pts" 2>/dev/null || true
  fi
done
echo "[$(date -u)] recover watcher done" | tee -a "$LOG"
