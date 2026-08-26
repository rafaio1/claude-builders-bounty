#!/usr/bin/env python3
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
        f.write(json.dumps(results) + "\n")
    
    return results

if __name__ == "__main__":
    print(json.dumps(cleanup_github_emails(), indent=2))
