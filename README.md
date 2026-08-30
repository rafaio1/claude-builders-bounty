# Claude Code PR Review Agent

A CLI tool that uses Claude Code to analyze GitHub PR diffs and post structured Markdown review comments.

## Installation

1. Ensure `claude` CLI is installed and authenticated: https://docs.anthropic.com/en/docs/claude-cli
2. Ensure `gh` CLI is installed and authenticated: https://cli.github.com/
3. Clone this repository and make the script executable:

```bash
git clone <this-repo>
cd claude-builders-bounty
chmod +x src/review.sh
```

## Usage

```bash
./src/review.sh https://github.com/owner/repo/pull/123
```

The agent will:
1. Fetch the PR diff via `gh pr diff`
2. Send it to Claude with a structured review prompt
3. Output a Markdown review with Summary, Risks, Suggestions, and Confidence Score

## Output Format

```markdown
### Summary
(2-3 sentences describing what this PR does)

### Identified Risks
- (bullet list of potential issues, security concerns, or edge cases)

### Improvement Suggestions
- (bullet list of actionable improvements)

### Confidence Score
(Low | Medium | High)
```

## Sample Outputs

See `samples/` directory for example reviews generated from real PRs.

## Requirements

- Bash 4+
- `gh` CLI v2.x (authenticated)
- `claude` CLI (authenticated with API access)
- Internet connection

Closes #4

Payout: 877hj5d4ya4N2B5gPsazm1dudN61Fkjz1V9izhD5m2TU
