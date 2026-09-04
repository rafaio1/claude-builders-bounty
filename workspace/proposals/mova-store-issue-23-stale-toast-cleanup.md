# Discovery Proposal: Fix Toast exit-timer cleanup (mova-store #23)

- **Bounty**: $100
- **Issue**: https://github.com/Movalabs-crew/mova-store/issues/23
- **Type**: discovery_proposal
- **Date**: 2026-09-04
- **Status**: Claimed — PR submitted, awaiting review

## Summary

Issue #23 reports that the Toast component’s exit timer is scheduled inside a nested `setTimeout` callback, and its cleanup function is returned from within that inner callback where it is never executed by React. As a result, the 300ms exit timer cannot be cancelled when `show` changes or the component unmounts. If a new toast is triggered within that window, the stale `onClose` from the previous toast fires and incorrectly hides the fresh message.

The same pattern is duplicated in `Notification.tsx`.

## Root Cause

In both `components/Toast.jsx` and `Notification.tsx`, the effect body schedules an outer timeout that then schedules the exit timeout. The cleanup return (`() => clearTimeout(exitTimer)`) lives inside the outer timeout’s callback, so React never receives it as the effect’s cleanup. When `show` toggles or the component unmounts, only the outer timer (if any) is cleaned up; the inner exit timer continues to fire and calls `onClose` against whatever toast is currently visible.

## Proposed Fix

Restructure the `useEffect` so the exit timer is created directly in the effect body (not inside another async callback) and its cleanup is returned at the top level of the effect. This ensures React can cancel the exit timer whenever dependencies change or the component unmounts.

### Acceptance Criteria (from issue)

1. Showing toast A then re-showing toast B within 300ms must **not** call `onClose` for B (verified with fake timers).
2. Unmounting mid-exit must **not** trigger `onClose` afterwards.
3. Both `Toast.jsx` and `Notification.tsx` must implement the corrected pattern.
4. `npm run test` must pass.

## Current Status

- **Claimant**: zhangb06
- **PR**: [#145](https://github.com/Movalabs-crew/mova-store/pull/145) — “fix: keep toast exit timer in effect scope so stale onClose cannot hide a re-shown toast”
- **Review**: Pending maintainer review and merge.

## Recommendation

No further implementation work is needed from this agent. The bounty has been claimed and a PR addressing all acceptance criteria has been submitted. Next steps are:

1. Monitor PR #145 for review feedback or requested changes.
2. If the PR is merged and tests pass on CI, the bounty is payable to zhangb06.
3. If the PR is abandoned or fails review after a reasonable period, the bounty may be reopened for re-claim.

## References

- Issue: https://github.com/Movalabs-crew/mova-store/issues/23
- PR: https://github.com/Movalabs-crew/mova-store/pull/145