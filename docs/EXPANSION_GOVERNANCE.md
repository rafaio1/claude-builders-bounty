 # Governança do Conselho de Expansão Autônoma — Agentic
 
 Este documento define o processo obrigatório para descoberta, julgamento e implementação de melhorias no repositório `/Agentic`.
 
 ## 1. Processo de Julgamento (Obrigatório)
 
 Toda proposta deve passar pelas cinco etapas abaixo antes de qualquer implementação:
 
 | Etapa | Papel | Responsabilidade |
 |---|---|---|
 | 1 | **Proponente** | Problema real com evidências, afetados, hipótese, KPI mensurável e benefício esperado. |
 | 2 | **Acusação/Cético** | Tentar reprovar por duplicação, complexidade, custo, risco financeiro, segurança, privacidade, legalidade/ToS, dependência humana, conflito com outros Codex, manutenção e custo de oportunidade. |
 | 3 | **Defesa** | Menor desenho reversível, mitigações, rollback, limites e experimento. |
 | 4 | **Auditor** | Validar evidências no servidor, Git, processos, ledgers, testes e fontes oficiais. Separar fato, estimativa e hipótese. Receita potencial ≠ realizada. |
 | 5 | **Juiz** | Veredito único: `REJEITAR`, `ADIAR`, `PILOTAR` ou `APROVAR_IMPLEMENTACAO`. Incluir votos, objeções, confiança e condições de promoção/reversão. |
 
 ## 2. Gates de Aprovação
 
 - Problema comprovado com evidência atual.
 - Sem duplicação de esforço existente.
 - KPI definido e critério de parada claro.
 - Rollback testável.
 - Custo e risco limitados.
 - Primeiro passo em sandbox/shadow/paper ou piloto zero/baixo custo.
 
 ### Proibições Absolutas
 Fraude, spam, evasão, acesso não autorizado, violação de escopo, exposição de `.env` ou secrets.
 
 ### Tiers de Autonomia
 | Tier | Descrição | Exemplos |
 |---|---|---|
 | **TIER 0** | Autônomo | Documentação, reconciliação, testes, observabilidade, validações internas. |
 | **TIER 1** | Piloto autônomo | Scanners passivos, simulações, dry-runs. |
 | **TIER 2** | Confirmação humana obrigatória | Trading real, credenciais, segurança ofensiva, dados bancários, comportamento externo. |
 
 ## 3. Concorrência e Git
 
 - Reconciliar `git status` e processos antes de editar.
 - Não sobrescrever mudanças alheias.
 - Preferir arquivos novos ou módulos sem dono.
 - Para código: branch/worktree isolado do MESMO repo, stage apenas arquivos próprios, testes proporcionais, integrar somente sem conflito.
 - Fonte da verdade única: `/Agentic`.
 
 ## 4. Artefatos Obrigatórios
 
 | Caminho | Conteúdo |
 |---|---|
 | `docs/EXPANSION_GOVERNANCE.md` | Este documento. |
 | `data/expansion/proposals.jsonl` | Registro imutável de propostas. |
 | `data/expansion/verdicts.jsonl` | Vereditos com votos e condições. |
 | `data/expansion/current_state.json` | Snapshot do estado auditado. |
 | `data/expansion/experiments/` | Resultados de pilotos e testes. |
 
 Cada registro deve conter: `proposal_id`, `timestamp`, evidências, `tier`, KPI, custo máximo, risco máximo, rollback, veredito, implementação, testes e resultado.
 
 ## 5. Loop Operacional
 
 1. Inventariar sistema e Codex ativos.
 2. Identificar gargalos concretos com evidência.
 3. Julgar no máximo uma proposta por ciclo.
 4. Executar o menor incremento aprovado.
 5. Medir KPI; promover, reverter ou arquivar.
 6. Repetir. Sem proposta boa, melhorar auditoria/observabilidade.
 7. Não marcar `complete`/`blocked` por falta temporária. Sem sleeps longos.
 
 ## 6. Estado Atual (Baseline 2026-08-26)
 
 - **Integridade**: `integrity.json` falha em `git_clean` (working tree suja) e `services_active` (loop failed, timers inactive).
 - **Trading**: V23d-v5 XRP REAL rodando inline (PID 3998155), state zerado após restart recente. Ledger mostra trades reais AVAX/DOGE/XRP com PnL misto.
 - **Improve pipeline**: 5 developing, 17 blocked, 196 pending, 23 applied. Proposta `imp-20260816-restaurar-git-clean` já existe em `developing`.
 - **Serviços ativos**: `agentic-portal.service` (8767), `tradingagents-portal.service`. Loop principal falhou.
 - **Untracked files**: scanners (galxe, hats, layer3, rabbithole) e revenue dirs não commitados nem gitignored.
