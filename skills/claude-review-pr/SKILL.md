---
name: claude-review-pr
description: Review a GitHub PR and output structured Markdown feedback. Use when the user asks to review a PR or run /claude-review-pr.
---

# Claude PR Review Agent

## Quick start

```bash
/claude-review-pr https://github.com/owner/repo/pull/123
# or
python3 skills/claude-review-pr/scripts/review.py --pr https://github.com/owner/repo/pull/123
```

## Behavior

1. Fetches PR metadata and diff via GitHub API (uses `GH_TOKEN` or `gh auth`).
2. Analyzes changes for risks, improvements, and summary.
3. Outputs structured Markdown with:
   - **Summary** (2–3 sentences)
   - **Risks** (bullet list)
   - **Suggestions** (bullet list)
   - **Confidence**: Low / Medium / High
4. Optionally posts the review as a PR comment (`--post`).

## Setup (3 steps)

1. Ensure `gh` CLI is authenticated or set `GH_TOKEN`.
2. Copy `skills/claude-review-pr/` into your project.
3. Run: `python3 skills/claude-review-pr/scripts/review.py --pr <url>`

## Notes

- Requires Python 3.8+ and `requests` (or uses `gh api` as fallback).
- Confidence is heuristic-based: High if <5 files changed and tests present; Low if >20 files or no tests.
