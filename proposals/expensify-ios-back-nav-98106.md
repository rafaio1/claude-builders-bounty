---
bounty_id: expensify-98106
title: "iOS - Tapping the back button navigates the user to the Inbox after moving the expense"
url: https://github.com/Expensify/App/issues/98106
amount: 250
currency: USD
due_date: 2026-09-02
status: overdue_awaiting_payment
type: discovery_proposal
provider: ghostcli-auto[1m]
created: 2026-09-04
---

# Discovery Proposal: Expensify iOS Back Button Navigation Bug

## Issue Summary

**Issue:** [#98106](https://github.com/Expensify/App/issues/98106)
**Bounty:** $250 (Due for payment 2026-09-02 — **OVERDUE**)
**Labels:** Awaiting Payment, Bug, Daily, KSv2, External
**Assignees:** mallenexpensify, mollfpr, ikevin127, nabi-ebrahimi

## Bug Description

After moving a tracked expense from Self DM to a workspace chat via "Submit it to someone", tapping the back button on iOS navigates the user to the Inbox instead of returning to the Self DM chat where the expense originated.

### Reproduction Steps

1. Open app and navigate to Self DM chat
2. Submit a track expense
3. Tap "Submit it to someone" within the whisper action
4. Search for and select a workspace to create the expense
5. After redirection to Workspace chat, tap the back button

### Expected Behavior

User is redirected back to Self DM Chat.

### Actual Behavior

Tapping the Back button navigates the user to the Inbox after moving the expense to the workspace chat.

### Affected Platforms

- iOS App (primary report)
- iOS mWeb Safari/Chrome
- Android App/mWeb
- Desktop Chrome/Safari

This is a **cross-platform navigation stack issue**, not iOS-specific despite the title.

## Technical Analysis

### Root Cause Hypothesis

The navigation stack is being incorrectly managed during the expense move flow. When an expense is moved from Self DM → Workspace:

1. The expense creation in the workspace likely uses `Navigation.navigate()` or equivalent with a `replace` or `reset` strategy
2. This replaces the Self DM route in the stack with the Workspace chat route
3. The back button then pops to whatever was below Self DM (typically Inbox/LHN) instead of returning to Self DM

### Likely Code Areas (Expensify/App React Native)

- `src/libs/Navigation/` — Navigation stack management, especially `navigate()`, `goBack()`, and route replacement logic
- `src/pages/iou/request/` or `src/components/MoneyRequest*` — Expense submission and move flow
- `src/libs/actions/IOU.ts` or similar — Server-side optimistic actions for moving expenses between chats
- Route definitions in `src/ROUTES.ts` — How Self DM and Workspace chat routes are parameterized

### Fix Direction

The fix likely involves one of:

1. **Preserving the Self DM route in the navigation stack** when navigating to the workspace chat after expense move (use `push` instead of `replace`)
2. **Explicitly setting the back destination** via navigation params when redirecting post-move
3. **Using a modal/presentation layer** for the workspace selection that doesn't mutate the underlying stack

## Bounty Status Assessment

| Field | Value |
|-------|-------|
| Due Date | 2026-09-02 |
| Current Date | 2026-09-04 |
| Status | **OVERDUE by 2 days** |
| Label | "Awaiting Payment" (suggests fix was merged/approved) |
| Actionability | Low — if awaiting payment, the fix is likely already submitted |

### Recommendation

**DO NOT CLAIM.** The "Awaiting Payment" label strongly indicates a fix has already been approved and is in the payment pipeline. The bounty due date has passed. Submitting a new proposal at this stage would be redundant and unlikely to be accepted.

If pursuing regardless:
- Verify no PR has been linked/merged by checking the issue comments and linked PRs
- Confirm with Expensify contributor community that the bounty is still open
- The cross-platform nature means any fix must be validated on all listed platforms

## Risk Factors

- **Overdue status**: Payment processing may have already begun for another contributor
- **Cross-platform scope**: Despite iOS title, bug affects all platforms — fix validation burden is higher
- **Navigation complexity**: Expensify's navigation system has known complexity; fixes can introduce regressions in other flows
- **Multiple assignees**: Four assignees suggest active internal tracking; external contribution may face coordination overhead