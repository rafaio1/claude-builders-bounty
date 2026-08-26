 # Public APIs Collective Indexer

 > **Status:** FUNCTIONAL_MVP (TIER0)
 > **Pipeline:** Laboratório de Receita Zero-Capital
 > **Zero-Capital:** Sim — apenas stdlib Python + raw GitHub content

 ## Visão Geral

 Este MVP indexa APIs públicas gratuitas do repositório
 [public-apis/public-apis](https://github.com/public-apis/public-apis),
 parseando tabelas markdown do README para extrair metadados estruturados
 (nome, descrição, categoria, auth, HTTPS, URL).

 O padrão demonstrado é **Markdown Table API Directory Parsing**, aplicável
 a qualquer diretório de recursos mantido em READMEs com tabelas padronizadas.

 ## Execução

 ```bash
 cd /Agentic/pilots/public-apis-indexer
 python3 main.py
 ```

 ### Saída Esperada

 - `apis_index.json` — índice com 1700+ APIs em 50+ categorias
 - Console log com timestamp UTC, contagem e top categorias

 ## Estrutura do Índice

 | Campo          | Descrição                                    |
 |----------------|----------------------------------------------|
 | `name`         | Nome da API                                  |
 | `description`  | Descrição curta (max 200 chars)              |
 | `category`     | Categoria extraída do header markdown        |
 | `auth`         | Tipo de autenticação (OAuth, apiKey, etc.)   |
 | `https`        | Suporte a HTTPS (Yes/No)                     |
 | `url`          | URL direta da documentação da API            |

 ## Restrições e Notas

 - **Parsing Sensível:** Depende da estrutura de tabela do README. Se o formato
   mudar, o parser pode precisar de ajuste. Graceful degradation gera índice vazio.
 - **Rate Limit:** Fetch único de raw content. Sem risco de rate limit.
 - **Sem Dependências Externas:** Apenas `json`, `urllib`, `re`, `datetime`.
 - **Idempotente:** Re-executar sobrescreve o índice anterior.

 ## Critério de Promoção TIER1

 Para sair de TIER0 → TIER1:
 1. Scaffolding funcional verificado ✅
 2. Execução bem-sucedida documentada
 3. Autorização explícita para execução comercial
 4. Caminho de monetização definido (ex: API discovery platform, curated bundles)

 ## Relacionados

 - `langflow-workflow-templates` — padrão similar de indexação de assets
 - Proposta original: `data/expansion/proposals.jsonl` (buscar por `method_351`)
