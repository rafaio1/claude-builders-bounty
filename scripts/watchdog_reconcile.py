#!/usr/bin/env python3
"""Watchdog reconciliation: map running Codex processes to expected agents,
detect stalled/orphaned sessions, and produce a durable status manifest."""
import json, subprocess, re, os, datetime

EXPECTED_AGENTS = {
    "analyst", "binance_bybit", "bounties", "central",
    "contador", "revenue_generator", "integrator", "bug_bounty"
}

def get_codex_processes():
    r = subprocess.run(["ps", "aux"], capture_output=True, text=True)
    procs = []
    for line in r.stdout.splitlines():
        if "codex" in line and "grep" not in line:
            # Extract session ID if present
            m = re.search(r'resume\s+([0-9a-f-]{36})', line)
            sid = m.group(1) if m else None
            # Extract model
            mm = re.search(r'-m\s+(\S+)|--model\s+(\S+)', line)
            model = (mm.group(1) or mm.group(2)) if mm else "unknown"
            # Extract PID
            parts = line.split()
            pid = parts[1] if len(parts) > 1 else "?"
            cpu = parts[2] if len(parts) > 2 else "?"
            mem = parts[3] if len(parts) > 3 else "?"
            etime = parts[9] if len(parts) > 9 else "?"
            procs.append({
                "pid": pid, "cpu": cpu, "mem": mem, "etime": etime,
                "session_id": sid, "model": model, "raw": line.strip()[:200]
            })
    return procs

def get_tmux_sessions():
    r = subprocess.run(["tmux", "list-sessions", "-F", "#{session_name}:#{session_created}"], 
                       capture_output=True, text=True)
    sessions = {}
    for line in r.stdout.strip().splitlines():
        if ":" in line:
            name, created = line.split(":", 1)
            sessions[name] = int(created)
    return sessions

def reconcile():
    procs = get_codex_processes()
    tmux = get_tmux_sessions()
    
    # Map known session IDs to agent names from handoff
    known_map = {
        "01a03a37-5be9-72b1-a6dc-a7c84ea6454d": "analyst",
        "01a03a37-62d8-7c91-a165-599d675dbffd": "binance_bybit", 
        "01a03a37-7bc4-7a13-9812-e5a409effe5f": "bounties",
        "01a03a37-64a3-7b83-88d2-5bba5f82f103": "central",
    }
    
    # Discover unmapped sessions
    mapped_sids = set(known_map.values())
    unmapped_procs = [p for p in procs if p["session_id"] and p["session_id"] not in known_map]
    
    report = {
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        "expected_agents": sorted(EXPECTED_AGENTS),
        "running_codex_count": len(procs),
        "tmux_sessions": list(tmux.keys()),
        "mapped_agents": {},
        "unmapped_sessions": [],
        "stalled_risk": [],
        "recommendations": []
    }
    
    for sid, agent in known_map.items():
        matching = [p for p in procs if p["session_id"] == sid]
        if matching:
            report["mapped_agents"][agent] = {
                "session_id": sid,
                "pid": matching[0]["pid"],
                "model": matching[0]["model"],
                "cpu": matching[0]["cpu"],
                "status": "running"
            }
        else:
            report["mapped_agents"][agent] = {"status": "NOT_RUNNING", "session_id": sid}
            report["recommendations"].append(f"Agent '{agent}' (sid={sid[:12]}...) not found in process list")
    
    # Check for agents without known session IDs
    for agent in EXPECTED_AGENTS - set(known_map.values()):
        report["mapped_agents"][agent] = {"status": "UNKNOWN_SESSION", "note": "Session ID not yet mapped"}
        report["recommendations"].append(f"Agent '{agent}' needs session ID discovery")
    
    for p in unmapped_procs:
        report["unmapped_sessions"].append({
            "session_id": p["session_id"],
            "pid": p["pid"],
            "model": p["model"]
        })
    
    # Write manifest
    manifest_path = "/Agentic/data/aro/watchdog_manifest.json"
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    with open(manifest_path, "w") as f:
        json.dump(report, f, indent=2)
    
    print(json.dumps(report, indent=2))
    return report

if __name__ == "__main__":
    reconcile()
