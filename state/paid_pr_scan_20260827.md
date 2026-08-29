# Paid PR scan — 2026-08-27

Status: **0 opportunities passed the Revenue v2 gates.** Keep `work_orders=[]`.

## Closest rejects

- D2 #1578 / Algora, nominal USD 50: issue open and payer active, but already assigned with an active linked PR. Reject duplicate-work risk.
  - https://github.com/terrastruct/d2/issues/1578
  - https://algora.io/terrastruct/bounties?status=open
- Mudlet #5310 / Algora, nominal USD 30: active project and payer history, but multiple claims and existing PRs. Reject competition and poor EV.
  - https://github.com/Mudlet/Mudlet/issues/5310
  - https://algora.io/Mudlet/bounties?status=open
- Electron #48191 / Opire, nominal USD 100: Opire listing is stale; the linked official GitHub issue is closed. Reject platform/GitHub state mismatch.
  - https://github.com/electron/electron/issues/48191
  - https://app.opire.dev/issues/01KPXQ3E5HG0S4MDWQ33Q63KMS
- Drizzle #1188 / legacy Algora: maintainer states the sponsor removed the bounty. Reject reward unavailable.
  - https://github.com/drizzle-team/drizzle-orm/issues/1188
- zeroperl #7 / Opire, nominal USD 1,500: repository redirects and linked issue is deleted. Reject stale listing/no acceptance target.
  - https://github.com/uswriting/zeroperl/issues/7
  - https://app.opire.dev/issues/01JN06N9GS8Q1KB2NJ318258HR

## Admission rule

Create a paid work order only when the linked issue is open, the reward is currently valid, payout path and claimant eligibility are verified, the maintainer/payer is active, there is no assignee or active competing PR, the conservative implementation effort is at most eight hours, no human/hardware/social proof is required, and expected net value is at least the configured minimum. Platform listings never override the linked official issue.

Unpaid reputation work may run only in a separate lane and must never be counted as revenue, receivable, claim, or financial pipeline.
