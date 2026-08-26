#!/bin/bash
# Watcher para sync do bitcoind testnet
LOG="/Agentic/logs/sync_watcher.log"
THRESHOLD=0.995

echo "[$(date -u)] Iniciando watcher de sync (alvo: ${THRESHOLD})" | tee -a "$LOG"

while true; do
  PROGRESS=$(docker exec btc-dev bitcoin-cli -testnet -rpcuser=robodev -rpcpassword=robodev getblockchaininfo 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('verificationprogress',0))" 2>/dev/null)
  
  if [ -z "$PROGRESS" ]; then
    echo "[$(date -u)] Erro ao obter progresso, aguardando..." | tee -a "$LOG"
    sleep 60
    continue
  fi

  READY=$(python3 -c "print(1 if float('$PROGRESS') >= $THRESHOLD else 0)")
  
  if [ "$READY" == "1" ]; then
    echo "[$(date -u)] ✅ SYNC COMPLETO ($PROGRESS). LND pronto para unlock." | tee -a "$LOG"
    # Tenta unlock automático do LND
    docker exec lnd-dev sh -c 'echo "password123" | lncli --network=testnet unlock --stdin' >> "$LOG" 2>&1
    echo "[$(date -u)] Unlock do LND executado. Verificando status..." | tee -a "$LOG"
    docker exec lnd-dev lncli --network=testnet getinfo | grep synced_to_chain | tee -a "$LOG"
    break
  else
    PCT=$(python3 -c "print(f'{float(\"$PROGRESS\")*100:.2f}%')")
    echo "[$(date -u)] Sync: $PCT ($PROGRESS)" | tee -a "$LOG"
  fi
  
  sleep 120
done
