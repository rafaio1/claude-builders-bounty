import json, os, datetime

RESULTS_DIR = "/Agentic/bugbounty/recon/results"
STATE_FILE = "/Agentic/orchestrator/state.json"
FINDINGS_FILE = os.path.join(RESULTS_DIR, "triaged_findings.json")

findings = []
for fname in os.listdir(RESULTS_DIR):
    if fname.startswith("nuclei_") and fname.endswith(".txt"):
        fpath = os.path.join(RESULTS_DIR, fname)
        with open(fpath) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # Format: [template] [protocol] [severity] url [extra]
                parts = line.split()
                if len(parts) >= 4:
                    findings.append({
                        "template": parts[0].strip("[]"),
                        "protocol": parts[1].strip("[]"),
                        "severity": parts[2].strip("[]"),
                        "url": parts[3],
                        "extra": " ".join(parts[4:]) if len(parts) > 4 else "",
                        "source_file": fname,
                        "detected_at": datetime.datetime.utcnow().isoformat() + "Z",
                        "status": "needs_validation",
                        "estimated_bounty_usd": 5000 if "critical" in parts[2] else 2000
                    })

with open(FINDINGS_FILE, "w") as f:
    json.dump(findings, f, indent=2)

# Update state
with open(STATE_FILE) as f:
    state = json.load(f)

state["subagents"]["bugbounty"]["status"] = "validation"
state["subagents"]["bugbounty"]["findings_count"] = len(findings)
state["subagents"]["bugbounty"]["potential_bounty_usd"] = sum(x["estimated_bounty_usd"] for x in findings)
state["subagents"]["bugbounty"]["last_updated"] = datetime.datetime.utcnow().isoformat() + "Z"

with open(STATE_FILE, "w") as f:
    json.dump(state, f, indent=2)

print(f"TRIAGED: {len(findings)} findings, potential ${sum(x['estimated_bounty_usd'] for x in findings)} USD")
