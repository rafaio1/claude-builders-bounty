# IBGE Municípios Indexer — TIER0 Scaffold

Indexador zero-capital de todos os municípios brasileiros via API oficial do IBGE.

## Fonte
- **API:** [servicodados.ibge.gov.br/api/v1/localidades/municipios](https://servicodados.ibge.gov.br/api/v1/localidades/municipios)
- **Parâmetros:** `orderBy=nome`
- **Autenticação:** Nenhuma (dados públicos abertos)
- **Compressão:** Resposta gzip suportada automaticamente

## Execução
```bash
python3 main.py
```

## Output
- `municipios_index.json` — 5571 municípios com hierarquia completa (UF, mesorregião, microrregião)

## Compliance
- ✅ Zero capital (sem custos)
- ✅ Sem signup externo
- ✅ Dados públicos oficiais (IBGE)
- ✅ Respeita licença da fonte
