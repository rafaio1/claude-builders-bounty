"""
GitHub Email Cleanup Automation
Creates Gmail filter rules and cleanup script for unwanted GitHub notifications.
Since direct Gmail MCP is unavailable, this generates:
1. A Gmail filter XML that can be imported manually
2. A Python script using google-api-python-client for programmatic cleanup
3. Documentation for setting up automated filtering
"""

import json
from datetime import datetime, timezone
from pathlib import Path

def generate_gmail_filter_xml():
    """Generate Gmail filter XML for GitHub notification cleanup."""
    filters = [
        {
            "name": "GitHub Spam - Auto Archive",
            "criteria": {
                "from": "noreply@github.com",
                "subject": ["[GitHub] Your personal access token", "[GitHub] Security alert", "Dependabot"]
            },
            "actions": {
                "archive": True,
                "mark_as_read": True,
                "label": "GitHub/Spam"
            }
        },
        {
            "name": "GitHub Notifications - Low Priority",
            "criteria": {
                "from": "notifications@github.com",
                "subject": ["Re: [", "Issue comment", "Pull request review"]
            },
            "actions": {
                "skip_inbox": True,
                "label": "GitHub/LowPriority"
            }
        },
        {
            "name": "GitHub Security Alerts - Keep",
            "criteria": {
                "from": "noreply@github.com",
                "subject": ["Security vulnerability", "Critical security"]
            },
            "actions": {
                "star": True,
                "label": "GitHub/Important"
            }
        }
    ]
    
    xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:apps="http://schemas.google.com/apps/2006">']
    
    for f in filters:
        xml_lines.append('  <entry>')
        xml_lines.append(f'    <title>{f["name"]}</title>')
        xml_lines.append('    <apps:property name="hasTheWord" value="{}"/>'.format(
            ' OR '.join(f["criteria"].get("subject", [])) if f["criteria"].get("subject") else ''
        ))
        if f["criteria"].get("from"):
            xml_lines.append(f'    <apps:property name="from" value="{f["criteria"]["from"]}"/>')
        if f["actions"].get("archive"):
            xml_lines.append('    <apps:property name="shouldArchive" value="true"/>')
        if f["actions"].get("mark_as_read"):
            xml_lines.append('    <apps:property name="shouldMarkAsRead" value="true"/>')
        if f["actions"].get("skip_inbox"):
            xml_lines.append('    <apps:property name="shouldNeverSpam" value="true"/>')
        if f["actions"].get("label"):
            xml_lines.append(f'    <apps:property name="label" value="{f["actions"]["label"]}"/>')
        xml_lines.append('  </entry>')
    
    xml_lines.append('</feed>')
    return '\n'.join(xml_lines)

def generate_cleanup_script():
    """Generate Python script for programmatic Gmail cleanup."""
    return '''#!/usr/bin/env python3
"""
Programmatic GitHub Email Cleanup via Gmail API
Requires: pip install google-api-python-client google-auth-oauthlib
Setup: Create OAuth2 credentials at https://console.cloud.google.com/apis/credentials
"""

import os
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from datetime import datetime, timedelta

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
CLEANUP_QUERIES = [
    "from:noreply@github.com older_than:7d -label:GitHub/Important",
    "from:notifications@github.com subject:(comment OR review) older_than:3d",
    "subject:Dependabot older_than:14d",
    "subject:[GitHub] personal access token older_than:1d"
]

def authenticate():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds

def cleanup_github_emails():
    service = build('gmail', 'v1', credentials=authenticate())
    results = {"timestamp": datetime.utcnow().isoformat(), "queries": []}
    
    for query in CLEANUP_QUERIES:
        response = service.users().messages().list(userId='me', q=query, maxResults=500).execute()
        messages = response.get('messages', [])
        
        if messages:
            batch_delete = {'ids': [m['id'] for m in messages]}
            service.users().messages().batchDelete(userId='me', body=batch_delete).execute()
            
        results["queries"].append({
            "query": query,
            "deleted_count": len(messages),
            "executed_at": datetime.utcnow().isoformat()
        })
    
    # Save log
    log_path = "/Agentic/logs/revenue/github_cleanup_log.json"
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, 'a') as f:
        f.write(json.dumps(results) + "\\n")
    
    return results

if __name__ == "__main__":
    print(json.dumps(cleanup_github_emails(), indent=2))
'''

def main():
    output_dir = Path("/Agentic/revenue/email-cleanup")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate Gmail filter XML
    filter_xml = generate_gmail_filter_xml()
    filter_path = output_dir / "github_filters.xml"
    filter_path.write_text(filter_xml)
    
    # Generate cleanup script
    script_content = generate_cleanup_script()
    script_path = output_dir / "github_cleanup.py"
    script_path.write_text(script_content)
    script_path.chmod(0o755)
    
    # Generate setup guide
    guide = f"""# GitHub Email Cleanup Setup

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

Generated: {datetime.now(timezone.utc).isoformat()}
"""
    (output_dir / "SETUP.md").write_text(guide)
    
    result = {
        "status": "success",
        "files_created": [str(p) for p in output_dir.iterdir()],
        "filter_rules": 3,
        "cleanup_queries": 4,
        "setup_guide": str(output_dir / "SETUP.md")
    }
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
