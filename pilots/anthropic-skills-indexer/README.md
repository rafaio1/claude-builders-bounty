 # Anthropic Skills Registry Indexer

 > **Status:** FUNCTIONAL_MVP (TIER0)
 > **Pipeline:** Laboratório de Receita Zero-Capital
 > **Zero-Capital:** Sim — apenas stdlib Python + GitHub API pública

 ## Visão Geral

 Este MVP indexa as skills oficiais do repositório
 [anthropics/skills](https://github.com/anthropics/skills), extraindo metadados
 estruturados das pastas de skill para uso futuro em catálogos, marketplaces ou
 sistemas de recomendação de capacidades de agente.

 O padrão demonstrado é **First-Party Skill Registry Discovery**, com alto valor
 sinalizado por ser fonte oficial da Anthropic.

 ## Execução

 ```bash
 cd /Agentic/pilots/anthropic-skills-indexer
 python3 main.py
 ```

 ### Saída Esperada

 - `skills_index.json` — índice estruturado com nome, path, SHA e URL de cada skill
 - Console log com timestamp UTC e contagem de skills encontradas

 ## Estrutura do Índice

 | Campo   | Descrição                                |
 |---------|------------------------------------------|
 | `name`  | Nome da skill (nome da pasta)            |
 | `type`  | Tipo do entry (sempre `dir` para skills) |
 | `path`  | Caminho no repositório                   |
 | `url`   | Link direto para a pasta no GitHub       |
 | `sha`   | Hash curto (8 chars) do commit           |

 ## Restrições e Notas

 - **Rate Limit:** Usa API pública sem token. Respeita limites padrão (60 req/h/IP).
   Para produção, adicionar `GITHUB_TOKEN` no header.
 - **Graceful Degradation:** Se o endpoint mudar ou retornar erro, o script não falha —
   gera índice vazio com aviso no console.
 - **Sem Dependências Externas:** Apenas `json`, `urllib`, `datetime` da stdlib.
 - **Idempotente:** Re-executar sobrescreve o índice anterior com novo timestamp.

 ## Critério de Promoção TIER1

 Para sair de TIER0 → TIER1, este MVP precisa:
 1. Scaffolding funcional verificado ✅
 2. Execução bem-sucedida documentada
 3. Autorização explícita para execução comercial
 4. Caminho de monetização definido (ex: skills marketplace, capability API, etc.)

 ## Relacionados

 - `hermes-agent-skill-wrapper` — mesmo padrão aplicado a skills do NousResearch
 - `langflow-workflow-templates` — padrão similar aplicado a templates de workflow
 - Proposta original: `data/expansion/proposals.jsonl` (buscar por `method_349`)
