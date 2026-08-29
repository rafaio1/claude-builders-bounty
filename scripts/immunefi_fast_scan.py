#!/usr/bin/env python3
"""
Immunefi Fast Scanner - Lightweight grep-based vulnerability scanner.
Skips full git clone; uses GitHub API/raw content for speed.
Targets: Ethena, DeXe, ENS (high-value, public repos).
Zero-capital: no slither dependency, pure regex + curl.
"""

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone

OUTPUT_DIR = "/Agentic/revenue/immunefi_reports"
LOG_PATH = "/Agentic/logs/immunefi_fast_scan.log"

TARGETS = {
"ethena": {
"program": "Ethena",
"max_bounty": 3_000_000,
"files": [
"https://raw.githubusercontent.com/ethena-labs/usde-public/main/contracts/USDe.sol",
"https://raw.githubusercontent.com/ethena-labs/staking-public/main/contracts/Staking.sol",
],
"scope": ["smart contract", "solidity", "oracle"],
},
"dexe": {
"program": "DeXe Protocol",
"max_bounty": 500_000,
"files": [
"https://raw.githubusercontent.com/dexe-network/DeXe-Protocol/master/contracts/gov/GovPool.sol",
"https://raw.githubusercontent.com/dexe-network/gov-pool/main/contracts/GovPool.sol",
],
"scope": ["smart contract", "solidity", "governance"],
},
"ens": {
"program": "ENS",
"max_bounty": 250_000,
"files": [
"https://raw.githubusercontent.com/ensdomains/ens-contracts/master/contracts/registry/ENSRegistry.sol",
"https://raw.githubusercontent.com/ensdomains/name-wrapper/main/contracts/NameWrapper.sol",
],
"scope": ["smart contract", "solidity", "dns"],
},
}

VULN_PATTERNS = [
("reentrancy", r"(?i)(call\{value|\.call\(|external\s+function.*payable)", "High"),
("unchecked-return", r"(?i)(\.transfer\(|\.send\(|require\(.*==\s*false)", "Medium"),
("delegatecall-risk", r"(?i)delegatecall\(", "High"),
("selfdestruct", r"(?i)(selfdestruct|suicide)\(", "Critical"),
("tx-origin-auth", r"(?i)tx\.origin", "High"),
("integer-overflow", r"(?i)(uint\d+\s*\+\s*|\-\s*uint\d+)", "Medium"),
("uninitialized-storage", r"(?i)(storage\s+pointer|uninitialized)", "High"),
("access-control-missing", r"(?i)(function\s+\w+\s*\([^)]*\)\s*(public|external)\s*(?!onlyOwner|onlyAdmin|restricted))", "Medium"),
]

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")

def fetch_raw(url, timeout=15):
    try:
        r = subprocess.run(
            ["curl", "-sL", "--max-time", str(timeout), url],
            capture_output=True, text=True, timeout=timeout+5
        )
        if r.returncode == 0 and len(r.stdout) > 100 and "404" not in r.stdout[:50]:
            return r.stdout
    except Exception as e:
        log(f"  FETCH ERROR {url}: {e}")
    return ""

def scan_content(content, filename):
    findings = []
    lines = content.split("\n")
    for pname, pattern, severity in VULN_PATTERNS:
        matches = list(re.finditer(pattern, content))
        if matches:
            line_num = content[:matches[0].start()].count("\n") + 1
            snippet = lines[line_num-1].strip()[:120] if line_num <= len(lines) else ""
            findings.append({
                "check": pname,
                "severity": severity,
                "file": filename,
                "line": line_num,
                "snippet": snippet,
                "count": len(matches)
            })
    return findings

def generate_report(program, findings, max_bounty, scope):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    critical = [f for f in findings if f["severity"] in ["Critical", "High"]]
    medium = [f for f in findings if f["severity"] == "Medium"]
    if not critical and not medium:
        return None
    report = f"# Vulnerability Report: {program}\n\n"
    report += f"**Date:** {ts}  \n**Program:** {program} (Immunefi Bug Bounty)  \n"
    report += f"**Max Bounty:** ${max_bounty:,}  \n**Scope:** {', '.join(scope)}  \n\n"
    report += "## Executive Summary\n\n"
    report += f"Automated static analysis identified **{len(critical)} high/critical** and **{len(medium)} medium** severity patterns in {program} smart contracts.\n\n"
    report += "## High/Critical Severity Findings\n\n"
    for i, f in enumerate(critical[:8], 1):
        report += f"### {i}. {f['check'].replace('-', ' ').title()} ({f['severity']})\n"
        report += f"- **File:** `{f['file']}` (Line {f['line']})\n"
        report += f"- **Occurrences:** {f['count']}\n"
        report += f"- **Code Snippet:** `{f['snippet']}`\n"
        report += f"- **Recommendation:** Verify exploitability in production context.\n\n"
    if medium:
        report += "## Medium Severity Findings\n\n"
        for i, f in enumerate(medium[:5], 1):
            report += f"- **{f['check']}:** `{f['file']}:{f['line']}` ({f['count']} occurrences)\n"
    report += "\n## Next Steps for Submission\n\n"
    report += "1. Manual Verification against deployed bytecode.\n"
    report += "2. PoC Development demonstrating exploit path.\n"
    report += "3. Impact Calculation based on current TVL.\n"
    report += "4. Submit via https://immunefi.com/submit/\n\n"
    report += f"---\n*Generated by Agentic Immunefi Fast Scanner v1.0 | {ts}*\n"
    return report

def main():
    log("=== Immunefi Fast Scan Start ===")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    total_findings = 0
    reports = 0
    for key, target in TARGETS.items():
        program = target["program"]
        log(f"\n--- Scanning {program} (Max: ${target['max_bounty']:,}) ---")
        all_findings = []
        for url in target["files"]:
            fname = url.split("/")[-1]
            log(f"  Fetching {fname}...")
            content = fetch_raw(url)
            if not content:
                log(f"    SKIP: Could not fetch or empty")
                continue
            findings = scan_content(content, fname)
            if findings:
                log(f"    Found {len(findings)} patterns in {fname}")
                all_findings.extend(findings)
            else:
                log(f"    Clean: No high-risk patterns")
            time.sleep(0.5)
        if all_findings:
            report = generate_report(program, all_findings, target["max_bounty"], target["scope"])
            if report:
                safe_name = f"{key}-fastscan-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}.md"
                out_path = os.path.join(OUTPUT_DIR, safe_name)
                with open(out_path, "w") as f:
                    f.write(report)
                reports += 1
                crit = len([x for x in all_findings if x["severity"] in ["Critical","High"]])
                log(f"  ✓ Report saved: {safe_name} ({crit} high/critical)")
                total_findings += len(all_findings)
        else:
            log(f"  No actionable findings for {program}")
    log(f"\n=== Fast Scan Complete: {reports} reports, {total_findings} total findings ===")
    state = {
        "last_run": datetime.now(timezone.utc).isoformat(),
        "scanner": "fast_grep_v1",
        "reports_generated": reports,
        "total_findings": total_findings,
        "targets": list(TARGETS.keys()),
        "next_action": "manual_review_and_poc"
    }
    with open(os.path.join(OUTPUT_DIR, "_fastscan_state.json"), "w") as f:
        json.dump(state, f, indent=2)

if __name__ == "__main__":
    main()
