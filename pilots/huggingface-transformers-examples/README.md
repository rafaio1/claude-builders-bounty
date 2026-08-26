 # HuggingFace Transformers Education Indexer

 > **Status:** FUNCTIONAL_MVP (TIER0)
 > **Pipeline:** Laboratório de Receita Zero-Capital
 > **Zero-Capital:** Sim — apenas stdlib Python + GitHub API pública

 ## Visão Geral

 Este MVP indexa ativos educacionais e exemplos do repositório
 [huggingface/transformers](https://github.com/huggingface/transformers),
 focando em subconjuntos estruturados (`examples/`, `notebooks/`, `docs/source/`)
 em vez do repo inteiro.

 O padrão demonstrado é **Large-Repo Structured Subset Discovery**, aplicável a
 qualquer repositório monolítico com pastas especializadas.

 ## Execução

 ```bash
 cd /Agentic/pilots/huggingface-transformers-examples
 python3 main.py
 ```

 ### Saída Esperada

 - `education_index.json` — índice multi-seção com contagem por pasta
 - Console log com timestamp UTC e amostra dos itens encontrados

 ## Estrutura do Índice

 | Campo          | Descrição                                    |
 |----------------|----------------------------------------------|
 | `sections`     | Dict com chave=nome da seção, valor=lista    |
 | `total_items`  | Contagem total de itens indexados            |
 | `target_paths` | Lista de caminhos consultados                |

 ## Restrições e Notas

 - **Foco Intencional:** Não tenta indexar o repo inteiro (>10k arquivos).
   Foca em pastas com valor educacional direto.
 - **Rate Limit:** API pública sem token (60 req/h/IP).
 - **Sem Dependências Externas:** Apenas stdlib Python.

 ## Critério de Promoção TIER1

 Para sair de TIER0 → TIER1:
 1. Scaffolding funcional verificado ✅
 2. Execução bem-sucedida documentada
 3. Autorização explícita para execução comercial
 4. Caminho de monetização definido (ex: curso, template marketplace, etc.)

 ## Relacionados

 - `langflow-workflow-templates` — padrão similar aplicado a templates
 - Proposta original: `data/expansion/proposals.jsonl` (buscar por `method_350`)
