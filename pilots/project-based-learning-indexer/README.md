# Project-Based Learning Tutorials Indexer

**Status:** TIER0 — SCAFFOLD_OK  
**Type:** Indexer  
**Source:** [practical-tutorials/project-based-learning](https://github.com/practical-tutorials/project-based-learning)  
**Zero-Capital:** ✅ stdlib only, sem custos

## Descrição

Indexador automático de tutoriais baseados em projetos. Extrai tutoriais por categoria/linguagem diretamente do README via GitHub API, gerando índice estruturado em JSON.

## Execução

```bash
python3 main.py
```

## Output

- `output.json` — Índice completo com categorias, nomes, URLs e descrições

## Resultados (2026-08-26)

- **405 tutoriais** indexados
- **37 categorias** cobertas
- Graceful degradation: retorna status ERROR se API falhar

## Estrutura

```
pilots/project-based-learning-indexer/
├── main.py       # Script principal (stdlib only)
├── output.json   # Índice gerado
└── README.md     # Este arquivo
```
