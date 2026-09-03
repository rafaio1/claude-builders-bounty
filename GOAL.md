# Unified Capital Goal

## Objective

Grow provider-confirmed work into **USD 20,000,000 settled and reconciled in Wise** through autonomous, evidence-based operations on this server.

The goal is not advanced by points, drafts, advertised values, open PRs, accepted claims, email text, aggregate wallet balances, or provider confirmation without transaction evidence. Only reconciled settlement counts as realized revenue.

## Durable execution

1. `capital-orchestrator-v4.service` remains active and performs a bounded GhostCLI cycle approximately hourly.
2. `agentic-revenue-control-plane-v2.service`, the bounty reconcilers, BugHunter, Gmail scanners, Telegram bridge, proposal gate, integrity guard, and watchdog continue their verified work under systemd.
3. Codex and Claude automation use only the loopback ApiFable alias `ghostcli-auto[1m]`. ApiFable owns the smartest-first fallback order. Server automation must not use an OpenAI login or OpenAI API.
4. Legacy and current bounty records are reconciled by deterministic scripts. LLMs may write idempotent proposals only; they cannot write canonical ledgers, invent financial identifiers, or mark settlement.
5. Every new receive-ledger recovery event must provide safe recovery instructions through Telegram and email without exposing seeds, private keys, tokens, or credentials.
6. GitHub PR notifications are archived and labeled, never deleted. Bounty-like email is retained as an untrusted signal until public provider evidence verifies it.
7. Discovery prioritizes any large bounty by expected net value in Wise, payment/rail confidence, costs, risk, and time; USDC may receive a route-simplicity bonus but is not a requirement.
8. Any asset without a proven autonomous path to Wise stays `route_pending` and emits one informational Telegram/email route-options notice with concrete exchange/swap/bridge/conversion possibilities, evidence requirements, costs, risks, and reason codes; it is never rejected or counted as settled for this reason.

## Autonomous operating policy

- Continue safe work without waiting for a person. Retry transient provider failures with bounded backoff while services remain supervised.
- No stage may assign work to a person. Telegram and email are informational only and state that human action is unnecessary. CAPTCHA, KYC, personal identity creation, personal acceptance, or another non-automatable gate makes that opportunity ineligible for this autonomous flow; record it, monitor only if useful, and continue elsewhere.
- Prefer verified, in-scope opportunities with an explicit payment rail and eligibility for the `rafaio1` identity. Rank any large bounty by expected net Wise value plus payment/rail confidence, costs, risk, and time. USDC may receive a bonus only for a simpler verified route; it is never required or inferred. Require the complete exact-asset/network path through self-custody, bridge/swap/exchange as needed, Bybit JIT or an alternative, conversion/fiat, and Wise. An incomplete route stays `candidate` or `route_pending` without rejecting an otherwise eligible bounty.
- Keep `candidate`, `submitted`, `accepted`, `payment_queued`, `provider_confirmed`, `wallet_received`, and `settled` distinct.
- Fail closed on ambiguous ownership, scope, payout evidence, receive address, network, txid, conversion route, or Wise reconciliation.
- This goal is standing authority to collect earned payouts and move them through verified, user-owned receive, exchange, and Wise rails when deterministic gates confirm ownership, asset, network, memo/tag, deposit availability, minimums, fees, liquidity, destination, and end-to-end reconciliation. Never guess a rail or bypass a failed gate.
- Every eligible crypto bounty receives first to an exact-asset-and-network self-custody wallet. Bybit is only a current JIT onward destination after wallet receipt; absent support or a rotated exchange address never rejects the bounty. `settled` requires the complete `settlement_scope`, not merely an inbound transaction.
- Execute a route automatically only after every technical and legal link, current destination, exact asset/network, liquidity, costs, fees, and causal identifiers are validated. A route-options alert may explain alternatives but must not make human action a required stage.
- Claims, fixes, PRs, and vulnerability reports may be submitted autonomously only for the `rafaio1` identity, inside current published scope and safe-harbor terms, after independent evidence and quality validation. Otherwise fail closed and continue another eligible opportunity.
- Trading is optional, not presumed profitable. It may use only reconciled user capital behind deterministic exposure, loss, liquidity, protection, and rollback limits after reproducible out-of-sample validation; never represent a backtest as a guarantee.
- Never restart legacy trading or bounty processes merely because an old PID, balance, deadline, or status file mentions them. Reconcile live provider state first.
- Continue monitoring external blockers automatically and notify only on a meaningful change, recovery, settlement, or critical failure.

## Success criterion

The goal is complete only when a provider/exchange trail and Wise API or statement reconcile at least **USD 20,000,000 settled**. Until then, services continue autonomously and reports state the realized amount truthfully.
