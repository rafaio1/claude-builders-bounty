# He4rt 4noobs Learning Path

**Status:** FUNCTIONAL_MVP | **Tier:** TIER0 | **Zero-Capital:** ✅

## Descrição
Gera um índice estruturado de trilhas de aprendizado a partir dos repositórios da comunidade [He4rt/4noobs](https://github.com/He4rt/4noobs), ordenado por relevância (stars).

## Estratégia Zero-Capital
- Usa apenas GitHub API pública (sem token)
- stdlib Python (`urllib`, `json`)
- Hospedagem estática gratuita (GitHub Pages / Cloudflare Pages) para futura interface web
- Monetização futura via certificados verificados ou mentoria (pago pelo usuário final, não pelo laboratório)

## Como executar
```bash
python3 main.py
```

## Output
Arquivo `learning_path_index.json` com metadados dos repositórios (descrição, stars, linguagem, URL).

## Arquivos
- `main.py` — Script principal
- `learning_path_index.json` — Índice gerado automaticamente

## Validação
- ✅ Execução exitosa (exit code 0)
- ✅ Datetime timezone-aware (UTC)
- ✅ 2 módulos válidos indexados (outros repos retornaram 404 - nomes podem variar)
- ✅ Scaffolding verificado na auditoria

## Notas
Alguns repositórios esperados (python4noobs, javascript4noobs, etc.) retornaram 404. A lista `REPOS_INDEX` no `main.py` deve ser atualizada conforme os nomes reais forem mapeados. O wrapper já trata falhas gracefully.
