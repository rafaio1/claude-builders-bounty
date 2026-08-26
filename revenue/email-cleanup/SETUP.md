# GitHub Email Cleanup Setup

## Generated Files
- `github_filters.xml`: Import into Gmail Settings > Filters and Blocked Addresses > Import filters
- `github_cleanup.py`: Automated cleanup script (requires OAuth2 setup)

## Quick Fix (Manual)
1. Open Gmail → Settings → See all settings → Filters and Blocked Addresses
2. Click "Import filters" → Upload `github_filters.xml`
3. Review and confirm imports

## Automated Cleanup Setup
1. Go to https://console.cloud.google.com/apis/credentials
2. Create OAuth 2.0 Client ID (Desktop app)
3. Download JSON as `credentials.json` in this directory
4. Run: `python3 github_cleanup.py`
5. Authorize when prompted

## Cron Job (Optional)
Add to crontab for daily cleanup:
```
0 3 * * * cd /Agentic/revenue/email-cleanup && python3 github_cleanup.py >> /Agentic/logs/revenue/cron_cleanup.log 2>&1
```

## What Gets Cleaned
- Dependabot alerts older than 14 days
- PR/issue comments older than 3 days  
- Personal access token notifications older than 1 day
- General GitHub notifications older than 7 days (except important security alerts)

Generated: 2026-08-21T01:38:36.782865+00:00
