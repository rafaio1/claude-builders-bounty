#!/usr/bin/env python3
"""
GhostCLI Master Orchestrator v1.1 - Real Execution
Fixes: Subagents now receive actual repo data from gh CLI instead of being asked to browse.
Focus: Fast payout cycles with verified payment methods.
"""
import os, sys, json, time, subprocess, requests, re
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path("/Agentic")
LOG_FILE = ROOT / "logs" / "ghostcli_orchestrator.log"
ENV_FILE = Path("/root/.automaton/.env")

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[ORCH] [{ts}] {msg}"
    print(line, flush=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def load_env():
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env

def get_live_bounties():
    """Fetch real bounties from GitHub using gh CLI"""
    try:
        # Search for recent bounty issues with confirmed payment
        cmd = [
            "gh", "search", "issues", 
            "label:bounty", "state:open", 
            "--created=>2026-08-27",
            "--limit=10",
            "--json=repository,title,url,body,createdAt"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            issues = json.loads(result.stdout)
            # Filter for repos with payment confirmation in body
            valid = []
            for issue in issues:
                body = (issue.get("body") or "").lower()
                if any(kw in body for kw in ["usd", "usdc", "payment", "reward", "$"]):
                    valid.append({
                        "repo": issue["repository"]["nameWithOwner"],
                        "title": issue["title"],
                        "url": issue["url"],
                        "body_preview": (issue.get("body") or "")[:500]
                    })
            return valid[:5]  # Top 5 most promising
    except Exception as e:
        log(f"Bounty fetch error: {e}")
    return []

def spawn_subagent(task_name: str, prompt: str, context: dict = None):
    """Spawn a GhostCLI subagent with real context data."""
    env = load_env()
    api_key = env.get("GHOSTCLI_API_KEY")
    base_url = env.get("GHOSTCLI_BASE_URL", "https://ghostcli.dev/v1")
    
    if not api_key:
        log("ERROR: No GHOSTCLI_API_KEY found")
        return False
    
    # Inject real context into prompt
    full_prompt = prompt
    if context:
        full_prompt += f"\n\n## REAL DATA CONTEXT\n```json\n{json.dumps(context, indent=2)}\n```\nUse ONLY this data. Do not hallucinate."
        
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "claude-fable-5[1m]",
        "messages": [{"role": "user", "content": full_prompt}],
        "max_tokens": 4096,
        "temperature": 0.1
    }
    
    try:
        log(f"Spawning subagent for: {task_name} (context_size={len(json.dumps(context or {}))})")
        r = requests.post(f"{base_url}/chat/completions", json=payload, headers=headers, timeout=180)
        if r.status_code == 200:
            content = r.json()["choices"][0]["message"]["content"]
            log(f"Subagent [{task_name}] completed. Output length: {len(content)}")
            out_dir = ROOT / "data" / "orchestrator" / task_name
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"{int(time.time())}.md").write_text(content)
            return content
        else:
            log(f"Subagent [{task_name}] failed: {r.status_code} {r.text[:200]}")
            return None
    except Exception as e:
        log(f"Subagent [{task_name}] exception: {e}")
        return None

def run_cycle():
    """Execute one orchestration cycle with real data injection."""
    log("Starting orchestration cycle v1.1")
    
    # Task 1: Bounty Analysis with REAL GitHub data
    bounties = get_live_bounties()
    if bounties:
        bounty_prompt = """You are an expert bounty hunter. Analyze these REAL GitHub bounty issues.
For each bounty:
1. Assess feasibility (can it be done in <4h?)
2. Estimate fair price based on complexity
3. Draft a concise PR description that references the issue
4. Identify the exact files likely needing changes
Output JSON array: [{repo, issue_url, feasible, estimated_hours, suggested_price_usd, pr_title, file_targets}]
Be conservative - only mark feasible if you're >80% confident."""
        spawn_subagent("bounty_analysis", bounty_prompt, {"bounties": bounties})
    else:
        log("No live bounties found this cycle")
    
    # Task 2: Freelance Proposal Generation (no external data needed)
    freelance_prompt = """Generate 3 HIGH-CONVERSION Upwork proposals for AI automation gigs.
Target niches: Data pipeline cleanup, LLM API integration, Discord bot development.
Each proposal must:
- Open with specific pain point acknowledgment
- Mention 2 relevant technical skills
- Include realistic timeline (3-7 days)
- Price between $300-$800 USD
- End with clear CTA
Output as markdown with clear separators."""
    spawn_subagent("freelance_proposals", freelance_prompt)
    
    # Task 3: Data Product Opportunity Scan
    data_prompt = """Identify 3 undervalued public datasets suitable for B2B sale.
Criteria:
- Commercial license allowed
- Requires cleaning/enrichment (value-add opportunity)
- Target buyers: Hedge funds, e-commerce, real estate
For each: Source URL, Cleaning steps, Buyer persona, Suggested price tier ($500/$2k/$10k)
Focus on datasets updated weekly/monthly for recurring revenue."""
    spawn_subagent("data_product_scout", data_prompt)
    
    log("Cycle complete")

if __name__ == "__main__":
    log("GhostCLI Orchestrator v1.1 starting (Real Data Injection)")
    while True:
        try:
            run_cycle()
            time.sleep(4 * 3600)  # 4h cycles for faster iteration
        except KeyboardInterrupt:
            log("Shutting down")
            break
        except Exception as e:
            log(f"Fatal error: {e}")
            time.sleep(300)
