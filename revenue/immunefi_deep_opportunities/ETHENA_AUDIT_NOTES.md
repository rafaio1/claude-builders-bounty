# Ethena Protocol Audit Notes (Preliminary)

## Target Info
- **Program**: Ethena Labs (Immunefi)
- **Max Bounty**: $3,000,000 (Critical Smart Contract)
- **Scope**: `EthenaMinting.sol`, `StakedUSDeV2.sol`, `USDeSilo.sol`, `USDe.sol`
- **Repo**: `ethena-labs/bbp-public-assets` (Archived/Frozen for audit)

## Static Analysis Results (Slither)
- **High/Medium Issues**: 0 detected by Slither (excluding informational).
- **Informational/Low**: Timestamp dependencies in vesting/cooldown logic (expected).
- **Note**: Absence of Slither findings suggests either high maturity or need for manual logic review.

## Manual Code Review Findings

### 1. StakedUSDeV2 Cooldown Logic
- `cooldownAssets` / `cooldownShares`: Moves assets to `USDeSilo` and sets `cooldownEnd`.
- `unstake`: Only executable if `block.timestamp >= cooldownEnd` OR `cooldownDuration == 0`.
- **Risk Area**: If admin sets `cooldownDuration = 0` while users are in active cooldown, `unstake` becomes immediately callable. This is documented behavior ("breaks ERC4626 standard"), but worth verifying if any state inconsistency arises during the transition window.
- **Verdict**: Likely intended design, but edge case during governance transition.

### 2. EthenaMinting Route Validation
- `verifyRoute`: Ensures sum of ratios == 10,000 and all addresses are whitelisted custodians.
- `_transferCollateral`: Uses integer division `(amount * ratios[i]) / ROUTE_REQUIRED_RATIO`. Remainder sent to last address.
- **Risk Area**: Rounding errors in collateral distribution. If `amount * ratios[i]` overflows uint256? Unlikely with realistic values, but theoretically possible with maliciously crafted orders if not capped.
- **Mitigation**: `belowMaxMintPerBlock` modifier limits per-block volume.

### 3. Vesting Accounting (StakedUSDe)
- `totalAssets() = balance - getUnvestedAmount()`
- `getUnvestedAmount()`: Linear vesting over 8 hours.
- **Risk Area**: Flash loan attack to manipulate share price right before/after vesting update? 
- **Mitigation**: `_checkMinShares()` prevents donation attacks. Vesting is time-based, not block-based.

### 4. Signature Replay / Nonce
- Bitmap nonce system (`_orderBitmaps`). Efficient but standard.
- `verifyOrder`: Checks expiry, signer, and delegated signer status.
- **Risk Area**: Delegated signer revocation race condition? If user revokes delegation after order signed but before execution, order still valid until expiry. Standard off-chain signature limitation.

## Next Steps
1. **PoC Construction**: Attempt to write a Foundry test demonstrating rounding error accumulation in `_transferCollateral` with extreme ratio distributions.
2. **Governance Transition Test**: Simulate `setCooldownDuration(0)` during active cooldown period to verify no fund locking.
3. **Decision**: If no critical PoC within 2 hours, pivot to **The Graph** ($50k max, higher hit rate) as per priority matrix.

## Status
🟡 **IN PROGRESS** - No critical vulnerability confirmed yet. Low-hanging fruit exhausted.
