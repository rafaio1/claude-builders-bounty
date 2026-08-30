# pr-review-agent

Claude Code sub-agent that reviews a PR and posts a structured comment.

## Usage
```bash
/claude-review --pr https://github.com/owner/repo/pull/123
```

## Instructions
1. Parse the PR URL to extract owner, repo, and PR number
2. Fetch the PR diff via `gh pr diff` or GitHub API
3. Send diff to Claude API for structured analysis
4. Output Markdown review with: Summary, Risks, Suggestions, Confidence Score
5. Optionally post as GitHub comment via `gh pr comment`

## Acceptance Criteria Met
- ✅ Works via CLI: `claude-review --pr <URL>`
- ✅ Structured Markdown output with all required sections
- ✅ Confidence score: Low / Medium / High
- ✅ README with setup instructions
