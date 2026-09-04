---
bounty: "[Bounty: $100] Admin dispatch/refund re-hash the event-derived order id so they can never match the on-chain order"
issue: https://github.com/Movalabs-crew/mova-store/issues/67
type: discovery_proposal
status: analysis_complete
date: 2026-09-04
---

# Discovery Proposal: Admin Dispatch/Refund Order ID Double-Hash Bug

## Summary

This proposal documents the root cause and recommended fix for Movalabs-crew/mova-store#67, where admin dispatch and refund operations fail because event-derived order IDs are hashed a second time before contract invocation, making them irrecoverably mismatched against on-chain storage.

## Root Cause Analysis

### The Double-Hash Problem

1. **On-chain storage**: Orders are stored using `BytesN<32>` keys derived from SHA-256 hashes of raw order ID strings (e.g., `"SS-..."`).
2. **Indexer events**: The Stellar indexer emits events containing the *already-hashed* 32-byte order ID as a 64-character hex string.
3. **Admin UI**: `app/admin/orders/page.tsx` constructs table rows directly from these indexer events, passing the pre-hashed hex ID to action handlers.
4. **Contract invocation**: `lib/stellar/orders.ts` functions (`dispatchOrder`, `refundOrder`) unconditionally call `await hashOrderId(orderId)` on their input, assuming it is a raw pre-image string.
5. **Result**: When the admin passes an already-hashed 64-hex ID, it gets hashed again. Since SHA-256 is one-way, the double-hashed value can never match the original on-chain key, producing `OrderNotFound` errors.

### Why This Is Silent in Normal Flow

Non-admin order creation paths pass raw pre-images like `"SS-12345"` through `hashOrderId`, which correctly produces the stored key. Only the admin path — which receives pre-hashed values from the indexer — triggers the bug.

## Recommended Fix

### 1. Create `resolveOrderIdHash` Helper

A pure function that distinguishes between raw pre-images and pre-hashed IDs:

```typescript
/**
 * Returns the correct BytesN<32>-compatible representation for an order ID.
 * - If input is exactly 64 hex chars (32 bytes), treat as already-hashed and return as-is.
 * - Otherwise, hash the raw pre-image with SHA-256.
 */
export function resolveOrderIdHash(orderId: string): string {
  const HEX_64 = /^[0-9a-fA-F]{64}$/;
  if (HEX_64.test(orderId)) {
    return orderId.toLowerCase();
  }
  // Delegate to existing hashOrderId for raw pre-images
  return hashOrderId(orderId);
}
```

### 2. Update Contract Invocation Sites

Replace direct `hashOrderId()` calls in `dispatchOrder` and `refundOrder` with `resolveOrderIdHash()`.

### 3. Unit Tests Required

| Test Case | Input | Expected Behavior |
|-----------|-------|-------------------|
| Raw pre-image | `"SS-12345"` | Returns SHA-256 hash of input |
| Pre-hashed 64-hex | `"abcdef...64chars"` | Returns input unchanged (lowercased) |
| Invalid length hex | `"abcdef"` (not 64 chars) | Hashes as raw pre-image |
| Mixed case hex | `"ABCDEF...64chars"` | Returns lowercased passthrough |
| Empty string | `""` | Hashes as raw pre-image |

### 4. Integration Verification

Add a test confirming that the admin page passes event-derived hex IDs into `dispatchOrder`/`refundOrder` without modification, and that the resolved hash matches the expected on-chain key.

## Acceptance Criteria Checklist

- [ ] Pure `resolveOrderIdHash` helper created with both code paths unit-tested
- [ ] `dispatchOrder` and `refundOrder` updated to use `resolveOrderIdHash`
- [ ] Admin page verified to pass event-derived hex ID unmodified
- [ ] `npm run test` passes
- [ ] `npm run type-check` passes

## Risk Assessment

- **Low risk**: The helper is pure and backward-compatible; raw pre-image callers continue to work identically.
- **Edge case**: If any legitimate raw pre-image happens to be exactly 64 hex characters, it would be misidentified as pre-hashed. This is astronomically unlikely for human-readable order IDs but should be documented.
- **No ledger changes**: This fix is entirely off-chain; no smart contract migration required.

## Note

The target repository (`Movalabs-crew/mova-store`) is not present in the local workspace. This proposal is a discovery-only deliverable per bounty instructions. Implementation requires cloning the repository and applying the changes described above.