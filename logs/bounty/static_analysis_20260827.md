# Análise Estática CDP Onramp — Vetores de Teste (Fail-Closed)
## Data: 2026-08-27T16:30 UTC
## Status: PLANEJAMENTO CONCLUÍDO (SEM EXECUÇÃO DE TESTES)

## Fonte Documental
- `/tmp/cdp_session_token_spec_raw.md` — OpenAPI 3.0.3 POST /v1/token
- `/tmp/cdp_onramp_security_reqs.md` — Security Requirements (CORS, Domain Allowlist)
- `/tmp/cdp_onramp_reference.md` — Reference docs (redirectUrl, sessionToken)
- `/tmp/h1_coinbase_policy.txt` — Política oficial H1 (revalidada)

## API Mapeada: POST https://api.developer.coinbase.com/onramp/v1/token
**Auth:** Bearer JWT (server-only)
**Rate Limit:** ≤5 req/s operacional; header X-HackerOne-Research: rafaio

### Parâmetros Identificados
| Campo | Tipo | Required | Notas de Segurança |
|---|---|---|---|
| addresses[] | array<AddressEntry> | YES | address + blockchains obrigatórios |
| addresses[].address | string | YES | Wallet destination (ETH/BTC/etc) |
| addresses[].blockchains | string[] | YES | Networks válidas p/ endereço |
| assets[] | string[] | NO | Filtro de tickers (BTC, ETH, USDC) |
| destinationWallets[] | array | DEPRECATED | Legacy param; still accepted? |
| clientIp | string | NO | "Do not trust X-Forwarded-For" |

### RedirectUrl (via URL query, não no token body)
- Validado contra Domain Allowlist no CDP Portal
- Formatos: `https://app.com`, `https://*.domain.com`, `custom-scheme://path`
- Se não match → redirect silenciosamente ignorado (transação completa sem redirecionar)

## Vetores de Análise Estática (Testáveis em Produção com Dados Próprios)

### V1: Parameter Confusion — addresses vs destinationWallets
**Hipótese:** Enviar ambos `addresses` (novo) e `destinationWallets` (deprecated) simultaneamente pode causar comportamento indefinido.
- Qual campo tem precedência?
- Pode bypassar validação de network se deprecated for processado primeiro?
- **Teste:** POST com ambos os campos preenchidos com valores conflitantes.
- **Risco:** Baixo (própria conta, próprios endereços).

### V2: clientIp Spoofing Validation Gap
**Hipótese:** A doc diz "Do not trust X-Forwarded-For" mas o campo `clientIp` é opcional no body.
- O que acontece se `clientIp` for omitido? Quote/session ainda funciona?
- Se fornecido, é realmente vinculado à sessão ou apenas logado?
- Pode um atacante criar tokens sem binding de IP e usá-los de qualquer origem?
- **Teste:** Criar token sem clientIp, tentar usar de IP diferente.
- **Nota:** Este vetor pode ser "by design" (client-side enforcement); verificar resposta.

### V3: Domain Allowlist Bypass via Scheme Confusion
**Hipótese:** Wildcard `https://*.domain.com` pode não validar scheme corretamente.
- `http://evil.domain.com` passa quando allowlist tem `https://*.domain.com`?
- `custom-scheme://anything` pode ser injetado como redirectUrl?
- Path traversal após wildcard: `https://*.domain.com/../evil`?
- **Teste:** Manipular redirectUrl na URL final (não no token creation).
- **Pré-requisito:** Token válido criado com endereço próprio.

### V4: Asset/Network Mismatch in addresses[]
**Hipótese:** Especificar blockchain não suportada para um endereço pode causar erro informativo excessivo ou fallback inseguro.
- `addresses: [{address: "0x...", blockchains: ["bitcoin"]}]` (ETH addr em BTC network)
- Resposta vaza internal routing logic?
- Permite comprar asset em network errada?
- **Teste:** Combinações inválidas address/blockchain.

## Dedupe Status
- ⚠️ H1 GraphQL unauthenticated → NÃO foi possível verificar report #3972388
- Web search upstream não retornou evidência pública destes vetores específicos
- **Decisão:** Proceder com análise estática e testes controlados; documentar cada probe com idempotency key única
- Se qualquer teste retornar resultado sugestivo de duplicate conhecido → STOP imediato e pivotar

## Regras Operacionais Reforçadas
1. Apenas produção (`api.developer.coinbase.com`); sandbox/testnet/staging = OOS
2. Own accounts/wallets only; zero dados de terceiros
3. Max 5 req/s; backoff exponencial em 429/401/403
4. Header `X-HackerOne-Research: rafaio` em todas as requests
5. Não submeter report até dedupe confirmado por fonte alternativa
6. Log completo em ledger.json com chave `cdp-onramp-{vector}-{date}`

## Próximo Passo Autorizado
Executar V1 (Parameter Confusion) com wallet de teste própria após confirmação final do escopo neste ciclo.
