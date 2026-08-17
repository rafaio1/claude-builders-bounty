# Improve pipeline

Gestão de filas: map enfileira, develop despeja no **Claude CLI** (modelos GhostCLI), review aplica em `main`.

```
improve/map/<stamp>     mapper (GhostCLI JSON)  → ledger em main
improve/dev/<id>        Claude CLI + GhostCLI   → implementa no disco; pytest
main                    reviewer (GhostCLI)     → merge + restart do loop
```

## Executores

1. **map** (`agentic-improve-map.timer`, horário): censo (Playwright, Claude CLI, GhostCLI, Bybit só booleanos) → GhostCLI devolve JSON de bottlenecks/melhorias → `improve/ledger.json` + `CURRENT.md`.
2. **develop** (`agentic-improve-dev.timer`, ~20 min): pega `pending` de maior prioridade, reclama branch `improve/dev/<id>` e **despeja o prompt no Claude CLI**. Auth/modelos via GhostCLI (`ANTHROPIC_BASE_URL=https://ghostcli.dev`, `GHOSTCLI_MODEL` / `claude-sonnet-5[1m]`). Claude edita o disco com ferramentas; o pipeline só valida paths, pytest e commit. Recusa `.env`, `data/`, secrets e `AGENTIC_LIVE_TRADE=1`.
3. **review** (`agentic-improve-review.timer`, ~20 min): Ghost revisa o diff contra `main`. Só então merge + restart `agentic-loop.service`.

## Comandos

```bash
.venv/bin/python -m agentic status
.venv/bin/python -m agentic improve status
.venv/bin/python -m agentic improve map
.venv/bin/python -m agentic improve develop
.venv/bin/python -m agentic improve review
.venv/bin/python -m agentic improve review --no-apply
.venv/bin/python -m agentic integrity
.venv/bin/python -m agentic aro status
scripts/local-control.sh {install|start|stop|restart|status|logs}
```

### Claude CLI + GhostCLI

O executor **develop** invoca o **Claude CLI** como ferramenta de edição; a autenticação e a seleção de modelo passam pelo proxy **GhostCLI** (`ANTHROPIC_BASE_URL=https://ghostcli.dev`, `GHOSTCLI_MODEL`). O operador não chama o Claude CLI diretamente — o pipeline injeta o prompt da proposta e valida apenas paths, pytest e commit.

Gates determinísticos valem mais que a IA: sem trade live, sem secrets, sem PoC. O loop de execução continua com `AGENTIC_LIVE_TRADE=0`.

## Integridade

`agentic integrity` (timer a cada 15 min) confirma que a versão em execução é `main` limpa, que o loop systemd aponta para `python -m agentic loop`, que o kill switch está em `AGENTIC_LIVE_TRADE=0` e que branches `improve/dev/*` não carregam scripts mortos. O relatório vai para `data/integrity.json`.

### Quando `git_clean` falha

1. **Não** use `git reset --hard`, `git checkout --`, `git clean -fd`, `--no-verify` nem force. Não commite `.env`, `data/`, locks ou secrets. Não ligue trade live.
2. **Lixo untracked**: apagar ou acrescentar no `.gitignore`.
3. O mapper emite um bottleneck p1 **por fatia**. O develop só versiona os `files_hint` daquela fatia.
4. Se o review rejeitar ou o pytest falhar, a proposta **volta a `pending`** com `review_feedback`. Depois de 3 requeues fica `rejected`/`blocked`.
