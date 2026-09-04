---
bounty_id: 101
repo: Movalabs-crew/mova-store
title: "Add per-job timeout-minutes to every CI job"
reward: 80
type: discovery_proposal
status: claim_ready
date: 2026-09-04
---

# Bounty #101 — Add per-job timeout-minutes to every CI job

## Summary

Issue [#101](https://github.com/Movalabs-crew/mova-store/issues/101) requests that every job in `.github/workflows/ci.yml` declare an explicit `timeout-minutes` value to prevent stalled Rust/wasm builds from exhausting runner resources. Suggested bounds are 15–20 min for frontend/security jobs and 30 min for contracts/rust-security jobs.

## Existing Work

PR [#151](https://github.com/Movalabs-crew/mova-store/pull/151) is **open** and already implements the requested changes:

| Job | Timeout |
|-----|---------|
| Frontend | 15 min |
| Security | 15 min |
| Contracts | 30 min |
| Rust Security | 30 min |
| CI Success (aggregator) | 10 min |

- Every job block under `jobs:` has a `timeout-minutes` key.
- No review comments or change requests exist on the PR.
- The PR satisfies both acceptance criteria from the issue.

## Claim Recommendation

The bounty is **ready to claim**. PR #151 fully addresses the requirements with no outstanding feedback. Recommended next steps:

1. Verify the PR passes CI (check Actions tab for green status).
2. If CI is green, submit the bounty claim referencing PR #151.
3. If CI has not run recently, push a no-op commit or rebase to trigger a fresh run before claiming.

## Risks / Notes

- The PR has zero reviews; some bounty programs require at least one approval before payout. Check the program rules.
- Timeout values should be validated against historical run times to avoid false failures on slow but legitimate builds. The chosen values (15/30) align with the issue's suggestions and appear reasonable.
- No competing PRs were found for this issue.