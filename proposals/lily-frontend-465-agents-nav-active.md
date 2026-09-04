# Proposal: Mark Agents Registry Nav Link Active on Detail Pages

- **Issue:** [Lilly-Protocol/lily-frontend#465](https://github.com/Lilly-Protocol/lily-frontend/issues/465)
- **Bounty:** $85
- **Type:** discovery_proposal
- **Date:** 2026-09-04

## Summary

The `SectionNav` component in `src/components/scaffold/section-nav.tsx` currently uses exact pathname matching to apply `aria-current="page"`. This causes the Agents Registry sidebar link to appear inactive when viewing agent detail pages (e.g., `/app/agents/<id>`), because the detail path does not exactly equal the registry path.

## Acceptance Criteria (from issue)

1. The Agents Registry link shows `aria-current="page"` and active styling on `/app/agents/<id>` routes.
2. Existing exact-match behavior for other routes remains unchanged.
3. Active-route tests cover the nested detail path and pass under `npm run test:run`.

## Proposed Implementation

### 1. Update `src/components/scaffold/section-nav.tsx`

Modify the active-link logic to use prefix matching for dashboard group links:

```tsx
// Current (exact match only):
const isCurrent = pathname === link.href;

// Proposed (prefix-aware for dashboard routes):
const isCurrent =
  pathname === link.href ||
  (link.href.startsWith("/app/") && pathname.startsWith(`${link.href}/`));
```

This ensures that any child route under a dashboard section (e.g., `/app/agents/abc`) marks the parent nav link as active, while preserving exact-match semantics for non-dashboard or top-level routes.

### 2. Extend Tests

Add a test case in the existing `SectionNav` test suite that stubs `usePathname` to return `/app/agents/test-id` and asserts that the Agents Registry link has `aria-current="page"`. Verify that unrelated links remain inactive.

### 3. Regression Safety

- Confirm that exact-match routes (e.g., `/app/settings`) still activate only their own link.
- Ensure no false positives for similarly-prefixed paths (e.g., `/app/agents-export` should NOT activate `/app/agents`). The trailing-slash check (`${link.href}/`) prevents this.

## Linked PR

- #519 (already opened per issue description)

## Status

**Ready for implementation.** The fix is localized to one component and its tests. No database, API, or schema changes required. Estimated effort: <1 hour.