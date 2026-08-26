#!/usr/bin/env python3
"""pr_freelance: High-Ticket Opportunity Scanner"""
import json
import os
from datetime import datetime, timezone

PIPELINE_PATH = "/Agentic/pr_freelance/contracts/pipeline.json"

def load_pipeline():
    if os.path.exists(PIPELINE_PATH):
        with open(PIPELINE_PATH) as f:
            return json.load(f)
    return {"leads": [], "last_scan": None}

def save_pipeline(data):
    data["last_scan"] = datetime.now(timezone.utc).isoformat()
    with open(PIPELINE_PATH, "w") as f:
        json.dump(data, f, indent=2)

if __name__ == "__main__":
    pipeline = load_pipeline()
    print(f"[pr_freelance] Pipeline loaded. Existing leads: {len(pipeline['leads'])}")
    print("[pr_freelance] Ready for bounty-hunter or manual lead injection.")
    save_pipeline(pipeline)
