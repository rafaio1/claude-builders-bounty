# Discovery Proposal: Contract Suite Pinning Error Envelope Shape Across All Handlers

- **Bounty**: $75 USD (USDC)
- **Issue**: [Lilly-Protocol/lily-backend#278](https://github.com/Lilly-Protocol/lily-backend/issues/278)
- **Type**: Testing / API Contract
- **Discovered**: 2026-09-04
- **Status**: Proposal Ready — Not Claimed

## Problem Summary

The lily-backend API defines a shared error response shape (`ApiErrorResponse`) in `api-response.ts`:

```ts
{ success: false, message: string, code?: string, details?: Record<string, string[]> }
```

However, there is no single contract test that verifies **every** handler conforms to this envelope across all HTTP error status classes. Existing tests cover individual cases in isolation:

- `not-found.test.ts` — 404 responses
- `method-not-allowed.test.ts` — 405 responses
- `rate-limiter-envelope.test.ts` — 429 responses
- `malformed-json.test.ts` — 400 validation
- `production-error-redaction.test.ts` — 500 internal errors

This fragmented coverage means a handler could drift from the contract (e.g., omitting `success: false`, returning `message` as a non-string, or including `code` when undefined) without any test catching it. A unified contract suite prevents such regressions.

## Acceptance Criteria (from issue)

1. Every tested response body has `success === false` and `message` of type `string`.
2. The `code` field appears **only** when defined by the handler, matching the contract in `api-response.ts`.
3. Validation errors (400) include `details` containing per-field messages.

## Required Status Classes to Cover

| Status | Trigger | Expected Envelope Fields |
|--------|---------|--------------------------|
| 400 | Malformed JSON / validation failure | `success`, `message`, `details` |
| 401 | Missing API key | `success`, `message`, `code` |
| 403 | Invalid/expired API key | `success`, `message`, `code` |
| 404 | Unknown route or agent ID | `success`, `message` |
| 405 | Wrong HTTP method on valid route | `success`, `message` |
| 410 | Expired quote reference | `success`, `message`, `code` |
| 429 | Rate limit exceeded | `success`, `message`, `code` |
| 500 | Internal server error | `success`, `message` (no stack/leak) |

## Proposed Implementation Plan

### 1. New Test File: `tests/error-envelope-contract.test.ts`

A single Vitest describe block with one `it()` per status class. Each test:

1. Constructs a representative request that triggers the target status.
2. Asserts the response status code matches expectation.
3. Parses the JSON body and validates against the envelope contract.

### 2. Shared Assertion Helper

Create a reusable `assertErrorEnvelope(response, expectedStatus, options?)` helper that:

- Checks `response.status === expectedStatus`
- Parses body as JSON (fails test if not valid JSON)
- Asserts `body.success === false`
- Asserts `typeof body.message === 'string'` and `body.message.length > 0`
- If `options.expectCode === true`: asserts `typeof body.code === 'string'`
- If `options.expectCode === false`: asserts `!('code' in body)`
- If `options.expectDetails === true`: asserts `body.details` is a non-null object with at least one key mapping to a string array
- Asserts no unexpected top-level keys beyond `{ success, message, code?, details? }`

### 3. Test Cases Outline

```ts
describe('Error envelope contract', () => {
  it('400 validation error includes details with per-field messages', async () => {
    // POST to an endpoint with invalid body → assert envelope + details
  });

  it('401 missing API key returns code field', async () => {
    // Request without Authorization header → assert envelope + code
  });

  it('403 invalid API key returns code field', async () => {
    // Request with bad key → assert envelope + code
  });

  it('404 unknown route omits code field', async () => {
    // GET /nonexistent → assert envelope, no code
  });

  it('405 wrong method omits code field', async () => {
    // DELETE on GET-only route → assert envelope, no code
  });

  it('410 expired quote returns code field', async () => {
    // Reference stale quote ID → assert envelope + code
  });

  it('429 rate limit returns code field', async () => {
    // Burst requests past limit → assert envelope + code
  });

  it('500 internal error redacts internals and omits code', async () => {
    // Trigger unhandled error → assert envelope, no stack trace leak
  });
});
```

### 4. Integration with Existing Tests

- The new suite is **additive** — it does not replace existing partial tests.
- Existing tests continue to verify handler-specific behavior; this suite verifies the shared shape.
- If existing tests already cover some assertions, they serve as redundant safety; no duplication concern.

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Triggering 500 in test requires controllable failure point | Medium | Identify existing error injection mechanism or add a test-only endpoint |
| Rate limiter test may be flaky under CI load | Low | Use fake timers or mock rate limiter state directly |
| 410 expired quote requires pre-seeded expired data | Low | Seed in test setup; use deterministic timestamps |
| Envelope assertion too strict blocks legitimate extensions | Low | Allow optional fields via `options` parameter; fail only on missing required fields |
| Test runner config may need adjustment for new file | Low | Follow existing test file naming convention (`*.test.ts`) |

## Estimated Effort

- **Implementation**: 2–3 hours (helper + 8 test cases)
- **Testing & Debugging**: 1 hour (ensure all triggers work in test environment)
- **Total**: ~3–4 hours

## Recommendation

**Claim this bounty.** The scope is well-defined with clear acceptance criteria. The existing partial tests prove each trigger mechanism works — this task is primarily about unifying them under a single contract assertion. The shared helper pattern reduces boilerplate and makes future handler additions automatically covered. No production code changes required.

## Next Steps

1. Clone/fork `lily-backend` repo
2. Review `api-response.ts` for exact type definition
3. Study existing partial tests for trigger patterns
4. Implement `assertErrorEnvelope` helper
5. Write all 8 status-class test cases
6. Run full test suite to confirm no regressions
7. Submit PR referencing issue #278
8. Link PR in bounty claim comment