#!/usr/bin/env python3
"""Direct Gmail Revenue Monitor - Bypasses broken MCP plugin"""
import os, sys, json, time, re, base64, requests
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

ROOT = Path("/Agentic")
LOG = ROOT / "logs" / "gmail_monitor.log"
LEDGER = ROOT / "data" / "aro" / "bounty_ledger.json"

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def get_access_token():
    load_dotenv(ROOT / ".env")
    cid = os.getenv("GOOGLE_CLIENT_ID")
    csec = os.getenv("GOOGLE_CLIENT_SECRET")
    rtok = os.getenv("GOOGLE_REFRESH_TOKEN")
    if not all([cid, csec, rtok]):
        log("ERROR: Missing Google OAuth creds in .env")
        return None
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": cid, "client_secret": csec,
        "refresh_token": rtok, "grant_type": "refresh_token"
    }, timeout=15)
    if r.status_code != 200:
        log(f"Token refresh failed: {r.text[:200]}")
        return None
    return r.json()["access_token"]

def check_emails(token):
    headers = {"Authorization": f"Bearer {token}"}
    api = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
    
    # Search for payout/payment confirmations
    queries = [
        "payout OR payment sent OR transferred OR wise newer_than:1d",
        "algora payout OR bounty paid OR merge AND paid newer_than:1d",
        "subject:payout OR subject:payment OR subject:transferred newer_than:1d"
    ]
    
    found_payouts = []
    seen_ids = set()
    
    for q in queries:
        try:
            r = requests.get(api, headers=headers, params={"q": q, "maxResults": 20}, timeout=15)
            if r.status_code != 200:
                continue
            msgs = r.json().get("messages", [])
            for m in msgs:
                mid = m["id"]
                if mid in seen_ids:
                    continue
                seen_ids.add(mid)
                
                detail = requests.get(f"{api}/{mid}", headers=headers, 
                                     params={"format": "full"}, timeout=15)
                if detail.status_code != 200:
                    continue
                    
                data = detail.json()
                subj = next((h["value"] for h in data["payload"]["headers"] if h["name"]=="Subject"), "")
                sender = next((h["value"] for h in data["payload"]["headers"] if h["name"]=="From"), "")
                
                body = ""
                def extract_body(p):
                    if "parts" in p:
                        for part in p["parts"]:
                            b = extract_body(part)
                            if b: return b
                    if p.get("mimeType") == "text/plain" and "data" in p.get("body", {}):
                        return base64.urlsafe_b64decode(p["body"]["data"]).decode("utf-8")
                    return ""
                body = extract_body(data["payload"])
                
                full_text = (subj + " " + body).lower()
                
                # High-confidence payout signals
                is_confirmed = any(k in full_text for k in [
                    "payment sent", "payout completed", "transferred to wise",
                    "funds released", "bounty paid", "payment processed"
                ])
                
                if is_confirmed:
                    amounts = re.findall(r'\$[\d,]+(?:\.\d+)?', subj + " " + body)
                    amount = max([int(a.replace("$","").replace(",","")) for a in amounts]) if amounts else 0
                    
                    found_payouts.append({
                        "subject": subj,
                        "sender": sender,
                        "amount": amount,
                        "preview": body[:300],
                        "detected_at": datetime.now(timezone.utc).isoformat()
                    })
                    log(f"PAYOUT DETECTED: ${amount} | {subj[:80]} | From: {sender}")
                    
        except Exception as e:
            log(f"Query error ({q[:30]}...): {e}")
    
    return found_payouts
    """Search for payout/payment confirmation emails."""
def update_ledger(payouts):
    if not payouts:
        return
        
    try:
        ledger = json.loads(LEDGER.read_text())
    except:
        ledger = {"bounties": [], "total_value": 0}
    
    updated = 0
    for p in payouts:
        # Try to match payout to existing bounty entry
        matched = False
        for b in ledger.get("bounties", []):
            if b.get("status") == "submitted" and p["amount"] > 0:
                # Simple heuristic: if amount matches or title keywords overlap
                if b.get("value") == p["amount"] or any(
                    kw in b.get("title","").lower() for kw in p["subject"].lower().split()[:5]
                ):
                    b["status"] = "paid"
                    b["paid_at"] = p["detected_at"]
                    b["payout_email_subject"] = p["subject"]
                    matched = True
                    updated += 1
                    break
        
        if not matched and p["amount"] > 0:
            ledger["bounties"].append({
                "title": p["subject"],
                "value": p["amount"],
                "status": "paid",
                "paid_at": p["detected_at"],
                "source": "gmail_payout_detection"
            })
            updated += 1
    
    ledger["total_value"] = sum(b.get("value", 0) for b in ledger["bounties"])
    LEDGER.write_text(json.dumps(ledger, indent=2, default=str))
    log(f"Ledger updated: {updated} entries marked as paid")
    """Search for payout/payment confirmation emails."""
if __name__ == "__main__":
    log("=== Gmail Revenue Monitor Starting ===")
    token = get_access_token()
    if not token:
        sys.exit(1)
    
    payouts = check_emails(token)
    if payouts:
        update_ledger(payouts)
        log(f"Found {len(payouts)} confirmed payouts this cycle")
    else:
        log("No confirmed payouts detected this cycle")
    
    log("=== Cycle Complete ===")
def send_email(token, to_addr, subject, body_text):
    """Send email via Gmail API using existing OAuth token. Requires gmail.send or gmail.modify scope."""
    import base64
    from email.mime.text import MIMEText
    
    msg = MIMEText(body_text)
    msg['to'] = to_addr
    msg['from'] = 'me'
    msg['subject'] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')
    
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    api = 'https://gmail.googleapis.com/gmail/v1/users/me/messages/send'
    r = requests.post(api, headers=headers, json={'raw': raw}, timeout=20)
    if r.status_code in (200, 201):
        log(f"Email sent to {to_addr}: {subject}")
        return {'sent': True, 'message_id': r.json().get('id')}
    else:
        log(f"Send failed ({r.status_code}): {r.text[:200]}")
        return {'sent': False, 'error': r.text[:200]}

def create_draft(token, to_addr, subject, body_text):
    """Create draft via Gmail API. Non-destructive write test for gmail.modify scope."""
    import base64
    from email.mime.text import MIMEText
    
    msg = MIMEText(body_text)
    msg['to'] = to_addr
    msg['from'] = 'me'
    msg['subject'] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')
    
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    api = 'https://gmail.googleapis.com/gmail/v1/users/me/drafts'
    r = requests.post(api, headers=headers, json={'message': {'raw': raw}}, timeout=20)
    if r.status_code in (200, 201):
        draft_id = r.json().get('id')
        log(f"Draft created: {subject} (id={draft_id})")
        # Clean up test draft immediately
        try:
            requests.delete(f'{api}/{draft_id}', headers=headers, timeout=10)
            log(f"Test draft {draft_id} cleaned up")
        except Exception as e:
            log(f"Draft cleanup warning: {e}")
        return {'created': True, 'draft_id': draft_id}
    else:
        log(f"Draft creation failed ({r.status_code}): {r.text[:200]}")
        return {'created': False, 'error': r.text[:200]}

def verify_send_capability(token):
    """Verify send capability by creating and deleting a test draft. Returns dict with capability status."""
    result = create_draft(token, 'test@example.com', '[AUTOMATED] Capability Test', 'This is an automated capability verification draft. Safe to ignore.')
    result['capability_verified'] = result.get('created', False)
    return result
