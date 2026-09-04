---
bounty: 90
currency: USD
provider: algora
status: discovery_complete
issue: https://github.com/Movalabs-crew/mova-store/issues/110
repo: Movalabs-crew/mova-store
type: discovery_proposal
created: 2026-09-04
---

# Proposal: Remove unused useCart import in checkout page

## Summary

Issue #110 offers a $90 bounty to fix an unused `useCart` import in the Mova Store checkout page. The file `app/checkout/page.tsx` imports the hook on line 3 but never invokes it, relying instead on direct `localStorage` reads. Additionally, `CartProvider` is only mounted under `app/shop/layout.jsx` and has no default context value, so any future attempt to call the hook from `/checkout` would throw at runtime.

## Recommended Fix

**Option A (preferred): Delete the unused import.**

- Remove `useCart` from the import statement in `app/checkout/page.tsx`.
- Verify `npm run lint` reports no unused-import warnings.
- No behavioral change; the page already uses localStorage directly.

This is the lowest-risk resolution because:
1. The hook is not called today, so removing it cannot break existing behavior.
2. Wrapping `/checkout` in `CartProvider` would require either moving the provider to a shared layout or adding a default context value — both are larger refactors that exceed the bounty scope and risk unintended side effects.
3. If the team later wants to migrate checkout to use the cart context, that should be a dedicated issue with its own design review.

## Acceptance Criteria (from issue)

- [ ] `/checkout` no longer imports `useCart` without using it.
- [ ] `npm run lint` reports no unused import errors for the checkout page.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Removing import breaks hidden dependency | Very Low | Medium | Grep confirms zero call sites in the file; lint will catch any remaining reference. |
| Future developer re-adds hook without provider | Medium | High | Add inline comment noting CartProvider is not available at `/checkout` route. |

## Files Affected

- `app/checkout/page.tsx` — remove `useCart` from import line 3.

## Notes for Claimant

- Clone `Movalabs-crew/mova-store`, create a branch from `main`.
- Make the single-line change, run `npm run lint`, commit.
- Open a PR referencing issue #110 and request review.
- Bounty payout is handled through Algora upon merge.

## Discovery Status

✅ Issue reviewed and requirements confirmed.
✅ Fix scoped to single-file import removal.
⏳ Awaiting claimant assignment or self-service PR.