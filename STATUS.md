# Autonomous Capital System - Reconciled Status

**Snapshot:** 2026-09-01T19:08:00Z  
**Execution host:** `179.198.117.31`  
**Goal state:** active toward USD 20,000,000 settled in Wise; not economically complete

## Financial truth

- Realized and reconciled revenue: **USD 0.00**.
- Wise-confirmed proceeds from this flow: **USD 0.00**.
- RustChain wallet observed balance: **64 RTC**; public history shows no pending or outgoing transfer.
- Public wallet history maps exactly three records and six transactions to `wallet_received`: **14 RTC** total.
- Settled RustChain records after the full conversion/exchange/fiat scope: **0 RTC**.
- Aggregate balance not causally mapped to those three records: **50 RTC**; it is excluded from bounty proceeds, liquidation, realized revenue, and Wise calculations unless separately attributed by provider and transaction evidence.
- RTC-to-Wise route: `route_pending`; absent RTC support is an onward-route state, not a bounty rejection.
- Wise route: `route_pending`; the BRL receive account is active, but neither Bybit-origin policy acceptance nor an autonomous BRL/Pix withdrawal has been proven.
- No transfer, bridge, swap, exchange order, fiat withdrawal, Wise credit, or realized-revenue write was performed; `funds_moved=false`.

## Canonical bounty state

- 52 entries total.
- 3 `wallet_received` with 14 RTC and six public transaction identifiers.
- 20 `submitted`.
- 16 `candidate`.
- 10 `blocked_no_payment_rail`.
- 2 `blocked_no_active_opportunity`.
- 1 `blocked_conflict_unfixable`.
- Canonical ledger SHA-256 is `1fdfd5e98f423e67f7c066ee20ff5150aef89bd809b086200b72aa1ba802c292`; privileged authority, manifest, and RustChain sidecar pass `LEDGER_VALID`.
- The generic LLM helper is proposal-only and cannot promote beyond `submitted`; existing keys and the three RustChain records are guarded against duplicates or downgrades.
- Two owned legacy PRs are now reconciled as `submitted`: Warpspeed issue 5 / PR 131 has USD 660 advertised but lacks the required claim confirmation and payment rail; Quadcopter issue 6 / PR 23 has no public reward amount or verified rail. Neither is revenue.
- Three other historical classifications were disproved or blocked by current public evidence: OSINT Market is a bounty-infrastructure discussion, Kaia proposal 191 is old and assigned to another identity, and the Grainlify repository/PR endpoint returns 404. The evidence snapshot is `/Agentic/state/legacy_bounty_reconciliation_20260901.json`.

## Payout routes and large-bounty ranking

- `/Agentic/state/payout_route_map.json` is a read-only, fail-closed end-to-end map. It currently has four routes, zero `complete_verified`, four `route_pending`, zero verified Wise net, and `funds_moved=false`.
- The RTC route is not executable yet: native RTC is not listed by Bybit, and RustChain documents native RTC-to-wRTC initiation as operator/admin-assisted with `RC_ADMIN_KEY` / `X-Admin-Key`; the live public management route is therefore not machine-authorized for this server.
- Conditional post-bridge liquidity is now proven read-only on the official Raydium route. Pool `8CF2Q8nSCxRacDShbtF86XTSrYjueBMKmfdR3MLdnYzb` quoted 14 wRTC through SOL into approximately 3.6 USDC with roughly 0.77-0.81% first-leg price impact in the latest snapshots. This is market evidence only: TVL is thin, quotes are time-sensitive, and no swap was submitted.
- Official RustChain issue `#8316` requests the operator-assisted bridge for exactly the 14 causally reconciled bounty RTC to the verified Solana destination. The autonomous watcher accepts only responses whose GitHub `author_association` is `OWNER`, `MEMBER`, or `COLLABORATOR`; comments cannot themselves authorize a transfer, and the 50 unmapped RTC remain excluded.
- Bybit currently verifies USDT/USDC deposits on the configured networks and live `USDTBRL`/`USDCBRL` spot books. The final path remains blocked because retail BRL/Pix requires an interactive account/UI/email/Google-2FA flow and Wise has not approved Bybit as an acceptable crypto-origin platform.
- The general Superteam scout validates 26 current explicit-token listings and deduplicates 13 overlaps with the USDC-only scout. The top advertised face values are 10,000 USDG, 10,000 USDG, and 8,000 USDG. They are not USD, revenue, settlement, or verified Wise net; all 26 currently have `autonomy_qualified=false`.
- Bybit currently lists neither USDG nor an `USDGBRL` spot market. USDG network and contract remain unknown until provider evidence binds the exact payout rail.

## Revenue signals and communication

- Gmail scanner examined 1,423 messages and persisted 1,171 untrusted signals with zero scanner errors.
- Three strict collection candidates remain, all already mapped to the existing RustChain issue 254 and PRs 8289/8295. MyZubster issue 617 was deterministically excluded because its official record explicitly disclaims payment.
- GitHub PR mail is labeled and archived, never deleted. The Inbox now contains zero explicit PR notifications; 84 additional PR messages were archived, while 680 non-PR messages and their 252 unread states were preserved. Bounty signals remain searchable after archive.
- All ledger recovery workflows assign every step to server controllers. The three RustChain bounties emitted verified `wallet_received` notices. Four stable self-custody wallets emitted deterministic public-only recovery and route receipts. The corrected RTC `route_pending` notice, including operator-bridge, exchange, OTC and provider-reissue possibilities, was delivered through Telegram and Gmail; the email outbox pending count is zero. Repeated planner/notifier runs emitted zero duplicates.
- RustChain bridge request `#8316` is monitored server-side. New trusted maintainer responses are delivered idempotently through Telegram and email; untrusted comments are recorded only as untrusted and cannot trigger fund movement.
- Recovery is a server responsibility. Every active recovery event has `action_required=false`, `human_action=none`, and `autonomous_recovery=true`. Identity/KYC/CAPTCHA/personal-acceptance opportunities are abandoned automatically in favor of eligible work.
- Telegram rule v6 accepts only the exact private allowlist, one-time verified wallet recovery receipts, one structured `route_options_pending` notice per route-policy revision, strictly validated RustChain bridge-maintainer responses, reconciled wallet payments/settlements, and evidence-backed real blocks. Route notices explain possible exchange/swap/bridge/conversion paths, evidence, costs, risks, and reason codes without rejecting the bounty or implying settlement; issue comments remain display-only and other routine pending changes remain silent.

## Runtime and models

- ApiFable listens only on `127.0.0.1:8787` and exposes only `ghostcli-auto[1m]`.
- Direct upstream model selection is rejected. The gateway currently selects the smartest route first and descends only on failure.
- Root Codex has no ChatGPT login or `auth.json`; retries are configured to 50 for provider requests and streams.
- Capital, watchdog, Telegram, BugHunter, revenue control plane, Gmail workers, reconcilers, integrity guard, and advisor are supervised by active/enabled systemd services or timers; the current failed-unit set is empty.
- The legacy `ghostcli-orchestrator.service` and `scalper-binance.service` are disabled and inactive so they cannot return after reboot and conflict with the current capital controller or re-enable an unreconciled trading loop.
- The continuous BugHunter loop remains unable to submit. A separate hourly autonomous admission controller may submit at most one report only after paid/open scope, safe harbor, fresh live validation, two independent evidence hashes, primary approval, a second GhostCLI review, TOCTOU re-read, and duplicate/idempotency gates. Its live state is `candidates=0`, `submitted=0`; 268 tests and 12 integrity checks pass.
- Capital uses a restricted ephemeral, tool-free, one-turn supervisory profile. Its current prompt preserves 3 `wallet_received` / 14 RTC / six txids, `conversion_pending`, zero settlement/Wise, the non-attribution of 50 unmapped RTC, and complete `settlement_scope` requirements. It ranks any large bounty by expected net Wise value, payment/rail confidence, costs, risk, and time; USDC gets only a verified route-simplicity bonus and is not required. The Claude advisor consumes only compact context without filesystem tools and does not overlap an active capital cycle.

## Active autonomous next work

1. Preserve and revalidate the three `wallet_received` RustChain records while monitoring RustChain issue `#8316` for an authenticated operator bridge protocol. Never copy a historical custody address, never create a second nonce during uncertain delivery, and do not attribute or move the remaining 50 RTC aggregate balance.
2. Continue polling all 20 submitted records for provider acknowledgment, merge, payout, and settlement evidence, while honoring claim and eligibility rules.
3. Keep financial writes behind the deterministic proposal gate and send recovery/critical-change notifications idempotently.
4. Keep cycles bounded, material-state deduplicated, and free of Codex/OpenAI account usage so GhostCLI operation remains sustainable.
5. Rank the 26 deduplicated current large-bounty candidates, and future sources, by verified expected net Wise value, payment/rail confidence, costs, risk, and time. Confirm the complete exact-asset/network route through self-custody, bridge/swap/exchange as needed, Bybit JIT or an alternative, conversion/fiat, and Wise. Keep incomplete routes pending without rejecting eligible bounties, and never count proceeds before Wise reconciliation.
6. For RTC and every other asset without a proven complete route, send idempotent Telegram/email notices for material route changes and trusted operator responses. Execute only after every technical/legal and destination/asset/network/fee gate is verified, including Wise acceptance and causal settlement reconciliation.

Old drafts, advertised bounty values, expired deadlines, stale PIDs, and historical wallet snapshots are context only. They are not current revenue and cannot authorize external actions.
