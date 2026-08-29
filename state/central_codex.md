# Codex Central - /Agentic

## Identidade
Codex Central coordenando servicos: Binance, Bybit, Wise, XM/MT5.

## Estado de Reconciliacao (2026-08-25T19:17Z)

| Servico | Status | Saldo USD | Modo | Credenciais |
|---------|--------|-----------|------|-------------|
| Binance | OK Operacional | $16.19 | live | .env OK |
| Bybit | OK Operacional | $22.30 | live (UNIFIED) | env OK |
| Wise | OK Operacional | $18.00 (BRL 100.00) | live | .env OK |
| XM/MT5 | OK Creds no .env | N/A | N/A | .env OK (migrado, verificado) |

**Capital total verificado: $56.49 USD**

## Posicoes Ativas (2026-08-25T19:17Z)

| Exchange | Par | Qty | Entry | TP | SL | Scalper |
|----------|-----|-----|-------|----|----|---------|
| Binance | DOGE/USDT | 56.0 | $0.08851 | $0.08894 | $0.08805 | scalp_binance |
| Bybit | SOL/USDT | 0.2049 | $98.49 | $99.67 | $97.70 | bybit_spot |
| Bybit | TRX/USDT | 23.86 | $0.3394 | $0.34347 | $0.33660 | scalp_bybit |

**PnL realizado: $0.00 (zero lucro realizado ate o momento)**

## Scalpers Ativos

| Sessao tmux | Script | Status | PID |
|-------------|--------|--------|-----|
| bybit_spot | subagent_trailing_unified.py bybit | Ativo, SOL+TRX positions | 2875359 |
| scalp_binance | subagent_trailing_unified.py binance | Ativo, DOGE position | - |
| scalp_bybit | subagent_trailing_unified.py bybit | Ativo, TRX position | - |
| (volatility) | volatility_monitor.py | Ativo, monitorando | 1497677 |

## Migracao MT5 - Status Final

- MT5_ACCOUNT: **REDACTED** -> .env linha 19 (verificado)
- MT5_SERVER: "XMGlobal-MT5 12" -> .env linha 20 (aspas aplicadas, verificado)
- MT5_PASS: **REDACTED** -> .env linha 21 (verificado)
- master_control.sh linha 31: comentada (#), creds migradas com sucesso
- reconcile.py: le MT5 creds do .env corretamente
- Resultado reconcile: account=362244368, server=XMGlobal-MT5 12, pass=SET

## Diretrizes Persistentes

1. NUNCA expor segredos - chaves/secret/tokens sempre redacted em logs
2. Preservar autorizacoes existentes - nao alterar permissoes sem evidencia
3. Exigir evidencia para lucro ou transferencia - nenhum valor movido sem verificacao on-chain/API
4. Estado duravel - tudo em /Agentic/state/
5. Passos curtos - uma acao por vez, verificar resultado, continuar

## Progresso (Fase 2)

1. [x] Reconciliar Binance, Bybit, Wise (saldos verificados)
2. [x] Migrar MT5 creds de master_control.sh para .env: MT5_ACCOUNT, MT5_SERVER, MT5_PASS
3. [x] Verificar ordens abertas no Bybit (0 ordens, 0 posicoes)
4. [x] Verificar ordens abertas na Binance (0 ordens)
5. [x] Avaliar estrategia de capital ($56.49 total) - ver abaixo
6. [x] Reconciliar risco e exposicao - ver abaixo
7. [x] Re-executar reconcile.py para confirmar MT5 creds no .env - confirmado

## Avaliacao de Capital ($56.74 USD)

### Distribuicao
- Binance: $16.24 USDT (spot, pronto para trading)
- Bybit: $22.50 (UNIFIED, multi-coin, pronto para trading)
- Wise: $18.00 (BRL 100.00, liquidez fiat)
- XM/MT5: sem saldo verificavel

### Estrategia
- Capital insuficiente para trading significativo com alavancagem alta
- Foco: micro-scalping spot em pares de alta liquidez (BTC, ETH, SOL)
- Bybit UNIFIED oferece mais flexibilidade (multi-coin, spot+futures)
- Wise como reservatorio fiat -> transferir para exchange quando possivel
- Bounty engine pode complementar capital acumulado

### Risco
- Max exposure por trade: ~20% do capital da exchange ($3-5)
- Stop loss: ~1.2% (configurado nos scalpers ativos)
- Take profit: ~1.2% (configurado nos scalpers ativos)
- Nao usar alavancagem > 5x com capital < $100
- Arb scan: 6 oportunidades viaveis detectadas, capital insuficiente para execucao significativa
- Scalpers rodando em modo conservador (spot, sem alavancagem)
- Dust em 35+ alts no Bybit: consolidacao pendente (dust < $0.01 cada)

## Proximos Passos (Fase 3)

1. [ ] Consolidar dust do Bybit (35+ alts com valor < $0.01 cada)
2. [ ] Monitorar saida das posicoes ativas (DOGE, SOL, TRX)
3. [ ] Avaliar transferencia Wise BRL -> USD para exchange
4. [ ] Considerar bounty engine para acumular capital
5. [ ] Re-executar reconcile.py periodicamente (cron ou loop)

## Arquivos de Estado
- /Agentic/state/reconciliation.json - estado de reconciliacao (auto-gerado)
- /Agentic/state/reconcile.py - script de reconciliacao
- /Agentic/state/central_codex.md - este arquivo (diretivas)
- /Agentic/orchestrator/state.json - estado do orquestrador
- /Agentic/ledger.jsonl - log de arbitragem

## Processos Ativos
- volatility_monitor.py - monitor de volatilidade (PID 1497677)
- subagent_trailing_unified.py bybit - scalping Bybit spot (PID 2868444, tmux: bybit_spot)

## Sessoes tmux
- bybit_spot: scalping ativo
- scalp_binance: preparado
- scalp_bybit: preparado

## Constraints
- sandbox_mode: danger-full-access
- approval_policy: never
- shell: bash (/usr/bin/bash)
