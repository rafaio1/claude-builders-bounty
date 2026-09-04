# Bounty Proposal: [Bounty: $85] Add decodePaymentEvent fixture tests including non-pay and foreign events

- **Issue**: https://github.com/Movalabs-crew/mova-store/issues/87
- **Amount**: $85 USDC
- **Type**: discovery_proposal / pr_based
- **Status**: proposal_ready — repo not cloned locally, submission requires fresh clone + test implementation
- **Date**: 2026-09-04

## Summary

This bounty requests fixture-based unit tests for `decodePaymentEvent` in `lib/stellar/events.ts` (lines 60–127) of the Movalabs-crew/mova-store repository. The function parses Stellar contract-event data from `GetSuccessfulTransactionResponse` objects without RPC calls. Current coverage is missing; the bounty pays $85 for a complete test suite that exercises every documented branch.

## Acceptance Criteria (from issue)

1. Expected topic-slot values (including the 64-hex order id) are asserted for the pay fixture.
2. Each documented branch is exercised; `npm run test` passes.

## Required Test Cases

| # | Scenario | Expected Behavior |
|---|----------|-------------------|
| 1 | Valid pay event | Returns decoded object with correct topic slots, 64-hex order id, amount, asset |
| 2 | Non-pay symbol (e.g., refund, transfer) | Skips / returns null or ignores non-pay events |
| 3 | Short topic list (< expected length) | Tolerates gracefully, no throw |
| 4 | Event absent from transaction | Returns null |
| 5 | Non-map data in event value | Handles without crash, returns null or safe default |
| 6 | Foreign/unrecognized event contract | Does not mis-parse; returns null |

## Implementation Plan

1. Clone `Movalabs-crew/mova-store` into `/Agentic/workspace/mova-store`.
2. Read `lib/stellar/events.ts` lines 60–127 to map exact branching logic and type signatures.
3. Locate or create test file (likely `lib/stellar/__tests__/events.test.ts` or similar).
4. Build minimal `GetSuccessfulTransactionResponse` fixtures for each scenario above — no live RPC needed.
5. Assert return shape, topic slot hex values, order-id length (64 hex chars), and null returns.
6. Run `npm run test` (or project-equivalent) to confirm green.
7. Open PR referencing issue #87.

## Blockers / Notes

- Repo is **not present** in `/Agentic/workspace/` or elsewhere on disk; must be cloned before implementation.
- No existing proposal for this bounty found in `/Agentic/proposals/`.
- Discovery-only task: this document captures requirements and plan. Actual code changes and PR submission are a separate execution step.

## Canonical Ledger Safety

✅ No canonical ledgers modified. Findings written only to `/Agentic/proposals/`.