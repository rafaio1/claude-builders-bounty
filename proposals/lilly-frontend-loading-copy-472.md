# Bounty Discovery: Replace Portuguese Loading Copy & Reconcile Tests

- **Issue**: [#472](https://github.com/Lilly-Protocol/lily-frontend/issues/472)
- **Bounty**: $95
- **Type**: Bug / Copy Fix / Test Reconciliation
- **Status**: Open, Unassigned
- **Discovered**: 2026-09-04

## Summary

The root loading screen (`src/app/loading.tsx`) renders a spinner with the label `Carregando…` (Portuguese), despite the app being English-only (`<html lang="en">` in `src/app/layout.tsx`) and `next-intl` only being scaffolded. Two test files assert contradictory copy against this component, guaranteeing at least one failure under vitest's default include pattern.

## Problem Detail

| File | Asserts | Status |
|------|---------|--------|
| `src/app/loading.test.tsx` | `/carregando/i` | Passes only if Portuguese copy remains |
| `src/app/__tests__/root-loading.test.tsx` | `/loading/i` | Passes only if English copy is used |

Both files are collected by vitest (`**/*.test.{ts,tsx}`), so the suite cannot be fully green regardless of which language the component uses.

## Proposed Fix

1. Change the visible label in `src/app/loading.tsx` from `Carregando…` to `Loading…`.
2. Update `src/app/loading.test.tsx` to assert `/loading/i` instead of `/carregando/i`.
3. Remove or consolidate the duplicate test file (`src/app/__tests__/root-loading.test.tsx`) since it is redundant once both assert the same English copy. Alternatively, keep both if they cover different aspects (e.g., accessibility vs. visual), but ensure neither contradicts the other.
4. Verify `npm run test:run` passes for all loading-related suites.

## Acceptance Criteria (from issue)

- [ ] `RootLoading` renders `Loading…` — no Portuguese text remains in `src/app/loading.tsx`.
- [ ] Both test files pass, or the duplicate is removed and the surviving test passes.
- [ ] `npm run test:run` is green for the loading suites.

## Risk Assessment

- **Low risk**: Purely presentational change + test alignment. No business logic, no API surface, no database interaction.
- **i18n consideration**: If `next-intl` is later activated, this string should be extracted to a message catalog. For now, hard-coded English matches the app's declared language.
- **Test consolidation**: Removing a test file reduces coverage surface. Before deleting, confirm the surviving test covers the same assertions (render, accessibility label, spinner presence). If the `__tests__/` version tests additional behavior (e.g., suspense boundary integration), merge those assertions into the primary test rather than deleting them.

## Suggested Approach for Claimant

1. Clone repo, run `npm run test:run -- src/app/loading.test.tsx src/app/__tests__/root-loading.test.tsx` to observe current failures.
2. Make the copy change and test update in a single commit.
3. Run full test suite to confirm no regressions.
4. Submit PR referencing #472 with before/after screenshots of the loading screen.

## Notes

- Issue created 2026-09-03 by @Imole2001.
- ETA stated as 24 hours from issue creation (deadline likely passed; bounty may still be claimable — verify on platform).
- Design reference linked in issue: [Figma](https://www.figma.com/design/GRBeDGDHzCGXefm3xmlbHF/Lily-Protocol) — check for any loading state specifications beyond copy.