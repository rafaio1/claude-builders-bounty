#!/usr/bin/env python3
import shutil
"""High-Ticket Bounty Sniper - Autonomous sub-agent for $1000+ bounties"""
import sys, os, json, time, re, subprocess, requests, shutil, tempfile
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed


# Session-level cache to prevent retrying skipped/failed repos in same run
_SESSION_SKIP_CACHE = set()
# Global skip list for known-broken repos (accessible in run_cycle)
SKIP_REPOS = {
    "near/bounties",
    "relayhop/ClaudeEarnSelf-runtime",
}
ROOT = Path("/Agentic")
LOG = ROOT / "logs" / "high_ticket_sniper.log"
LEDGER = ROOT / "data" / "aro" / "high_ticket_ledger.json"
WORKSPACE = ROOT / "workspace" / "high-ticket"
ENV_FILES = [ROOT / ".env", Path("/root/.automaton/.env")]

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def load_env():
    env = {}
    for ef in ENV_FILES:
        if ef.exists():
            for line in open(ef):
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    env[k] = v
    return env

def ghostcli_complete(prompt, max_tokens=4000):
    env = load_env()
    api_key = env.get("APIFABLE_API_KEY") or env.get("GHOSTCLI_API_KEY_FALLBACK") or env.get("GHOSTCLI_API_KEY")
    local_base = "http://127.0.0.1:8787"
    base_url = local_base
    raw_model = re.sub(r'\x1b\[[0-9;]*m', '', env.get("GHOSTCLI_MODEL", "z-ai/glm-5.3")).split('[')[0].strip()
    model = raw_model
    if "fable" in model.lower():
        model = "z-ai/glm-5.3"
    if not api_key:
        log("ERROR: No GhostCLI API key")
        return None
    # Use local gateway (ApiFable on :8787) as primary — remote ghostcli.dev returns 403
    # local model killed per user request
    # local_base = "http://127.0.0.1:8787"
    local_base = "http://127.0.0.1:8787"
    base_url = local_base
    endpoints = [(base_url, api_key)]
    fb = env.get("GHOSTCLI_API_KEY_FALLBACK")
    if fb and fb != api_key:
        endpoints.append((base_url, fb))
    # Try Senior Pipeline first for complex generation tasks
    try:
        from senior_dev_pipeline import run_pipeline
        import tempfile
        if "files_to_change" in prompt and "HIGH-VALUE" in prompt:
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

    last_err = None
    for ep_base, key in endpoints:
        if not key:
            continue
        try:
            resp = requests.post(f"{ep_base}/v1/chat/completions",
                json={"model": model, "messages": [{"role": "user", "content": prompt}],
                      "max_tokens": max_tokens, "temperature": 0.1},
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                timeout=(10, 600))
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            last_err = e
            log(f"GhostCLI error (ep={ep_base}, key={key[:8]}...): {e}")
            continue
    log(f"GhostCLI failed all endpoints: {last_err}")
    return None

def discover_high_ticket():
    """Find bounties >= $500 from Algora API + GitHub search"""
    log("=== HIGH TICKET DISCOVERY ===")
    found = []
    seen_urls = set()
    
    # Method 1: Algora HTML Scraping (API returns HTML/406 now)
    try:
        import requests as req
        import re as _re
        import json as _json
        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        # Try explore page which often lists bounties
        resp = req.get("https://console.algora.io/explore", headers=headers, timeout=120)
        if resp.status_code == 200:
            # Look for embedded JSON data in script tags
            matches = _re.findall(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', resp.text, _re.DOTALL)
            if not matches:
                matches = _re.findall(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', resp.text, _re.DOTALL)
            
            parsed_count = 0
            for m in matches:
                try:
                    data = _json.loads(m)
                    # Flatten search for bounty-like structures
                    # This is heuristic since structure varies
                    def extract_bounties(obj, depth=0):
                        if depth > 10: return
                        if isinstance(obj, dict):
                            # Check if this dict looks like a bounty
                            if ('reward' in obj or 'amount' in obj) and ('url' in obj or 'issue_url' in obj or 'href' in obj):
                                url = obj.get('url') or obj.get('issue_url') or obj.get('href') or ""
                                reward = obj.get('reward') or obj.get('amount') or obj.get('value') or 0
                                if isinstance(reward, str):
                                    reward = int(_re.sub(r'[^0-9]', '', reward) or 0)
                                if reward >= 500 and url and url not in seen_urls:
                                    seen_urls.add(url)
                                    title = obj.get('title') or obj.get('name') or "?"
                                    repo = obj.get('repo') or obj.get('repository') or obj.get('org') or "unknown"
                                    found.append({"url": url, "title": title, "value": int(reward),
                                                  "repo": repo, "labels": ["algora"], "body_preview": ""})
                                    log(f"  FOUND (Algora Scraper): ${int(reward)} - {title[:80]} ({repo})")
                                    nonlocal parsed_count
                                    parsed_count += 1
                            for v in obj.values():
                                extract_bounties(v, depth+1)
                        elif isinstance(obj, list):
                            for item in obj:
                                extract_bounties(item, depth+1)
                    
                    extract_bounties(data)
                except Exception:
                    pass
            if parsed_count == 0:
                log("  Algora Scraper: No bounty JSON found in HTML")
        else:
            log(f"  Algora Scraper HTTP {resp.status_code}")
    except Exception as e:
        log(f"  Algora Scraper error: {e}")

    # Method 1b: Immunefi public bounties (high-value security audits)
    try:
        resp = req.get("https://immunefi.com/api/bounties/?status=active&min_reward=1000",
            timeout=120, headers={"Accept": "application/json", "User-Agent": "BountyBot/2.0"})
        if resp.status_code == 200:
            data = resp.json()
            bounties = data if isinstance(data, list) else data.get("bounties", data.get("data", []))
            for b in bounties[:30]:
                url = b.get("url") or b.get("issue_url") or ""
                if not url or url in seen_urls:
                    continue
                reward = b.get("reward") or b.get("amount") or b.get("max_reward") or 0
                if isinstance(reward, str):
                    reward = int(re.sub(r'[^0-9]', '', reward) or 0)
                if reward < 1000:
                    continue
                seen_urls.add(url)
                repo = b.get("repo") or b.get("project") or "?"
                title = b.get("title") or b.get("name") or "?"
                found.append({"url": url, "title": title, "value": int(reward),
                    "repo": repo, "labels": ["immunefi"], "body_preview": ""})
                log(f"  FOUND (Immunefi): ${int(reward)} - {title[:80]} ({repo})")
    except Exception as e:
        log(f"  Immunefi API error: {e}")

    # Method 1c: Code4rena contests (high-value smart contract audits)
    try:
        resp = req.get("https://api.code4rena.com/v2/contests?status=open",
            timeout=120, headers={"Accept": "application/json", "User-Agent": "BountyBot/2.0"})
        if resp.status_code == 200:
            data = resp.json()
            contests = data if isinstance(data, list) else data.get("contests", data.get("data", []))
            for c in contests[:20]:
                url = c.get("url") or c.get("repo") or ""
                if not url or url in seen_urls:
                    continue
                prize = c.get("prizePool") or c.get("totalPrize") or c.get("amount") or 0
                if isinstance(prize, str):
                    prize = int(re.sub(r'[^0-9]', '', prize) or 0)
                if prize < 5000:
                    continue
                seen_urls.add(url)
                title = c.get("title") or c.get("name") or "?"
                repo = c.get("repo") or c.get("repository") or "?"
                found.append({"url": url, "title": title, "value": int(prize),
                    "repo": repo, "labels": ["code4rena"], "body_preview": ""})
                log(f"  FOUND (Code4rena): ${int(prize)} - {title[:80]} ({repo})")
    except Exception as e:
        log(f"  Code4rena API error: {e}")

    
    # Method 2: Direct GitHub API search (more reliable than gh CLI for complex queries)
    SPAM_PATTERNS = ["bounty-scout", "bounty-plaza", "bounty-alert", "opportunity-bot",
                     "bounty-finder", "bounty-tracker", "bounty-aggregator", "bounty-hub",
                     "zhangjiayang6835-cyber", "relayhop/sn-monetization",
                     # Repos that consistently fail (empty, already submitted, or invalid bounties)
                     "syscoin/syscoin-gitcoin", "dao-global-hackathon/open-lane",
                     # False positive $1M+ bounties (VDP policies, not real code bounties)
                     "hackerone", "bugcrowd", "intigriti", "yeswehack"]
    
    # Use GitHub REST API directly with proper auth
    gh_token = os.environ.get("GITHUB_TOKEN", "")
    if not gh_token:
        # Try to get from gh config
        try:
            res = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                gh_token = res.stdout.strip()
        except:
            pass
    
    headers = {"Accept": "application/vnd.github.v3+json"}
    if gh_token:
        headers["Authorization"] = f"Bearer {gh_token}"
    
    # High-value focused queries
    api_queries = [
        "label:bounty+state:open+sort:updated",
        "label:%22%F0%9F%92%B0+bounty%22+state:open+sort:updated",
        "bounty+%24+state:open+sort:updated",
        "label:algora+state:open+sort:updated",
        "label:gitcoin+state:open+sort:updated",
        "%22%241000%22+bounty+state:open",
        "%22%245000%22+bounty+state:open",
        "%22security+audit%22+bounty+state:open",
        "%22smart+contract%22+bounty+state:open",
        # Expanded discovery - new ecosystems and higher values
        "%22%2410000%22+bounty+state:open",
        "%22%2425000%22+bounty+state:open",
        "label:bug+bounty+state:open+sort:updated",
        "label:immunefi+state:open+sort:updated",
        "label:code4rena+state:open+sort:updated",
        "label:sherlock+state:open+sort:updated",
        "%22protocol+upgrade%22+bounty+state:open",
        "%22critical+fix%22+bounty+state:open",
        "%22vulnerability%22+bounty+state:open+sort:updated",
        "org:celestiaorg+bounty+state:open",
        "org:cosmos+bounty+state:open",
        "org:solana-labs+bounty+state:open",
        "org:near+bounty+state:open",
        "org:aptos-labs+bounty+state:open",
        "org:sui-io+bounty+state:open",
        "org:ethereum+bounty+state:open",
        "org:paritytech+bounty+state:open",
    ]
    
    for q in api_queries:
        try:
            url = f"https://api.github.com/search/issues?q={q}&per_page=50"
            # Ensure fresh auth header for each request
            if gh_token:
                headers["Authorization"] = f"Bearer {gh_token}"
            resp = requests.get(url, headers=headers, timeout=120)
            if resp.status_code == 403:
                # Rate limited or forbidden - check reset time and wait
                reset_ts = int(resp.headers.get("x-ratelimit-reset", "0"))
                now_ts = int(time.time())
                wait_secs = max(10, min(reset_ts - now_ts + 5, 60)) if reset_ts else 30
                log(f"  GH API 403 (rate limit?), waiting {wait_secs}s before next query")
                time.sleep(wait_secs)
                continue
            if resp.status_code != 200:
                log(f"  GH API query failed ({resp.status_code}): {q[:50]}")
                continue
            data = resp.json()
            items = data.get("items", [])
            if not items:
                continue
            for item in items:
                url_str = item.get("html_url", "")
                if not url_str or url_str in seen_urls:
                    continue
                repo_full = item.get("repository_url", "").split("/")[-2:]
                repo_name = "/".join(repo_full) if len(repo_full) == 2 else "?"
                if any(p in repo_name.lower() for p in SPAM_PATTERNS):
                    continue
                title = item.get("title", "")
                body = (item.get("body", "") or "")[:3000]
                labels = [l.get("name", "") for l in item.get("labels", [])]
                # Extract dollar value aggressively
                value = 0
                for text in [title, body] + labels:
                    for pattern in [r'\$(\d[\d,]*)', r'(\d[\d,]+)\s*(?:USD|USDC|USDT)', r'(?:bounty|reward|prize)[:\s]*\$?(\d[\d,]*)']:
                        m = re.search(pattern, str(text), re.IGNORECASE)
                        if m:
                            try:
                                val = int(m.group(1).replace(",", ""))
                                if val >= 100:
                                    value = max(value, val)
                            except:
                                pass
                # Cap at $500k - higher values are almost always VDP/policy docs, not code bounties
                if value > 500000:
                    log(f"  SKIPPED (likely false positive ${value}): {title[:60]}")
                    continue
                if value >= 100 or any(lb.lower() in ["bounty", "💰 bounty", "algora", "gitcoin", "dework", "reward"] for lb in labels):
                    seen_urls.add(url_str)
                    found.append({"url": url_str, "title": title, "value": value or 250,
                                  "repo": repo_name, "labels": labels, "body_preview": body[:500]})
                    if value >= 500:
                        log(f"  FOUND (GH-API): ${value} - {title[:70]} ({repo_name})")
        except Exception as e:
            log(f"  GH API error: {e}")
        time.sleep(2)
    
    # Method 3: Fallback to gh CLI for additional coverage
    cli_queries = [
        'bounty "$" state:open is:issue sort:updated-desc',
        'label:bounty state:open is:issue sort:updated-desc',
        'label:"bug bounty" state:open is:issue sort:updated-desc',
        '"$1000" OR "$5000" OR "$10000" bounty state:open is:issue sort:updated-desc',
        'label:immunefi OR label:code4rena OR label:sherlock state:open is:issue sort:updated-desc',
        '"security audit" OR "vulnerability" bounty state:open is:issue sort:updated-desc',
        '"protocol upgrade" OR "critical fix" bounty state:open is:issue sort:updated-desc',
        'bounty language:rust state:open is:issue sort:updated-desc',
        'bounty language:solidity state:open is:issue sort:updated-desc',
        'bounty language:go state:open is:issue sort:updated-desc',
    ]
    for q in cli_queries:
        try:
            cmd = f'gh search issues "{q}" --limit 50 --json repository,title,url,labels,body'
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=45)
            if res.returncode != 0 or not res.stdout.strip() or res.stdout.strip() == "[]":
                continue
            items = json.loads(res.stdout)
            for item in items:
                url = item.get("url", "")
                if not url or url in seen_urls:
                    continue
                repo = item.get("repository", {}).get("nameWithOwner", "?")
                if any(p in repo.lower() for p in SPAM_PATTERNS):
                    continue
                
                title = item.get("title", "")
                body = item.get("body", "")[:3000]
                labels = [l.get("name","") if isinstance(l, dict) else str(l) for l in item.get("labels", [])]
                
                value = 0
                for text in [title] + labels + [body]:
                    for pattern in [r'\$(\d[\d,]*)', r'(\d[\d,]*)\s*(?:USD|USDC)']:
                        m = re.search(pattern, str(text), re.IGNORECASE)
                        if m:
                            try:
                                value = max(value, int(m.group(1).replace(",", "")))
                            except:
                                pass
                
                if value >= 100:
                    seen_urls.add(url)
                    found.append({"url": url, "title": title, "value": value,
                                  "repo": repo, "labels": labels, "body_preview": body[:500]})
                    log(f"  FOUND (GH): ${value} - {title[:80]} ({repo})")
                elif any(lb.lower() in ["bounty", "💰 bounty", "algora", "gitcoin", "dework"] for lb in labels):
                    # Include label-confirmed bounties even without explicit $ amount
                    seen_urls.add(url)
                    found.append({"url": url, "title": title, "value": value or 250,
                                  "repo": repo, "labels": labels, "body_preview": body[:500]})
                    log(f"  FOUND (GH-LABEL): ${value or 250} - {title[:80]} ({repo})")
        except Exception as e:
            log(f"  Query failed: {e}")
        time.sleep(3)
    
    log(f"Discovered {len(found)} bounties (>= $500 or label-confirmed)")
    return sorted(found, key=lambda x: x["value"], reverse=True)


def execute_bounty(target):
    """Clone, fix, and submit PR for a high-ticket bounty"""
    url = target["url"]
    title = target["title"]
    value = target["value"]
    repo = target["repo"]
    


    log(f"=== EXECUTING ${value}: {title[:60]} ===")
    
    # Check if already submitted
    ledger = {}
    if LEDGER.exists():
        try:
            ledger = json.loads(LEDGER.read_text())
        except Exception:
            pass
    done_urls = {b.get("url") for b in ledger.get("bounties", [])}
    # Also check PR URLs - a bounty may have been submitted even if issue URL differs
    done_pr_urls = {b.get("pr_url") for b in ledger.get("bounties", []) if b.get("pr_url")}
    # Check main bounty ledger too for cross-reference
    try:
        main_ledger = json.loads((ROOT / "data" / "aro" / "bounty_ledger.json").read_text())
        for b in main_ledger.get("bounties", []):
            if b.get("pr_url"):
                done_pr_urls.add(b["pr_url"])
            if b.get("url"):
                done_urls.add(b["url"])
    except Exception:
        pass
    
    if url in done_urls:
        log(f"  Already submitted (issue URL match), skipping")
        return "SKIP"
        # Track consecutive skips to detect exhaustion
        global _consecutive_skips
        _consecutive_skips = getattr(sys.modules[__name__], '_consecutive_skips', 0) + 1
        if _consecutive_skips >= 10:
            log(f"  WARNING: {_consecutive_skips} consecutive skips - target pool may be exhausted")
            log(f"  Consider expanding search queries or waiting for new bounties")
            _consecutive_skips = 0  # Reset to avoid spamming
        return None
    # Reset skip counter on successful new target
    _consecutive_skips = 0
    
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    # Clean stale temp dirs to prevent disk/object corruption
    import glob
    # DISABLED: Aggressive cleanup was deleting active workspace dirs
    # for stale in glob.glob(str(WORKSPACE / "ht_*")):
    fork_owner = "rafaio1"
    repo_name = repo.split("/")[-1]
    # Override fork name for repos with known corruption issues
    FORK_NAME_OVERRIDES = {"near/bounties": "near-bounties", "bounties": "near-bounties"}
    # Repos to skip due to persistent server-side issues
    SKIP_REPOS = {
    "near/bounties",  # Persistent server-side corruption
    "relayhop/ClaudeEarnSelf-runtime",  # Session cache confirmed skip
    "near/bounties",  # git index-pack failed - confirmed server-side object corruption
    
    }

    if repo.lower() in FORK_NAME_OVERRIDES or repo_name.lower() in FORK_NAME_OVERRIDES:
        repo_name = FORK_NAME_OVERRIDES.get(repo.lower(), FORK_NAME_OVERRIDES.get(repo_name.lower(), repo_name))
        log(f"  Using alternate fork name: {fork_owner}/{repo_name}")
    
    # Skip repos with known server-side corruption BEFORE any API calls
    # Check session cache first to avoid repeated failures
    cache_key = f"{repo}:{value}"
    if cache_key in _SESSION_SKIP_CACHE:
        log(f"  SKIPPING {repo} (session cache - previously failed/skipped)")
        return "SKIP"
        
    if repo.lower() in SKIP_REPOS or repo_name.lower() in SKIP_REPOS:
        log(f"  SKIPPING {repo} (known server-side corruption)")
        _SESSION_SKIP_CACHE.add(cache_key)
        return "SKIP"

    try:
        tmp_dir = tempfile.mkdtemp(prefix=f"ht_{value}_", dir=str(WORKSPACE))
        # Step 1: Ensure fork exists BEFORE cloning
        check_res = subprocess.run(["gh", "repo", "view", f"{fork_owner}/{repo_name}", "--json", "name"],
                                   capture_output=True, text=True, timeout=15)
        if check_res.returncode != 0:
            log(f"  Fork {fork_owner}/{repo_name} not found, creating...")
            fork_res = subprocess.run(["gh", "repo", "fork", repo, "--clone=false"],
                                      capture_output=True, text=True, timeout=60)
            if fork_res.returncode != 0:
                log(f"  Cannot fork {repo}: {fork_res.stderr[:200]}")
                return None
            log(f"  Fork created successfully")
            time.sleep(5)  # Wait for GitHub to propagate
        
        # Step 2: Clone from upstream
        clone_res = subprocess.run(["git", "clone", "--depth", "1", "--filter=blob:none", f"https://github.com/{repo}.git", tmp_dir],
                                   capture_output=True, text=True, timeout=120)
        if clone_res.returncode != 0:
            log(f"  Clone failed: {clone_res.stderr[:200]}")
            return None
        
        # Get issue details
        match = re.match(r'https://github.com/([^/]+)/([^/]+)/(?:issues|pull)/(\d+)', url)
        if not match:
            log(f"  Cannot parse issue URL")
            return None
        owner, repo_name, issue_num = match.groups()
        
        issue_res = subprocess.run(["gh", "issue", "view", issue_num, "--repo", f"{owner}/{repo_name}",
                                    "--json", "title,body"], capture_output=True, text=True, timeout=120)
        issue_body = ""
        if issue_res.returncode == 0:
            idata = json.loads(issue_res.stdout)
            issue_body = idata.get("body", "")[:5000]
        
        # Generate fix via GhostCLI
        prompt = f"""You are fixing a HIGH-VALUE (${value}) open-source bounty. Generate a complete, production-ready fix.

ISSUE: {title}
URL: {url}
REPO: {repo}
ISSUE DESCRIPTION:
{issue_body}

REQUIREMENTS:
- Output a JSON object with this exact structure:
{{
  "files_to_change": [
    {{"path": "relative/path/to/file", "action": "modify|create", "content": "full file content after fix"}}
  ],
  "branch_name": "fix/descriptive-name",
  "commit_message": "fix: concise description",
  "pr_title": "fix: concise description",
  "pr_body": "## Summary\\nBrief explanation of the fix\\n\\n## Changes\\n- Bullet points"
}}
- The fix MUST pass all existing tests
- Handle ALL edge cases mentioned in the issue
- Follow the project's code style exactly
- Only output valid JSON, no markdown fences"""
        
        response = ghostcli_complete(prompt, max_tokens=12000)
        if not response:
            log(f"  GhostCLI returned empty response")
            return None
        
        # Parse JSON from response
        json_match = re.search(r'\{[\s\S]*\}', response)
        if not json_match:
            log(f"  No JSON found in response")
            return None
        
        try:
            fix_plan = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            log(f"  JSON parse error: {e}, attempting repair...")
            # Attempt to repair truncated JSON by closing open braces/brackets
            raw = json_match.group()
            for _ in range(10):
                try:
                    fix_plan = json.loads(raw)
                    log(f"  Repaired JSON successfully")
                    break
                except json.JSONDecodeError:
                    pass
                # Try adding closing chars
                opens = raw.count('{') - raw.count('}')
                arr_opens = raw.count('[') - raw.count(']')
                suffix = ''
                if opens > 0:
                    suffix += '}' * opens
                if arr_opens > 0:
                    suffix += ']' * arr_opens
                raw = raw + suffix
            else:
                log(f"  Could not repair JSON after attempts")
                return None
        
        files = fix_plan.get("files_to_change", [])
        if not files:
            log(f"  No files to change in plan")
            return None
        
        branch = fix_plan.get("branch_name", f"fix/ht-{issue_num}-{int(time.time())}")
        commit_msg = fix_plan.get("commit_message", f"fix: {title[:50]}")
        pr_title = fix_plan.get("pr_title", f"fix: {title[:80]}")
        pr_body = fix_plan.get("pr_body", f"Fixes #{issue_num}\n\n${value} bounty")
        
        # Apply changes
        subprocess.run(["git", "checkout", "-b", branch], cwd=tmp_dir, capture_output=True, timeout=10)
        
        for f in files:
            fpath = os.path.join(tmp_dir, f["path"])
            os.makedirs(os.path.dirname(fpath), exist_ok=True)
            with open(fpath, "w") as fh:
                fh.write(f.get("content", ""))
            log(f"  Written: {f['path']}")
        
        # Commit and push
        subprocess.run(["git", "add", "-A"], cwd=tmp_dir, capture_output=True, timeout=10)
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=tmp_dir, capture_output=True, timeout=10)
        
        # Set remote to our fork and add upstream
        subprocess.run(["git", "remote", "set-url", "origin", f"https://github.com/{fork_owner}/{repo_name}.git"],
                       cwd=tmp_dir, capture_output=True, timeout=10)
        subprocess.run(["git", "remote", "add", "upstream", f"https://github.com/{repo}.git"],
                       cwd=tmp_dir, capture_output=True, timeout=10)
        subprocess.run(["git", "fetch", "origin"], cwd=tmp_dir, capture_output=True, timeout=120)
        
        # Use --force to handle diverged fork branches safely
        push_res = subprocess.run(["git", "push", "--force", "origin", branch], cwd=tmp_dir, 
                                  capture_output=True, text=True, timeout=60)
        if push_res.returncode != 0:
            stderr = push_res.stderr
            if "Repository not found" in stderr or "404" in stderr:
                log(f"  Fork not found, attempting to create via gh...")
                fork_res = subprocess.run(["gh", "repo", "fork", f"{owner}/{repo_name}", "--clone=false"],
                                          capture_output=True, text=True, timeout=120)
                if fork_res.returncode == 0:
                    log(f"  Fork created, retrying push...")
                    time.sleep(5)
                    push_res = subprocess.run(["git", "push", "--force", "origin", branch], cwd=tmp_dir,
                                              capture_output=True, text=True, timeout=60)
            
            if push_res.returncode != 0:
                log(f"  Push failed: {push_res.stderr[:200]}")
                return None
        
        # Create PR
        pr_cmd = ["gh", "pr", "create", "--repo", f"{owner}/{repo_name}", "--base", "main",
                  "--head", f"{fork_owner}:{branch}", "--title", pr_title, "--body", pr_body]
        pr_res = subprocess.run(pr_cmd, capture_output=True, text=True, timeout=120)
        
        pr_url = None
        if pr_res.returncode == 0:
            pr_url = pr_res.stdout.strip()
        else:
            # Try master
            pr_cmd[pr_cmd.index("main")] = "master"
            pr_res2 = subprocess.run(pr_cmd, capture_output=True, text=True, timeout=120)
            if pr_res2.returncode == 0:
                pr_url = pr_res2.stdout.strip()
        
        if not pr_url:
            log(f"  PR creation failed: {pr_res.stderr[:300] if pr_res else (pr_res2.stderr[:300] if pr_res2 else "unknown")}")
            return None
        
        log(f"  PR CREATED: {pr_url}")
        
        # Record in ledger
        if "bounties" not in ledger:
            ledger["bounties"] = []
        ledger["bounties"].append({
            "url": url, "title": title, "value": value, "repo": repo,
            "pr_url": pr_url, "status": "submitted",
            "submitted_at": datetime.now(timezone.utc).isoformat()
        })
        ledger["total_value"] = sum(b.get("value", 0) for b in ledger["bounties"])
        LEDGER.write_text(json.dumps(ledger, indent=2, default=str))
        
        return pr_url
        
    except Exception as e:
        log(f"  Execution error: {e}")
        _SESSION_SKIP_CACHE.add(cache_key)
        return None
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True) if "tmp_dir" in locals() else None

def run_cycle():
    log("=== HIGH TICKET SNIPER CYCLE START ===")
    targets = discover_high_ticket()
    
    # Pre-filter already-submitted targets before execution
    ledger = {}
    if LEDGER.exists():
        try:
            ledger = json.loads(LEDGER.read_text())
        except Exception:
            pass
    done_urls = {b.get("url") for b in ledger.get("bounties", [])}
    try:
        main_ledger = json.loads((ROOT / "data" / "aro" / "bounty_ledger.json").read_text())
        for b in main_ledger.get("bounties", []):
            if b.get("pr_url"): done_urls.add(b["pr_url"])
            if b.get("url"): done_urls.add(b["url"])
    except Exception:
        pass
    fresh_targets = [t for t in targets if t.get("url") not in done_urls]
    # Pre-filter SKIP_REPOS to prevent wasting execution slots on known-broken targets
    fresh_targets = [t for t in fresh_targets if t.get("repo","").lower() not in SKIP_REPOS and t.get("repo","").split("/")[-1].lower() not in SKIP_REPOS]
    skipped = len(targets) - len(fresh_targets)
    if skipped > 0:
        log(f"  Pre-filtered {skipped}/{len(targets)} already-submitted targets")
    targets = fresh_targets
    
    if not targets:
        log("No fresh high-ticket bounties found this cycle")
    else:
        # Execute top 3 highest-value FRESH bounties per cycle
        for t in targets[:3]:
            result = execute_bounty(t)
            if result == "SKIP":
                pass  # Already submitted, skip logged inside execute_bounty
            elif result:
                log(f"SUCCESS: ${t['value']} -> {result}")
            else:
                log(f"FAILED: ${t['value']} - {t['title'][:50]}")
            time.sleep(10)
    
    log("=== CYCLE COMPLETE ===\n")

if __name__ == "__main__":
    import traceback, sys
    # Redirect stderr to log file for crash diagnostics
    class TeeStderr:
        def __init__(self, logfile):
            self.logfile = logfile
            self.orig = sys.stderr
        def write(self, msg):
            self.orig.write(msg)
            if msg.strip():
                log(f"STDERR: {msg.strip()}")
        def flush(self):
            self.orig.flush()
    sys.stderr = TeeStderr(LOG)
    
    log("High-Ticket Bounty Sniper v2.0 starting (interval=600s, Algora API enabled)")
    while True:
        try:
            run_cycle()
        except Exception as e:
            log(f"FATAL: {e}")
            log(traceback.format_exc())
        time.sleep(600)
