#!/usr/bin/env python3
"""
Feedback-Learning Loop Integration Module
Applies learned rules to pre-submission gates and hypothesis generation.
"""
import json
import os
from datetime import datetime, timezone

RULES_PATH = "logs/bounty/feedback/rules/generated_rules.json"
LEDGER_PATH = "logs/bounty/feedback/h1_feedback_ledger.jsonl"
CHECKLIST_PATH = "logs/bounty/feedback/pre_submission_checklist.json"

def load_rules():
    """Load current feedback-derived rules."""
    if not os.path.exists(RULES_PATH):
        return []
    with open(RULES_PATH) as f:
        return json.load(f)

def load_ledger():
    """Load report history for pattern matching."""
    entries = []
    if not os.path.exists(LEDGER_PATH):
        return entries
    with open(LEDGER_PATH) as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))
    return entries

def check_dedupe(program, title_snippet, vector_keywords):
    """FEEDBACK-001: Verify dedupe search before submission."""
    ledger = load_ledger()
    matches = []
    for entry in ledger:
        if entry.get("program") == program:
            existing_title = entry.get("title", "").lower()
            for kw in vector_keywords:
                if kw.lower() in existing_title:
                    matches.append({
                        "report_id": entry.get("report_id"),
                        "title": entry.get("title"),
                        "state": entry.get("state")
                    })
    return {
        "rule": "FEEDBACK-001",
        "passed": len(matches) == 0,
        "potential_duplicates": matches,
        "action": "ABORT_AND_REVIEW" if matches else "PROCEED"
    }

def check_impact_evidence(draft_content, program):
    """FEEDBACK-002 & 003: Verify impact demonstration meets standards."""
    required_sections = ["impact", "proof of concept", "steps to reproduce"]
    content_lower = draft_content.lower()
    
    missing = []
    for section in required_sections:
        if section not in content_lower:
            missing.append(section)
    
    # Check for weak impact indicators (config-only, no exploitation)
    weak_indicators = [
        "exposes version", "header reveals", "configuration file",
        "informational only", "no direct impact"
    ]
    has_weak = any(ind in content_lower for ind in weak_indicators)
    
    return {
        "rule": "FEEDBACK-002/003",
        "passed": len(missing) == 0 and not has_weak,
        "missing_sections": missing,
        "weak_impact_detected": has_weak,
        "action": "REVISE_DRAFT" if (missing or has_weak) else "PROCEED"
    }

def run_pre_submission_gates(program, title, draft_content, vector_keywords):
    """Execute all feedback-derived gates before submission."""
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "program": program,
        "title": title,
        "gates": []
    }
    
    # Gate 1: Dedupe
    dedupe_result = check_dedupe(program, title, vector_keywords)
    results["gates"].append(dedupe_result)
    
    # Gate 2: Impact Evidence
    impact_result = check_impact_evidence(draft_content, program)
    results["gates"].append(impact_result)
    
    # Overall decision
    all_passed = all(g["passed"] for g in results["gates"])
    results["overall"] = "APPROVED" if all_passed else "BLOCKED"
    results["blocking_issues"] = [
        g["rule"] for g in results["gates"] if not g["passed"]
    ]
    
    # Save checklist
    os.makedirs(os.path.dirname(CHECKLIST_PATH), exist_ok=True)
    with open(CHECKLIST_PATH, "w") as f:
        json.dump(results, f, indent=2)
    
    return results

def update_rules_from_feedback(new_feedback_entry):
    """Incrementally update rules when new feedback arrives."""
    rules = load_rules()
    state = new_feedback_entry.get("state", "")
    program = new_feedback_entry.get("program", "")
    
    # Pattern: duplicate -> strengthen dedupe rule
    if state == "duplicate":
        for rule in rules:
            if rule["rule_id"] == "FEEDBACK-001":
                rule["description"] += f" | Reinforced by {program} dup"
                break
    
    # Pattern: informative -> strengthen impact rule  
    elif state == "informative":
        for rule in rules:
            if rule["rule_id"] == "FEEDBACK-002":
                rule["description"] += f" | Reinforced by {program} informative"
                break
    
    with open(RULES_PATH, "w") as f:
        json.dump(rules, f, indent=2)
    
    return rules

if __name__ == "__main__":
    print("Feedback-Learning Integration Module loaded")
    print(f"Rules available: {len(load_rules())}")
    print(f"Ledger entries: {len(load_ledger())}")
