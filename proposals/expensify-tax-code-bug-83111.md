# Discovery Proposal: Expensify Tax Code Bug #83111

## Bounty Metadata
- **Issue**: https://github.com/Expensify/App/issues/83111
- **Title**: Tax - Tax name is missing and tax is no longer selected after changing tax code
- **Bounty**: $250
- **Due Date**: 2026-08-28 (OVERDUE as of 2026-09-04)
- **Status**: Awaiting Payment — PR already deployed to production
- **Upwork Job ID**: 2024978932059523878
- **Type**: discovery_proposal

## Bug Summary
In Expensify App v9.3.24-1, editing a tax code in workspace settings causes the associated tax rate name to disappear from existing expenses. The tax also becomes deselected. When merging multiple expenses, only the percentage displays without the rate name. This affects all platforms (Android, iOS, Windows, macOS).

## Reproduction Steps
1. Enable taxes; create expenses with 0% and 5% rates.
2. Confirm tax field shows correct rate name.
3. Navigate to workspace settings → upgrade workspace.
4. Edit and save the tax code for both 0% and 5% rates.
5. Reopen an expense → click tax field → name is missing.
6. Merge multiple expenses via checkbox → only percentage shown.

## Expected Behavior
- Tax rate name persists after editing the tax code.
- Tax remains selected in the list post-edit.
- Merged expenses display full tax rate name, not just percentage.

## Actual Behavior
- Tax rate name disappears after modifying the tax code.
- Tax is deselected in the picker.
- Merged expenses show only the numeric percentage.

## Root Cause Hypothesis
The bug likely stems from how tax codes are keyed/referenced when updated. Possible causes:
1. **Key mutation on edit**: Editing a tax code may generate a new internal key/ID, orphaning references in existing expense records that still point to the old key.
2. **Optimistic update mismatch**: The UI may optimistically remove the old tax entry before the server confirms the new one, causing a transient or permanent loss of the name mapping.
3. **Policy-level cache invalidation**: After saving edited tax codes, the policy/tax data may be re-fetched but the local expense objects aren't reconciled against the new tax map, leaving stale references.
4. **Merge aggregation logic**: The merge view may look up tax names by current policy keys only, ignoring historical keys attached to individual expenses.

## Proposed Investigation Path
1. Locate the tax code edit handler in workspace settings (likely in `src/pages/workspace/taxes/` or similar).
2. Trace how tax entries are stored in Onyx — check if the key changes on edit vs. being updated in-place.
3. Review the expense tax field component to see how it resolves a tax rate name from a stored reference.
4. Check the merge expense logic for how it aggregates tax display values.
5. Verify whether the backend returns the same tax ID after an edit or generates a new one.

## Claim Eligibility Assessment
⚠️ **This bounty is marked "Awaiting Payment"**, meaning a fix has already been submitted, reviewed, merged, and deployed. The due date (2026-08-28) has passed. New claims for this specific bug are unlikely to be accepted unless the existing fix was reverted or incomplete.

**Recommendation**: Do NOT begin implementation work. If pursuing, first confirm on the issue thread whether the bounty is still open for additional contributors or if this is solely awaiting payment disbursement to the original solver.

## Action Items
- [ ] Verify current issue status on GitHub (check for closed/merged PR links)
- [ ] Confirm bounty availability before investing development time
- [ ] If still open, follow investigation path above to locate root cause
- [ ] Submit proposal comment on issue with root cause analysis before coding