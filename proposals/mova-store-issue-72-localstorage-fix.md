# Proposal: Fix localStorage.clear() wiping Supabase session (Issue #72)

## Problem
`localStorage.clear()` is called in `app/checkout/page.tsx` (lines 63, 102) and `components/Navbar.jsx` (line 66). This removes **all** keys from localStorage, including the Supabase auth session (`sb-*-auth-token`), inadvertently logging users out after checkout or when interacting with cart-related flows.

## Solution
Replace blanket `localStorage.clear()` with targeted removal of only cart-related keys. Supabase session management must remain untouched; logout should exclusively use `supabase.auth.signOut()`.

## Patch

### `app/checkout/page.tsx`

```diff
- localStorage.clear();
+ // Only clear cart data; preserve Supabase session and other app state
+ const cartKeys = Object.keys(localStorage).filter(key =>
+   key.startsWith('cart_') || key === 'mova_cart' || key === 'checkout_items'
+ );
+ cartKeys.forEach(key => localStorage.removeItem(key));
```

Apply this replacement at both line 63 and line 102.

### `components/Navbar.jsx`

```diff
  const handleLogout = async () => {
-   localStorage.clear();
+   // Clear non-session app state; supabase.auth.signOut() handles session cleanup
+   const keysToPreserve = Object.keys(localStorage).filter(key =>
+     key.startsWith('sb-') && key.endsWith('-auth-token')
+   );
+   const allKeys = Object.keys(localStorage);
+   allKeys.forEach(key => {
+     if (!keysToPreserve.includes(key)) {
+       localStorage.removeItem(key);
+     }
+   });
    await supabase.auth.signOut();
  };
```

## Recommended: Shared Utility

Create `lib/storage.ts` to centralize safe clearing and prevent future regressions:

```typescript
// lib/storage.ts

const SUPABASE_SESSION_PATTERN = /^sb-.*-auth-token$/;

/** Cart-related key prefixes/patterns — update as the app evolves */
const CART_KEY_PATTERNS = [
  /^cart_/i,
  /^mova_cart$/i,
  /^checkout_items$/i,
];

export function clearCartStorage(): void {
  const keys = Object.keys(localStorage).filter(key =>
    CART_KEY_PATTERNS.some(pattern => pattern.test(key))
  );
  keys.forEach(key => localStorage.removeItem(key));
}

export function clearNonSessionStorage(): void {
  const keys = Object.keys(localStorage).filter(
    key => !SUPABASE_SESSION_PATTERN.test(key)
  );
  keys.forEach(key => localStorage.removeItem(key));
}
```

Then refactor the call sites:

```diff
  // app/checkout/page.tsx
- localStorage.clear();
+ import { clearCartStorage } from '@/lib/storage';
+ clearCartStorage();

  // components/Navbar.jsx
- localStorage.clear();
+ import { clearNonSessionStorage } from '@/lib/storage';
+ clearNonSessionStorage();
  await supabase.auth.signOut();
```

## Comment to Post on Issue #72

---

### Fix for `localStorage.clear()` wiping Supabase session

**Root cause:** Three calls to `localStorage.clear()` remove all keys including `sb-*-auth-token`, destroying the persisted Supabase session.

**Fix:** Replace with targeted key removal that preserves Supabase session tokens.

#### Changes

1. **`app/checkout/page.tsx` (lines 63 & 102):** Replace `localStorage.clear()` with a filtered removal that only deletes cart-related keys (`cart_*`, `mova_cart`, `checkout_items`).

2. **`components/Navbar.jsx` (line 66 in `handleLogout`):** Replace `localStorage.clear()` with a filtered removal that preserves any key matching `sb-*-auth-token`. Session cleanup is already handled by the subsequent `supabase.auth.signOut()` call.

3. **(Recommended)** Extract a shared utility in `lib/storage.ts` exporting `clearCartStorage()` and `clearNonSessionStorage()` to prevent future regressions. Both functions explicitly skip Supabase session keys.

#### Key principle
Never call `localStorage.clear()` in an app that uses Supabase client-side auth. Always use targeted `removeItem()` calls, and let `supabase.auth.signOut()` be the sole mechanism for session teardown.

I can submit a PR with these changes if the maintainers approve this approach.

---