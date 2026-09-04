---
bounty_id: 89
repo: Movalabs-crew/mova-store
title: "Add StellarCheckoutButton component tests for connect, busy, error and success states"
value_usd: 85
type: discovery_proposal
status: source_not_in_workspace
date: 2026-09-04
issue_url: https://github.com/Movalabs-crew/mova-store/issues/89
---

# Discovery: StellarCheckoutButton Test Bounty (#89)

## Finding

The `StellarCheckoutButton` component, its dependencies (`lib/stellar/checkout`, `lib/stellar/freighter`), and any existing test files **do not exist** in the `/Agentic` workspace. A recursive search for `StellarCheckoutButton`, `stellar/checkout`, and `stellar/freighter` returned zero results. This bounty cannot be implemented locally without first cloning or syncing the `mova-store` repository.

## Bounty Requirements (from issue)

| State | Assertion |
|-------|-----------|
| **Busy/Disabled** | Button is disabled while `busy` prop is true or `disabled` prop is set |
| **Connect** | Missing `publicKey` triggers connect flow then calls `payWithStellar` |
| **Error** | `WalletError` message surfaces in the alert span |
| **Success** | Payment-confirmed state renders with a transaction link |

**Acceptance criterion:** All assertions pass under `npm run test` with module mocks and no network access.

## Proposed Test Plan (for future implementation)

1. **Clone/sync** `Movalabs-crew/mova-store` into the workspace.
2. **Locate** `components/StellarCheckoutButton.jsx` (lines 38–99 per issue).
3. **Create** `components/__tests__/StellarCheckoutButton.test.jsx` using Vitest + @testing-library/react.
4. **Mock modules:**
   - `../lib/stellar/checkout` → mock `payWithStellar`
   - `../lib/stellar/freighter` → mock `connect`, `getPublicKey`
5. **Test cases:**
   - `renders disabled when busy=true`
   - `renders disabled when disabled=true`
   - `triggers connect then payWithStellar when publicKey is missing`
   - `displays WalletError message in alert span`
   - `renders payment-confirmed state with tx link on success`
6. **Verify:** `npm run test -- StellarCheckoutButton` passes with zero network calls.

## Recommendation

This bounty should be **claimed only after** the mova-store source is available in the workspace. The test plan above is ready to execute once the component files are present. No canonical ledgers were modified.