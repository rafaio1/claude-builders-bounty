---
bounty_id: mova-store-22
title: "[Bounty: $100] Import connectWallet in StellarWalletButton to fix ReferenceError"
source_url: https://github.com/Movalabs-crew/mova-store/issues/22
type: discovery_proposal
status: ready_for_claim
created_at: 2026-09-04
provider: ghostcli-auto[1m]
---

# Discovery Proposal: Fix StellarWalletButton ReferenceError

## Issue Summary
`StellarWalletButton.jsx` throws a `ReferenceError` when users click the connect button because `connectWallet` is called in `handleConnect` (line 37) but never imported from `lib/stellar/freighter`. This blocks wallet connectivity on `/checkout` and `/admin/orders` routes.

## Root Cause Analysis
The component imports `currentAddress`, `freighterAvailable`, `WalletError`, and `shortAddress` from `lib/stellar/freighter` but omits `connectWallet`. The sibling component `StellarCheckoutButton.jsx` correctly imports all five symbols including `connectWallet`, confirming the function exists in the freighter module and the omission is accidental.

## Proposed Fix
**File:** `components/StellarWalletButton.jsx`  
**Change:** Add `connectWallet` to the existing import statement on lines 3-4.

```diff
- import { currentAddress, freighterAvailable, WalletError, shortAddress } from '../lib/stellar/freighter';
+ import { currentAddress, freighterAvailable, WalletError, shortAddress, connectWallet } from '../lib/stellar/freighter';
```

No other changes required — `handleConnect` already calls `connectWallet()` correctly at line 37; it simply needs the symbol in scope.

## Acceptance Criteria (from issue)
1. Clicking the wallet button invokes the Freighter wallet request without throwing errors.
2. On successful connection, the truncated address (`shortAddress`) displays in the button.
3. ESLint passes with no new warnings.
4. Behavior matches `StellarCheckoutButton.jsx` connect flow.

## Verification Plan
1. Run `pnpm lint` to confirm no import/scope errors.
2. Manual test: navigate to `/checkout`, click wallet button, approve Freighter prompt, verify address display.
3. Regression check: confirm `/admin/orders` wallet connect also works.
4. Optional: add unit test mocking `lib/stellar/freighter` to assert `connectWallet` is invoked on click.

## Risk Assessment
- **Risk Level:** Low — single-line import addition, no logic changes.
- **Side Effects:** None expected; `connectWallet` is already used identically in `StellarCheckoutButton`.
- **Dependencies:** Requires Freighter extension installed for manual testing; CI may need mock if not present.

## Bounty Claim Readiness
This proposal fully scopes the fix. A contributor can claim and submit a PR with the one-line import change plus verification evidence. No architectural decisions or additional discovery needed.