---
bounty_id: mova-store-83
provider: movalabs-crew
repo: Movalabs-crew/mova-store
issue: 83
title: "Make Navbar About Us / Contact Us links navigate home when clicked from non-landing pages"
bounty_amount: 90
currency: USD
type: discovery_proposal
status: proposal_ready
created: 2026-09-04
---

# Proposal: Fix Navbar Anchor Links on Non-Landing Pages

## Problem Summary

The navbar's `About Us` and `Contact Us` links use anchor hrefs (`#aboutus`, `#contact`) that only resolve on the landing page. A document-level click handler in `components/Navbar.jsx:26-46` calls `preventDefault()` on all `a[href^='#']` links and attempts smooth-scroll to the target element. When the user is on `/shop`, `/blog`, or `/checkout`, the target section does not exist in the DOM, so the click is swallowed and nothing happens.

## Root Cause

- **File**: `components/Navbar.jsx`, lines 26–46
- **Behavior**: Global event listener matches `a[href^='#']`, prevents default navigation, then queries `document.querySelector(href)`. If the element is `null`, the handler returns without fallback.
- **Impact**: Users cannot reach About Us or Contact Us sections from any non-home route.

## Proposed Fix

Modify the click handler to detect when the target element is absent and fall back to full navigation to the home page with the anchor fragment:

```jsx
// Pseudocode for updated handler
document.addEventListener('click', (e) => {
  const anchor = e.target.closest('a[href^="#"]');
  if (!anchor) return;

  const targetId = anchor.getAttribute('href');
  const targetEl = document.querySelector(targetId);

  if (targetEl) {
    // Same-page smooth scroll (existing behavior)
    e.preventDefault();
    targetEl.scrollIntoView({ behavior: 'smooth' });
  } else {
    // Target not on this page — navigate to home with fragment
    // Do NOT preventDefault; let browser navigate to /#aboutus or /#contact
    // Optionally use router.push('/' + targetId) for SPA frameworks
  }
});
```

### Key Implementation Notes

1. **Preserve existing smooth scroll**: When `targetEl` exists (i.e., user is on the home page), behavior must remain identical to current implementation.
2. **Fallback navigation**: When `targetEl` is `null`, allow default navigation to `/#<fragment>` or use the app router to push `'/' + targetId`. This ensures the home page loads and the browser scrolls to the section.
3. **Post-navigation scroll**: If using an SPA router, attach a one-time scroll handler after route change completes to ensure the section is scrolled into view (some routers strip fragments on navigation).
4. **No changes to link markup**: The fix is entirely within the click handler; no need to conditionally render different hrefs based on current route.

## Acceptance Criteria Verification

| Criterion | How Verified |
|-----------|-------------|
| Clicking About Us from `/shop` lands on home page's about section | Manual test: navigate to `/shop`, click About Us → verify URL becomes `/#aboutus` and section is visible |
| Clicking Contact Us from `/blog` lands on home page's contact section | Manual test: navigate to `/blog`, click Contact Us → verify URL becomes `/#contact` and section is visible |
| Same-page smooth scroll still works on home page | Manual test: on `/`, click About Us → verify smooth scroll without page reload |
| No regression on other anchor links | Verify any other `#`-prefixed links in the app still function correctly |

## Risk Assessment

- **Low risk**: Change is isolated to a single event handler in `Navbar.jsx`.
- **Edge case**: If additional pages ever add their own `#aboutus` or `#contact` sections, the handler would correctly scroll to those instead of navigating home (desired behavior).
- **SPA consideration**: If the app uses client-side routing (React Router, Next.js, etc.), prefer `router.push()` over raw `<a>` navigation to maintain SPA behavior. Check framework before implementing.

## Estimated Effort

- **Scope**: Single file change (~10–15 lines modified)
- **Testing**: Manual verification across 3–4 routes
- **Time estimate**: < 1 hour

## Claim Readiness

This proposal documents the root cause, fix strategy, and acceptance criteria mapping. Ready for implementation claim upon approval.