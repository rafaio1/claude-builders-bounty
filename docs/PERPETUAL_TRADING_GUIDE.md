# Guia de Operação em Perpétuos para Subagentes Codex

## 1. Por que Migrar do Spot para Perpétuos?
- **Spot:** Ganho limitado à valorização do ativo (1x). Capital ineficiente para meta de USD 1M.
- **Perpétuos:** Alavancagem permite multiplicar exposição sem imobilizar capital total. Funding rate pode gerar receita passiva adicional.
- **Risco:** Liquidação, funding negativo, slippage em alta volatilidade.

## 2. Regras de Ouro (NÃO NEGOCIÁVEIS)
1. **Alavancagem Máxima:** 3x a 5x para estratégias direcionais; até 10x apenas em arbitragem/funding com hedge perfeito.
2. **Stop Loss Obrigatório:** Nunca operar sem SL técnico ou por tempo. Risco máximo por trade: 1-2% do bankroll.
3. **Funding Rate Check:** Antes de abrir posição longa, verificar funding das últimas 8h. Se > 0.1%/8h, reconsiderar ou hedgear.
4. **Liquidez Mínima:** Só operar pares com volume 24h > $50M e spread < 0.05%.
5. **Correlação:** Não abrir posições correlacionadas > 0.7 sem reduzir tamanho individual.

## 3. Estratégias Prioritárias para Escala
### A. Funding Rate Arbitrage (Baixo Risco)
- Long spot + Short perp quando funding > 0.05%/8h consistente.
- Lucro = funding recebido - taxas.
- Ideal para capital ocioso.

### B. Breakout com Confirmação de Volume (Médio Risco)
- Entrada após rompimento de consolidação > 4h com volume 2x média.
- Alavancagem 3x, SL abaixo da consolidação, TP 2:1.
- Filtros: RSI não sobrecomprado, tendência macro favorável.

### C. Mean Reversion em Extremos (Alto Risco/Retorno)
- Apenas em desvios > 3σ da VWAP 200 períodos.
- Alavancagem 2x max, entrada escalonada em 3 níveis.
- SAIR imediatamente se perder nível chave.

## 4. Gestão de Posição e Saída
- **Trailing Stop:** Ativar após 1R de lucro. Distância = 1.5x ATR.
- **Parcial:** Fechar 50% no primeiro TP, mover SL para breakeven.
- **Time Stop:** Se posição não andar em 24h, fechar manualmente. Capital parado é custo de oportunidade.

## 5. Métricas de Sucesso por Agente
| Métrica | Spot Baseline | Perp Target |
|---------|---------------|-------------|
| ROI Mensal | 2-5% | 15-30% |
| Sharpe Ratio | < 1.0 | > 1.5 |
| Max Drawdown | 10% | 15% (controlado) |
| Win Rate | 40-50% | 45-55% |
| Profit Factor | 1.2 | > 1.8 |

## 6. Integração com Sistema ARO
- Todos os sinais de entrada/saída devem ser logados em `/Agentic/data/aro/trades/perpetuals.jsonl`.
- Feedback de lucratividade diário via `profitability-by-channel.json` atualizado automaticamente.
- Emails de alertas de risco extremo (funding > 0.3%, liquidação iminente) são PERTINENTES e devem ser roteados, não deletados.

## 7. Aviso Legal
Este guia é para agentes automatizados sob supervisão humana. Perdas podem exceder o capital inicial em casos de gap/slippage. Sempre validar parâmetros em paper trading antes de live.
