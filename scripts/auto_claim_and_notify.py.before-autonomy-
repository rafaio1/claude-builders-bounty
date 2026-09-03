#!/usr/bin/env python3
"""
Auto-Claim & Notification Loop
- Checks inbox for new bounties
- Verifies ledger status
- Executes /claim on eligible targets
- Sends Telegram digest
"""
import json, os, sys, time, subprocess, urllib.request
from datetime import datetime, timezone

sys.path.insert(0, '/Agentic/internal')
from env import apply
apply()

LEDGER = '/Agentic/data/aro/bounty_ledger.json'
INBOX = '/Agentic/data/aro/inbox/pending_bounties.jsonl'
TG_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TG_CHAT = os.environ.get('TELEGRAM_CHAT_ID', '')

def log(msg): print(f"[{datetime.now(timezone.utc).isoformat()}] {msg}")

def send_tg(text):
    if not TG_TOKEN or not TG_CHAT: return
    try:
        data = json.dumps({'chat_id': TG_CHAT, 'text': text, 'parse_mode': 'Markdown'}).encode()
        req = urllib.request.Request(f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage', 
                                     data=data, headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=10)
    except Exception as e: log(f"TG_ERROR: {e}")

def gh_claim(repo, num):
    try:
        # Check if already commented by us recently to avoid spam
        res = subprocess.run(['gh', 'issue', 'view', str(num), '--repo', repo, '--json', 'comments'], 
                             capture_output=True, text=True, timeout=15)
        if res.returncode == 0:
            comments = json.loads(res.stdout).get('comments', [])
            for c in comments[-3:]:
                if '/claim' in c.get('body', '').lower() and c.get('author', {}).get('login') == 'ghost-cli-agent':
                    return False, "Already claimed recently"
        
        # Post claim
        subprocess.run(['gh', 'issue', 'comment', str(num), '--repo', repo, '--body', '/claim'], 
                       check=True, timeout=15)
        return True, "Claim posted"
    except Exception as e: return False, str(e)

def main():
    log("Starting Auto-Claim Cycle")
    
    # Load Ledger
    with open(LEDGER) as f: ledger = json.load(f)
    claimed_keys = {f"{e['repo']}#{e.get('issue')}" for e in ledger['entries'] if e.get('status') in ['claimed', 'completed_pending_payout', 'submitted', 'in_review']}
    
    # Process Inbox
    new_claims = []
    if os.path.exists(INBOX):
        with open(INBOX) as f:
            for line in f:
                try:
                    item = json.loads(line)
                    url = item.get('url', '')
                    if '/issues/' not in url: continue
                    parts = url.split('/')
                    repo = f"{parts[3]}/{parts[4]}"
                    num = parts[-1]
                    key = f"{repo}#{num}"
                    
                    if key not in claimed_keys:
                        success, msg = gh_claim(repo, num)
                        if success:
                            new_claims.append(f"• `{key}` - {item.get('title','?')}")
                            # Add to ledger immediately to prevent re-claim in next cycle
                            ledger['entries'].append({
                                'repo': repo, 'issue': int(num), 'status': 'claimed',
                                'claimed_at': datetime.now(timezone.utc).isoformat(),
                                'note': f"Auto-claimed via script. {item.get('reason','')}"
                            })
                            log(f"CLAIMED: {key}")
                        else:
                            log(f"SKIP {key}: {msg}")
                        time.sleep(2) # Rate limit respect
                except Exception as e: log(f"PARSE_ERROR: {e}")
    
    # Save updated ledger
    if new_claims:
        with open(LEDGER, 'w') as f: json.dump(ledger, f, indent=2)
        send_tg(f"🎯 *Novos Claims Automáticos*\n\n" + "\n".join(new_claims))
        log(f"Notified {len(new_claims)} new claims")
    else:
        log("No new claims this cycle")

if __name__ == '__main__':
    main()
