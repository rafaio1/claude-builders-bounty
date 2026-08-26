#!/usr/bin/env bash
# Rotina de expurgo para aliviar memória e disco do servidor
# Uso: bash /Agentic/scripts/cleanup_workspace.sh

set -euo pipefail

echo "=== INICIANDO EXPURGO $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

# 1. Limpar caches do npm/yarn/pnpm
echo "[1/6] Limpando caches de package managers..."
npm cache clean --force 2>/dev/null || true
yarn cache clean 2>/dev/null || true
pnpm store prune 2>/dev/null || true

# 2. Remover node_modules órfãos em bounties antigas (manter apenas lily-sdk ativo)
echo "[2/6] Removendo node_modules órfãos..."
find /Agentic/revenue/bounties -mindepth 2 -maxdepth 2 -name "node_modules" -type d \
  ! -path "*/lily-sdk/*" -exec rm -rf {} + 2>/dev/null || true

# 3. Limpar coverage reports antigos
echo "[3/6] Limpando coverage reports..."
find /Agentic -name "coverage" -type d -exec rm -rf {} + 2>/dev/null || true

# 4. Truncar logs antigos (>7 dias ou >50MB)
echo "[4/6] Truncando logs antigos..."
find /Agentic/logs -name "*.json" -mtime +7 -size +50M -exec truncate -s 0 {} + 2>/dev/null || true
find /Agentic/logs -name "*.log" -mtime +7 -exec truncate -s 0 {} + 2>/dev/null || true

# 5. Limpar branches locais já merged no lily-sdk
echo "[5/6] Limpando branches locais merged..."
cd /Agentic/revenue/bounties/lily-sdk 2>/dev/null && {
  git fetch origin --prune 2>/dev/null || true
  git branch --merged main 2>/dev/null | grep -v "main\|master" | xargs -r git branch -d 2>/dev/null || true
} || true

# 6. Limpar tmp e arquivos temporários
echo "[6/6] Limpando arquivos temporários..."
rm -rf /tmp/patch_*.py /tmp/*.tmp 2>/dev/null || true
find /Agentic -name "*.tmp" -delete 2>/dev/null || true

# Relatório final
DISK_BEFORE=$(df -h /Agentic | tail -1 | awk '{print $3}')
echo ""
echo "=== EXPURGO CONCLUÍDO ==="
echo "Uso de disco atual: $DISK_BEFORE"
echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
