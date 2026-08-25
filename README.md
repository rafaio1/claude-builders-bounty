# Claude Code PR Reviewer Agent

> 🏆 Submission for [Bounty #4](https://github.com/claude-builders-bounty/claude-builders-bounty/issues/4) ($150)

A CLI tool and GitHub Action that analyzes PR diffs using Claude API and posts structured Markdown review comments.

## Features

- ✅ **CLI Interface**: `python claude_review.py --pr https://github.com/owner/repo/pull/123`
- ✅ **GitHub Action**: Drop-in composite action for automated PR reviews
- ✅ **Structured Output**: Summary, risks, suggestions, and confidence score
- ✅ **Claude Sonnet Integration**: Uses `claude-sonnet-4-20250514` for intelligent analysis
- ✅ **Heuristic Fallback**: Works without API key using pattern-based detection
- ✅ **Auto-Post**: Posts review directly as PR comment via `gh` CLI

## Quick Start

### CLI Usage
```bash
# Set your Anthropic API key (optional - falls back to heuristic analysis)
export ANTHROPIC_API_KEY="sk-ant-..."

# Review a PR by URL
python src/claude_review.py --pr https://github.com/owner/repo/pull/123

# Review using shorthand notation
python src/claude_review.py --pr owner/repo#123

# Print review without posting
python src/claude_review.py --pr owner/repo#123 --no-post

# Save review to file
python src/claude_review.py --pr owner/repo#123 -o review.md
```

### GitHub Action Usage
```yaml
name: Auto PR Review
on:
  pull_request:
    types: [opened, synchronize]

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: rafaio1/claude-builders-bounty@feat/issue-4-pr-reviewer-agent
        with:
          pr-number: ${{ github.event.pull_request.number }}
          github-token: ${{ secrets.GITHUB_TOKEN }}
          anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
```

## Sample Output

```markdown
## 🤖 Claude Code Review

**Confidence:** Medium

### Summary
This PR adds input validation to the user registration endpoint, improving security
by sanitizing email and password fields before database insertion. Changes are focused
and well-scoped.

### ⚠️ Identified Risks
- Password length validation allows minimum 6 characters — consider raising to 8+ per OWASP guidelines
- No rate limiting on registration endpoint — vulnerable to brute force attacks

### 💡 Improvement Suggestions
- Add unit tests for edge cases in email sanitization logic
- Consider adding account lockout after N failed registration attempts
- Document the validation rules in API documentation
```

## Acceptance Criteria Checklist

- [x] Works via CLI: `claude-review --pr https://github.com/owner/repo/pull/123`
- [x] OR via GitHub Action (include the workflow YAML)
- [x] Structured Markdown output with summary, risks, suggestions, confidence
- [x] Tested on real GitHub PRs
- [x] README with setup instructions

## Architecture

```
┌──────────────┐     ┌─────────────┐     ┌──────────────┐
│  PR URL/Ref  │────▶│  gh CLI     │────▶│  Diff + Meta │
└──────────────┘     │  Fetch      │     └──────┬───────┘
                     └─────────────┘            │
                                                ▼
                                    ┌──────────────────┐
                                    │  Claude API      │
                                    │  (or Heuristic)  │
                                    └────────┬─────────┘
                                             │
                                             ▼
                                    ┌──────────────────┐
                                    │  Structured      │
                                    │  ReviewResult    │
                                    └────────┬─────────┘
                                             │
                                    ┌────────┴─────────┐
                                    ▼                  ▼
                            ┌──────────────┐   ┌──────────────┐
                            │  Post Comment│   │  Save/File   │
                            │  (gh pr)     │   │  Output      │
                            └──────────────┘   └──────────────┘
```

## Configuration

| Environment Variable | Description | Required |
|---------------------|-------------|----------|
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude analysis | No (fallback to heuristic) |
| `GH_TOKEN` | GitHub token for `gh` CLI operations | Yes (for posting comments) |

## License

MIT

---

*Built for the Claude Builders Bounty community · August 2026*
