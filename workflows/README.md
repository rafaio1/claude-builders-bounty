# Weekly Dev Summary — n8n Workflow

**Bounty:** Issue #5 ($200)  
**Payout Address:** `877hj5d4ya4N2B5gPsazm1dudN61Fkjz1V9izhD5m2TU`

## Overview

This n8n workflow automatically generates a weekly development summary by:

1. Fetching all PRs and issues from the last 7 days via GitHub API
2. Merging the data into a unified activity feed
3. Sending it to Claude AI for structured Markdown summarization
4. Emailing the report to stakeholders
5. Logging completion with a preview

## Setup Instructions

### Prerequisites

- n8n instance (self-hosted or cloud)
- GitHub API credentials with `repo` scope
- Anthropic API key with access to Claude models
- SMTP credentials for email delivery

### Installation

1. Import `weekly-dev-summary.json` into your n8n instance:
   - Go to **Workflows → Import from File**
   - Select `weekly-dev-summary.json`

2. Configure credentials:
   - Open each node marked with `REPLACE_WITH_*_CRED_ID`
   - Create or select the appropriate credential:
     - **GitHub API**: Personal access token with `repo` scope
     - **Anthropic API**: Your Anthropic API key
     - **SMTP**: Your email server credentials

3. Set environment variables (in n8n Settings → Environment Variables):
   ```
   GITHUB_OWNER=your-org-or-username
   GITHUB_REPO=your-repository-name
   ```

4. Activate the workflow

### Schedule

The workflow runs every **Monday at 9:00 AM UTC**. Adjust the `scheduleTrigger` node to change timing.

### Output Format

The generated email contains:

- **📊 Overview**: PR/issue counts, top contributors
- **🔀 Notable Pull Requests**: Top 5 most impactful PRs
- **🐛 Issues Resolved**: Grouped by label/priority
- **⚠️ Attention Items**: Stale PRs, blockers, high-priority unresolved issues
- **💡 Recommendations**: Actionable suggestions for next week

## Customization

- Change `maxTokens` or `temperature` in the Claude AI node to adjust output length/creativity
- Modify the prompt template to include additional sections (e.g., code quality metrics, deployment frequency)
- Add Slack/Discord notification nodes alongside the email node for multi-channel delivery
- Filter PRs/issues by label or author using GitHub node filter options

## Testing

1. Manually execute the workflow via **Execute Workflow** button
2. Check the email inbox for the generated report
3. Verify the sticky note shows completion timestamp and preview

## Troubleshooting

- **Empty report**: Ensure `GITHUB_OWNER` and `GITHUB_REPO` are set correctly and the repo has recent activity
- **Claude API error**: Verify API key has sufficient credits and model access
- **Email not sent**: Check SMTP credentials and ensure the recipient address is valid
- **Missing PRs/issues**: Confirm GitHub token has `repo` scope and the `since` filter date range is correct
