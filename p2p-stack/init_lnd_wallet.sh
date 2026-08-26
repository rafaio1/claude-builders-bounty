#!/bin/bash
# Script interativo para criar wallet do LND no RoboSats
# Rode este script diretamente no terminal do servidor via SSH

set -e
cd /Agentic/p2p-stack/robosats

echo "=== Inicialização da Wallet LND (RoboSats) ==="
echo "Este script requer interação manual para definir senha e seed."
echo ""

# Parar container se estiver rodando
docker compose stop lnd 2>/dev/null || true
sleep 2

# Criar wallet interativamente
echo "Iniciando criação da wallet..."
echo "Quando solicitado, digite uma senha forte (>8 chars) e pressione Enter."
echo "Para as perguntas seguintes, pressione Enter para aceitar padrões."
echo ""
docker compose run --rm -it --entrypoint "lncli --network=testnet create" lnd

echo ""
echo "Wallet criada! Reiniciando LND..."
docker compose up -d lnd
sleep 5

# Verificar status
if docker compose ps lnd | grep -q "Up"; then
    echo "✅ LND está rodando!"
    echo "Agora rode: docker compose up -d backend frontend clean-orders follow-invoices"
else
    echo "❌ LND falhou ao iniciar. Verifique: docker compose logs lnd"
fi
