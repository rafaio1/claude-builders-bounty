#!/usr/bin/env python3
"""
Revenue Orchestrator v2.0 - Closes the Loop to Payment
Coordinates: Product Sales (Gumroad/B2B) + Bounty Hunting + Payout Verification
Focus: FAST revenue with verified payment paths only.
"""
import json, os, sys, time, subprocess
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path("/Agentic")
LOG = ROOT / "logs" / "revenue_orchestrator_v2.log"

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[REV-ORCH-v2] [{ts}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def check_gumroad_status():
    """Check if Gumroad credentials exist or if manual listing is needed."""
    env_files = [Path("/root/.automaton/.env"), ROOT / ".env"]
    has_gumroad = False
    for ef in env_files:
        if ef.exists():
            content = ef.read_text()
            if "GUMROAD" in content.upper():
                has_gumroad = True
                break
    
    listing_script = ROOT / "scripts" / "gumroad_listing_cmds.sh"
    packages = ROOT / "revenue" / "packages"
    
    status = {
        "has_credentials": has_gumroad,
        "listing_automation_ready": listing_script.exists(),
        "products_packaged": (packages / "fda_import_refusal_cleaner.py").exists() and 
                             (packages / "universal_bot_framework.py").exists(),
        "action_required": "manual_login_and_upload" if not has_gumroad else "api_listing_possible",
        "estimated_time_to_first_sale": "24-72h after listing live"
    }
    return status

def check_bounty_pipeline():
    """Audit bounty ledger for REAL payment opportunities only."""
    ledger_path = ROOT / "data" / "aro" / "bounty_ledger.json"
    if not ledger_path.exists():
        return {"status": "no_ledger", "actionable": 0}
    
    try:
        data = json.loads(ledger_path.read_text())
        reconciled = data.get("reconciled_bounties", [])
        
        # Filter for ONLY bounties with verified payment mechanism
        actionable = []
        stale_count = 0
        rejected_count = 0
        
        for b in reconciled:
            status = b.get("status", "")
            value = b.get("value", 0)
            repo = b.get("repo", "")
            
            if status == "rejected_by_bot" or b.get("audit_classification") == "closed_rejected_by_bot":
                rejected_count += 1
                continue
            
            if b.get("repo_activity_status") == "stale_inactive":
                stale_count += 1
                continue
                
            if status == "pr_submitted" and value > 0:
                # Only count if maintainer is responsive OR program honors payments
                if b.get("maintainer_responsive") or b.get("program_honors_payments"):
                    actionable.append({
                        "repo": repo,
                        "pr": b.get("pr"),
                        "value": value,
                        "currency": b.get("currency", "USD"),
                        "stage": b.get("lifecycle_stage", "unknown")
                    })
        
        return {
            "total_tracked": len(reconciled),
            "actionable_prs": len(actionable),
            "stale_repos": stale_count,
            "rejected": rejected_count,
            "potential_value_usd": sum(a["value"] for a in actionable),
            "items": actionable[:5]  # Top 5
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}

def check_b2b_outreach():
    """Verify B2B email batch is ready for deployment."""
    batch_path = ROOT / "revenue" / "outreach" / "fda_email_batch.json"
    if not batch_path.exists():
        return {"status": "not_generated"}
    
    try:
        batch = json.loads(batch_path.read_text())
        return {
            "status": "ready",
            "count": len(batch),
            "verticals_covered": list(set(b["vertical"] for b in batch)),
            "deployment_method": "manual_smtp_or_outreach_tool_needed",
            "note": "No email API keys configured - requires human sender or SMTP setup"
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}

def generate_fast_revenue_plan():
    """Create prioritized action plan for fastest path to cash."""
    gumroad = check_gumroad_status()
    bounties = check_bounty_pipeline()
    b2b = check_b2b_outreach()
    
    plan = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "objective": "Generate revenue with verified payment closure",
        "priority_lanes": [],
        "blockers": [],
        "immediate_actions": []
    }
    
    # Lane 1: Gumroad (Fastest if we can list)
    if gumroad["products_packaged"] and gumroad["listing_automation_ready"]:
        lane1 = {
            "lane": "Digital Product Sales (Gumroad)",
            "potential": "$497 + $297 per sale",
            "time_to_revenue": "24-72h after listing",
            "status": "READY_TO_LIST",
            "next_step": "Execute gumroad_listing_cmds.sh via Playwright OR manual upload",
            "payment_verified": True,
            "priority": 1
        }
        if not gumroad["has_credentials"]:
            lane1["blocker"] = "No API key - requires browser login/session"
            plan["blockers"].append("Gumroad: Need manual login or session cookie")
        plan["priority_lanes"].append(lane1)
        plan["immediate_actions"].append("Run: playwright-cli open https://gumroad.com/login -> authenticate -> execute listing script")
    
    # Lane 2: B2B Direct Sales (Higher ticket, slower close)
    if b2b.get("status") == "ready":
        lane2 = {
            "lane": "B2B FDA Dataset Direct Sales",
            "potential": "$497 x volume",
            "time_to_revenue": "3-14 days (sales cycle)",
            "status": "EMAILS_READY_NO_SENDER",
            "next_step": "Configure SMTP or use outreach tool (Lemlist/Instantly)",
            "payment_verified": True,
            "priority": 2
        }
        plan["priority_lanes"].append(lane2)
        plan["blockers"].append("B2B: No email sending infrastructure configured")
        plan["immediate_actions"].append("Set up SMTP creds in .env OR export batch to CSV for manual send")
    
    # Lane 3: Bounties (Only actionable ones)
    if bounties.get("actionable_prs", 0) > 0:
        lane3 = {
            "lane": "Open Source Bounties",
            "potential": f"${bounties['potential_value_usd']} pending",
            "time_to_revenue": "7-30 days (review + payout cycle)",
            "status": f"{bounties['actionable_prs']} PRs in review",
            "next_step": "Monitor PRs, respond to reviews, verify payout method",
            "payment_verified": "PARTIAL - depends on maintainer response",
            "priority": 3,
            "top_opportunities": bounties.get("items", [])
        }
        plan["priority_lanes"].append(lane3)
    else:
        plan["blockers"].append("Bounties: All tracked PRs are stale/rejected. New scouting needed.")
    
    # Critical blocker summary
    if not any(l.get("payment_verified") == True for l in plan["priority_lanes"]):
        plan["critical_alert"] = "NO VERIFIED PAYMENT PATH ACTIVE - All lanes require setup"
    
    return plan

if __name__ == "__main__":
    log("Revenue Orchestrator v2.0 starting audit")
    plan = generate_fast_revenue_plan()
    
    out_path = ROOT / "data" / "revenue" / "fast_revenue_plan.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(plan, indent=2))
    
    log(f"Plan generated: {len(plan['priority_lanes'])} lanes, {len(plan['blockers'])} blockers")
    log(f"Saved to {out_path}")
    
    # Print summary
    print("\n=== FAST REVENUE PLAN SUMMARY ===")
    for lane in plan["priority_lanes"]:
        print(f"[P{lane['priority']}] {lane['lane']}: {lane['status']} (${lane['potential']})")
    if plan["blockers"]:
        print("\n⚠️  BLOCKERS:")
        for b in plan["blockers"]:
            print(f"   - {b}")
    if plan.get("critical_alert"):
        print(f"\n🚨 {plan['critical_alert']}")
    print(f"\nFull plan: {out_path}")
