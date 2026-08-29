# The Graph Staking Audit Notes

## Target: LibFixedMath & Exponential Rebates
**Status**: Deep Dive Complete - No Critical Exploit Found
**Verdict**: Low probability of high-severity bug. Math is battle-tested (derived from Bprotocol/0x). Precision loss exists but is bounded and accounted for.

## Key Findings

### 1. LibFixedMath.sol (127-bit signed fixed point)
- **Overflow Checks**: `_mul` uses `c/a != b` which is safe for int256 except MIN_FIXED_VAL edge cases, but those are explicitly handled in `abs()` and `sub()`.
- **Ln/Exp Bounds**: Strictly clamped. `ln` reverts on x <= 0 or x > 1. `exp` saturates to 0 below EXP_MIN_VAL (-63.875) and reverts above 0. This prevents unbounded exponentiation attacks.
- **Precision**: Taylor series for ln/exp use sufficient terms for 127-bit precision within the operational range. No obvious truncation vulnerabilities that could be exploited for profit.

### 2. Exponential Rebates Formula
Formula: `(1 - alpha * exp(-lambda * stake / fees)) * fees`
- **Clamping**: If `exponent > MAX_EXPONENT (15)`, returns full `fees`. Safe upper bound.
- **Alpha Zero Check**: Handled correctly (returns full fees).
- **Fees Zero Check**: Handled correctly (returns 0).
- **Type Safety**: Uses `int256` for intermediate math, converts back to `uint256` via `uintMul` which clamps negatives to 0. Prevents negative rebate exploits.

### 3. Staking.sol collect() Logic
- **Monotonic Accumulation**: `alloc.collectedFees` only increases. `newRebates` is recalculated on total accumulated fees each time.
- **Diff Protection**: `MathUtils.diffOrZero(newRebates, alloc.distributedRebates)` ensures indexers can never claim more than the delta. Even if parameters change mid-allocation, over-rebating is impossible.
- **Cap Protection**: `MathUtils.min(queryRebates, queryFees)` ensures rebates never exceed current batch fees. Prevents draining pool via stale state.
- **Tax/Curation First**: Protocol tax and curation fees are deducted BEFORE rebate calculation. Base for rebate is strictly net fees.

## Potential (Low Severity) Vectors
1. **Rounding Dust**: Repeated small collections might leave wei-level dust due to integer division in `uintMul`. Not exploitable for profit, just gas inefficiency.
2. **Parameter Change Arbitrage**: If governance changes alpha/lambda between collect() calls, indexers might get slightly less or more than intended. Mitigated by diffOrZero/min caps. Not a theft vector.
3. **Exponent Saturation**: At extreme stake/fee ratios, rebate saturates to 100%. Intended behavior per MAX_EXPONENT check.

## Recommendation
**PIVOT AWAY**. This codebase is mature, audited multiple times, and uses well-established math libraries. Finding a critical bug here requires novel mathematical insight beyond standard static analysis. ROI on further audit time is low compared to newer/smaller protocols.

## Next Actions
1. Commit these notes to master.
2. Pivot to next Immunefi target with higher surface area (newer L2 bridges, restaking protocols, or fresh DeFi launches).
3. Monitor existing GitHub bounty PRs for merge/payment.
