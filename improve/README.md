# Improve pipeline

Três executores GhostCLI otimizam o próprio Agentic. A versão **em execução** é sempre a branch `main` (ou `master`).

```
improve/map/<stamp>     mapper (1h)  → merge do censo/ledger em main
improve/dev/<id>        developer    → patch + pytest; não entra em execução ainda
main                    reviewer     → Ghost review + pytest + merge + restart do loop
```

## Executores

1. **map** (`agentic-improve-map.timer`, horário): lê a saúde das ferramentas (Playwright, GhostCLI, Bybit só booleanos), o kill switch e o git, e pede à GhostCLI um mapa de bottlenecks **e** melhorias plausíveis. Grava `improve/maps/*.json`, atualiza `improve/ledger.json` e `improve/CURRENT.md`.
2. **develop** (`agentic-improve-dev.timer`, ~20 min): pega a proposta `pending` de maior prioridade, reclama em `main`, abre `improve/dev/<id>` e pede à Ghost o conteúdo completo dos arquivos. Recusa `.env`, `data/`, secrets Bybit/GhostCLI e `AGENTIC_LIVE_TRADE=1`. pytest tem de passar.
3. **review** (`agentic-improve-review.timer`, ~20 min): Ghost revisa o diff contra `main`. Só então faz merge em `main` e reinicia `agentic-loop.service`. Rejeição **não** mistura o código na versão que está rodando.

## Comandos

```bash
.venv/bin/python -m agentic status
.venv/bin/python -m agentic improve status
.venv/bin/python -m agentic improve map
.venv/bin/python -m agentic improve develop
.venv/bin/python -m agentic improve review
.venv/bin/python -m agentic improve review --no-apply
.venv/bin/python -m agentic integrity
scripts/local-control.sh {install|start|stop|restart|status|logs}
```

Gates determinísticos valem mais que a Ghost: sem trade live, sem secrets, sem PoC. O loop de execução continua com `AGENTIC_LIVE_TRADE=0`.

## Integridade

`agentic integrity` (timer a cada 15 min) confirma que a versão em execução é `main` limpa, que o loop systemd aponta para `python -m agentic loop`, que o kill switch está em `AGENTIC_LIVE_TRADE=0` e que branches `improve/dev/*` não carregam scripts mortos. O relatório vai para `data/integrity.json`.

### Quando `git_clean` falha

1. **Não** use `git reset --hard`, `git checkout --`, `git clean -fd`, `--no-verify` nem force. Não commite `.env`, `data/`, locks ou secrets. Não ligue trade live.
2. **Lixo untracked**: apagar ou acrescentar no `.gitignore`.
3. O mapper emite um bottleneck p1 **por fatia**. O develop só versiona os `files_hint` daquela fatia.
4. Se o review rejeitar ou o pytest falhar, a proposta **volta a `pending`** com `review_feedback`. Depois de 3 requeues fica `rejected`/`blocked`.
