# DeXe Protocol — Security Research & Attack Surface Analysis

**Date**: 2026-09-04  
**Target**: DeXe Protocol (Immunefi Bug Bounty)  
**Type**: Discovery / Pre-PoC Analysis  
**Max Payout**: $500,000 USDC  

---

## Executive Summary

DeXe Protocol is a decentralized DAO governance platform enabling token-weighted voting, delegation, and reward distribution. This analysis identifies three high-priority attack surfaces warranting local-fork PoC development. No mainnet testing was performed per program rules. All findings are theoretical and require reproduction on a local fork before submission.

---

## Attack Surface 1: Delegate Vote Weight Manipulation via Re-delegation Race

### Vulnerability Class
Governance Logic / State Machine Race Condition

### Description
DeXe's delegation model allows token holders to delegate voting power to representatives. If the delegation contract does not atomically update both the delegator's withdrawn weight and the new delegate's accumulated weight within the same transaction boundary, a malicious actor can:

1. Delegate to Delegate A
2. In the same block (via flashbot bundle or MEV), re-delegate to Delegate B before Delegate A's weight is decremented
3. Result: Both delegates temporarily hold inflated voting power equal to the delegator's balance

### Impact
- **Severity**: Critical (if exploitable during active proposal voting window)
- **Funds at Risk**: Governance treasury decisions, protocol parameter changes, grant approvals
- **Payout Estimate**: $50,000–$500,000 depending on treasury size under governance control

### PoC Requirements
- Fork Ethereum mainnet at latest block
- Deploy attacker contract that calls `delegate()` twice in single transaction via multicall or custom contract
- Assert that `getVotingPower(delegateA)` + `getVotingPower(delegateB)` > total supply during race window
- Demonstrate passing a proposal that would fail under correct accounting

### Key Contracts to Audit
- `DeXeGovernance.sol` or equivalent delegation registry
- `VoteWeightCalculator.sol` or inline weight accumulation logic
- Check for `nonReentrant` modifiers on delegation functions
- Verify whether weight snapshots are taken at block start vs. transaction execution time

---

## Attack Surface 2: Reward Distribution Rounding Exploit in Merkle Claims

### Vulnerability Class
Arithmetic / Precision Loss Accumulation

### Description
If DeXe distributes rewards via Merkle trees with per-user claim amounts calculated off-chain using integer division, systematic rounding-down across thousands of recipients can leave residual tokens unclaimed in the distributor contract. An attacker who controls or influences the off-chain calculation (e.g., via manipulated staking duration inputs) could:

1. Inflate their own claim amount by ensuring favorable rounding direction
2. Drain residual dust from prior epochs if cleanup function lacks access control
3. Compound over multiple distribution cycles

### Impact
- **Severity**: High (theft of yield/royalties per bounty table)
- **Funds at Risk**: Accumulated reward pool residuals; potentially 0.1–2% of total distributed rewards per epoch
- **Payout Estimate**: $5,000–$10,000

### PoC Requirements
- Obtain historical Merkle roots and leaf data from DeXe subgraph or IPFS
- Replicate off-chain calculation script; identify rounding direction
- Write test showing cumulative loss exceeds 1% over 10 epochs with realistic user distribution
- Demonstrate extraction mechanism (direct claim or permissionless sweep)

### Key Contracts to Audit
- `RewardDistributor.sol` or `MerkleClaimer.sol`
- Off-chain scripts in DeXe GitHub repos (look for `Math.floor`, integer division without remainder handling)
- Check if `unclaimedRewards` variable is ever reset or transferred without authorization

---

## Attack Surface 3: Proposal Execution After Cancellation via Timelock Bypass

### Vulnerability Class
Access Control / State Transition Validation

### Description
DAO governance systems often implement timelocks between proposal passage and execution. If DeXe allows proposal cancellation but does not invalidate already-queued timelock transactions, an attacker could:

1. Pass a malicious proposal with minimal quorum during low-activity period
2. Queue it in the timelock
3. Have allies cancel the proposal publicly (creating false sense of security)
4. Execute the queued transaction after timelock expires, since cancellation only updated proposal state, not timelock queue

### Impact
- **Severity**: Critical (unauthorized fund movement or parameter change)
- **Funds at Risk**: Entire treasury controlled by timelock executor
- **Payout Estimate**: $100,000–$500,000

### PoC Requirements
- Identify timelock contract address and its relationship to governance module
- Submit test proposal on fork; pass with minimum votes
- Call `cancelProposal()` and verify timelock queue entry persists
- Advance fork timestamp past delay; call `executeTransaction()` successfully
- Document exact function signatures and state variables involved

### Key Contracts to Audit
- `TimelockController.sol` (may be OpenZeppelin fork)
- `Governor.sol` cancellation logic — check if it calls `timelock.cancel()` or only updates internal mapping
- Event logs for `ProposalCanceled` vs. `TransactionCancelled` — absence of latter is red flag

---

## Recommended Next Steps

1. **Clone DeXe Protocol repositories** from official GitHub (`dexe-network/DeXe-Protocol` or similar)
2. **Set up Foundry/Hardhat fork environment** pinned to current mainnet block
3. **Prioritize Attack Surface 3** — timelock bypasses are historically common in DAO upgrades and have highest critical-severity conversion rate
4. **Validate contract addresses** via Etherscan verified source or DeXe docs before auditing; Immunefi uses Primacy of Impact so correct target identification is researcher responsibility
5. **Document all findings with line-number references** and gas-optimized PoC scripts

---

## Compliance Notes

- ✅ No mainnet or public testnet interaction performed
- ✅ Analysis based solely on architectural patterns common to DAO governance systems and DeXe's documented functionality
- ✅ All PoC paths specify local fork execution only
- ✅ Canonical ledgers and financial files untouched
- ✅ KYC and human submission acknowledged as mandatory next steps post-PoC

---

## References

- Immunefi Program: https://immunefi.com/bug-bounty/dexeprotocol/information/
- DeXe Docs: https://docs.dexe.network/
- OpenZeppelin Governor/Timelock Docs (for pattern comparison): https://docs.openzeppelin.com/contracts/5.x/governance