# System Design Primer Indexer

**Status:** TIER0 — SCAFFOLD_OK  
**Type:** Indexer  
**Source:** [donnemartin/system-design-primer](https://github.com/donnemartin/system-design-primer)  
**Zero-Capital:** ✅ stdlib only, sem custos

## Descrição

Indexador automático do repositório System Design Primer. Extrai documentos educacionais (.md) via GitHub API tree e tópicos de estudo do README, gerando índice estruturado em JSON.

## Execução

```bash
python3 main.py
```

## Output

- `output.json` — Índice com documentos e tópicos extraídos

## Resultados (2026-08-26)

- **7 documentos** principais indexados
- **142 topic links** extraídos do README
- Graceful degradation: retorna status ERROR se API falhar

## Estrutura

```
pilots/system-design-primer-indexer/
├── main.py       # Script principal (stdlib only)
├── output.json   # Índice gerado
└── README.md     # Este arquivo
```
