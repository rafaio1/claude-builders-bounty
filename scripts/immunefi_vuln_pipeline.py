#!/usr/bin/env python3
"""
Immunefi Vulnerability Pipeline - Zero-Capital Bug Bounty Orchestrator
Clones target repos, runs static analysis (slither/mythril), and generates
markdown vulnerability reports for Immunefi submission.
Focuses on high-value programs: Ethena ($3M), DeXe ($500k), ENS ($250k).
"""

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = "/Agentic/workspaces/immunefi"
OUTPUT_DIR = "/Agentic/revenue/immunefi_reports"
LOG_PATH = "/Agentic/logs/immunefi_vuln_pipeline.log"
DEEP_OPP_DIR = "/Agentic/revenue/immunefi_deep_opportunities"

# Target repos mapped to Immunefi programs (public GitHub sources)
TARGETS = {
    "ethena": {
        "program": "Ethena",
        "repos": [
            "https://github.com/ethena-labs/usde-public",
            "https://github.com/ethena-labs/staking-public",
        ],
        "max_bounty": 3_000_000,
        "scope": ["smart contract", "solidity", "oracle"],
    },
    "dexe": {
        "program": "DeXe Protocol",
        "repos": [
            "https://github.com/dexe-network/DeXe-Protocol",
            "https://github.com/dexe-network/gov-pool",
        ],
        "max_bounty": 500_000,
        "scope": ["smart contract", "solidity", "governance"],
    },
    "ens": {
        "program": "ENS",
        "repos": [
            "https://github.com/ensdomains/ens-contracts",
            "https://github.com/ensdomains/name-wrapper",
        ],
        "max_bounty": 250_000,
        "scope": ["smart contract", "solidity", "dns"],
    },
}

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")

def run_cmd(cmd, cwd=None, timeout=120):
    """Run shell command safely."""
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=cwd
        )
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"
    except Exception as e:
        return -1, "", str(e)

def clone_repo(url, dest):
    """Clone or update a git repo."""
    if os.path.exists(dest):
        log(f"  Updating existing repo: {dest}")
        code, out, err = run_cmd("git pull --ff-only", cwd=dest, timeout=60)
        if code != 0:
            log(f"  WARN: git pull failed ({err[:100]}), re-cloning")
            run_cmd(f"rm -rf {dest}")
        else:
            return True
    
    log(f"  Cloning {url} -> {dest}")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    code, out, err = run_cmd(f"git clone --depth 1 {url} {dest}", timeout=180)
    if code != 0:
        log(f"  ERROR cloning {url}: {err[:200]}")
        return False
    return True

def find_solidity_files(repo_path):
    """Find all .sol files in repo."""
    sol_files = []
    for root, dirs, files in os.walk(repo_path):
        # Skip node_modules, test, lib directories for speed
        dirs[:] = [d for d in dirs if d not in ['node_modules', 'test', 'tests', 'lib', '.git']]
        for f in files:
            if f.endswith('.sol'):
                sol_files.append(os.path.join(root, f))
    return sol_files[:50]  # Limit to avoid excessive scanning

def run_slither(sol_file, output_path):
    """Run slither static analyzer on a Solidity file."""
    code, out, err = run_cmd(
        f"slither {sol_file} --json {output_path} --exclude-informational --exclude-low 2>/dev/null || true",
        timeout=90
    )
    if os.path.exists(output_path):
        try:
            with open(output_path) as f:
                data = json.load(f)
            results = data.get("results", {})
            findings = results.get("detectors", [])
            return findings
        except:
            pass
    return []

def generate_report(program_name, findings, repo_url, scope_keywords):
    """Generate Immunefi-style markdown vulnerability report."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # Filter to high/critical severity
    critical = [f for f in findings if f.get("impact") in ["Critical", "High"]]
    medium = [f for f in findings if f.get("impact") == "Medium"]
    
    if not critical and not medium:
        return None
    
    report = f"""# Vulnerability Report: {program_name}

**Date:** {ts}
**Program:** {program_name} (Immunefi)
**Repository:** {repo_url}
**Scope Keywords:** {', '.join(scope_keywords)}

## Executive Summary

Automated static analysis identified **{len(critical)} critical/high** and **{len(medium)} medium** severity issues in the {program_name} smart contracts. These findings require manual verification and PoC development before submission.

## Critical/High Severity Findings

"""
    
    for i, f in enumerate(critical[:5], 1):
        check = f.get("check", "unknown")
        impact = f.get("impact", "Unknown")
        desc = f.get("description", "No description available")
        elements = f.get("elements", [])
        source = ""
        if elements:
            src_info = elements[0].get("source_mapping", {})
            filename = src_info.get("filename_relative", "unknown")
            lines = src_info.get("lines", [])
            source = f"`{filename}:{lines[0] if lines else '?'}`"
        
        report += f"""### Finding #{i}: {check}
- **Severity:** {impact}
- **Location:** {source}
- **Description:** {desc[:500]}
- **Recommendation:** Manual review required. Verify if this pattern is exploitable in production context.

"""
    
    if medium:
        report += "## Medium Severity Findings\n\n"
        for i, f in enumerate(medium[:5], 1):
            check = f.get("check", "unknown")
            desc = f.get("description", "")[:300]
            report += f"- **{check}:** {desc}\n"
    
    report += f"""
## Next Steps

1. **Manual Verification:** Review each finding against actual contract logic and deployment parameters.
2. **PoC Development:** Create minimal reproduction case demonstrating exploit path.
3. **Impact Assessment:** Calculate funds at risk based on current TVL ({program_name} vault).
4. **Submission:** Format final report per Immunefi guidelines and submit via dashboard.

---
*Generated by Agentic Immunefi Pipeline v1.0 | {ts}*
"""
    return report

def main():
    log("=== Immunefi Vuln Pipeline Start ===")
    os.makedirs(WORKSPACE, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Check if slither is available
    code, _, _ = run_cmd("which slither")
    has_slither = (code == 0)
    if not has_slither:
        log("WARN: slither not installed. Attempting pip install...")
        run_cmd("pip install slither-analyzer 2>&1 | tail -3", timeout=120)
        code, _, _ = run_cmd("which slither")
        has_slither = (code == 0)
        if not has_slither:
            log("ERROR: Cannot install slither. Falling back to grep-based scan.")
    
    total_findings = 0
    reports_generated = 0
    
    for key, target in TARGETS.items():
        program = target["program"]
        log(f"\n--- Processing {program} (Max: ${target['max_bounty']:,}) ---")
        
        for repo_url in target["repos"]:
            repo_name = repo_url.split("/")[-1].replace(".git", "")
            repo_path = os.path.join(WORKSPACE, key, repo_name)
            
            if not clone_repo(repo_url, repo_path):
                continue
            
            sol_files = find_solidity_files(repo_path)
            log(f"  Found {len(sol_files)} Solidity files in {repo_name}")
            
            if not has_slither:
                # Fallback: grep for common vuln patterns
                log(f"  Running grep-based pattern scan (no slither)")
                patterns = [
                    ("reentrancy", r"call\{value:"),
                    ("unchecked-return", r"\.transfer\(|\.send\("),
                    ("delegatecall", r"delegatecall\("),
                    ("selfdestruct", r"selfdestruct\(|suicide\("),
                    ("tx-origin", r"tx\.origin"),
                ]
                findings = []
                for pname, pattern in patterns:
                    code, out, _ = run_cmd(f"grep -rn '{pattern}' {repo_path}/contracts/ 2>/dev/null | head -5")
                    if out.strip():
                        findings.append({
                            "check": pname,
                            "impact": "Medium",
                            "description": f"Pattern match: {pname} detected in source",
                            "elements": [{"source_mapping": {"filename_relative": "multiple", "lines": []}}]
                        })
                        log(f"    Pattern '{pname}': {len(out.strip().splitlines())} matches")
            else:
                # Run slither on first 5 contracts (speed optimization)
                findings = []
                scan_dir = os.path.join(repo_path, "contracts")
                if not os.path.exists(scan_dir):
                    scan_dir = repo_path
                
                code, out, _ = run_cmd(f"slither {scan_dir} --json /tmp/slither_out.json --exclude-informational 2>/dev/null || true", timeout=180)
                if os.path.exists("/tmp/slither_out.json"):
                    try:
                        with open("/tmp/slither_out.json") as f:
                            data = json.load(f)
                        findings = data.get("results", {}).get("detectors", [])
                        log(f"  Slither found {len(findings)} issues in {repo_name}")
                    except Exception as e:
                        log(f"  ERROR parsing slither output: {e}")
                        findings = []
            
            if findings:
                report = generate_report(program, findings, repo_url, target["scope"])
                if report:
                    safe_name = f"{key}-{repo_name}-{datetime.now(timezone.utc).strftime('%Y%m%d')}.md"
                    out_path = os.path.join(OUTPUT_DIR, safe_name)
                    with open(out_path, "w") as f:
                        f.write(report)
                    reports_generated += 1
                    critical_count = len([x for x in findings if x.get("impact") in ["Critical", "High"]])
                    log(f"  ✓ Generated report: {safe_name} ({critical_count} critical/high)")
                    total_findings += len(findings)
            
            time.sleep(1)  # Rate limit between repos
    
    log(f"\n=== Pipeline Complete: {reports_generated} reports, {total_findings} total findings ===")
    
    # Write summary state
    state = {
        "last_run": datetime.now(timezone.utc).isoformat(),
        "reports_generated": reports_generated,
        "total_findings": total_findings,
        "targets_processed": list(TARGETS.keys()),
        "next_action": "manual_review_and_poc_development"
    }
    with open(os.path.join(OUTPUT_DIR, "_pipeline_state.json"), "w") as f:
        json.dump(state, f, indent=2)

if __name__ == "__main__":
    main()
