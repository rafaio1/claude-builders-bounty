 # Runbook de Operação do Integrador
 
 > Meta Aspiracional: 20.000.000 USDT liquidados e reconciliados
 > Repositório: `rafaio1/agentic-integration` (PRIVATE)
 
 ## 1. Ciclo de Integração Contínuo
 
 ```
 [Inspecionar git status] → [Classificar arquivos] → [Scan de secrets]
        ↓                          ↓                        ↓
 [Ignorar runtime/state]   [Maduro? → Testar]      [Segredo? → Excluir/Bloquear]
        ↓                          ↓                        ↓
 [Atualizar .gitignore]    [Documentar + Commit]   [Registrar bloqueio]
        ↓                          ↓
 [Push seguro]          [Atualizar FEATURES.md]
 ```
 
 ## 2. Checklist Pré-Push Obrigatório
 
 - [ ] `gh repo view rafaio1/agentic-integration --json isPrivate` retorna `true`
 - [ ] `git remote -v` aponta para `rafaio1/agentic-integration.git`
 - [ ] `grep -rE` com padrão de secrets retorna vazio nos arquivos staged
 - [ ] Nenhum `.env`, `.key`, `.pid`, `.log`, `state*.json` no staging area
 - [ ] Commits são atômicos e descritivos (não WIP de outro agente)
 - [ ] Branch master está limpa de conflitos não resolvidos
 
 ## 3. Estados Operacionais
 
 ### `active`
 Há features maduras ou trabalho útil disponível. Execute ciclo completo.
 
 ### `waiting_monitoring`
 Dependência externa impede progresso imediato (CI, payout, resposta de mantenedor, janela de mercado).
 - Registre evidência no commit ou issue
 - Defina backoff: próxima verificação em X horas/dias
 - Continue buscando trabalho paralelo dentro do escopo
 - **Nunca marque como complete**
 
 ### `blocked`
 Impedimento real repetido por 3+ ciclos consecutivos sem nenhuma ação útil possível.
 - Documente o bloqueio com evidências
 - Preserve plano de recuperação e monitoramento
 - Reavalie a cada ciclo se alguma ação parcial é viável
 
 ## 4. Scan de Secrets (Padrão Obrigatório)
 
 ```bash
 grep -rliE "(gho_|ghp_|sk-[a-zA-Z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN (RSA |EC )?PRIVATE KEY|password\s*=\s*[\"'][^\"']{8,}|api[_-]?key\s*=\s*[\"'][^\"']{8,}|secret\s*=\s*[\"'][^\"']{8,}|token\s*=\s*[\"'][^\"']{8,})" <diretórios-candidatos>
 ```
 
 Se detectar: **não commite**. Adicione ao `.gitignore` ou remova do staging.
 
 ## 5. Diretórios Sempre Ignorados
 
 | Padrão | Motivo |
 |--------|--------|
 | `.env`, `.env.*` | Credenciais locais |
 | `data/`, `state/`, `logs/` | Dados runtime efêmeros |
 | `*.pid`, `*.log`, `*.err`, `*.out` | Processos ativos |
 | `orchestrator/*state*.json` | Estado de trading ao vivo |
 | `bounties/immunefi/*/`, `bugbounty/oss/*/` | Repos externos com .git próprio |
 | `p2p-stack/mostro/`, `p2p-stack/robosats/node/(lnd\|cln\|db)/` | Chaves TLS e dados de nó |
 | `improve/traces/` | Traces de debug com paths locais |
 | `bybit_futures/data/`, `bybit_futures/logs/` | Dados de trading |
 | `workspace/bounty-exec/*/`, `workspace/high-ticket/*/`, `workspace/sparepack/` | Workspaces com .git embutido |
 | `__pycache__/`, `.venv/`, `node_modules/`, `target/` | Build artifacts |
 
 ## 6. Reconciliação Financeira
 
 - Toda receita deve ter rastro: commit → PR → merge → payout → conciliação
 - Coordene com CONTADOR antes de registrar qualquer valor
 - Potencial ≠ ganho. Só registre após liquidação confirmada
 - Dupla contagem é falha crítica: reconcilie cruzando fontes
 
 ## 7. Recuperação de Falhas
 
 | Falha | Ação |
 |-------|------|
 | Push rejeitado (auth/remote) | Verifique `gh auth status` e `git remote -v`. Não force push. |
 | Conflito de merge | Resolva preservando autoria. Nunca descarte mudanças concorrentes. |
 | Secret detectado pós-commit | Reverta o commit, sanitize, refaça. Não force push para corrigir. |
 | Testes falhando | Documente falha, não commite código quebrado. Crie issue se necessário. |
 | Repo tornado público acidentalmente | Torne privado imediatamente via `gh repo edit --visibility private`. Audite acessos. |
 
 ## 8. Auditoria Periódica
 
 A cada ciclo de integração:
 1. Verifique `docs/FEATURES.md` está atualizado
 2. Confirme `docs/INTEGRATION_RULES.md` existe e não foi alterado indevidamente
 3. Valide que nenhum arquivo sensível escapou no último push
 4. Atualize métricas de integração (commits, features, secrets bloqueados)
