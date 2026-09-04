---
bounty: 483
repo: Lilly-Protocol/lily-frontend
title: "Source manifest.ts strings and colors from siteConfig and SURFACE_THEME_COLOR"
value: 95
type: discovery_proposal
status: ready_to_claim
date: 2026-09-04
---

# Discovery: Bounty #483 — Source manifest.ts from siteConfig & SURFACE_THEME_COLOR

## Summary

The bounty asks to eliminate hardcoded strings and colors in `src/app/manifest.ts` by sourcing them from `siteConfig` and `SURFACE_THEME_COLOR`. **This work has already been completed on the default branch.** The current `manifest.ts` already imports from `@/config/site`, uses `siteConfig.name`, `siteConfig.shortName`, `siteConfig.description`, and `siteConfig.themeColor` for all string and color fields. A test file `src/app/manifest.test.ts` also exists and asserts field equality against config constants.

## Current State of Files

### `src/app/manifest.ts` (already refactored)

```ts
import { routes, siteConfig } from "@/config/site";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: siteConfig.name,
    short_name: siteConfig.shortName,
    description: siteConfig.description,
    start_url: routes.home,
    display: "standalone",
    background_color: siteConfig.themeColor,
    theme_color: siteConfig.themeColor,
    icons: [ /* unchanged icon entries */ ],
  };
}
```

- ✅ No hardcoded name, short_name, or description strings
- ✅ `theme_color` and `background_color` sourced from `siteConfig.themeColor`
- ✅ Icon entries preserved as required

### `src/config/site.ts`

Exports `siteConfig` with:
- `name: 'Lily Protocol'`
- `shortName: 'Lily'`
- `description: 'Contributor-ready frontend foundation…'`
- `themeColor: '#f7f7f5'`

### `src/config/viewport.ts`

Exports `SURFACE_THEME_COLOR = "#f7f7f5"` — matches `siteConfig.themeColor` value but is **not imported** in `manifest.ts`. The manifest uses `siteConfig.themeColor` directly instead.

### `src/app/manifest.test.ts` (already exists)

Asserts:
- `manifest().name === siteConfig.name`
- `manifest().short_name === siteConfig.shortName`
- `manifest().theme_color === siteConfig.themeColor`
- `manifest().background_color === siteConfig.themeColor`
- Icon array equality

## Gap Analysis

| Acceptance Criterion | Status | Notes |
|---|---|---|
| No hardcoded string/color duplicates in manifest.ts | ✅ Done | All values sourced from siteConfig |
| Test file asserts manifest fields equal config constants | ✅ Done | `manifest.test.ts` exists with correct assertions |
| `npm run test:run` passes | ⚠️ Not verified locally | Repo cloned at depth-1; deps not installed |
| `SURFACE_THEME_COLOR` used in manifest | ⚠️ Partial | Value matches but manifest imports `siteConfig.themeColor` rather than `SURFACE_THEME_COLOR` directly |

### Minor Remaining Issue

The bounty title specifically mentions sourcing from `SURFACE_THEME_COLOR`, but the current implementation uses `siteConfig.themeColor` instead. Both resolve to `"#f7f7f5"`. Two options:

1. **Accept as-is**: `siteConfig.themeColor` is the canonical source; `SURFACE_THEME_COLOR` in `viewport.ts` is a parallel constant for viewport metadata. They share the same value by convention. This is arguably cleaner since the manifest already imports `siteConfig`.
2. **Import `SURFACE_THEME_COLOR` explicitly**: Change `theme_color` and `background_color` in `manifest.ts` to use `SURFACE_THEME_COLOR` from `@/config/viewport` instead of `siteConfig.themeColor`. This satisfies the letter of the bounty title but introduces a second import and creates a coupling between manifest and viewport config.

**Recommendation**: Option 1 is architecturally superior. If the maintainer wants `SURFACE_THEME_COLOR` referenced directly, the fix is a one-line import change.

## Claim Readiness

This bounty appears to have been completed (possibly via PR #510 or #511 referenced in the issue). Before claiming:

1. Verify no open PR already addresses this exact scope
2. Confirm `npm run test:run` passes with current code
3. If the `SURFACE_THEME_COLOR` direct reference is required, submit a small follow-up PR swapping the import

## Related

- Issue: https://github.com/Lilly-Protocol/lily-frontend/issues/483
- Linked PRs: #510, #511
- Config files: `src/config/site.ts`, `src/config/viewport.ts`