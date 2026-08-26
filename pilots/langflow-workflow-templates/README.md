 # LangFlow Workflow Templates Indexer

 > **Status:** FUNCTIONAL_MVP (TIER0)
 > **Pipeline:** Laboratório de Receita Zero-Capital
 > **Zero-Capital:** Sim — apenas stdlib Python + GitHub API pública

 ## Visão Geral

 Este MVP indexa os *starter projects* (templates de workflow) do repositório oficial
 [langflow-ai/langflow](https://github.com/langflow-ai/langflow), extraindo metadados
 estruturados para uso futuro em marketplaces, catálogos ou sistemas de recomendação.

 O padrão demonstrado aqui é **Template Discovery via Public Repo**, aplicável a qualquer
 ecossistema open-source que exponha assets padronizados em diretórios conhecidos.

 ## Execução

 ```bash
 cd /Agentic/pilots/langflow-workflow-templates
 python3 main.py
 ```

 ### Saída Esperada

 - `workflow_templates_index.json` — índice estruturado com nome, path, SHA, tamanho e URL
 - Console log com timestamp UTC e contagem de templates encontrados

 ## Estrutura do Índice

 | Campo            | Descrição                                      |
 |------------------|------------------------------------------------|
 | `name`           | Nome do template (sem extensão)                |
 | `filename`       | Nome do arquivo `.json` original               |
 | `path`           | Caminho no repositório                         |
 | `url`            | Link direto para o arquivo no GitHub           |
 | `sha`            | Hash curto (8 chars) do commit                 |
 | `size_bytes`     | Tamanho do arquivo em bytes                    |

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
 4. Caminho de monetização definido (ex: API paga, marketplace listing, etc.)

 ## Relacionados

 - `hermes-agent-skill-wrapper` — mesmo padrão de indexação aplicado a skills de agente
 - `frontendbr-vagas-alert-bot` — digest automatizado via GitHub API
 - Proposta original: `data/expansion/proposals.jsonl` (buscar por `LANGFLOW-WORKFLOW-TEMPLATES`)
