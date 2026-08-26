# FrontendBR Vagas Alert Bot

**Status:** FUNCTIONAL_MVP | **Tier:** TIER0 | **Zero-Capital:** ✅

## Descrição
Bot que monitora issues do repositório [frontendbr/vagas](https://github.com/frontendbr/vagas) e gera um digest formatado com as vagas mais recentes filtradas por palavras-chave de frontend.

## Estratégia Zero-Capital
- Usa apenas GitHub API pública (sem token para leitura básica)
- stdlib Python (`urllib`, `json`)
- Projetado para rodar via GitHub Actions (free tier)
- Estado local via `last_seen_ids.json` para deduplicação

## Como executar
```bash
python3 main.py
```

## Output
Digest em Markdown com título, link e labels das vagas encontradas nas últimas 48h.

## Arquivos
- `main.py` — Script principal
- `config.json` — Configuração de keywords e repositório
- `.github/workflows/digest.yml` — Workflow para execução automática
- `last_seen_ids.json` — Estado gerado automaticamente

## Validação
- ✅ Execução exitosa (exit code 0)
- ✅ Datetime timezone-aware (UTC)
- ✅ Digest formatado corretamente
- ✅ Scaffolding verificado na auditoria
