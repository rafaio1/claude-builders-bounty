# V23d-v5 Risk Filters Documentation

## Hourly Risk Filter (Based on Historical Ledger Analysis)

High-risk hours identified: [6, 11, 20, 21, 23] UTC

These hours accounted for disproportionate losses in historical data.
When V23d-v5 is unblocked for paper/live trading:
- Reduce position size by 50% during these hours, OR
- Skip entry signals entirely during these hours

## Statistical Unblock Criteria

1. Minimum 30 paper trades with V23d-v5
2. Net expectancy > 0.08% per trade after fees
3. Max drawdown < 5% of bankroll (~0.49 USDT)
4. Walk-forward validation on out-of-sample data
5. Failure/restart/reconciliation tests passed
6. Deterministic loss limits per trade/day/strategy
7. Explicit human approval before any LIVE operation

## Code Compliance

- Auto-promotion gate REMOVED from sniper_v23d_xrp.py
- is_live variable REMOVED (manual approval only)
- Zero tmux sessions active when blocked
- State/ledger integrity verified
