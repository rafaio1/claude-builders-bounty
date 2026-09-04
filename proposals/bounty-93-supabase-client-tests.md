# Bounty #93: Add Unit Tests for Shared Supabase Client Construction

- **Source**: https://github.com/Movalabs-crew/mova-store/issues/93
- **Bounty**: $85
- **Type**: discovery_proposal
- **Date**: 2026-09-04
- **Status**: Discovery Complete — Repo Not Locally Available

## Summary

Issue #93 requests unit tests for `lib/supabase.js` in the `mova-store` repository. The file constructs a Supabase client at module scope with conditional logic for missing environment variables, but none of this branching is currently tested.

## Acceptance Criteria (from issue)

1. Create `tests/lib/supabase.test.ts` that mocks `@supabase/supabase-js` and reloads the module under stubbed environments.
2. Verify `createClient` receives the stubbed URL/key and auth options (`persistSession`, `autoRefreshToken`, `detectSessionInUrl`).
3. Verify `console.warn` fires and placeholders are used when env vars are empty.
4. `npm run test` passes.

## Discovery Findings

### Local Codebase Search

- No `mova-store` directory found under `/Agentic`.
- No `lib/supabase.js` or `lib/supabase.ts` file exists in the local workspace.
- Grep for "supabase" across all JS/TS files returned only unrelated hits in `node_modules` and a single reference in `ophirpay/src/lib/startup.ts` (different project).

### Conclusion

The `mova-store` repository is not cloned or available in the current working environment. This bounty cannot be executed locally without first obtaining the source code.

## Proposed Implementation Plan

If the repo were available, the implementation would follow this approach:

### Test File: `tests/lib/supabase.test.ts`

```typescript
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';

// Mock @supabase/supabase-js before importing the module under test
vi.mock('@supabase/supabase-js', () => ({
  createClient: vi.fn(() => ({ mock: true })),
}));

describe('lib/supabase.js', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    vi.resetModules();
    process.env = { ...originalEnv };
  });

  afterEach(() => {
    process.env = originalEnv;
    vi.restoreAllMocks();
  });

  it('passes correct URL, key, and auth options to createClient', async () => {
    process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://test.supabase.co';
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'test-anon-key';

    const { createClient } = await import('@supabase/supabase-js');
    await import('../../lib/supabase.js');

    expect(createClient).toHaveBeenCalledWith(
      'https://test.supabase.co',
      'test-anon-key',
      expect.objectContaining({
        auth: expect.objectContaining({
          persistSession: expect.any(Boolean),
          autoRefreshToken: expect.any(Boolean),
          detectSessionInUrl: expect.any(Boolean),
        }),
      })
    );
  });

  it('warns and uses placeholders when env vars are missing', async () => {
    delete process.env.NEXT_PUBLIC_SUPABASE_URL;
    delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { createClient } = await import('@supabase/supabase-js');
    await import('../../lib/supabase.js');

    expect(warnSpy).toHaveBeenCalled();
    expect(createClient).toHaveBeenCalledWith(
      expect.any(String), // placeholder URL
      expect.any(String), // placeholder key
      expect.anything()
    );
  });
});
```

### Key Technical Considerations

- **Module reloading**: Since `lib/supabase.js` constructs the client at module scope, each test must use `vi.resetModules()` and dynamic `import()` to re-evaluate the module with fresh env vars.
- **Mock hoisting**: `vi.mock()` must be at the top level; the factory returns a mock `createClient` that can be inspected per-test.
- **Auth option shape**: The exact boolean values for `persistSession`, `autoRefreshToken`, and `detectSessionInUrl` should be verified against the actual source once available.
- **Test runner**: The issue references `npm run test`; confirm whether the project uses Vitest, Jest, or another runner and adjust imports accordingly.

## Blockers

| Blocker | Resolution |
|---------|-----------|
| `mova-store` repo not cloned locally | Clone from `https://github.com/Movalabs-crew/mova-store` before implementation |
| Exact env var names unconfirmed | Inspect `lib/supabase.js` source to verify variable names and placeholder values |
| Test runner unknown | Check `package.json` scripts and devDependencies after clone |

## Recommendation

This bounty is straightforward and well-scoped. Estimated effort: ~1 hour once the repo is available. Recommend cloning the repo and proceeding with implementation.