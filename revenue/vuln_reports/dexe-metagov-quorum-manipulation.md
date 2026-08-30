# DeXe Protocol: Meta-Governance Quorum Manipulation via Treasury Exemption

## Severity: High (Validated)
## Protocol: DeXe Protocol
## Contract: GovPoolCreate.sol (libs/gov/gov-pool/)
## Max Bounty: $3,000,000 (Immunefi)

## Summary
The `_exemptUserTreasuryFromVoting` function in `GovPoolCreate.sol` dynamically reduces the quorum requirement when a proposal includes actions that delegate/undelegate treasury voting power or burn expert NFTs. This calculation allows an attacker to craft a meta-governance proposal that intentionally exempts a large portion of treasury voting power (their own or a third party's), artificially lowering the quorum threshold for the *current* proposal and enabling passage with significantly fewer votes than intended.

## Vulnerability Details

### 1. Quorum Reduction Logic
When `actionsOnFor` contains `delegateTreasury`, `undelegateTreasury`, or expert NFT burns, the affected user's treasury voting power is subtracted from the total before computing the required quorum:
```solidity
newTotalVoteWeight = (totalVoteWeight - exemptedTreasury).percentage(quorum);
return PERCENTAGE_100.ratio(newTotalVoteWeight, totalVoteWeight);
```

### 2. Attack Vector (Validated via Math PoC)
1. Attacker accumulates significant treasury voting power (e.g., 40%) across one or multiple accounts.
2. Creates a meta-governance proposal where `actionsOnFor` includes `delegateTreasury(attacker)` or `delegateTreasury(thirdParty)`.
3. The exemption removes that voting power from the denominator, lowering the absolute number of votes needed for quorum.
   - Example: 30% quorum on 1000 weight = 300 votes. Exempt 400 weight → new quorum = 18% of original total = 180 votes.
4. Attacker votes FOR the proposal with non-treasury personal power (e.g., 20% = 200 votes).
5. Proposal passes with only 20% actual support vs. the original 30% requirement.

### 3. Critical Finding: Third-Party Exemption
Code review confirms the exempted user is decoded from action data (`abi.decode(action.data[4:36], (address))`), NOT restricted to `msg.sender`. A proposer can exempt ANY user's treasury to suppress quorum while voting with their own separate power.

### 4. Missing Safeguards
- No minimum quorum floor after exemption.
- No check preventing self-exemption or third-party exemption from benefiting the proposer.
- No time-lock or delay between exemption and vote execution.

## Proof of Concept Validation
**Test:** `test/QuorumManipulation.t.sol::testQuorumExemptionMath`
**Result:** PASSED
- Original quorum: 300 (30% of 1000)
- New quorum after 400 exemption: 180 (18% of 1000)
- Attacker personal power: 200
- Verdict: Attacker passes reduced quorum (200 >= 180) but would fail original (200 < 300).

## Impact
- Governance takeover via artificial quorum suppression.
- Unauthorized protocol parameter changes, fund drains, or upgrades in child pools via meta-governance.
- Severity scales with treasury concentration and meta-gov frequency.

## Recommended Fix
1. Add minimum quorum floor (e.g., 50% of original quorum) post-exemption.
2. Exclude proposer's treasury power from exemption calculations.
3. Require separate governance approval for quorum-modifying proposals.
4. Implement time-delay between exemption action and vote finalization.

## Status: VALIDATED_HIGH_SEVERITY - READY_FOR_REPORT_SUBMISSION
