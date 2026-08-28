# Revenue Control Plane v2

This is the financial source of truth for `/Agentic`. Runtime executes only on `179.198.117.31`; the private repository `rafaio1/agentic-integration` is the source of code and policy.

## Truth model

- `tools/revenue_db.py` owns the canonical SQLite schema and revenue predicate.
- `tools/revenue_evidence.py` derives build receipts from official GitHub API responses.
- `tools/revenue_settlement_evidence.py` derives realized revenue from official provider responses.
- `tools/revenue_workflow.py` advances at most one receipt-gated checkpoint.
- `tools/revenue_control_plane.py` schedules verified work and advances at most one work order per cycle.
- `tools/codex_budget_governor.py` calls the same canonical revenue predicate; it has no independent ledger rule.

JSONL, email, Telegram, issue/PR labels, comments, nominal values and scanner output are never financial truth.

## Build workflow

1. `claim_confirmed`: official open issue assigned to `rafaio1`.
2. `tests_passed`: official successful GitHub Actions run for the exact head SHA.
3. `pr_published`: open non-draft PR by `rafaio1`, using the tested SHA and linking the issue.
4. `review_approved`: external `APPROVED` review by a different GitHub user whose association is `OWNER`, `MEMBER` or `COLLABORATOR`.
5. `delivery_accepted`: merge performed by a third party.

A merge proves delivery only. It does not prove that the bounty platform still owes money, and it never creates a receivable by itself.

## Settlement workflow

The supported verifier is fail-closed Stripe Connect transfer verification. A confirmed settlement requires a live `tr_*` transfer attributed to the exact work order, reward and payer; the immutable destination must equal `STRIPE_DESTINATION_ACCOUNT_ID`; linked platform and destination transactions must be official, final and available; and `gross - fee = net` must reconcile.

Confirmed transfers are revalidated. A later partial or full reversal removes revenue idempotently and reopens collection. Evidence older than 24 hours cannot fund the AI budget.

## Discovery contract

Discovery is deliberately separate from validation and scheduling.

A future `tools/revenue_discovery.py` may ingest only a bounded, structured listing from an official bounty platform host. It may call only `revenue_db.create_lead()`. It must never call `record_official_validation()`, `verify_opportunity()` or `build_work_orders()`.

Minimum admission fields for a lead are an immutable platform reward ID, official reward URL, fixed amount/currency, open platform state and linked GitHub issue URL. These fields remain untrusted hints until a separate validation phase re-fetches reward detail, GitHub issue/repo state, competition, payer history, payout eligibility and claimant eligibility.

Do not reuse `scripts/algora_bounty_scanner.py`, `scripts/bounty_engine.py`, `scripts/autonomous_bounty_orchestrator.py`, `tools/opportunity_scaler.py` or other keyword/label/scraping engines as v2 sources. They may remain isolated legacy data, but cannot write to the v2 database.

Do not deploy a discovery timer until the official structured endpoint, host allowlist, redirect policy, pagination bound and fixtures have been independently verified. The intended cadence is a oneshot service every six hours, at most one source and 50 items per run.

## Operating rule

Continue `discover -> validate -> claim -> implement/test -> review -> PR -> external approval/merge -> revalidate payment obligation -> verify settlement -> revalidate reversals`. A cycle returning no eligible opportunity is not success, failure, revenue or permission to relax a gate. Wait for the bounded interval and rotate.
