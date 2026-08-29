#!/usr/bin/env python3
"""
Freelance Executor v1.0 - Converts Orchestrator Proposals to Real Deliverables
Takes generated proposals/data products and executes the actual work via GhostCLI subagents.
Focus: Immediate revenue generation from existing orchestrator outputs.
"""
import os, sys, json, time, subprocess, requests
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path("/Agentic")
LOG_FILE = ROOT / "logs" / "freelance_executor.log"
ORCH_DIR = ROOT / "data" / "orchestrator"

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[EXEC] [{ts}] {msg}"
    print(line, flush=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def load_env():
    env = {}
    for p in [Path("/root/.automaton/.env"), ROOT / ".env"]:
        if p.exists():
            for line in p.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env

def spawn_worker(task_name: str, prompt: str, context: str = ""):
    """Spawn a GhostCLI worker to execute paid work."""
    env = load_env()
    api_key = env.get("GHOSTCLI_API_KEY")
    base_url = env.get("GHOSTCLI_BASE_URL", "https://ghostcli.dev/v1")
    
    full_prompt = prompt
    if context:
        full_prompt += f"\n\n## CONTEXT\n{context}"
    
    payload = {
        "model": "claude-fable-5[1m]",
        "messages": [{"role": "user", "content": full_prompt}],
        "max_tokens": 8192,
        "temperature": 0.1
    }
    
    try:
        r = requests.post(
            f"{base_url}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=300
        )
        if r.status_code == 200:
            content = r.json()["choices"][0]["message"]["content"]
            out_dir = ORCH_DIR / "deliverables" / task_name
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"{int(time.time())}.md").write_text(content)
            log(f"Worker [{task_name}] delivered {len(content)} chars")
            return content
    except Exception as e:
        log(f"Worker [{task_name}] failed: {e}")
    return None

def execute_data_product():
    """Build the FDA Import Refusal dataset cleaner identified by scout."""
    log("Executing data product: FDA Import Refusal Cleaner")
    prompt = """Create a production-ready Python script that:
1. Downloads FDA Import Refusal reports from https://www.accessdata.fda.gov/scripts/importrefusals/
2. Parses HTML tables into structured JSON with fields: date, product, manufacturer, country, violation_code, reason
3. Cleans manufacturer names (normalize casing, remove Inc/LLC suffixes)
4. Outputs clean CSV ready for B2B sale
5. Includes error handling and retry logic
6. Has a main() function that runs end-to-end

Write complete, runnable code. No placeholders."""
    spawn_worker("fda_cleaner", prompt)

def execute_freelance_template():
    """Build reusable bot template for Discord/Telegram gigs."""
    log("Executing freelance deliverable: Universal Bot Template")
    prompt = """Create a modular Python bot framework that works for both Discord and Telegram.
Requirements:
- Single codebase, platform-agnostic core logic
- Built-in: FAQ responder, lead capture form, API webhook caller
- Config via .env file
- Dockerfile included
- README with deployment instructions
- Example configs for both platforms

This is a $500-$800 deliverable. Make it production-quality."""
    spawn_worker("bot_template", prompt)

def run_cycle():
    log("Freelance Executor cycle starting")
    
    # Check what the orchestrator has produced
    proposals = list((ORCH_DIR / "freelance_proposals").glob("*.md")) if (ORCH_DIR / "freelance_proposals").exists() else []
    data_scouts = list((ORCH_DIR / "data_product_scout").glob("*.md")) if (ORCH_DIR / "data_product_scout").exists() else []
    
    log(f"Found {len(proposals)} proposals, {len(data_scouts)} data scouts")
    
    # Execute highest-value items first
    if data_scouts:
        execute_data_product()
    
    if proposals:
        execute_freelance_template()
    
    log("Executor cycle complete")

if __name__ == "__main__":
    log("Freelance Executor v1.0 starting")
    while True:
        try:
            run_cycle()
            time.sleep(8 * 3600)  # 8h cycles - deliverables take time
        except KeyboardInterrupt:
            break
        except Exception as e:
            log(f"Fatal: {e}")
            time.sleep(300)
