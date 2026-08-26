# IBGE News/Releases Indexer — TIER0 Scaffold

Indexador zero-capital de releases e notícias oficiais do IBGE.

## Fonte
- **API:** [servicodados.ibge.gov.br/api/v3/noticias](https://servicodados.ibge.gov.br/api/v3/noticias)
- **Parâmetros:** `tipo=release&quantidade=50`
- **Autenticação:** Nenhuma (dados públicos abertos)

## Execução
```bash
python3 main.py
```

## Output
- `news_index.json` — 30 releases indexados com título, resumo, data, categoria e URL

## Compliance
- ✅ Zero capital (sem custos)
- ✅ Sem signup externo
- ✅ Dados públicos oficiais (IBGE)
- ✅ Respeita licença da fonte
