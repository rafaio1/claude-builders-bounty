#!/bin/bash
cd /Agentic/orchestrator
pkill -9 -f subagent_trailing_unified 2>/dev/null
sleep 2
nohup python3 -u subagent_trailing_unified.py bybit > bybit_spot.log 2>&1 &
echo "BYBIT_PID=$!"
nohup python3 -u subagent_trailing_unified.py binance > binance_spot.log 2>&1 &
echo "BINANCE_PID=$!"
