# Proposal: Compare Configured API Keys in Constant Time

- **Bounty**: [$75] Compare configured API keys in constant time
- **Issue**: https://github.com/Lilly-Protocol/lily-backend/issues/287
- **Repo**: Lilly-Protocol/lily-backend
- **Type**: discovery_proposal
- **Date**: 2026-09-04

## Vulnerability Summary

The `apiKeyAuth` middleware in `src/common/http/api-key-auth.middleware.ts` currently validates API keys using a standard JavaScript string equality check (`!==`). This comparison short-circuits on the first differing byte, creating a timing side-channel that allows an attacker to deduce the correct API key character-by-character by measuring response latency with sufficient statistical precision.

## Proposed Fix

Replace the non-constant-time string comparison with Node.js `crypto.timingSafeEqual`. The implementation must:

1. Reject missing or empty keys immediately (preserving existing 401/403 behavior).
2. Convert both the provided key and the configured key to `Buffer` instances using the same encoding (UTF-8).
3. If buffer lengths differ, perform a dummy comparison against a zero-filled buffer of the configured key's length before returning 403 — this prevents length-leakage while still rejecting wrong-length inputs.
4. Call `crypto.timingSafeEqual(bufA, bufB)` for equal-length buffers and return 403 only when it returns `false`.

### Reference Implementation Sketch

```ts
import { timingSafeEqual } from 'node:crypto';

function safeCompare(provided: string, expected: string): boolean {
  const expectedBuf = Buffer.from(expected, 'utf8');
  if (!provided) return false;

  const providedBuf = Buffer.from(provided, 'utf8');
  if (providedBuf.length !== expectedBuf.length) {
    // Constant-time reject: compare against a decoy to avoid leaking length
    const decoy = Buffer.alloc(expectedBuf.length);
    timingSafeEqual(expectedBuf, decoy);
    return false;
  }

  return timingSafeEqual(providedBuf, expectedBuf);
}
```

The middleware should call `safeCompare(providedKey, securityConfig.authApiKey)` instead of `providedKey !== securityConfig.authApiKey`.

## Acceptance Criteria Mapping

| Criterion | How It Is Met |
|---|---|
| Missing/wrong key still returns 401/403 exactly as before | Early guard for missing header preserved; `safeCompare` returns `false` for all invalid inputs, triggering the same `AppError(403, ...)` path |
| Comparison uses `crypto.timingSafeEqual` or equivalent constant-time primitive | Direct use of `timingSafeEqual` from `node:crypto` |
| Unit test covers matching, wrong-length, and near-miss keys | New test file `api-key-auth.middleware.spec.ts` with three cases: exact match → passes; shorter/longer key → 403; single-char-off key → 403 |

## Testing Strategy

- **Unit**: Vitest suite exercising `safeCompare` directly and the full middleware via mocked `next()` / `AppError`. Include a timing-harness test that asserts no statistically significant latency difference between wrong-first-byte and wrong-last-byte inputs over ≥10,000 iterations.
- **Integration**: Existing E2E auth tests must continue to pass unchanged.
- **Regression**: Verify that legitimate requests with valid keys are not impacted in latency beyond negligible overhead (~µs).

## Risk Assessment

- **Low risk**: Change is isolated to one middleware function; no schema, migration, or API contract changes.
- **Encoding caveat**: Both sides must use identical encoding. UTF-8 is the project default and matches how keys are stored in config. Document this assumption in code comments.
- **Length-leak mitigation**: The dummy-comparison branch ensures wrong-length inputs do not leak the expected key length through early-return timing.

## Status

**READY FOR IMPLEMENTATION** — proposal complete, awaiting PR submission against `Lilly-Protocol/lily-backend`.