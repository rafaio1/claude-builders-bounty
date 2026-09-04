---
bounty_id: 449
repo: Lilly-Protocol/lily-frontend
title: "Give SiteFooter safe registry defaults so SectionLayout pages render a single footer"
value_usd: 95
type: discovery_proposal
status: ready_to_claim
date: 2026-09-04
linked_pr: 538
---

# Discovery Proposal: SiteFooter Safe Registry Defaults

## Problem Summary

`SectionLayout` renders `SiteFooter` without providing required route props, causing a runtime crash (`TypeError: Cannot read properties of undefined (reading 'map')`) on multiple page types. Additionally, marketing layouts currently render **two** footers (one from the section layout and one hard-coded in the root/marketing layout), violating the single-footer contract.

## Root Cause Analysis

1. **Missing prop defaults**: `src/components/scaffold/site-footer.tsx` expects route arrays (legal links, support links) as required props. `SectionLayout` does not pass these, leaving them `undefined`.
2. **Duplicate footer instances**: The marketing root layout at `(marketing)/layout.tsx` includes its own `<SiteFooter />` or imports from `src/components/site-footer.tsx` (a separate hard-coded module), while `SectionLayout` also renders a footer. This produces two `<footer>` elements per page.
3. **Hard-coded vs. registry divergence**: The root-level `src/components/site-footer.tsx` uses static link lists that drift from `src/config/routes.ts`, the canonical registry source.

## Proposed Fix

### 1. Make SiteFooter props optional with registry defaults

In `src/components/scaffold/site-footer.tsx`:

```tsx
interface SiteFooterProps {
  legalRoutes?: RouteEntry[];
  supportRoutes?: RouteEntry[];
}

export function SiteFooter({
  legalRoutes = getSectionRoutes('legal'),
  supportRoutes = getSectionRoutes('support'),
}: SiteFooterProps) {
  // existing render logic — now safe when called without props
}
```

This ensures `SectionLayout` can render `<SiteFooter />` with zero props and still produce correct, registry-synchronized links.

### 2. Remove duplicate footer from marketing layout

In `src/app/(marketing)/layout.tsx`:

- Remove any direct `<SiteFooter />` or import from `src/components/site-footer.tsx`.
- Rely solely on the footer rendered by `SectionLayout` (which wraps marketing pages).

### 3. Delete or redirect the hard-coded footer module

- Delete `src/components/site-footer.tsx` (the non-scaffold, hard-coded version).
- If other files import it, update those imports to use `src/components/scaffold/site-footer.tsx`.

### 4. Add single-footer assertion test

In `src/components/scaffold/__tests__/site-footer.test.tsx`:

```tsx
it('renders exactly one <footer> element', () => {
  const { container } = render(<SiteFooter />);
  expect(container.querySelectorAll('footer')).toHaveLength(1);
});
```

## Acceptance Criteria Mapping

| Criterion | How It Is Met |
|-----------|---------------|
| `SectionLayout` renders without errors | Optional props default via `getSectionRoutes()` — no more `.map()` on `undefined` |
| Single `<footer>` on every route-group page | Duplicate removed from marketing layout; only `SectionLayout`'s footer remains |
| Marketing pages show registry-driven links | Defaults pull from `src/config/routes.ts` via `getSectionRoutes('legal')` / `getSectionRoutes('support')` |
| Tests pass (`npm run test:run`) | Existing tests preserved; new single-footer assertion added |

## Files to Modify

| File | Change |
|------|--------|
| `src/components/scaffold/site-footer.tsx` | Make props optional, add registry defaults |
| `src/components/scaffold/section-layout.tsx` | No change needed (already renders `<SiteFooter />` without props) |
| `src/app/(marketing)/layout.tsx` | Remove duplicate footer instance |
| `src/components/site-footer.tsx` | Delete (hard-coded duplicate) |
| `src/components/scaffold/__tests__/site-footer.test.tsx` | Add single-footer assertion |
| `src/config/routes.ts` | No change (already canonical source) |

## Risk Assessment

- **Low risk**: Changes are additive (optional props with defaults) and subtractive (removing duplicates). No new dependencies.
- **Regression check**: Verify all page routes render without console errors after change. Run full test suite.
- **Linked PR #538**: May already contain partial implementation — review for conflicts before submitting.

## Claim Readiness

This proposal is complete and actionable. All acceptance criteria are addressed with specific file-level changes. Ready for bounty claim submission upon implementation verification.