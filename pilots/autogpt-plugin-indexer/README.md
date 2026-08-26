 # AutoGPT Plugin Registry Indexer

 > **Status:** FUNCTIONAL_MVP (TIER0)
 > **Pipeline:** Laboratório de Receita Zero-Capital
 > **Zero-Capital:** Sim — apenas stdlib Python + GitHub API pública

 ## Visão Geral

 Este MVP indexa plugins e ferramentas do ecossistema
 [Significant-Gravitas/AutoGPT](https://github.com/Significant-Gravitas/AutoGPT),
 tentando múltiplos caminhos conhecidos para localizar o diretório de plugins.

 O padrão demonstrado é **Multi-Path Plugin Discovery**, aplicável a repos grandes
 com estrutura histórica variável (classic, forge, sdk).

 ## Execução

 ```bash
 cd /Agentic/pilots/autogpt-plugin-indexer
 python3 main.py
 ```

 ### Saída Esperada

 - `plugins_index.json` — índice estruturado ou índice vazio com nota de degradação
 - Console log com timestamp UTC e caminho descoberto (ou aviso de fallback)

 ## Restrições e Notas

 - **Repo Dinâmico:** AutoGPT reestrutura frequentemente. O script tenta 3 caminhos
   conhecidos e usa graceful degradation se nenhum retornar conteúdo.
 - **Rate Limit:** API pública sem token (60 req/h/IP).
 - **Sem Dependências Externas:** Apenas stdlib Python.

 ## Critério de Promoção TIER1

 Para sair de TIER0 → TIER1:
 1. Scaffolding funcional verificado ✅
 2. Execução bem-sucedida documentada
 3. Autorização explícita para execução comercial
 4. Caminho de monetização definido

 ## Relacionados

 - `hermes-agent-skill-wrapper` — mesmo padrão aplicado a skills
 - Proposta original: `data/expansion/proposals.jsonl` (buscar por `method_348`)
