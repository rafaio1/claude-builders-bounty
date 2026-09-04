# Discovery Proposal: Evict Expired Quotes and Bound Payments In-Memory Store

- **Bounty**: $80 USD (USDC)
- **Issue**: [Lilly-Protocol/lily-backend#264](https://github.com/Lilly-Protocol/lily-backend/issues/264)
- **Type**: Enhancement / Memory Safety
- **Discovered**: 2026-09-04
- **Status**: Proposal Ready — Not Claimed

## Problem Summary

`payments.service.ts` maintains two unbounded in-memory stores:

1. `quotesStore` (Map) — accumulates every created quote indefinitely. `refreshExpiry` only marks entries as "expired" on read, so unread expired quotes persist for the process lifetime.
2. `paymentsStore` — appends executed payments with no eviction policy.

This contrasts with the agents service, which enforces `MAX_IN_MEMORY_AGENTS` and evicts oldest entries. The payments service has no equivalent bound, creating a memory leak proportional to quote/payment volume over time.

## Acceptance Criteria (from issue)

1. Quotes past `QUOTE_TTL_MS` are removed from `quotesStore` within the sweep interval even if never read.
2. Quote store never exceeds configured max count (oldest evicted), verified via `vi.useFakeTimers`.
3. `reset()` empties both `quotesStore` and `paymentsStore`.

## Proposed Implementation Plan

### 1. Periodic Sweep Timer
- Add an unref'd `setInterval` (e.g., every 60s or configurable) that iterates `quotesStore` and deletes entries where `createdAt + QUOTE_TTL_MS < Date.now()`.
- Call `.unref()` on the timer handle so it doesn't prevent Node.js process exit.
- Store the timer reference for cleanup in `reset()`.

### 2. Bounded Quote Store
- Define `MAX_QUOTES` constant (analogous to `MAX_IN_MEMORY_AGENTS`).
- On `createQuote`, after insertion, check `quotesStore.size > MAX_QUOTES`. If exceeded, delete the oldest entry (by insertion order — Map preserves insertion order).
- Alternatively, combine with lazy eviction: sweep up to N oldest expired entries before enforcing hard cap.

### 3. Reset Cleanup
- Ensure `reset()` calls `clearInterval(sweepTimer)` and sets `quotesStore.clear()` + `paymentsStore.clear()`.
- Verify existing tests still pass; add new test covering timer teardown.

### 4. Test Strategy
- Use `vi.useFakeTimers()` to advance time past `QUOTE_TTL_MS` and assert expired entries are removed without manual reads.
- Insert `MAX_QUOTES + N` entries and verify only `MAX_QUOTES` remain, with oldest evicted.
- Assert `reset()` clears both stores and stops the sweep timer.

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Timer prevents graceful shutdown | Low | `.unref()` + explicit clear in reset |
| Eviction removes active quote mid-use | Medium | TTL should exceed max quote validity window; document assumption |
| Map iteration during concurrent mutation | Low | Single-threaded Node.js event loop; no race condition |
| Existing tests depend on stale entries | Medium | Audit test suite for implicit reliance on unbounded store |

## Estimated Effort

- **Implementation**: 1–2 hours
- **Testing**: 1 hour
- **Total**: ~3 hours

## Recommendation

**Claim this bounty.** The scope is well-defined, the fix pattern exists in the codebase (agents service), and acceptance criteria are testable with fake timers. No architectural changes required — purely additive cleanup logic.

## Next Steps

1. Clone/fork `lily-backend` repo
2. Implement changes per plan above
3. Submit PR referencing issue #264
4. Link PR in bounty claim comment