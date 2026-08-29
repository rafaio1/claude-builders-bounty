#!/usr/bin/env python3
"""
Autonomous Bounty Claimer.
Runs every 2 hours to check for pending bounties and attempt claims.
Sends notifications to Telegram on success/failure.
"""
import sys, os, json, subprocess, time
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, "/Agentic/src")
from telegram_ops import send_message, _log

LEDGER_PATH = Path("/Agentic/data/aro/bounty_ledger.json")
REVENUE_DIR = Path("/Agentic/revenue")
LOG_FILE = Path("/Agentic/logs/bounty_claimer.log")

def log(msg: str):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] BOUNTY: {msg}"
    print(line, flush=True)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except: pass

def load_ledger():
    if LEDGER_PATH.exists():
        try: return json.loads(LEDGER_PATH.read_text())
        except: pass
    return {"bounties": [], "claims": []}

def find_pending_opportunities():
    """Scan revenue directories for unclaimed opportunities."""
    pending = []
    if not REVENUE_DIR.exists():
        return pending
    
    for subdir in REVENUE_DIR.iterdir():
        if not subdir.is_dir(): continue
        for f in subdir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                status = data.get("status", "").lower()
                if status in ("pending", "available", "open", "unclaimed"):
                    pending.append({
                        "file": str(f),
                        "title": data.get("title", f.name),
                        "value": data.get("value", data.get("reward", "?")),
                        "platform": subdir.name
                    })
            except: pass
    return pending

def run_claim_cycle():
    log("=== Starting Bounty Claim Cycle ===")
    send_message("🔄 <b>Bounty Claimer:</b> Iniciando ciclo automático de verificação...")
    
    ledger = load_ledger()
    pending = find_pending_opportunities()
    
    if not pending:
        msg = "✅ Nenhum bounty pendente encontrado neste ciclo."
        log(msg)
        send_message(f"🔍 {msg}")
        return
    
    found_msg = f"🎯 <b>{len(pending)}</b> oportunidades pendentes encontradas:\n"
    for i, p in enumerate(pending[:5], 1):
        found_msg += f"\n{i}. <b>{p['title']}</b>\n   💰 {p['value']} | 🏷️ {p['platform']}"
    
    send_message(found_msg)
    log(f"Found {len(pending)} pending opportunities")
    
    # Attempt qualification/claim via existing ARO tooling if available
    qualifier = Path("/Agentic/deploy/systemd/agentic-algora-bounty-qualifier.service")
    cli_tool = Path("/Agentic/.venv/bin/python")
    
    claimed_count = 0
    for opp in pending[:3]:  # Limit to 3 per cycle to avoid rate limits
        log(f"Attempting claim for: {opp['title']}")
        try:
            # Try using agentic CLI if available
            if cli_tool.exists():
                result = subprocess.run(
                    [str(cli_tool), "-m", "agentic", "bounty", "qualify", "--file", opp["file"]],
                    capture_output=True, text=True, timeout=120, cwd="/Agentic"
                )
                if result.returncode == 0:
                    claimed_count += 1
                    send_message(f"✅ <b>Claim iniciado:</b> {opp['title']}")
                    log(f"Claim initiated successfully for {opp['title']}")
                else:
                    log(f"Qualify returned {result.returncode}: {result.stderr[:200]}")
            else:
                log("No agentic CLI found, skipping automated claim")
                break
        except subprocess.TimeoutExpired:
            log(f"Timeout claiming {opp['title']}")
        except Exception as e:
            log(f"Error claiming {opp['title']}: {e}")
    
    summary = f"📊 <b>Ciclo concluído:</b>\n• Verificados: {len(pending)}\n• Claims iniciados: {claimed_count}"
    send_message(summary)
    log(f"Cycle complete: {claimed_count}/{len(pending)} claims initiated")

if __name__ == "__main__":
    run_claim_cycle()
