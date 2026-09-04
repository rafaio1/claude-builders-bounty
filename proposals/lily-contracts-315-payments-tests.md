---
bounty_id: Lilly-Protocol/lily-contracts#315
repo: Lilly-Protocol/lily-contracts
title: "[Bounty: $85] Fix the payments unit tests that use out-of-scope variables and a stale initialize signature"
amount_usd: 85
currency: USD
asset: USDC
url: https://github.com/Lilly-Protocol/lily-contracts/issues/315
status: discovery_complete
claim_type: pr_based
discovered_at: 2026-09-04T10:37:40.010931+00:00
proposal_created_at: 2026-09-04
---

# Discovery Proposal: Fix Payments Unit Tests (#315)

## Summary

Bounty #315 targets compilation failures in `contracts/payments/src/test.rs` within the `Lilly-Protocol/lily-contracts` repository. The test suite fails to compile due to undefined variables and an outdated `initialize` function signature. This is a **pr_based** claim requiring a merged pull request that resolves all listed issues.

## Affected File

- `contracts/payments/src/test.rs`

## Required Fixes

### 1. Undefined `treasury` variable
- **Test:** `creates_and_settles_payment_intents`
- **Problem:** Asserts against `config.treasury` using a local `treasury` variable that `bootstrap()` never returns.
- **Fix:** Either capture `treasury` from the bootstrap/config return value, or assert directly against `config.treasury` without an intermediate undefined binding.

### 2. Undefined `wallet_id` variable
- **Tests:** `rejects_settle_after_cancellation`, `accepts_the_maximum_payment_amount`
- **Problem:** References `wallet_id` which is not defined in scope.
- **Fix:** Define `wallet_id` from the appropriate helper output (e.g., wallet creation helper or config), or replace with the correct identifier available in each test's setup block.

### 3. Stale four-argument `initialize` calls
- **Tests:** Two tests use `initialize(&admin, &treasury, &fee_bps, &wallet)` (four arguments).
- **Required signature:** `initialize(&admin, &treasury, &fee_bps)` (three arguments).
- **Fix:** Remove the fourth `&wallet` argument from both call sites. The wallet-related config work is deferred; these tests must match the current three-arg contract.

## Acceptance Criteria

1. `cargo test -p payments` compiles without undefined-identifier errors.
2. All three named tests pass with correct assertions.
3. No four-argument `initialize` invocations remain in the payments test module.
4. PR is opened against `Lilly-Protocol/lily-contracts` and references issue #315.

## Claim Strategy

- **Type:** PR-based (merge required for payout).
- **Autonomy qualified:** Yes — no KYC or identity gate at discovery time.
- **Risk:** Low. All fixes are localized to a single test file with no production code changes.
- **Estimated effort:** < 1 hour for an experienced Rust/Soroban developer.

## Next Steps

1. Fork/clone `Lilly-Protocol/lily-contracts`.
2. Apply the three fixes above in `contracts/payments/src/test.rs`.
3. Run `cargo test -p payments` locally to confirm green.
4. Open a PR referencing `#315` and request review per repo contributing guidelines.
5. After merge, submit claim through the bounty platform with PR link.

## Notes

- Source repo was not found locally under `/Agentic`; implementation requires cloning from GitHub.
- Bounty metadata sourced from `/Agentic/revenue/github_title_opportunities/Lilly-Protocol_lily-contracts_315.json`.
- Issue details extracted via live fetch on 2026-09-04.