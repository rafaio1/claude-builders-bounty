# DeXe Protocol: Meta-Governance Quorum Manipulation via Treasury Exemption

## Severity: High
## Protocol: DeXe Protocol
## Contract: GovPoolCreate.sol (libs/gov/gov-pool/)
## Max Bounty: $3,000,000 (Immunefi)

## Summary
The `_exemptUserTreasuryFromVoting` function in `GovPoolCreate.sol` dynamically reduces the quorum requirement when a proposal includes actions that delegate/undelegate treasury voting power or burn expert NFTs. The new quorum is calculated as:
```solidity
newTotalVoteWeight = (totalVoteWeight - exemptedTreasury).percentage(quorum);
return PERCENTAGE_100.ratio(newTotalVoteWeight, totalVoteWeight);
```
This calculation may allow an attacker to craft a meta-governance proposal that intentionally exempts a large portion of treasury voting power, artificially lowering the quorum threshold for the *current* proposal and potentially enabling passage with significantly fewer votes than intended.

## Vulnerability Details

### 1. Quorum Reduction Logic
When `actionsOnFor` contains `delegateTreasury`, `undelegateTreasury`, or expert NFT burns, the affected user's treasury voting power is subtracted from the total before computing the required quorum. This is intended to prevent proposals from failing due to self-referential voting power changes.

### 2. Attack Vector
An attacker could:
1. Acquire or control accounts with significant treasury voting power
2. Create a meta-governance proposal where `actionsOnFor` delegates/undelegates their own treasury power
3. The exemption removes their voting power from the denominator, lowering the absolute number of votes needed for quorum
4. Simultaneously vote FOR the proposal with non-treasury power (personal/delegated votes)
5. The proposal passes with less total support than the original quorum intended

### 3. Meta-Governance Amplification
Since this is meta-governance (voting on another pool's proposal), the impact cascades:
- Lower quorum in child pool → easier to pass malicious proposals
- Attacker controls both the quorum reduction AND the vote execution
- The `_validateMetaGovernance` check ensures parity between `actionsOnFor` and `actionsAgainst`, but does NOT validate whether the exemption itself is being weaponized

### 4. Missing Safeguards
- No minimum quorum floor after exemption
- No check preventing self-exemption from benefiting the proposer
- No time-lock or delay between exemption and vote execution

## Proof of Concept Outline
1. Attacker accumulates 40% of total treasury voting power across multiple accounts
2. Creates meta-gov proposal with `delegateTreasury(attacker)` in `actionsOnFor`
3. Quorum drops from e.g., 30% to 18% (60% remaining * 30%)
4. Attacker votes FOR with 20% personal power → exceeds new 18% quorum
5. Proposal executes: treasury delegated + underlying action passes
6. Result: Attacker-controlled proposal passes with only 20% actual support vs original 30% requirement

## Impact
- Governance takeover via artificial quorum suppression
- Unauthorized protocol parameter changes, fund drains, or upgrades
- Severity scales with treasury concentration and meta-gov frequency

## Recommended Fix
1. Add minimum quorum floor (e.g., 50% of original quorum) post-exemption
2. Exclude proposer's treasury power from exemption calculations
3. Require separate governance approval for quorum-modifying proposals
4. Implement time-delay between exemption action and vote finalization

## Status: DRAFT - REQUIRES TESTNET VALIDATION
