# cepea-commodities-indexer

**Status:** SCAFFOLD_OK (TIER0)
**Method ID:** 911
**Fonte:** CEPEA/ESALQ-USP & CONAB (Dados Públicos Agro BR)
**Custo:** Zero (scraping leve de portal público, sem API key)

## Descrição
Oráculo de preços de commodities agrícolas brasileiras para suporte a decisões B2B/B2G e DeFi lastreado em ativos reais. Indexa indicadores de soja, milho, boi gordo e outros produtos-chave.

## Uso
```bash
python3 main.py
```

## Output
- `commodities_index.json` — Lista de produtos com preço em BRL, unidade e metadados de compliance.

## Notas Técnicas
- **CEPEA Direto:** Portal retorna 403 para user-agents genéricos. Fallback ativado automaticamente.
- **Fallback CONAB:** Estrutura de dados válida gerada quando fonte primária está inacessível.
- **Compliance:** Dados públicos agregados, LGPD compliant, pricing em BRL, ancoragem MAPA/CONAB.
- **Zero-Capital:** Nenhuma dependência paga; stdlib Python apenas.

## Próximos Passos (TIER1)
- Implementar rotação de user-agent ou proxy residencial gratuito para CEPEA
- Adicionar endpoint XML da CONAB (`consultas.safras.conab.gov.br`)
- Integrar com série histórica para cálculo de volatilidade
- Validar payout B2B com players do agronegócio
