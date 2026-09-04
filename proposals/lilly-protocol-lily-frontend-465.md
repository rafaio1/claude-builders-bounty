---
bounty_id: "Lilly-Protocol/lily-frontend#465"
title: "Mark the agents registry nav link active when viewing an agent detail page"
provider: Lilly-Protocol
repo: lily-frontend
issue: 465
bounty_amount: 85
type: discovery_proposal
status: ready_for_claim
date: 2026-09-04
---

# Discovery Proposal: Agents Registry Nav Active State on Detail Pages

## Problem

The `SectionNav` component in `src/components/scaffold/section-nav.tsx` uses exact pathname matching to determine the active nav link. When a user navigates to an agent detail page (e.g., `/app/agents/<id>`), the "Agents Registry" nav link loses its active state because the concrete URL with an ID does not exactly match the parameterized route pattern for the registry list page.

## Root Cause

The active-state logic performs a strict equality check (`pathname === link.href`) rather than a prefix-aware match. Detail pages are children of the registry route but have distinct pathnames, so the parent nav item is never highlighted.

## Proposed Fix

Update the active-state determination in `SectionNav` to treat a link as current when **either**:

1. The pathname matches the link href exactly (preserves existing behavior for all non-nested routes), **or**
2. The pathname starts with the link href followed by a `/` (covers child/detail routes like `/app/agents/abc123`)

### Pseudocode

```tsx
const isActive =
  pathname === link.href ||
  (link.href !== "/" && pathname.startsWith(link.href + "/"));
```

The guard `link.href !== "/"` prevents the root link from being spuriously active on every page.

## Acceptance Criteria (from issue)

- [ ] Visiting an agent detail URL renders the Agents Registry link with `aria-current="page"` and active styling
- [ ] Exact-match behavior for other routes remains unchanged
- [ ] Active-route tests cover the nested detail path and pass under `npm run test:run`

## Files to Modify

| File | Change |
|------|--------|
| `src/components/scaffold/section-nav.tsx` | Update `isActive` logic to support prefix matching for dashboard groups |
| Test file for `SectionNav` (co-located or in `__tests__/`) | Add test case for detail-page active state; verify existing exact-match tests still pass |

## Risk Assessment

- **Low risk**: The change is a single boolean expression update in a presentational component.
- **Edge case**: Routes that share a prefix but are not parent-child (e.g., `/app/agents` and `/app/agents-settings`) would be incorrectly matched. Mitigation: the trailing `/` guard ensures only true child paths match. If such sibling routes exist, consider an explicit `childRoutes` config on the nav item instead.
- **No database or API changes required.**

## Testing Strategy

1. Unit test: mock `usePathname()` returning `/app/agents/some-id` → assert Agents Registry link has `aria-current="page"`.
2. Unit test: mock `usePathname()` returning `/app/agents` → assert same link is active (exact match preserved).
3. Unit test: mock `usePathname()` returning `/app/billing` → assert Agents Registry link is **not** active.
4. Run full suite: `npm run test:run` passes.

## Claim Readiness

This proposal is complete and ready for implementation. The fix is well-scoped, the acceptance criteria are clear, and no external dependencies or design decisions are blocking.