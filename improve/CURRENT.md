# Agentic improve

Atualizado: 2026-08-18T16:02:31+00:00

A versão em execução é sempre `main` (ou `master`). Mapas, desenvolvimento e review vivem em branches `improve/*` e só entram na execução depois do review.

## Censo

- playwright: True
- ghostcli: True
- bybit_key: True
- bybit_secret: True
- loop interval: 90
- live_trade_disabled: True
- last_tick: 2026-08-18T15:59:03+00:00
- git_clean: ok
- dirty_paths: []

## Ghost

Mapeamento de gargalos de contexto no Playwright e latência do loop, com melhorias focadas em traces para eval e otimização de ferramentas.

## Ledger

{"pending": 203, "blocked": 16, "applied": 17, "developing": 5}

- `imp-20260816-restaurar-git-clean-working-tree-limpa-na-main` [pending/p1] Restaurar git_clean: working tree limpa na main
- `imp-20260816-restaurar-git-clean-fatia-playbook-versionar-aro` [blocked/p1] Restaurar git_clean (fatia playbook): versionar ARO.md e src/agentic/aro/
- `imp-20260816-tick-de-sa-de-n-o-deixa-estado-leg-vel-por-m-qui` [pending/p2] Tick de saúde não deixa estado legível por máquina
- `imp-20260816-review-feedback-n-o-estruturado-faz-o-develop-er` [pending/p2] review_feedback não estruturado faz o develop errar o alvo
- `imp-20260816-carga-de-credenciais-sem-valida-o-expl-cita-do-a` [pending/p3] Carga de credenciais sem validação explícita do arquivo canônico
- `imp-20260816-tools-padronizar-navegador-via-playwright-cli-em` [pending/p2] [tools] Padronizar navegador via playwright-cli em vez de MCP
- `imp-20260816-ai-traces-sanitizados-da-ghostcli-eval-do-review` [blocked/p2] [ai] Traces sanitizados da GhostCLI + eval do reviewer
- `imp-20260816-tools-validar-sa-das-do-censo-com-jq-antes-de-ag` [pending/p3] [tools] Validar saídas do censo com jq antes de agir
- `imp-20260816-restaurar-git-clean-motor-loop-env-cli-ghostcli` [applied/p1] Restaurar git_clean (Motor: loop, env, cli, ghostcli): working tree limpa na main
- `imp-20260816-restaurar-git-clean-outros-arquivos-sujos-workin` [blocked/p1] Restaurar git_clean (Outros arquivos sujos): working tree limpa na main
- `imp-20260816-status-do-loop-com-sa-de-de-playwright-e-ghostcl` [pending/p2] Status do loop com saúde de Playwright e GhostCLI
- `imp-20260816-documentar-skill-playwright-cli-no-mapa-de-ferra` [pending/p3] Documentar skill playwright-cli no mapa de ferramentas
- `imp-20260816-traces-sanitizados-da-ghostcli-no-improve` [pending/p2] Traces sanitizados da GhostCLI no improve
- `imp-20260816-kill-switch-agentic-live-trade-vis-vel-na-integr` [pending/p2] Kill switch AGENTIC_LIVE_TRADE visível na integridade
- `imp-20260816-tick-de-sa-de-reexecuta-probes-caras-a-cada-90s` [blocked/p1] Tick de saúde reexecuta probes caras a cada 90s
- `imp-20260816-carregamento-de-credenciais-sem-cache-e-risco-de` [applied/p1] Carregamento de credenciais sem cache e risco de vazamento em logs
- `imp-20260816-review-feedback-n-o-estruturado-favorece-alargam` [pending/p2] review_feedback não estruturado favorece alargamento de escopo
- `imp-20260816-portal-autenticado-fora-do-tick-de-sa-de` [pending/p3] Portal autenticado fora do tick de saúde
- `imp-20260816-chamadas-ghostcli-sem-timeout-podem-travar-o-tic` [pending/p3] Chamadas GhostCLI sem timeout podem travar o tick
- `imp-20260816-prefer-ncia-sistem-tica-por-playwright-cli-sobre` [pending/p2] Preferência sistemática por playwright-cli sobre MCP
