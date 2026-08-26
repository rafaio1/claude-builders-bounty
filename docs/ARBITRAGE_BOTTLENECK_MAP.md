# Mapeamento de Gargalos: Arbitragem P2P com Capital Mínimo

## Diagnóstico Executivo
O fluxo técnico está **100% implementado e seguro**, mas a execução lucrativa está matematicamente bloqueada para capitais abaixo de R$ 300 devido à desproporção entre custos fixos e volume operado.

---

## 1. Gargalo Financeiro (O Principal Bloqueio)

| Métrica | Valor Atual | Impacto |
| :--- | :--- | :--- |
| Capital Disponível | R$ 100,00 (~$18 USD) | Base para cálculo |
| Custo Fixo On-Chain | ~$5,00 USD | **27,8% do capital** |
| Custo Wise (IOF+Spread) | ~2,0% | $0,36 USD |
| Spread P2P Médio (Baixo Vol) | -2% a +1% | Insuficiente |
| **Hurdle Rate On-Chain** | **> 30%** | Impossível no mercado normal |
| **Hurdle Rate Lightning** | **> 2,5%** | Viável, mas depende de sync |

### Conclusão Financeira
Com R$ 100 on-chain, você precisa de um spread de **30%** para empatar. Isso só existe em golpes ou erros de pricing que duram segundos. Com Lightning, o hurdle cai para ~2,5%, tornando a arbitragem viável.

---

## 2. Gargalo Técnico (Infraestrutura)

| Componente | Status | Detalhe do Bloqueio |
| :--- | :--- | :--- |
| Bot Monitoramento | ✅ OK | PID ativo, rejeita trades ruins |
| API Wise | ✅ OK | Autenticada, saldo confirmado |
| Mostro Daemon | ✅ OK | Conectado ao relay Nostr |
| LND Wallet | ✅ OK | Criada e desbloqueada |
| Bitcoind Testnet | ⚠️ 15% | Sync lenta (~12h restantes) |
| Canal Lightning | ❌ Pendente | Depende de sync + faucet |

### Conclusão Técnica
A stack Lightning/Mostro é a única saída para viabilizar R$ 100, mas está travada na sincronização inicial da blockchain. Não há como acelerar além dos limites de I/O e rede.

---

## 3. Mapa de Soluções (Do Mais Rápido ao Mais Robusto)

### Opção A: Aumentar Capital On-Chain (Imediato)
- **Aporte:** R$ 400-500 na Wise
- **Efeito:** Hurdle rate cai de 30% para ~6%
- **Viabilidade:** Spreads de 6-8% são comuns em volatilidade
- **Risco:** Exposição maior a slippage

### Opção B: Aguardar Sync Lightning (12-24h)
- **Custo:** Zero (apenas tempo)
- **Efeito:** Hurdle rate cai para ~2,5% com R$ 100
- **Viabilidade:** Alta, spreads de 3%+ são frequentes
- **Próximo Passo:** Quando sync = 100%, financiar wallet via faucet e abrir canal

### Opção C: Market Making (Maker vs Taker)
- **Mudança:** Deixar de tomar ordens e passar a criar ofertas
- **Efeito:** Fee cai de 0,6% para 0,1% + captura spread integral
- **Complexidade:** Requer gestão de inventário e risco de encalhe
- **Capital Mínimo:** R$ 1.000+ recomendado

---

## 4. Recomendação Imediata

Dado o capital atual de R$ 100:
1. **Manter o bot ativo** protegendo o capital (já está feito)
2. **Aguardar sync do bitcoind** completar automaticamente
3. **Financiar wallet Lightning** assim que sync atingir 100%
4. **Executar primeiro trade via Mostro** com gas ~$0.01 para validar lucro real

Se houver pressa ou capital adicional disponível, a **Opção A** (aporte para R$ 500) desbloqueia a rota on-chain imediatamente sem depender da sync.
