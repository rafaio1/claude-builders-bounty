# Usual Labs Security Analysis & Bounty Candidates

## Target: Sherlock $16M Bounty Program
**Contracts Analyzed:** USD0, SwapperEngine, ClassicalOracle, DaoCollateral
**Date:** 2026-08-30

---

## 🔴 Critical Vulnerability Candidate #1: Oracle Staleness Bypass via Timeout Misconfiguration

### Location
`ClassicalOracle.sol:78-93` (`_latestRoundData`)

### Description
The oracle staleness check uses a per-token `timeout` value set during `initializeTokenOracle()`. The validation in line 89 checks:
```solidity
if (block.timestamp > $.tokenToOracleInfo[token].timeout + updatedAt) {
    revert OracleNotWorkingNotCurrent();
}
```

However, the `timeout` is an admin-set parameter (max `ONE_WEEK`). If an admin sets an excessively long timeout (e.g., 7 days) for USDC, and Chainlink's USDC/USD feed goes stale for 6 days, the SwapperEngine will continue to accept the stale price. During periods of USDC depeg or market stress, this could allow:
1. Minting USD0 at inflated USDC valuations
2. Arbitrage extraction by providing stale-priced USDC orders

### Exploit Path
1. Monitor Chainlink USDC/USD heartbeat vs configured timeout
2. When feed lags but hasn't exceeded timeout, submit large USDC deposit orders
3. Match against USD0 providers who assume fresh pricing
4. Profit from price discrepancy when feed updates

### Severity Assessment
- **Likelihood:** Medium (requires specific timeout misconfiguration + Chainlink delay)
- **Impact:** High (direct fund extraction from swappers)
- **Bounty Tier:** Medium-High ($50k-$200k estimated)

---

## 🔴 Critical Vulnerability Candidate #2: Rounding Loss Accumulation in Partial Order Matching

### Location
`SwapperEngine.sol:307-340` (`_provideUsd0ReceiveUSDC`)

### Description
When matching partial orders, the USD0 equivalent is calculated per-order using:
```solidity
uint256 usd0Amount = _getUsd0WadEquivalent(amountOfUsdcFromOrder, usdcWadPrice);
```

The conversion involves WAD math (18 decimals) with implicit truncation on division. For each partial match, rounding favors the contract (dust loss). Over thousands of small partial matches, this dust accumulates in the SwapperEngine contract balance rather than being distributed to order requesters or liquidity providers.

More critically: if `_getUsd0WadEquivalent` rounds DOWN consistently, a provider matching many small orders receives less USD0 than the aggregate fair value, while the requester gets full USDC. This creates an exploitable asymmetry.

### Exploit Path
1. Create many small USDC orders (just above `minimumUSDCAmountProvided`)
2. Attacker provides USD0 to match all small orders in single tx
3. Cumulative rounding loss means attacker pays less USD0 than fair value
4. Withdraw matched USDC at full value → profit from accumulated dust

### Severity Assessment
- **Likelihood:** High (no special conditions needed, just gas-efficient batching)
- **Impact:** Medium-Low per tx, High at scale
- **Bounty Tier:** Medium ($25k-$100k estimated)

---

## 🟡 Medium Vulnerability Candidate #3: Reentrancy Window in withdrawUSDC → safeTransfer

### Location
`SwapperEngine.sol:258-279` (`withdrawUSDC`)

### Description
The function follows checks-effects-interactions correctly for state updates (`order.active = false`, `order.tokenAmount = 0` before transfer). However, `$.usdcToken.safeTransfer(msg.sender, amountToWithdraw)` calls out to an external token contract.

If USDC were ever upgraded to support ERC-777-style hooks (or if a malicious wrapper is used as the USDC token in testing/fork environments), the recipient could re-enter other SwapperEngine functions. The `nonReentrant` modifier protects against direct reentrancy, but cross-function reentrancy into `depositUSDC` or `provideUsd0ReceiveUSDC` could potentially manipulate order state if the guard doesn't cover all entry points uniformly.

### Note
This is lower severity because USDC mainnet is plain ERC-20 without hooks. But it's valid for audit completeness and may qualify as informational/low bounty.

### Severity Assessment
- **Likelihood:** Very Low (mainnet USDC has no hooks)
- **Impact:** Medium (theoretical fund manipulation)
- **Bounty Tier:** Informational/Low ($1k-$10k)

---

## Next Steps for Validation

1. **Fork mainnet** and test Candidate #2 with batched small orders — measure actual dust accumulation
2. **Check current ClassicalOracle timeout config** for USDC via on-chain read
3. **Review AbstractOracle base contract** for additional staleness edge cases
4. **Submit highest-confidence finding** to Sherlock within 48h for fastest triage

## Rapid Payout Parallel Track
See `state/rapid_vectors.md` for MEV/arbitrage opportunities using existing Bybit infrastructure.
