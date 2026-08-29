# Weekly Dev Summary (n8n + Claude)

Automated weekly narrative summary of GitHub repository activity using Claude API.

## Setup (5 Steps)

1. **Import Workflow**: In n8n, go to Workflows → Import from File → select `workflow.json`
2. **Configure Credentials**: Add Anthropic API credential named "Claude API" in n8n credentials
3. **Set Environment Variables**: In n8n Settings → Environment Variables, add:
   - `GITHUB_REPO`: owner/repo format (e.g., `facebook/react`)
   - `GITHUB_TOKEN`: GitHub PAT with repo read access
   - `DISCORD_WEBHOOK_URL`: Discord webhook URL for delivery
   - `SUMMARY_LANGUAGE`: `EN` or `FR` (optional, defaults to EN)
4. **Activate Workflow**: Toggle workflow active switch to ON
5. **Test Run**: Click "Execute Workflow" manually to verify end-to-end execution

## Features

- Weekly cron trigger (Friday 5pm UTC)
- Fetches commits, closed issues, and merged PRs via GitHub API
- Generates narrative summary using Claude Sonnet 4
- Delivers formatted summary to Discord webhook
- Configurable language (EN/FR) and target repository

## Screenshot

![Successful Execution](./execution_screenshot.png)

## Bounty

Closes claude-builders-bounty/claude-builders-bounty#5
