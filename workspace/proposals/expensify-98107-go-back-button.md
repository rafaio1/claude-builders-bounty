---
bounty_id: expensify-app-98107
issue_url: https://github.com/Expensify/App/issues/98107
title: "Web - Go back to home page button is not responsive"
bounty_amount: 250
currency: USD
due_date: 2026-09-02
status: discovery_complete
provider: ghostcli-auto[1m]
created_at: 2026-09-04
type: discovery_proposal
---

# Discovery Proposal: Expensify App #98107

## Issue Summary

**Title:** [Due for payment 2026-09-02] [$250] Web - Go back to home page button is not responsive  
**Bounty:** $250 USD  
**Labels:** Awaiting Payment, Bug, Daily, External  
**Regression Version:** v9.4.51-1  
**Environments Affected:** Staging and Production  

## Reproduction Steps

1. Navigate to the specific staging URL (referenced in issue)
2. Click "Go back to home page" button

## Expected Behavior

Home page will open.

## Actual Behavior

"Go back to home page" button is not responsive — no navigation occurs.

## Current Status

- Issue is labeled **"Awaiting Payment"**, indicating a fix has likely been merged or approved but payment processing is pending.
- No linked PRs found under the Development section at time of discovery.
- References regression test #467825 and an associated Upwork job.
- Due date was **2026-09-02** (2 days overdue as of 2026-09-04).

## Assessment

### Claim Viability: LOW

This bounty appears to be in the **payment processing stage** rather than open for new claims:

1. The "Awaiting Payment" label typically means a solution has been accepted and is queued for payout.
2. The due date has already passed (2026-09-02), suggesting the work window has closed.
3. No active "Help Wanted" or "Open to contributors" label is present.

### Recommended Action

- **Do not submit a new fix** — the bounty is likely already claimed and awaiting disbursement.
- **Monitor** the issue for status changes (e.g., "Paid" label) to confirm resolution.
- If the issue reverts to "Open" or "Help Wanted" without a merged PR, reassess claim viability.

## Technical Notes (if reopened)

The bug is a navigation failure on web, likely caused by:
- Event handler not attached or prevented by a conditional render
- Router state mismatch after a redirect or auth check
- Regression introduced in v9.4.51-1 — diff against prior release tag would identify the breaking commit
- Check `Navigation` / `Link` components and any recent changes to route guards or error boundaries

## References

- Issue: https://github.com/Expensify/App/issues/98107
- Regression Test: #467825