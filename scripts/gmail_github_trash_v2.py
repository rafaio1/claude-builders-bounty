#!/usr/bin/env python3
"""Gmail GitHub->TRASH v2: classify then batchModify with intent/applied separation."""
import json, sys, os, hashlib, time, base64
from pathlib import Path
from datetime import datetime, timezone

STATE_DIR = Path("/Agentic/state")
LOG_DIR = Path("/Agentic/logs/supervisor")
RECEIPT_PATH = STATE_DIR / "gmail_github_trash_receipts.jsonl"
PROPOSALS_DIR = Path("/Agentic/data/aro/proposals")

RULE_VERSION = "gmail-inbox-v1"
GITHUB_DOMAINS = {"github.com", "notifications.github.com"}
PRESERVE_KEYWORDS = ["bounty", "claim", "payout", "security", "account", "wallet", "ledger", "settlement"]

def load_credentials():
    env_path = Path.home() / ".automaton" / ".env"
    creds = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                creds[k.strip()] = v.strip().strip('"').strip("'")
    return creds

def get_gmail_service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    # Use systemd LoadCredential path (matches agentic-gmail-inbox-ingestor.service)
    token_path = Path("/Agentic/.config/gmail_oauth_token.json")
    if not token_path.exists():
        raise RuntimeError(f"No Gmail token at {token_path}")
    with open(token_path) as f:
        token_data = json.load(f)
    credentials = Credentials(
        token=None,
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=token_data.get("client_id"),
        client_secret=token_data.get("client_secret"),
        scopes=token_data.get("scopes"),
    )
    return build("gmail", "v1", credentials=credentials)

def is_github_authenticated(msg):
    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
    sender = headers.get("from", "").lower()
    domain = None
    for d in GITHUB_DOMAINS:
        if d in sender:
            domain = d
            break
    if not domain:
        return False, None, "sender_not_github"
    dkim = headers.get("authentication-results", "").lower()
    dmarc_pass = "dmarc=pass" in dkim or "dkim=pass" in dkim
    if not dmarc_pass:
        return False, domain, "dkim_dmarc_fail"
    return True, domain, "ok"

def has_preserve_signal(msg):
    snippet = msg.get("snippet", "").lower()
    subject = ""
    for h in msg.get("payload", {}).get("headers", []):
        if h["name"].lower() == "subject":
            subject = h["value"].lower()
    text = snippet + " " + subject
    return any(kw in text for kw in PRESERVE_KEYWORDS)

def fingerprint(msg):
    raw = msg.get("id", "") + msg.get("snippet", "")
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

def write_receipt(msg_id, status, reason, rule_version, fp, extra=None):
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "msg_id": msg_id,
        "status": status,
        "reason": reason,
        "rule_version": rule_version,
        "content_fingerprint": fp,
    }
    if extra:
        entry.update(extra)
    with open(RECEIPT_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")

def already_applied(msg_id):
    if not RECEIPT_PATH.exists():
        return False
    for line in RECEIPT_PATH.read_text().splitlines():
        try:
            r = json.loads(line)
            if r.get("msg_id") == msg_id and r.get("status") == "applied":
                return True
        except Exception:
            continue
    return False

def process_message(service, msg_id):
    if already_applied(msg_id):
        return "skipped_already_applied"
    msg = service.users().messages().get(userId="me", id=msg_id, format="metadata").execute()
    fp = fingerprint(msg)
    is_gh, domain, auth_reason = is_github_authenticated(msg)
    if not is_gh:
        write_receipt(msg_id, "classified_untrusted_input", auth_reason, RULE_VERSION, fp, {"sender_domain": domain})
        return f"not_github:{auth_reason}"
    preserve = has_preserve_signal(msg)
    if preserve:
        write_receipt(msg_id, "classified_preserved", "financial_signal_detected", RULE_VERSION, fp, {"sender_domain": domain})
        return "preserved_financial_signal"
    write_receipt(msg_id, "intent", "pending_batch_modify", RULE_VERSION, fp, {"sender_domain": domain})
    try:
        service.users().messages().batchModify(
            userId="me",
            body={"ids": [msg_id], "removeLabelIds": ["INBOX", "UNREAD"], "addLabelIds": ["TRASH"]}
        ).execute()
        write_receipt(msg_id, "applied", "trashed_after_intent", RULE_VERSION, fp, {"sender_domain": domain})
        return "applied"
    except Exception as e:
        write_receipt(msg_id, "failed", str(e)[:200], RULE_VERSION, fp, {"sender_domain": domain})
        return f"failed:{e}"

def main():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    service = get_gmail_service()
    results = service.users().messages().list(userId="me", q="in:inbox from:github.com", maxResults=50).execute()
    messages = results.get("messages", [])
    stats = {"total": len(messages), "applied": 0, "preserved": 0, "skipped": 0, "failed": 0, "not_github": 0}
    for m in messages:
        outcome = process_message(service, m["id"])
        if outcome == "applied":
            stats["applied"] += 1
        elif "preserved" in outcome:
            stats["preserved"] += 1
        elif "already_applied" in outcome:
            stats["skipped"] += 1
        elif "not_github" in outcome:
            stats["not_github"] += 1
        elif "failed" in outcome:
            stats["failed"] += 1
        else:
            stats["skipped"] += 1
    print(json.dumps(stats))

if __name__ == "__main__":
    main()
