# Bounty Proposal: Deduplicate the `docs` target in the Makefile

- **Issue**: [Lilly-Protocol/lily-contracts#303](https://github.com/Lilly-Protocol/lily-contracts/issues/303)
- **Bounty**: $95 USDC
- **Type**: discovery_proposal
- **Date**: 2026-09-04

## Problem

The `Makefile` defines the `docs` target twice:

1. **Line ~28** (strict version):
   ```makefile
   docs:
   	RUSTDOCFLAGS="-D warnings" cargo doc --workspace --no-deps
   ```

2. **Line ~46** (lenient version):
   ```makefile
   docs:
   	cargo doc --workspace --no-deps
   ```

GNU Make uses the last-defined recipe, so the lenient version silently overrides the strict one. This means:

- `make docs` does **not** fail on rustdoc warnings.
- CI relies on `make doc` (singular), which is correctly strict — but the documented/help-text target `docs` is broken.
- `make -n docs` shows a `cargo doc` invocation **without** `RUSTDOCFLAGS=-D warnings`.
- Make emits an overriding-recipe warning when parsing the file.

## Proposed Fix

Delete the second (lenient) `docs` target entirely (lines 45–46 in the current Makefile). Keep only the first definition that includes `RUSTDOCFLAGS="-D warnings"`.

### Resulting Makefile diff

```diff
-docs:
-	cargo doc --workspace --no-deps
-
 size-report: build-wasm
```

No other changes are needed. The remaining `docs` target already matches what `make ci` expects via the `doc` target (both use identical flags).

## Verification Checklist

After applying the fix:

- [ ] `make -n docs` outputs exactly one `cargo doc` invocation containing `RUSTDOCFLAGS=-D warnings`
- [ ] `make docs` fails when rustdoc emits any warning
- [ ] No overriding-recipe warning from `make`
- [ ] `make ci` continues to pass (it calls `doc`, not `docs`, but both now behave identically)
- [ ] Help text (`make help`) accurately describes the `docs` target

## Notes

- The `doc` (singular) and `docs` (plural) targets are functionally identical after this fix. A follow-up could consolidate them into a single canonical name, but that is out of scope for this bounty which specifically asks to deduplicate `docs`.
- This is a pure deletion — no new code, no behavioral change beyond restoring the intended strict mode.