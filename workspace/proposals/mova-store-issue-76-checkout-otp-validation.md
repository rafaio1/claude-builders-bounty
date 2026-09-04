# Bounty Proposal: Mova Store #76 — Checkout OTP Strict Validation

- **Bounty**: $90
- **Issue**: https://github.com/Movalabs-crew/mova-store/issues/76
- **Type**: discovery_proposal
- **Date**: 2026-09-04
- **Status**: ready-for-claim

## Summary

The checkout flow in `app/checkout/page.tsx` validates the one-time password (OTP) using loose integer comparison (`parseInt(enteredOtp) === otp`). This accepts malformed input such as digits followed by non-numeric characters (e.g., `"123abc"` parses to `123`) and fails to enforce zero-padded 6-digit codes. The fix requires strict string equality against a zero-padded value, wiring up the existing `validateOTP` utility, and constraining the input field.

## Vulnerability Details

### Current Behavior (Insecure)

```tsx
// app/checkout/page.tsx:31
const otp = Math.floor(Math.random() * 1000000) + 1;

// Validation (loose)
if (parseInt(enteredOtp) === otp) { /* success */ }
```

**Problems:**

1. `Math.random() * 1000000 + 1` produces integers from 1–999999, often fewer than 6 digits (e.g., `42` instead of `000042`).
2. `parseInt("123abc")` returns `123`, so trailing junk is silently accepted.
3. No `maxLength`, `inputMode`, or pattern constraint on the input element.
4. `lib/validation.ts` contains an unused `validateOTP` function that enforces the correct format.

### Expected Behavior (Secure)

- OTP generated as a zero-padded 6-digit string: `"000042"`.
- Validation via exact string equality after trimming input.
- Input field restricted to 6 numeric characters with `inputMode="numeric"` and `maxLength={6}`.
- Letters-only and mixed alphanumeric inputs rejected.

## Proposed Fix

### 1. Generate Zero-Padded OTP

Replace numeric generation with padded string:

```tsx
// Before
const otp = Math.floor(Math.random() * 1000000) + 1;

// After
const otp = String(Math.floor(Math.random() * 1000000)).padStart(6, "0");
```

### 2. Strict String Comparison

Replace `parseInt` with trimmed string equality:

```tsx
// Before
if (parseInt(enteredOtp) === otp) { ... }

// After
if (enteredOtp.trim() === otp) { ... }
```

Or delegate to the existing validator in `lib/validation.ts`:

```tsx
import { validateOTP } from "@/lib/validation";

if (validateOTP(enteredOtp, otp)) { ... }
```

### 3. Constrain Input Element

```tsx
<input
  type="text"
  inputMode="numeric"
  maxLength={6}
  pattern="[0-9]{6}"
  value={enteredOtp}
  onChange={(e) => setEnteredOtp(e.target.value.replace(/\D/g, ""))}
/>
```

### 4. Wire Up Existing Validator

Ensure `lib/validation.ts` exports and is imported:

```ts
// lib/validation.ts
export function validateOTP(input: string, expected: string): boolean {
  const cleaned = input.trim();
  return /^\d{6}$/.test(cleaned) && cleaned === expected;
}
```

## Acceptance Criteria Checklist

- [ ] Wrong numeric codes rejected
- [ ] Digits followed by junk characters rejected (e.g., `"123abc"`)
- [ ] Correct zero-padded values accepted (e.g., `"000042"`)
- [ ] Letters-only input rejected
- [ ] `validateOTP` used in checkout validation
- [ ] Input has `maxLength={6}` and `inputMode="numeric"`
- [ ] OTP stored/generated as zero-padded 6-digit string

## Files to Modify

| File | Change |
|------|--------|
| `app/checkout/page.tsx` | Pad OTP generation, replace `parseInt` with string equality or `validateOTP`, add input constraints |
| `lib/validation.ts` | Ensure `validateOTP` is exported and correctly implemented |

## Risk Assessment

- **Severity**: Medium — authentication bypass at checkout allows unauthorized order completion.
- **Scope**: Single route (`/checkout`), no database schema changes.
- **Regression risk**: Low — change is localized to OTP comparison logic; existing tests should cover valid code acceptance.

## Notes

- Source code for `mova-store` is not present in the local workspace; this proposal is based on the issue description and fetched repository metadata.
- Implementation should include unit tests for `validateOTP` covering edge cases: leading zeros, trailing whitespace, non-numeric input, wrong length.