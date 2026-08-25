# n8n + Claude Code — Automated Weekly Dev Summary

> 🏆 Submission for [Bounty #5](https://github.com/claude-builders-bounty/claude-builders-bounty/issues/5) ($200)

A complete, importable n8n workflow that automatically generates a narrative weekly development summary using the Claude API.

## Features

- ✅ **Weekly Cron Trigger**: Runs every Friday at 5pm (configurable)
- ✅ **GitHub Activity Fetching**: Commits, closed issues, and merged PRs from the last 7 days
- ✅ **Claude Sonnet Integration**: Generates insightful narrative summaries via `claude-sonnet-4-20250514`
- ✅ **Dual Output**: Email delivery + local file archive
- ✅ **Zero Code Nodes**: Pure n8n native nodes, no custom JavaScript required
- ✅ **Credential Placeholders**: Clear setup instructions for GitHub & Anthropic API keys

## Quick Start (3 Steps)

### 1. Import the Workflow
Open n8n → Workflows → Import from File → Select `workflows/weekly_dev_summary.json`

### 2. Configure Credentials
Set up two credentials in n8n:
- **GitHub API**: Personal access token with `repo` scope
- **Anthropic API**: Your Anthropic API key

Then update the credential references in the workflow nodes:
- `Fetch Commits`, `Fetch Closed Issues`, `Fetch Merged PRs` → select your GitHub credential
- `Claude API — Generate Summary` → select your Anthropic credential

### 3. Set Repository & Email
Edit the first node ("Weekly Cron") or add a Set node to define:
- `owner`: GitHub repository owner/org
- `repo`: Repository name
- `WEEKLY_SUMMARY_EMAIL`: Recipient email address

Activate the workflow and it will run automatically every Friday at 5pm.

## Workflow Architecture

```
┌─────────────────┐
│  Weekly Cron     │  Friday 5pm UTC
│  (Schedule)      │
└────────┬────────┘
         │
    ┌────┼────────────────┐
    ▼    ▼                ▼
┌──────┐ ┌──────────┐ ┌──────────┐
│Commits│ │Issues    │ │PRs       │
│(GH)  │ │Closed(GH)│ │Merged(GH)│
└──┬───┘ └────┬─────┘ └────┬─────┘
   │          │             │
   └──────────┼─────────────┘
              ▼
      ┌──────────────┐
      │ Merge Data   │
      └──────┬───────┘
             ▼
      ┌──────────────┐
      │ Claude API   │  claude-sonnet-4-20250514
      │ Summarize    │
      └──────┬───────┘
        ┌────┴────┐
        ▼         ▼
   ┌────────┐ ┌────────┐
   │ Email  │ │ Save   │
   │ Send   │ │ File   │
   └────────┘ └────────┘
```

## Sample Output

### 📊 Weekly Dev Summary — 8/25/2026

**Highlights:**
- Implemented gas sponsorship relay with EIP-712 meta-transactions (#183)
- Added batch agent registration reducing gas costs by ~40% (#182)
- Fixed critical governance quorum bypass vulnerability (#180)

**Commits:** 47 commits by 12 contributors
- Notable: SafeERC20 integration across all payout paths

**Issues Resolved:** 8 closed
- Key fixes: Timelock delay validation, lottery refund mechanism, vault fee rounding

**PRs Merged:** 6 merged
- Major changes: Dynamic ABI encoding support, structured API error responses

**Trends & Observations:**
Velocity increased 35% WoW. Focus shifted from core contracts to SDK tooling and API hardening. No open security-critical issues remain.

## Acceptance Criteria Checklist

- [x] Exportable n8n workflow (importable `.json` file)
- [x] Trigger: weekly cron (Friday at 5pm)
- [x] Fetches from GitHub API: commits, closed issues, merged PRs for the week
- [x] Calls Claude API (`claude-sonnet-4-20250514`) to generate a narrative summary
- [x] Sends summary via email
- [x] Saves summary to file as backup/archive
- [x] README with setup instructions in 3 steps or fewer
- [x] Tested structure validated against n8n schema

## Configuration Reference

| Variable | Description | Default |
|----------|-------------|---------|
| `owner` | GitHub repo owner/org | *(required)* |
| `repo` | Repository name | *(required)* |
| `WEEKLY_SUMMARY_EMAIL` | Email recipient | `team@example.com` |
| Cron schedule | Execution frequency | Friday 17:00 UTC |
| Claude model | LLM for summarization | `claude-sonnet-4-20250514` |
| Max tokens | Summary length limit | 1024 |
| Temperature | Creativity level | 0.3 |

## License

MIT

---

*Built for the Claude Builders Bounty community · August 2026*
