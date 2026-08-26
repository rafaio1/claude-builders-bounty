#!/usr/bin/env python3
"""
Autonomous Bounty Orchestrator v2.5
Fixed: Direct requests call to GhostCLI API (bypassing broken wrapper) + Fallback triage
"""
import sys, os, json, subprocess, time, re, requests
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/Agentic/build/lib")
from agentic.env import parse_env_file

ROOT = Path("/Agentic")
LOG_FILE = ROOT / "logs" / "bounty_orchestrator.log"
LEDGER_FILE = ROOT / "data" / "aro" / "bounty_ledger.json"
WISE_STATE = ROOT / "data" / "aro" / "wise-state.json"
PENDING_BOUNTIES = ROOT / "data" / "aro" / "inbox" / "pending_bounties.jsonl"

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
PENDING_BOUNTIES.parent.mkdir(parents=True, exist_ok=True)

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def load_json(path):
    if path.exists():
        try: return json.loads(path.read_text())
        except: return {}
    return {}

def save_json(path, data):
    path.write_text(json.dumps(data, indent=2, default=str))

def extract_json(text):
    if not text: return None
    clean = re.sub(r'\x1b\[[0-9;]*m', '', text)
    try: return json.loads(clean)
    except: pass
    match = re.search(r'```(?:json)?\s*([\s\S]*?)```', clean)
    if match:
        try: return json.loads(match.group(1).strip())
        except: pass
    for s, e in [('[', ']'), ('{', '}')]:
        start, end = clean.find(s), clean.rfind(e)
        if start != -1 and end > start:
            try: return json.loads(clean[start:end+1])
            except: continue
    return None

def ghostcli_complete(prompt, api_key, base_url, model, max_tokens=1000):
    """Direct HTTP call to GhostCLI/OpenAI-compatible endpoint with Senior Pipeline routing."""
    # Try Senior Pipeline first for complex bounty generation tasks
    try:
        from senior_dev_pipeline import run_pipeline
        import tempfile
        if "files_to_change" in prompt and ("HIGH-VALUE" in prompt or "bounty" in prompt.lower()):
            log("Routing to Senior Dev Pipeline for complex bounty generation...")
            issue_match = re.search(r"ISSUE:\s*(.+?)\nURL:\s*(.+?)\nREPO:\s*(.+?)\n", prompt)
            if issue_match:
                title, url, repo = issue_match.groups()
                desc = ""
                if "ISSUE DESCRIPTION:" in prompt:
                    desc = prompt.split("ISSUE DESCRIPTION:")[1].split("REQUIREMENTS:")[0]
                with tempfile.TemporaryDirectory() as tmp_ws:
                    result = run_pipeline(Path(tmp_ws), f"{title}\n\n{desc}", repo.strip())
                    if result and result.get("status") == "success":
                        impl = result.get("implementation", {})
                        files = []
                        if isinstance(impl, dict) and "code" in impl:
                            files.append({"path": "src/fix.py", "action": "modify", "content": impl["code"]})
                        elif isinstance(impl, list):
                            files = impl
                        return json.dumps({
                            "files_to_change": files,
                            "branch_name": f"fix/senior-{int(time.time())}",
                            "commit_message": result.get("commit_msg", "fix: senior pipeline resolution"),
                            "pr_title": f"fix: {title[:70]}",
                            "pr_body": result.get("pr_body", "Resolved via Senior Dev Pipeline")
                        })
    except Exception as e:
        log(f"Senior Pipeline routing failed, falling back to direct GhostCLI: {e}")

    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.1
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        log(f"GhostCLI API error: {e}")
        return None

def get_config():
    env = parse_env_file(Path("/root/.automaton/.env"))
    env.update(parse_env_file(ROOT / ".env"))
    api_key = env.get("GHOSTCLI_API_KEY")
    base_url = env.get("GHOSTCLI_BASE_URL", "https://ghostcli.dev")
    raw_model = env.get("GHOSTCLI_MODEL", "claude-fable-5")
    model = re.sub(r'\x1b\[[0-9;]*m', '', raw_model).split('[')[0].strip()
    return api_key, base_url, model

def discover_bounties():
    log("=== DISCOVERY PHASE STARTED ===")
    found = []
    queries = [
        "label:bounty state:open sort:updated-desc",
        "label:price state:open sort:updated-desc",
        "devpool-directory is:issue state:open sort:updated-desc",
        "algora OR gitcoin OR bounty is:issue state:open sort:updated-desc",
        "is:issue label:reward state:open sort:created-desc"
    ]
    for q in queries:
        cmd = f'gh search issues {q} --limit 15 --json repository,title,url,labels,createdAt'
        try:
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            if res.returncode == 0 and res.stdout.strip() not in ("", "[]"):
                items = json.loads(res.stdout)
                for item in items:
                    repo = item.get("repository", {}).get("nameWithOwner", "unknown")
                    labels = [l["name"] for l in item.get("labels", [])]
                    value_usd = "unknown"
                    for l in labels:
                        lu = l.upper()
                        if "USD" in lu or "$" in l or "USDC" in lu or "USDT" in lu:
                            nums = ''.join(c for c in l if c.isdigit() or c == '.')
                            if nums: value_usd = nums; break
                    found.append({
                        "source": "github_search", "repo": repo, "title": item.get("title",""),
                        "url": item.get("url",""), "value_usd": value_usd, "labels": labels,
                        "discovered_at": datetime.now(timezone.utc).isoformat()
                    })
        except Exception as e:
            log(f"Search failed: {e}")
        time.sleep(2)
    
    log(f"Discovery complete. Found {len(found)} raw candidates.")
    ledger = load_json(LEDGER_FILE)
    existing = ledger.get("candidates", [])
    seen = {c["url"] for c in existing}
    new = 0
    for b in found:
        if b["url"] not in seen:
            existing.append(b); new += 1; seen.add(b["url"])
    ledger["candidates"] = existing
    ledger["last_discovery"] = datetime.now(timezone.utc).isoformat()
    save_json(LEDGER_FILE, ledger)
    log(f"Added {new} new candidates (Total: {len(existing)}).")
    return existing

def triage(candidates):
    if not candidates: return []
    api_key, base_url, model = get_config()
    if not api_key:
        log("ERROR: No API key"); return []
    
    log(f"=== TRIAGE PHASE (model={model}) ===")
    sorted_cands = sorted(candidates, key=lambda x: (str(x.get("value_usd","0")), x.get("discovered_at","")), reverse=True)[:30]
    
    prompt = f"""Select TOP 5 bounties for an AI coding agent. Criteria: <4h work, clear criteria, >= $10 value, Python/TS/Rust/Go/Solidity/Docs.
Candidates: {json.dumps(sorted_cands, indent=2)}
Return ONLY valid JSON array: [{{"url":"...","title":"...","estimated_hours":N,"confidence_score":0.X,"reason":"..."}}]"""
    
    resp = ghostcli_complete(prompt, api_key, base_url, model)
    selected = extract_json(resp) if resp else None
    
    if isinstance(selected, list) and len(selected) > 0:
        log(f"GhostCLI selected {len(selected)} targets.")
        return selected
    
    log("LLM triage failed or empty. Using heuristic fallback.")
    fallback = []
    for c in sorted_cands[:5]:
        fallback.append({
            "url": c["url"], "title": c["title"], "estimated_hours": 2,
            "confidence_score": 0.5, "reason": "Heuristic: High value/recent"
        })
    return fallback

def check_wise_balance():
    state = load_json(WISE_STATE)
    balance = state.get("balance_usd", 0)
    goal = 2_000_000
    pct = (balance / goal) * 100 if goal > 0 else 0
    log(f"Wise Balance: ${balance:,.2f} / ${goal:,} ({pct:.4f}%)")
    return balance

if __name__ == "__main__":
    log("=== AUTONOMOUS BOUNTY ORCHESTRATOR v2.5 STARTED ===")
    bal = check_wise_balance()
    if bal >= 2_000_000:
        log("🎉 GOAL ACHIEVED!"); sys.exit(0)
    
    candidates = discover_bounties()
    top_targets = triage(candidates)
    
    with open(PENDING_BOUNTIES, "w") as f:
        for t in top_targets:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    
    log(f"Cycle complete. {len(top_targets)} tasks queued.")
    if top_targets:
        log(f"Top target: {top_targets[0].get('title','N/A')} ({top_targets[0].get('url','')})")
