 # Agentic Integration Context
 
 ## Objetivo
 Repositório privado de integração contínua para o projeto Agentic.
 Este documento serve como ponto de entrada para qualquer nova IA ou agente
 que precise entender o estado, a arquitetura e as decisões deste repositório.
 
## Estado Atual (2026-08-26T12:30Z)
 - **Remoto**: https://github.com/rafaio1/agentic-integration.git (PRIVATE)
 - **Branch principal**: master
- **Último commit**: b02e883 docs: update FEATURES inventory with cadaf36 integrations
- **Penúltimo commit**: cadaf36 feat: integrate revenue streams, products, templates and p2p-stack init
- **Arquivos rastreados**: src/, api/, docs/, prompts/, skills/, orchestrator/, scripts/, tools/, products/, revenue/, templates/, workspace/, p2p-stack/init_lnd_wallet.sh
- **Features integradas neste ciclo**: bounty_automation_template, email-cleanup, content-monetization, micro-saas manifests, web3 bugbounty templates, V23D risk filters doc, p2p-stack LND init, workspace orchestrators
- **Testes**: 35/35 passando (telegram_gate + triage_contract)
- **Remoto validado**: rafaio1/agentic-integration (PRIVATE=true)
 - **Arquivos rastreados**: src/, api/, docs/, prompts/, skills/, orchestrator/, scripts/, tools/
 - **Arquivos NÃO rastreados (intencional)**: .env, data/, state/, logs/, *.pid, *.log, ledger.jsonl, .venv/, node_modules/, __pycache__/, .agentic*.lock, arb_dashboard.html, typescript/, build/, workspace/, bounties/, bugbounty/, revenue/, p2p-stack/, mt5_bridge/, wise_liquidity/, pr_freelance/, improve/, .agents/, .claude/, .codex/, .config/, .playwright*/
 
 ## Decisões Técnicas
 1. **Segurança primeiro**: Nenhum segredo, token, chave ou credencial é versionado.
    O arquivo `scripts/recon_p2p.py` foi excluído do commit inicial por conter
    referência a api_key em string concatenada (mesmo sendo placeholder).
 2. **Artefatos efêmeros**: Logs, PIDs, estados JSON runtime e caches são ignorados.
 3. **Dados locais**: Diretórios data/, state/, ledger.jsonl contêm dados operacionais
    sensíveis ou voláteis — nunca versionar.
 4. **Ambientes virtuais**: .venv/ e node_modules/ são regeneráveis; não versionar.
 5. **Locks de agente**: .agentic.lock e .agentic-improve.lock são estado local de
    outros agentes Orca; não devem ser compartilhados via git.
 
 ## Estrutura Versionada
 - `src/`: Código-fonte principal (Python portal, plugins TypeScript)
 - `api/`: Definições de API e erros
 - `docs/`: Documentação de arquitetura, operações, segurança, changelog
 - `prompts/`: Prompts de missão e configuração de agentes
 - `skills/`: Skills Codex/Orca reutilizáveis
 - `orchestrator/`: Bots de trading, scalpers, snipers, backtests (código apenas)
 - `scripts/`: Scripts de automação, bounty, revenue, P2P (código apenas)
 - `tools/`: Ferramentas auxiliares (gmail, telegram, decision router)
 
 ## Próximas Ações
 1. Revisar arquivos untracked restantes (179) para identificar features maduras
 2. Verificar se há testes automatizados para adicionar ao CI
 3. Criar runbook de operação em docs/RUNBOOK.md
 4. Estabelecer inventário de features em docs/FEATURES.md
 5. Monitorar outros chats Orca com goals ativos para reconciliação
 
 ## Limitações Conhecidas
 - Sem CI/CD configurado ainda
 - Sem testes automatizados no repositório
 - Alguns scripts podem depender de variáveis de ambiente não documentadas
 - Histórico anterior do repo TentOfTrials-bounty-67 não foi migrado (era público)
