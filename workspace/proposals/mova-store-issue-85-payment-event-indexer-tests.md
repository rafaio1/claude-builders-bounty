---
name: mova-store-issue-85-payment-event-indexer-tests
description: Discovery proposal for bounty $95 — unit tests for PaymentEventIndexer.decodeEvent topic naming, filters and data shapes
metadata:
  type: project
  bounty_url: https://github.com/Movalabs-crew/mova-store/issues/85
  status: discovery_complete
  created: 2026-09-04
---

# Bounty #85: Add unit tests for PaymentEventIndexer.decodeEvent

## Status: DISCOVERY COMPLETE — Target codebase not cloned locally

The `mova-store` repository is **not present** in the current workspace. The bounty targets `lib/stellar/indexer.ts` (lines 194–230) and expects a new test file at `tests/lib/stellar/indexer.test.ts`, neither of which exist in any cloned repo under `/Agentic`.

### What was searched
- Full recursive search for `PaymentEventIndexer` across all `.ts`, `.tsx`, `.js`, `.md` files → **zero matches**.
- Search for `lib/stellar/indexer.ts` path → **not found**.
- Search for any `mova-store` directory → **not found**.
- Existing Stellar indexer code lives in `/Agentic/soroban-backend/src/indexer/` (different project, different API surface).

## Bounty Requirements (from issue #85)

| Criterion | Detail |
|-----------|--------|
| **Target method** | `PaymentEventIndexer.decodeEvent` (private, `lib/stellar/indexer.ts:194-230`) |
| **Test file** | `tests/lib/stellar/indexer.test.ts` (new) |
| **Fixture library** | `@stellar/stellar-sdk` ScVal builders only — no network calls |
| **Acceptance 1** | Non-watched symbols filtered out; map entries merge by key; vector data joins under `fields.value` |
| **Acceptance 2** | Payment-shaped fixture confirms topic4 as the 64-hex order id (guards StellarOrderWatch.jsx regression) |
| **Acceptance 3** | Tests pass `npm run test` offline |

## Required Test Coverage

### 1. Topic Naming
- Assert correct ordering of `topic1` through `topicN` fields in decoded output.
- Verify symbol extraction from `topics[0]`.

### 2. Filters
- Watched-symbols filter drops unwatched symbols.
- Null/non-symbol topics handled gracefully (no crash, correct fallback).

### 3. Data Shapes
- **Map**: entries merge by key into decoded object.
- **Vector**: elements joined under `fields.value`.
- **Scalar**: single value assigned correctly.

## Next Steps to Claim

1. Clone `https://github.com/Movalabs-crew/mova-store` into workspace.
2. Read `lib/stellar/indexer.ts` lines 194–230 to understand exact decode logic.
3. Write `tests/lib/stellar/indexer.test.ts` covering all three acceptance criteria.
4. Run `npm run test` to confirm green.
5. Submit PR referencing issue #85.

## Risk Notes
- The method is **private** — tests may need to access it via module-level export or test the public method that calls it. Check if there's an existing test harness pattern in the repo.
- The `StellarOrderWatch.jsx` regression guard (acceptance 2) implies a specific payment event shape; the fixture must match production format exactly.
- No existing tests for this method were found in the issue description, so this is greenfield coverage.

**Why:** This proposal documents full discovery so implementation can begin immediately once the repo is cloned.
**How to apply:** Clone mova-store, read the target method, then write tests matching the three acceptance criteria above. Link back to [[mova-store-issue-22-stellar-wallet-fix]] and [[mova-store-issue-23-stale-toast-cleanup]] for related mova-store context.