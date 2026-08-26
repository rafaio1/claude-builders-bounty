#!/bin/bash
# Revenue Suite Cron - Runs all autonomous revenue scripts in sequence
# Designed for crontab: */15 * * * * /Agentic/scripts/cron_revenue_suite.sh >> /Agentic/logs/cron_revenue.log 2>&1

set -euo pipefail
LOG="/Agentic/logs/cron_revenue.log"
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "[$TS] === CRON REVENUE SUITE START ===" >> "$LOG"

# Step 1: OpenBugBounty monitor
echo "[$TS] Running OpenBugBounty monitor..." >> "$LOG"
python3 /Agentic/scripts/openbugbounty_register.py >> "$LOG" 2>&1 || echo "[$TS] WARN: openbugbounty failed" >> "$LOG"

# Step 2: DeFi bounty scanner
echo "[$TS] Running DeFi bounty scanner..." >> "$LOG"
python3 /Agentic/scripts/defi_bounty_scanner.py >> "$LOG" 2>&1 || echo "[$TS] WARN: defi_scanner failed" >> "$LOG"

# Step 3: Vuln report pipeline
echo "[$TS] Running vuln report pipeline..." >> "$LOG"
python3 /Agentic/scripts/vul_report_autonomous.py >> "$LOG" 2>&1 || echo "[$TS] WARN: vuln_pipeline failed" >> "$LOG"

# Step 4: Revenue orchestrator (aggregates all)
echo "[$TS] Running revenue orchestrator..." >> "$LOG"
python3 /Agentic/scripts/revenue_orchestrator.py >> "$LOG" 2>&1 || echo "[$TS] WARN: orchestrator failed" >> "$LOG"

echo "[$TS] === CRON REVENUE SUITE COMPLETE ===" >> "$LOG"
