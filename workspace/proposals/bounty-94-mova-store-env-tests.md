# Bounty #94: Add unit tests for env.ts config loaders

- **Repository**: Movalabs-crew/mova-store
- **Issue**: https://github.com/Movalabs-crew/mova-store/issues/94
- **Bounty**: $95
- **Type**: discovery_proposal
- **Date**: 2026-09-04

## Status: NOT CLAIMABLE — Source code not available locally

## Summary

The bounty requires adding unit tests to `tests/lib/env.test.ts` for three config loader functions in `lib/env.ts`:

1. `loadEmailJSConfig` (lines 142-165)
2. `loadSupabaseConfig` (lines 168-185)
3. `loadAdminConfig` (lines 188-197)

Plus helper functions `requireEnv` / `getEnv` (lines 76-99).

## Requirements (from issue)

- Use `vi.stubEnv` for environment variable mocking
- Each missing required field must push one error with the correct message
- Whitespace-only values count as missing
- `loadEmailJSConfig`: default recipient is undefined when unset
- `loadAdminConfig`: trims/lowercases entries, drops empties, returns `[]` for blank or comma-only strings
- Errors arrays and messages asserted per loader
- `npm run test` must pass

## Discovery Findings

### Local codebase search: NO MATCH

- Searched `/Agentic` recursively for files named `env.ts` — found 3 unrelated files (redocly, openprogram-llms, ophirpay)
- Searched for directories named `mova-store` — none found
- Searched all `.ts`/`.tsx` files for function names `loadEmailJSConfig`, `loadSupabaseConfig`, `loadAdminConfig` — zero matches
- The `mova-store` repository is **not cloned** into this workspace

### Conclusion

This bounty cannot be executed without first cloning `https://github.com/Movalabs-crew/mova-store.git` into the workspace. The source file `lib/env.ts` and existing test file `tests/lib/env.test.ts` are not present locally.

## Recommended Next Steps

1. Clone the repository: `git clone https://github.com/Movalabs-crew/mova-store.git /Agentic/workspace/mova-store`
2. Install dependencies: `cd /Agentic/workspace/mova-store && npm install`
3. Review `lib/env.ts` to understand exact validation logic and error messages
4. Review existing `tests/lib/env.test.ts` to match test patterns
5. Write tests covering all three loaders per the acceptance criteria
6. Run `npm run test` to verify passing
7. Submit PR referencing issue #94

## Proposal Classification

**Discovery only** — no code changes made. Repository access is the blocking dependency.
