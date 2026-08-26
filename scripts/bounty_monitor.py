#!/usr/bin/env python3
"""
Bounty Monitor - Checa bounties pagos e notifica via Telegram
Rodar periodicamente via cron ou systemd timer
"""
import json, os, sys, subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path("/Agentic")
LEDGER_PATH = REPO_ROOT / "logs/bounty/ledger.json"
ENV_PATH = REPO_ROOT / ".env"

def load_env():
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env

def send_telegram(token, chat_id, text, parse_mode="Markdown"):
    import urllib.request, urllib.parse
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }).encode()
    req = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"Telegram error: {e}", file=sys.stderr)
        return None

def check_pr_status(repo, pr_number):
    """Check if PR is merged via gh cli"""
    try:
        result = subprocess.run(
            ["gh", "pr", "view", str(pr_number), "--repo", repo, "--json", "state,mergedAt,url"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception as e:
        print(f"GH error for {repo}#{pr_number}: {e}", file=sys.stderr)
    return None

def main():
    env = load_env()
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    
    if not token or not chat_id:
        print("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in .env")
        sys.exit(1)
    
    if not LEDGER_PATH.exists():
        print("Ledger not found")
        sys.exit(1)
    
    data = json.loads(LEDGER_PATH.read_text())
    entries = data.get("discovered", [])
    
    notifications = []
    updated = False
    
    for entry in entries:
        if entry.get("status") != "pr_submitted":
            continue
        
        pr_url = entry.get("pr_url", "")
        if not pr_url or "/pull/" not in pr_url:
            continue
        
        repo = entry.get("repo", "")
        pr_num = pr_url.rstrip("/").split("/")[-1]
        
        pr_info = check_pr_status(repo, pr_num)
        if not pr_info:
            continue
        
        state = pr_info.get("state", "").upper()
        merged_at = pr_info.get("mergedAt")
        
        if state == "MERGED" and merged_at:
            bounty = entry.get("estimated_bounty_usd", 0)
            title = entry.get("title", "Unknown")
            issue = entry.get("issue", "?")
            
            entry["status"] = "merged"
            entry["merged_at"] = merged_at
            updated = True
            
            msg = (
                f"🎉 *BOUNTY PAGO/MERGED!*\n\n"
                f"📦 `{repo}`\n"
                f"🔗 Issue #{issue} — PR #{pr_num}\n"
                f"📝 {title}\n"
                f"💰 *${bounty} USD*\n\n"
                f"✅ Merged em: {merged_at[:10]}\n"
                f"🔍 {pr_url}"
            )
            notifications.append(msg)
            print(f"MERGED: {repo}#{pr_num} - ${bounty}")
        
        elif state == "CLOSED" and not merged_at:
            entry["status"] = "closed_rejected"
            entry["closed_at"] = datetime.now(timezone.utc).isoformat()
            updated = True
            
            msg = (
                f"❌ *PR REJEITADO*\n\n"
                f"📦 `{repo}`\n"
                f"🔗 Issue #{entry.get('issue', '?')} — PR #{pr_num}\n"
                f"📝 {entry.get('title', 'Unknown')}\n\n"
                f"⚠️ Ação necessária: revisar feedback ou reabrir."
            )
            notifications.append(msg)
            print(f"CLOSED: {repo}#{pr_num}")
    
    if updated:
        data["discovered"] = entries
        LEDGER_PATH.write_text(json.dumps(data, indent=2))
        print("Ledger updated")
    
    # Send notifications
    for msg in notifications:
        send_telegram(token, chat_id, msg)
    
    if not notifications:
        print(f"No status changes. {sum(1 for e in entries if e.get('status')=='pr_submitted')} PRs still pending.")
    else:
        total_merged = sum(e.get("estimated_bounty_usd", 0) for e in entries if e.get("status") == "merged")
        summary = f"📊 *Resumo da Verificação*\n\n🔄 {len(notifications)} mudanças detectadas\n💵 Total merged acumulado: *${total_merged} USD*"
        send_telegram(token, chat_id, summary)

if __name__ == "__main__":
    main()
