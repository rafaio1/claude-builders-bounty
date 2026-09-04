# Proposal: Resolve next-intl imports (Lilly-Protocol/lily-frontend#452)

- **Bounty**: $80 USDC
- **Issue**: https://github.com/Lilly-Protocol/lily-frontend/issues/452
- **Type**: discovery_proposal
- **Date**: 2026-09-04

## Summary

The `lily-frontend` repository contains dead i18n scaffolding: several files import from `next-intl`, but the package is not declared in `package.json` and is absent from `node_modules`. This causes TS2307 build failures. Additionally, the root layout hard-codes `lang="en"` and never mounts a locale-aware layout, so even if the dependency were installed, the i18n code paths would remain disconnected.

## Affected Files

| File | Problem |
|------|---------|
| `src/i18n/routing.ts` | Imports `next-intl/routing` — module not found |
| `src/i18n/request.ts` | Imports `next-intl/server` — module not found |
| `src/app/[locale]/layout.tsx` | Imports client/provider helpers from `next-intl` — module not found; route group `[locale]` exists but is unused |
| `messages/en.json` | Translation file with no consumer |
| Root `layout.tsx` | Hard-coded `lang="en"`, bypasses locale resolution |

## Recommended Fix

**Option A — Remove unused scaffolding (preferred)**

Since there is no active multi-language requirement documented in `docs/architecture.md` or elsewhere, and no translations beyond `en.json`:

1. Delete `src/i18n/` directory entirely.
2. Delete `src/app/[locale]/` route group; move any unique pages to `src/app/`.
3. Delete `messages/en.json`.
4. Verify root `layout.tsx` keeps `lang="en"` (already correct for single-locale).
5. Run `pnpm typecheck` and `pnpm build` to confirm clean compilation.

**Option B — Install and wire next-intl**

Only if multi-language support is planned imminently:

1. Add `next-intl` to `dependencies` in `package.json`.
2. Configure `next-intl` plugin in `next.config.ts`.
3. Replace hard-coded `lang="en"` in root layout with `<html lang={locale}>` using `getLocale()` from `next-intl/server`.
4. Wire `NextIntlClientProvider` in `[locale]/layout.tsx`.
5. Add at least one additional locale to validate the setup.

## Rationale for Option A

- No product requirement for i18n exists in current docs.
- Adding a dependency solely to silence build errors introduces maintenance burden without user-facing value.
- The `[locale]` route group has zero traffic or links pointing to it.
- Removal is reversible via git history if i18n is needed later.

## Acceptance Criteria

- [ ] `pnpm typecheck` passes with zero TS2307 errors related to `next-intl`.
- [ ] `pnpm build` completes successfully.
- [ ] No remaining imports of `next-intl` anywhere in the codebase (verified via grep).
- [ ] If Option A: `src/i18n/`, `src/app/[locale]/`, and `messages/` are removed.
- [ ] If Option B: At least two locales render correctly and language switcher functions.

## Estimated Effort

- Option A: ~30 minutes
- Option B: ~3–4 hours

## Claim Status

- **Status**: ready_to_claim
- **Claim type**: pr_based
- **Autonomy qualified**: yes