# Bounty Discovery: Add Unit Tests for lib/auth.js (Issue #41)

- **Source:** https://github.com/Movalabs-crew/mova-store/issues/41
- **Bounty:** $90
- **Type:** discovery_proposal
- **Date:** 2026-09-04

## Summary

Issue #41 requests unit tests for `lib/auth.js` in the Movalabs-crew/mova-store repository. The file contains `mapAuthUser` (lines 6–21) and auth helpers `login`, `signup`, `logout`, `loginWithGoogle` (lines 23–76) that wrap Supabase calls with throw-on-error behavior. None of these currently have test coverage.

## Requirements

1. Create `tests/lib/auth.test.js` using Vitest (`vi.mock` for `./supabase`).
2. Cover `mapAuthUser(null)` and every fallback precedence path: `full_name` → `name` → `display_name` → email prefix → `'User'` default.
3. Verify each helper returns the mapped user on success and throws `Error(message)` when the mocked Supabase client returns an error.
4. No environment variables or real network calls — Supabase must be fully mocked.
5. `npm run test` must pass.

## Acceptance Criteria

- [ ] `mapAuthUser` fallback precedence is exhaustively asserted.
- [ ] All four helpers have both resolve and reject paths tested.
- [ ] Test file runs in isolation with no external dependencies.
- [ ] CI-green via `npm run test`.

## Linked PR

- #154 (referenced in issue as existing work)

## Notes for Implementation

- Repo was not found locally under `/Agentic`; contributor will need to clone `Movalabs-crew/mova-store`.
- Stack appears to be Vite/Vitest based on the `vi.mock` directive in the issue description.
- The mock should replicate the Supabase JS client shape (`auth.signInWithPassword`, `auth.signUp`, `auth.signOut`, `auth.signInWithOAuth`) including the `{ data, error }` return tuple.
- Consider extracting `mapAuthUser` into a pure function importable without side effects to simplify testing.

## Status

**Discovery complete.** Proposal ready for claim or implementation assignment.