---
bounty_id: 70
repo: Movalabs-crew/mova-store
title: "[Bounty: $80] Clear StellarOrderWatch's error banner once the indexer recovers from a transient failure"
amount: 80
type: discovery_proposal
status: ready_for_claim
date: 2026-09-04
---

# Discovery Proposal: StellarOrderWatch Error Banner Recovery

## Problem Summary

The `StellarOrderWatch` component displays a persistent amber error banner after a single transient indexer failure, even when the indexer subsequently recovers. This is a state management bug where the UI error state is set but never cleared.

### Root Cause

- **Component (`components/StellarOrderWatch.jsx`, lines 35-39):** The `onStatus` handler only calls `setError()` when `s.lastError` is truthy. It never resets the error to `null` or `undefined` when a subsequent status update indicates recovery.
- **Backend (`lib/stellar/indexer.ts`, lines 135-138):** The indexer correctly clears `lastError` after successful polls, but this signal is ignored by the frontend.

Result: A single failed poll leaves the error banner visible forever, despite the monitor continuing to function correctly.

## Proposed Fix

### 1. Update `onStatus` Handler in `StellarOrderWatch.jsx`

Add an `else` branch (or equivalent conditional) to clear the error state when:
- `running === true` AND `lastError` is falsy/undefined → clear error
- A successful order match occurs → treat as resolving any prior error

```jsx
// Pseudocode for the fix
const onStatus = (s) => {
  if (s.lastError) {
    setError(s.lastError);
  } else if (s.running && !s.lastError) {
    // NEW: Clear error on recovery
    setError(null);
  }
  
  // Existing order match logic...
  if (s.matchedOrder) {
    setError(null); // Also clear on successful match
    // ... rest of match handling
  }
};
```

### 2. Add Component Test

Create or extend the test suite to verify the recovery behavior:

```javascript
test('clears error banner when indexer recovers', async () => {
  const { container, onStatusCallback } = render(<StellarOrderWatch />);
  
  // Simulate transient failure
  act(() => {
    onStatusCallback({ running: true, lastError: 'Connection timeout' });
  });
  expect(container.querySelector('.error-banner')).toBeInTheDocument();
  
  // Simulate recovery
  act(() => {
    onStatusCallback({ running: true, lastError: undefined });
  });
  expect(container.querySelector('.error-banner')).not.toBeInTheDocument();
});
```

## Acceptance Criteria Checklist

- [ ] Component test drives mocked indexer with `{running:true, lastError:'x'}` then `{running:true, lastError:undefined}` and asserts banner disappears
- [ ] Successful order match also clears prior error state
- [ ] `npm run test` passes
- [ ] No regression in existing error display behavior

## Files to Modify

| File | Change |
|------|--------|
| `components/StellarOrderWatch.jsx` | Add error-clearing logic in `onStatus` handler |
| `__tests__/StellarOrderWatch.test.jsx` (or similar) | Add recovery test case |

## Risk Assessment

- **Low risk**: Change is isolated to error state management; no data flow or API changes
- **Edge case to verify**: Ensure error still displays correctly during active failures (no false clearing)
- **Test coverage**: New test prevents regression

## Claim Readiness

This proposal is ready for implementation. All technical details are specified, acceptance criteria are defined, and the fix scope is well-bounded. Estimated effort: <1 hour for experienced developer familiar with the codebase.