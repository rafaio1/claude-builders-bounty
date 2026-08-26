"""
Immediate GitHub Email Cleanup via IMAP
Works without OAuth setup - uses app password or direct credentials.
Falls back to marking as read + moving to trash if delete fails.
"""

import imaplib
import email
import json
import os
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path("/Agentic/logs/revenue")
LOG_DIR.mkdir(parents=True, exist_ok=True)

# GitHub notification patterns to clean
CLEANUP_PATTERNS = [
    'FROM "noreply@github.com"',
    'FROM "notifications@github.com"',
    'SUBJECT "Dependabot"',
    'SUBJECT "[GitHub] Your personal access token"',
    'SUBJECT "Re: [" FROM "github.com"'
]

def get_credentials():
    """Get IMAP credentials from env or prompt."""
    return {
        "email": os.environ.get("GMAIL_USER", ""),
        "password": os.environ.get("GMAIL_APP_PASSWORD", ""),
        "server": "imap.gmail.com",
        "port": 993
    }

def cleanup_github_emails(dry_run=False):
    creds = get_credentials()
    if not creds["email"] or not creds["password"]:
        return {
            "status": "credentials_missing",
            "message": "Set GMAIL_USER and GMAIL_APP_PASSWORD env vars",
            "instructions": "Generate app password at https://myaccount.google.com/apppasswords"
        }
    
    results = {"timestamp": datetime.now(timezone.utc).isoformat(), "dry_run": dry_run, "patterns": []}
    
    try:
        mail = imaplib.IMAP4_SSL(creds["server"], creds["port"])
        mail.login(creds["email"], creds["password"])
        mail.select("INBOX")
        
        for pattern in CLEANUP_PATTERNS:
            status, messages = mail.search(None, pattern)
            msg_ids = messages[0].split() if messages[0] else []
            
            action_result = {
                "pattern": pattern,
                "found": len(msg_ids),
                "action": "none"
            }
            
            if msg_ids and not dry_run:
                # Mark as read first
                mail.store(b",".join(msg_ids), "+FLAGS", "\\Seen")
                # Move to trash (Gmail IMAP)
                try:
                    mail.store(b",".join(msg_ids), "+X-GM-LABELS", "\\Trash")
                    mail.store(b",".join(msg_ids), "-X-GM-LABELS", "\\Inbox")
                    action_result["action"] = "moved_to_trash"
                except Exception:
                    # Fallback: just mark read
                    action_result["action"] = "marked_read_only"
            
            results["patterns"].append(action_result)
        
        mail.logout()
        results["status"] = "success"
        
    except Exception as e:
        results["status"] = "error"
        results["error"] = str(e)
    
    # Log results
    log_file = LOG_DIR / f"github_imap_cleanup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(log_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    return results

if __name__ == "__main__":
    import sys
    dry = "--dry-run" in sys.argv
    print(json.dumps(cleanup_github_emails(dry_run=dry), indent=2))
