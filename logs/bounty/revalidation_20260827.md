 # Revalidação Oficial Coinbase CDP — 2026-08-27

 ## Status: ✅ REVALIDADO (FAIL-CLOSED SATISFEITO)

 ## Fonte Primária
 - **Endpoint:** `https://hackerone.com/coinbase` (Accept: application/json)
 - **Data da consulta:** 2026-08-27T14:32 UTC
 - **Arquivo raw:** `/tmp/h1_coinbase_api.json` (12469 bytes)
 - **Política extraída:** `/tmp/h1_coinbase_policy.txt` (4484 bytes)

 ## Estado do Programa
 | Campo | Valor |
 |---|---|
 | submission_state | `open` |
 | rejecting_submissions | `false` |
 | offers_bounties | `true` |
 | last_policy_change_at | 2026-07-30T20:06:14.382Z |
 | launched_publicly_at | 2014-03-28T22:09:39.471Z |

 ## Escopo Confirmado
 > "The scope of this program is Web2 products, assets and infrastructure owned by Coinbase."

 - **Web3 explicitamente fora deste programa** → deve ser submetido via Cantina.
 - CDP (Coinbase Developer Platform) é produto Web2 de propriedade da Coinbase → **dentro do escopo**.
 - Ativos específicos não listados na API pública (structured_scopes ausente); escopo definido por política textual.

 ## Safe Harbor
 > "Coinbase adheres to and supports the HackerOne Gold Standard Safe Harbor terms."

 - Pesquisadores autorizados sob os termos do HackerOne Gold Standard.
 - Submissão obrigatória via HackerOne (Web2) ou Cantina (Web3).

 ## Exclusões Explícitas (Out of Scope)
 - Social engineering
 - Username enumeration
 - Rate Limiting (non-critical issues)
 - Physical security
 - Non-security-impacting UX issues
 - Deprecated open source libraries
 - Vulnerabilities in third-party applications that integrate with Coinbase
 - Ability to abuse existing banking functionality (ACH, chargebacks)
 - Publicly available leaked credentials (rotated)
 - **Demo apps, testnet, staging environments, etc.** ← CRÍTICO: testes apenas em produção controlada ou sandbox oficial documentada

 ## Limites e Regras de Teste
 - **Rate limiting:** Não testar rate limiting como vulnerabilidade standalone (out of scope).
 - **Max req/s:** Handoff v2 especifica ≤5 req/s manual probes; header `X-HackerOne-Research: rafaio`.
 - **Dados:** Own accounts/test IDs only. NO live user data.
 - **Destrutividade:** Apenas testes não destrutivos, proporcionais, sem persistência/exfiltração/DoS.
 - **cb-mpc library:** Extreme category out of scope; hard-to-exploit = medium = out of scope.

 ## Divergências vs Handoff v2
 | Item Handoff v2 | Política Oficial Atual | Status |
 |---|---|---|
 | `*.coinbase.com` in scope | "Web2 products, assets and infrastructure owned by Coinbase" | ✅ Compatível (não contraditório) |
 | CDP APIs & SDKs in scope | Incluído como Web2 product de propriedade Coinbase | ✅ Compatível |
 | Smart Contracts (SpendPermissionManager) | Web3 findings → Cantina | ⚠️ **DIVERGÊNCIA**: smart contracts provavelmente fora do H1 program; verificar se SpendPermissionManager é considerado Web2 ou Web3 antes de testar |
 | Safe Harbor granted | Gold Standard Safe Harbor confirmado | ✅ Confirmado |
 | Max 5 req/s | Não especificado na policy oficial; handoff v2 mantém como regra operacional | ✅ Regra interna válida |
 | Header X-HackerOne-Research | Não mencionado na policy; prática recomendada para identificação | ✅ Boa prática mantida |

 ## Decisão GO/NO-GO para Próxima Fase
 - **GO** para testes Web2 contra CDP APIs/SDKs (*.coinbase.com) respeitando exclusões e limites.
 - **NO-GO** para testes contra smart contracts até confirmar elegibilidade no H1 vs Cantina.
 - **NO-GO** para qualquer teste em testnet/staging/demo (explicitamente out of scope).
 - **DEDUPE OBRIGATÓRIO** antes de submissão: cross-check com report #3972388 (Wolt duplicate lesson) e disclosures públicos.

 ## Idempotency Key Pendente
 - `h1-programs-401-20260827` registrado neste ciclo (API programs endpoint retornou 401 anteriormente; policy endpoint funcionou normalmente).

 ---
 *Gerado automaticamente pelo agente GhostCLI. Nenhuma ação de teste executada neste ciclo.*
