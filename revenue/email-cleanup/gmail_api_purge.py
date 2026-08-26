"""
Gmail API Direct Purge for GitHub Notifications
Adjusted queries for ClankerNation/OpenAgents flood + general cleanup.
Uses existing OAuth2 credentials in this directory.
"""
import os
import sys
import json
from datetime import datetime, timezone
from pathlib import Path

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    print("ERROR: Missing dependencies.")
    print("Run: pip install google-api-python-client google-auth-oauthlib")
    sys.exit(1)

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
CLEANUP_DIR = Path("/Agentic/revenue/email-cleanup")
LOG_DIR = Path("/Agentic/logs/revenue")
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Adjusted queries targeting the specific flood + general GitHub noise
PURGE_QUERIES = [
    # Specific flood mentioned by user
    "from:github.com subject:ClankerNation",
    "from:github.com subject:OpenAgents",
    "from:github.com subject:PR #5871",
    "from:github.com subject:feat(api): add WebSocket",
    # General GitHub notification cleanup
    "from:notifications@github.com subject:\"Re: [\" older_than:1d",
    "from:noreply@github.com older_than:7d -label:important -label:starred",
    "from:github.com subject:Dependabot older_than:14d",
]

def get_credentials():
    creds = None
    token_path = CLEANUP_DIR / "token.json"
    creds_path = CLEANUP_DIR / "credentials.json"
    
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Token refresh failed: {e}")
        
        if not creds or not creds.valid:
            if not creds_path.exists():
                print(f"ERROR: {creds_path} not found.")
                print("Download OAuth2 client credentials from Google Cloud Console")
                return None
            
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
            
            with open(token_path, 'w') as token:
                token.write(creds.to_json())
    
    return creds

def purge_github_emails(dry_run=False):
    creds = get_credentials()
    if not creds:
        return {"status": "error", "message": "Authentication failed - check credentials.json"}
    
    try:
        service = build('gmail', 'v1', credentials=creds)
        results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "dry_run": dry_run,
            "queries": [],
            "total_processed": 0,
            "status": "success"
        }
        
        for query in PURGE_QUERIES:
            try:
                response = service.users().messages().list(
                    userId='me', q=query, maxResults=500
                ).execute()
                
                messages = response.get('messages', [])
                count = len(messages)
                action_taken = "skipped_dry_run" if dry_run else "none"
                
                if messages and not dry_run:
                    msg_ids = [m['id'] for m in messages]
                    # Batch trash: remove from inbox, move to trash
                    service.users().messages().batchModify(
                        userId='me',
                        body={
                            'ids': msg_ids,
                            'removeLabelIds': ['INBOX'],
                            'addLabelIds': ['TRASH']
                        }
                    ).execute()
                    action_taken = f"trashed_{count}"
                
                results["queries"].append({
                    "query": query,
                    "found": count,
                    "action": action_taken
                })
                results["total_processed"] += count
                
            except HttpError as e:
                results["queries"].append({
                    "query": query,
                    "error": str(e),
                    "found": 0
                })
        
        log_file = LOG_DIR / f"api_purge_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(log_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        return results
        
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    mode = "DRY RUN" if dry else "LIVE DELETE"
    print(f"=== Gmail API Purge ({mode}) ===")
    print(f"Queries: {len(PURGE_QUERIES)}")
    print(f"Creds dir: {CLEANUP_DIR}")
    print("")
    
    result = purge_github_emails(dry_run=dry)
    print(json.dumps(result, indent=2))
    
    if result.get("status") == "success":
        print(f"\n✓ Processed {result['total_processed']} messages")
        if not dry:
            print("✓ Emails moved to Trash (recoverable for 30 days)")
    else:
        print(f"\n✗ Error: {result.get('message')}")
