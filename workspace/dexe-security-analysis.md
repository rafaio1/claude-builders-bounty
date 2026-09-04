# DeXe Protocol Security Analysis — Immunefi Bounty Deliverable

**Date:** 2026-09-05
**Target:** DeXe Protocol (BSC Mainnet)
**Scope:** Smart Contracts — Governance, Voting Power, Rewards, PriceFeed
**Analyst:** Automated Security Research Pipeline

---

## Executive Summary

This report identifies **three concrete vulnerability hypotheses** in the DeXe Protocol governance system, derived from source code analysis of the official GitHub repository (`dexe-network/DeXe-Protocol`). The most critical finding is a **spot-price oracle manipulation vector in `UniswapPathFinder`** that could allow flash-loan-based inflation of voting power or reward valuations. Secondary findings include a **delegation reward double-accounting edge case in `GovPoolMicropool`** and a **polynomial voting power curve boundary condition in `PolynomialPower`**.

---

## Attack Surface Summary

| Component | Contract / Library | Key Risk Area |
|-----------|-------------------|---------------|
| Vote Counting | `GovPoolVote.sol` | Delegated vote aggregation across Personal/Micropool/Treasury types |
| Voting Power Transform | `PolynomialPower.sol` | Polynomial curves with hardcoded coefficients; threshold transitions |
| Token/NFT Custody | `GovUserKeeper.sol` | Lock/unlock lifecycle; delegation balance accounting |
| Reward Distribution | `GovPoolRewards.sol` | Partial payment handling; reentrancy surface via `sendFunds` |
| Micropool Claims | `GovPoolMicropool.sol` | Delegator reward calculation tied to delegation timestamps |
| Oracle Pricing | `PriceFeed.sol` + `UniswapPathFinder.sol` | Spot-price queries against Uniswap V2/V3 without TWAP protection |
| Proposal Execution | `GovPoolExecute.sol` | Arbitrary external calls with value transfer before commission payment |

---

## Vulnerability Hypothesis #1: Flash Loan Oracle Manipulation via Spot Price Queries

### Severity: **Critical** (Potential direct theft / governance manipulation)

### Description

The `PriceFeed` contract uses `UniswapPathFinder` to determine token prices by querying **spot reserves** on Uniswap V2 routers (`getAmountsOut`) and Uniswap V3 quoters (`quoteExactInputSingle`). These are **instantaneous spot price queries**, not time-weighted average prices (TWAP).

In `UniswapPathFinder._calculateSingleSwapV2`, the router's `getAmountsOut` returns the current reserve ratio. An attacker can:

1. Flash-borrow a large amount of the base token
2. Swap into the target token on the same Uniswap V2 pair, severely skewing reserves
3. Call any DeXe governance function that invokes `PriceFeed.getNormalizedPriceOutUSD()` or similar — the manipulated spot price is used for:
   - Calculating voting power thresholds for proposal creation
   - Determining reward token valuations
   - Evaluating quorum requirements denominated in USD-equivalent terms
4. Repay the flash loan within the same transaction

### Affected Code Paths

- `PriceFeed.sol:getNormalizedPriceOutUSD()` → `getNormalizedExtendedPriceOut()` → `getExtendedPriceOut()` → `UniswapPathFinder.getUniswapPathWithPriceOut()`
- `_findBestHop()` iterates all pool types and selects the one returning the best output — this means the attacker only needs to manipulate **one** liquidity pool to control the reported price
- No TWAP, no staleness check, no deviation guard

### Reproduction Approach

```solidity
// Pseudocode PoC
function attack() external {
    // 1. Flash borrow 1M USDC from Aave/Balancer
    uint256 borrowed = flashLoan(USDC, 1_000_000e18);
    
    // 2. Swap USDC → DEXE on the smallest V2 pair to maximize price impact
    uniswapRouter.swapExactTokensForTokens(borrowed, 0, [USDC, DEXE], address(this), deadline);
    
    // 3. Call DeXe governance function that reads DEXE price
    //    e.g., createProposal() which checks minVotesForCreating in USD terms
    govPool.createProposal(manipulatedParams);
    
    // 4. Reverse swap and repay flash loan
    uniswapRouter.swapExactTokensForTokens(dexeBalance, 0, [DEXE, USDC], address(this), deadline);
    repayFlashLoan(borrowed);
}
```

### Impact Assessment

- **Governance manipulation:** Attacker can artificially inflate/deflate token prices to bypass proposal creation thresholds or manipulate reward calculations
- **Reward extraction:** If rewards are denominated in a token priced via this oracle, inflated prices yield excess rewards
- **Prerequisite:** Sufficient flash-loan capital and a low-liquidity pair in the path tokens set
- **Mitigation gap:** The `_verifyProvidedPath` function allows custom paths, expanding the attack surface to any user-specified routing

### Confidence: **High** — Spot price usage without TWAP is a well-documented anti-pattern. The absence of any oracle staleness or deviation check in the reviewed code confirms exposure.

---

## Vulnerability Hypothesis #2: Delegator Reward Double-Accounting via Timestamp Collision in GovPoolMicropool

### Severity: **Medium** (Potential reward overpayment)

### Description

In `GovPoolMicropool.saveDelegationInfo()`, delegation power snapshots are stored with `block.timestamp` as the key:

```solidity
if (length > 0 && delegationTimes[length - 1] == block.timestamp) {
    delegationTimes.pop();
    delegationPowers.pop();
}
delegationTimes.push(block.timestamp);
delegationPowers.push(getDelegatedAssetsPower(msg.sender, delegatee));
```

The deduplication only checks if the **last** entry matches the current timestamp. However, in `_getExpectedRewards()`, the lookup uses `lowerBound(quorumReachedTime)` to find the applicable delegation power:

```solidity
uint256 index = timestamps.lowerBound(quorumReachedTime);
if (index == 0) return 0;
if (index == timestamps.length || timestamps[index] != quorumReachedTime) --index;
```

**Edge case:** If a delegator performs multiple delegation changes across different blocks but the quorum timestamp falls between two snapshots where the `lowerBound` resolution picks a stale higher-power snapshot, the reward calculation uses an outdated (potentially higher) delegation power value. Combined with the fact that `partiallyClaimed` tracking resets on full claim failure (`isClaimed` set back to false), there exists a narrow window where:

1. Delegator has high power at time T1
2. Delegator reduces delegation at T2
3. Quorum reached at T3 where T1 < T3 < T2 (due to block ordering or early completion)
4. `lowerBound(T3)` resolves to T1's power (higher than actual at T3)
5. Reward calculated on inflated power

### Reproduction Approach

1. Delegate significant tokens to a delegatee at block N
2. Create/vote on a proposal that will reach quorum quickly (early completion enabled)
3. Undelegate partial tokens at block N+1
4. Ensure quorum triggers at a timestamp that `lowerBound` maps to block N's snapshot
5. Claim micropool rewards — calculated against the higher pre-undelegation power

### Impact Assessment

- **Overpayment magnitude:** Proportional to the delegation delta and the number of affected proposals
- **Requires:** Early completion setting enabled + precise timing coordination
- **Self-limiting:** Each overclaim reduces the remaining reward pool, but does not prevent initial exploitation
- **Data integrity:** `partiallyClaimed` accounting may compound errors across retry claims

### Confidence: **Medium** — Requires specific timing conditions. The `lowerBound` binary search behavior needs formal verification against the exact EnumerableSet implementation used.

---

## Vulnerability Hypothesis #3: Polynomial Voting Power Curve Boundary Discontinuity

### Severity: **Low-Medium** (Governance fairness / potential threshold gaming)

### Description

`PolynomialPower.sol` applies different polynomial formulas based on whether a voter's stake crosses hardcoded thresholds:

- **Holders:** Linear below `HOLDER_THRESHOLD` (7% of supply), polynomial above
- **Experts:** Different polynomials below/above `EXPERT_THRESHOLD` (6.63% of supply)

At the threshold boundary, the transition between linear and polynomial regimes may produce a **discontinuity** or **non-monotonic region** where marginally increasing stake *decreases* effective voting power, or vice versa.

The holder polynomial coefficients are:
- `HOLDER_A = 1041 * 10^22`
- `HOLDER_B = -7211 * 10^19`  
- `HOLDER_C = 1994 * 10^17`

Evaluated at the threshold input `(100 * 7 * PRECISION / totalSupply) - 7 * PRECISION = 0`, the polynomial yields `freeCoefficient = 0`, meaning the transition point should be continuous. However, the **expert** curve uses separate `EXPERT_BEFORE_THRESHOLD_*` coefficients evaluated at raw percentage inputs vs. offset inputs post-threshold, creating a potential mismatch at exactly `663/100 * PRECISION`.

### Exploitation Vector

An attacker holding tokens near the expert threshold could:
1. Calculate the exact voting power at `threshold - ε` and `threshold + ε`
2. If non-monotonic, strategically deposit/withdraw tiny amounts to maximize power-per-token efficiency
3. In governance scenarios where expert status grants multiplicative bonuses, this amplifies the effect

### Impact Assessment

- **Limited direct financial impact** — affects voting weight distribution, not fund custody
- **Governance fairness concern** — violates the principle that more stake should never yield less influence
- **Exploitability depends on** coefficient values producing measurable discontinuity (requires numerical evaluation)

### Confidence: **Low-Medium** — Requires numerical analysis of the polynomial at boundary points. The `assert(polynomial >= 0)` guards prevent negative outputs but do not guarantee monotonicity.

---

## Recommendations

1. **Oracle (Critical):** Replace spot price queries with TWAP oracles (Uniswap V3 TWAP, Chainlink, or Pyth). Add staleness checks and deviation guards. Never use user-supplied custom paths for governance-critical pricing.
2. **Micropool Rewards (Medium):** Use proposal creation timestamp or voting start timestamp as the delegation snapshot reference instead of relying on `lowerBound` against quorum time. Consider merkle-tree-based reward proofs to eliminate on-chain accounting complexity.
3. **Voting Power Curves (Low):** Publish formal verification of monotonicity for both polynomial regimes. Add fuzz tests covering threshold ±ε regions.

---

## Scope Compliance Note

All findings relate to in-scope BSC mainnet contracts per the Immunefi program page. No test files, mock contracts, or social engineering vectors were included. Oracle manipulation via flash loans is explicitly in-scope per the bounty rules ("oracle manipulation/flash loans" listed as eligible, distinct from excluded "incorrect third-party oracle data").

---

## Sources

- [DeXe Protocol Bug Bounties — Immunefi](https://immunefi.com/bug-bounty/dexeprotocol/information/)
- [DeXe Protocol Bug Bounties — Scope](https://immunefi.com/bug-bounty/dexeprotocol/scope/)
- [DeXe Protocol GitHub Repository](https://github.com/dexe-network/DeXe-Protocol)
- [Dexe Network Audits by Hacken](https://hacken.io/audits/dexe-network/)
- [DeXe Protocol Smart Contracts — HackenProof](https://hackenproof.com/programs/dexe-protocol-smart-contracts)