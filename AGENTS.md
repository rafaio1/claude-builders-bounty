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

### Regra de seleção (obrigatória)

Para **navegação headless básica** (abrir URL, snapshot, click, type, screenshot, fechar),
use **sempre** `playwright-cli`. O MCP só é permitido quando a tarefa exige:

- inspeção de DOM complexa (árvores profundas, atributos dinâmicos, shadow DOM);
- estado persistente entre múltiplas interações que o CLI não suporta;
- avaliação de JavaScript no contexto da página com retorno estruturado.

Se a tarefa pode ser resolvida com um único comando do CLI, **não invoque o MCP**.
O MCP consome significativamente mais tokens e aumenta a latência do tick.

### CLI (preferir — menos tokens)

```bash
playwright-cli open https://example.com
playwright-cli snapshot
playwright-cli click e1
playwright-cli type "texto"
playwright-cli screenshot
playwright-cli close
```

Skill: `playwright-cli` (`~/.claude/skills/playwright-cli` e `~/.agents/skills/playwright-cli`).

### MCP (apenas quando necessário)

Servidor `playwright` via `playwright-mcp --headless --isolated --no-sandbox`.
Use exclusivamente para os casos listados acima; documente no trace por que o CLI não foi suficiente.

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

A versão em execução é `main`/`master` via `agentic-loop.service`. Map/develop/review da GhostCLI vivem em `improve/*` e só entram no loop depois do review. **Develop** é fila → Claude CLI com modelos GhostCLI (`ANTHROPIC_BASE_URL`). Kill switch: `AGENTIC_LIVE_TRADE=0`. Constituição ARO: `ARO.md` (não enfraquecer; participação 20% imutável; sem contacto comercial até autorização). Portal: `agentic-portal.service` na porta 8767.

```bash
.venv/bin/python -m agentic improve status
scripts/local-control.sh status
```

Ver `improve/README.md`.
