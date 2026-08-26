# Awesome-Selfhosted Indexer

**Status:** SCAFFOLD_OK (FUNCTIONAL_MVP)  
**Category:** Self-Hosted Software Discovery  
**Zero-Capital:** ✅  

## Descrição

Indexador estruturado do repositório [awesome-selfhosted/awesome-selfhosted](https://github.com/awesome-selfhosted/awesome-selfhosted). Extrai entradas de software self-hosted open-source com metadados de categoria, URL e descrição.

## Fonte de Dados

- **URL:** `https://raw.githubusercontent.com/awesome-selfhosted/awesome-selfhosted/master/README.md`
- **Licença:** MIT (redistribuição permitida com atribuição)
- **Rate Limit:** GitHub Raw CDN, sem autenticação necessária
- **Atualização:** Sob demanda (re-executar `main.py`)

## Output

- **Arquivo:** `selfhosted_index.json`
- **Campos:** name, url, description, category
- **Total entries:** ~1192 (varia conforme upstream)

## Uso

```bash
python3 main.py
```

## Monetização Potencial (TIER1 - Requer Autorização)

- Curated B2B self-hosted alternatives database
- Migration consulting lead generation
- Enterprise self-hosted software comparison SaaS
