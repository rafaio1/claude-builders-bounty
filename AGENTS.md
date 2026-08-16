# Agentic — ferramentas para agentes GhostCLI

Este workspace está preparado para Claude Code e Codex apontados à [GhostCLI](https://ghostcli.dev). Os agentes já têm shell, filesystem e navegador.

## Modelos

| Ferramenta | Endpoint | Modelo padrão |
|---|---|---|
| Claude Code | `ANTHROPIC_BASE_URL=https://ghostcli.dev` | `claude-sonnet-5[1m]` (subir para `claude-opus-5[1m]` / `claude-fable-5[1m]` quando a tarefa for difícil) |
| Codex CLI | provider `ghostcli` em `~/.codex/config.toml` | `claude-fable-5[1m]` |

A chave GhostCLI fica em `~/.automaton/.env` (`GHOSTCLI_API_KEY`). Não copie a chave para o git.

## Bybit (env interna)

Credenciais canónicas: `/root/.automaton/bybit-murre.env` (`BYBIT_REAL_API_KEY`, `BYBIT_REAL_API_SECRET`). Cópia de serviço: `/opt/murre/.env`. O systemd do TradingAgents já carrega o ficheiro canónico.

Neste repo elas entram só na env interna, **sem ir para o git**:

- `internal/load-env.sh` — source no shell
- `internal/env.py` — `apply()` / `bybit_credentials()` em Python
- `.env` e `.claude/settings.local.json` — gerados por `internal/sync-env.py` (modo `0600`)

Aliases disponíveis: `BYBIT_API_KEY` / `BYBIT_API_SECRET` (iguais às `BYBIT_REAL_*`). Modo: `BYBIT_MODE=live`, `BYBIT_CATEGORY=spot`.

Não imprima, não cole e não faça commit destas variáveis. Recarregar: `python3 internal/sync-env.py`.

## Navegador

Headless Chromium, isolado, `--no-sandbox` (o processo corre como root).

**Preferir CLI** (menos tokens):

```bash
playwright-cli open https://example.com
playwright-cli snapshot
playwright-cli click e1
playwright-cli type "texto"
playwright-cli screenshot
playwright-cli close
```

Skill: `playwright-cli` (`~/.claude/skills/playwright-cli` e `~/.agents/skills/playwright-cli`).

**MCP** (estado persistente da página): servidor `playwright` via `playwright-mcp --headless --isolated --no-sandbox`.

## Shell e arquivos

Claude Code e Codex já expõem Bash, leitura/escrita de arquivos, grep e git. `jq` está instalado. Use o cwd do projeto; não invente secrets — leia `~/.automaton/.env` se precisar da GhostCLI.

## Como disparar

```bash
# Claude Code → GhostCLI
cd /Agentic
claude --model 'claude-sonnet-5[1m]'

# Codex → GhostCLI
cd /Agentic
codex
```

## Autocrescimento e deploy

A versão em execução é `main`/`master` via `agentic-loop.service`. Map/develop/review da GhostCLI vivem em `improve/*` e só entram no loop depois do review. Kill switch: `AGENTIC_LIVE_TRADE=0`.

```bash
.venv/bin/python -m agentic improve status
scripts/local-control.sh status
```

Ver `improve/README.md`.
