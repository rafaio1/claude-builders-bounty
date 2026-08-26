# DadosGovBR Catalog Indexer — TIER0 Scaffold

Indexador zero-capital de catálogos de dados abertos governamentais do Brasil.

## Fonte
- **Origem:** [dadosgovbr/catalogos-dados-brasil](https://github.com/dadosgovbr/catalogos-dados-brasil) (GitHub Static)
- **Arquivo:** `dados/catalogos.csv`
- **Licença:** Dados públicos oficiais

## Motivo do Fallback
A API oficial (`dados.gov.br/dados/api/publico/conjuntos-dados`) retorna HTTP 401 Unauthorized sem bearer token.
Este scaffold usa a fonte estática oficial no GitHub como alternativa zero-capital válida.

## Execução
```bash
python3 main.py
```

## Output
- `catalogs_index.json` — 39 catálogos indexados com metadados (título, URL, município, UF, esfera, poder, solução)

## Compliance
- ✅ Zero capital (sem custos)
- ✅ Sem signup externo
- ✅ Dados públicos oficiais
- ✅ Respeita licença da fonte
