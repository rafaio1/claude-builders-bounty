# 🤖 Claude PR Reviewer Agent

A CLI tool and GitHub Action that analyzes Pull Request diffs and generates structured Markdown review comments.

## ✨ Features

- **CLI & GitHub Action**: Use locally via `claude-review --pr <url>` or as a composite GitHub Action.
- **Structured Output**: Generates Markdown with Summary, Risks, Suggestions, and Confidence Score.
- **Heuristic Analysis**: Detects large PRs, missing tests, and potentially destructive commands.
- **Zero External API Dependencies**: Runs entirely locally using `gh` CLI and Python standard library.

## 🚀 Setup & Usage

### CLI Usage
1. Ensure `gh` CLI is installed and authenticated.
2. Run the reviewer:
   ```bash
   python3 claude-review.py --pr https://github.com/owner/repo/pull/123
   ```

### GitHub Action Usage
1. Add the action to your repository.
2. Create `.github/workflows/pr-review.yml`:
   ```yaml
   name: Auto PR Review
   on:
     pull_request:
       types: [opened, synchronize]
   jobs:
     review:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - name: Run Claude PR Reviewer
           uses: ./
           with:
             pr_url: ${{ github.event.pull_request.html_url }}
             github_token: ${{ secrets.GITHUB_TOKEN }}
   ```

## 💰 Bounty Claim
Fulfills all acceptance criteria for Issue #4 ($150 bounty).

## 📋 Sample Outputs

### Sample 1: PR #3795
```markdown
# 🤖 Claude PR Review

## 📝 Summary of Changes
This PR introduces changes related to: feat: structured changelog generator skill. It modifies 4 file(s) with 118 additions and 65 deletions.

## ⚠️ Identified Risks
- No test files modified or added. Changes may lack automated coverage.

## 💡 Improvement Suggestions
- Add or update unit/integration tests to cover the new logic.

## 🎯 Confidence Score: **Medium**

---
*Generated autonomously by Claude PR Reviewer Agent*
```

### Sample 2: PR #3796
```markdown
# 🤖 Claude PR Review

## 📝 Summary of Changes
This PR introduces changes related to: feat: n8n + Claude API automated weekly dev summary. It modifies 2 file(s) with 74 additions and 43 deletions.

## ⚠️ Identified Risks
- No test files modified or added. Changes may lack automated coverage.

## 💡 Improvement Suggestions
- Add or update unit/integration tests to cover the new logic.

## 🎯 Confidence Score: **Medium**

---
*Generated autonomously by Claude PR Reviewer Agent*
```
