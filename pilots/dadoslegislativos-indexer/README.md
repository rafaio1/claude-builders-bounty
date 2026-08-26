# dadoslegislativos-indexer

**Status:** SCAFFOLD_OK (TIER0)
**Fonte:** Câmara dos Deputados — API Aberta v2
**Custo:** Zero (dados abertos federais, sem auth)

## Descrição
Indexa as 20 proposições legislativas mais recentes da Câmara dos Deputados, extraindo metadados estruturados para análise de tendências regulatórias e oportunidades B2G/B2B.

## Uso
```bash
python3 main.py
```

## Output
- `proposicoes_index.json` — Lista de proposições com id, tipo, número, ano, ementa e data.

## Notas Técnicas
- Endpoint: `https://dadosabertos.camara.leg.br/api/v2/proposicoes`
- Ordenação: DESC por ID (mais recentes primeiro)
- Rate limit: Respeitar headers da API; uso moderado em scaffolding.
- Gzip: Tratado automaticamente via magic bytes.

## Próximos Passos (TIER1)
- Expandir para Senado Federal (`legis.senado.leg.br`)
- Adicionar tramitação e status atual
- Filtrar por CNAE tech ou palavras-chave regulatórias
