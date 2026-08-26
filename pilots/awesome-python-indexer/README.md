# Awesome Python Curated List Indexer

**Status:** TIER0 — SCAFFOLD_OK  
**Type:** Indexer  
**Source:** [vinta/awesome-python](https://github.com/vinta/awesome-python)  
**Zero-Capital:** ✅ stdlib only, sem custos

## Descrição

Indexador automático da lista curada awesome-python. Extrai bibliotecas por categoria diretamente do README via GitHub API, gerando índice estruturado em JSON.

## Execução

```bash
python3 main.py
```

## Output

- `output.json` — Índice completo com categorias, nomes, URLs e descrições

## Resultados (2026-08-26)

- **485 bibliotecas** indexadas
- **75 categorias** cobertas
- Graceful degradation: retorna status ERROR se API falhar

## Estrutura

```
pilots/awesome-python-indexer/
├── main.py       # Script principal (stdlib only)
├── output.json   # Índice gerado
└── README.md     # Este arquivo
```
