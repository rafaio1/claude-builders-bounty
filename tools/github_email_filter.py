#!/usr/bin/env python3
"""
GitHub Email Filter & Auto-Archive Agent
Fixed: Use batchModify to add TRASH label instead of batchDelete (avoids scope issues with some token states)
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

try:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request
except ImportError:
    print("ERROR: google-auth/google-api-python-client not installed.")
    sys.exit(1)

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
TOKEN_PATH = '/Agentic/.config/gmail_oauth_token.json'
PENDING_PATH = '/Agentic/data/aro/inbox/pending.jsonl'

GITHUB_NOISE_PATTERNS = [
    r'digest', r'weekly update', r'monthly summary',
    r'newsletter', r'trending', r'stars you missed',
    r'new follower', r'someone liked', r'repository invitation',
    r'unsubscribe', r'notifications you can unsubscribe',
]

GITHUB_PERTINENT_PATTERNS = [
    r'security alert', r'vulnerability', r'cve-',
    r'billing|invoice|payment|receipt',
    r'pull request.*merged|pr.*merged',
    r'issue.*assigned|mention',
    r'action required|verify|confirm',
    r'bounty|contract|proposal',
]

def classify_github_email(subject: str, snippet: str) -> dict:
    text = f"{subject} {snippet}".lower()
    for pattern in GITHUB_NOISE_PATTERNS:
        if re.search(pattern, text):
            # SAFETY: Never auto-trash during discovery/triage. Noise is enqueued
            # as candidate_trash_post_action so a human or post-action step can
            # confirm deletion after ledger evidence exists. This prevents loss
            # of CLA, payout, KYC, contract, security or ambiguous messages.
            return {'category': 'noise', 'action': 'candidate_trash_post_action', 'reason': f'github_noise:{pattern}'}
    for pattern in GITHUB_PERTINENT_PATTERNS:
        if re.search(pattern, text):
            return {'category': 'pertinent', 'action': 'keep_and_route', 'reason': f'github_signal:{pattern}'}
    return {'category': 'unknown', 'action': 'keep_for_review', 'reason': 'unclassified_github'}

def process_github_emails():
    if not os.path.exists(TOKEN_PATH):
        print(f"BLOCKED: OAuth2 token not found at {TOKEN_PATH}")
        return False
    
    with open(TOKEN_PATH, 'r') as f:
        token_data = json.load(f)
    
    creds = Credentials(
        token=token_data.get('token'),
        refresh_token=token_data.get('refresh_token'),
        token_uri=token_data.get('token_uri', 'https://oauth2.googleapis.com/token'),
        client_id=token_data.get('client_id'),
        client_secret=token_data.get('client_secret'),
        scopes=SCOPES
    )
    
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_data['token'] = creds.token
        with open(TOKEN_PATH, 'w') as f:
            json.dump(token_data, f, indent=2)
    
    service = build('gmail', 'v1', credentials=creds)
    
    results = service.users().messages().list(
        userId='me', q='from:github.com newer_than:7d', maxResults=50
    ).execute()
    
    messages = results.get('messages', [])
    if not messages:
        print("No GitHub emails found in last 7 days.")
        return True
    
    trash_ids = []
    pertinent_count = 0
    
    for msg_meta in messages:
        msg = service.users().messages().get(userId='me', id=msg_meta['id'], format='metadata').execute()
        headers = {h['name']: h['value'] for h in msg.get('payload', {}).get('headers', [])}
        subject = headers.get('Subject', '')
        snippet = msg.get('snippet', '')
        
        classification = classify_github_email(subject, snippet)
        
        if classification['action'] == 'candidate_trash_post_action':
            # Enqueue for post-action review; do NOT add to trash_ids here.
            # Individual trash only after action completed and ledger recorded.
            entry = {
                'source': 'gmail_github',
                'message_id': msg_meta['id'],
                'subject': subject,
                'classification': classification,
                'status': 'pending_review',
                'discovered_at': datetime.now(timezone.utc).isoformat(),
            }
            with open(PENDING_PATH, 'a') as pf:
                pf.write(json.dumps(entry) + '\n')
        elif classification['action'] == 'keep_and_route':
            pertinent_count += 1
            entry = {
                'source': 'gmail_github',
                'message_id': msg_meta['id'],
                'subject': subject,
                'classification': classification,
                'parsed_at': datetime.now(timezone.utc).isoformat()
            }
            os.makedirs(os.path.dirname(PENDING_PATH), exist_ok=True)
            with open(PENDING_PATH, 'a') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    
    # SAFETY: Never auto-trash during discovery/triage.
    # Noise classification is logged but messages stay in INBOX.
    # Individual trash only after action completed and ledger recorded.
    if trash_ids:
        for mid in trash_ids:
            entry = {
                'source': 'gmail_github',
                'message_id': mid,
                'subject': '',
                'classification': {'category': 'noise', 'action': 'candidate_trash_post_action', 'reason': 'github_noise_deferred'},
                'parsed_at': datetime.now(timezone.utc).isoformat(),
                'note': 'Deferred trash: requires explicit post-action confirmation'
            }
            os.makedirs(os.path.dirname(PENDING_PATH), exist_ok=True)
            with open(PENDING_PATH, 'a') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        print(f"DEFERRED TRASH {len(trash_ids)} GitHub noise emails → enqueued for post-action review (NOT deleted).")
    
    print(f"KEPT {pertinent_count} pertinent GitHub emails → routed to {PENDING_PATH}")
    print(f"REVIEW {len(messages) - len(trash_ids) - pertinent_count} unclassified GitHub emails.")
    return True

if __name__ == '__main__':
    success = process_github_emails()
    sys.exit(0 if success else 1)
