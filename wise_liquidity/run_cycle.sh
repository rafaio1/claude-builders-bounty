#!/bin/bash
# Wise Liquidity Main Cycle - Orchestrates monitoring and bridging
set -e
SCRIPT_DIR="/Agentic/wise_liquidity"

echo "=== Wise Liquidity Cycle Start: $(date -u) ==="

# Step 1: Scan for arbitrage and update state
python3 "$SCRIPT_DIR/monitor.py"

# Step 2: Assess bridge needs and allocate if possible
python3 "$SCRIPT_DIR/bridge.py"

echo "=== Wise Liquidity Cycle End: $(date -u) ==="
