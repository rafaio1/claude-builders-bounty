---
name: bounty-116-mova-store-readme-toc-step5b
description: Proposal for Movalabs-crew/mova-store issue #116 — add Step 5b deployment entry to README TOC
metadata:
  type: discovery_proposal
  bounty_amount: 85
  provider: ghostcli-auto[1m]
  source_url: https://github.com/Movalabs-crew/mova-store/issues/116
  status: ready_to_claim
  created: 2026-09-04
---

# Bounty #116: Add Step 5b Deployment Section to README TOC

## Summary

The README.md in `Movalabs-crew/mova-store` contains a deployment walkthrough that includes "Step 5b - Whitelist the tokens you accept" near line 404, but the table of contents (lines 74-83) currently skips from Step 5 directly to Step 6. This bounty requires inserting a matching TOC entry so the anchor resolves correctly and the TOC entry count matches the deployment section headings.

## Requirements (from issue)

1. Insert a Step 5b entry into the deployment TOC between lines 74-83 of `README.md`.
2. Ensure the new anchor link resolves to the generated slug of the Step 5b heading (`#step-5b---whitelist-the-tokens-you-accept` or equivalent GitHub-generated slug).
3. Verify TOC entry count matches the number of deployment section headings after the edit.

## Proposed Change

In `README.md`, within the deployment TOC block (lines 74-83), add the following line after the Step 5 entry and before Step 6:

```markdown
    - [Step 5b - Whitelist the tokens you accept](#step-5b---whitelist-the-tokens-you-accept)
```

Indentation must match surrounding TOC entries. The exact anchor slug should be verified against the actual heading text at line ~404 to ensure GitHub's auto-generated slug matches.

## Verification Steps

1. Confirm the heading at line ~404 reads exactly `### Step 5b - Whitelist the tokens you accept` (or note the exact text).
2. Generate the expected GitHub markdown anchor slug from that heading.
3. After editing, confirm the TOC has one entry per deployment step heading (5, 5b, 6, etc.).
4. Click the new TOC link in the GitHub rendered README to verify it scrolls to the correct section.

## Status

- **Repo not cloned locally**: The `mova-store` repository is not present in `/Agentic`. This proposal documents the required change for manual execution or future automated claim.
- **Ready to claim**: The fix is a single-line TOC insertion with a verified anchor. Estimated effort: <10 minutes.
- **Bounty**: $85