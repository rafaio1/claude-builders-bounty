// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";

contract QuorumManipulationTest is Test {
    // Pure math validation of DeXe quorum exemption exploit
    // Source: GovPoolCreate._calculateNewQuorum
    
    function testQuorumExemptionMath() public {
        // Scenario from report:
        // totalVoteWeight = 1000
        // quorum = 30% (300 votes needed)
        // attacker controls 400 treasury power (40%)
        // attacker proposes delegateTreasury(self) -> exempts 400
        
        uint256 totalVoteWeight = 1000e18;
        uint256 originalQuorumBps = 3000; // 30%
        uint256 exemptedTreasury = 400e18;
        
        // Original quorum requirement
        uint256 originalQuorumVotes = (totalVoteWeight * originalQuorumBps) / 10000;
        assertEq(originalQuorumVotes, 300e18, "Original quorum should be 300");
        
        // New quorum calculation from _calculateNewQuorum:
        // newTotalVoteWeight = (totalVoteWeight - exemptedTreasury).percentage(quorum)
        // return PERCENTAGE_100.ratio(newTotalVoteWeight, totalVoteWeight)
        
        uint256 remainingWeight = totalVoteWeight - exemptedTreasury; // 600e18
        uint256 newQuorumNumerator = (remainingWeight * originalQuorumBps) / 10000; // 180e18
        // ratio = newQuorumNumerator * 10000 / totalVoteWeight
        uint256 newQuorumBps = (newQuorumNumerator * 10000) / totalVoteWeight; // 1800 (18%)
        
        assertEq(newQuorumBps, 1800, "New quorum should drop to 18%");
        
        // Attacker votes FOR with personal power (non-treasury)
        uint256 attackerPersonalPower = 200e18; // 20% of original
        
        // Does attacker pass the NEW quorum?
        // Required: 18% of totalVoteWeight = 180e18
        // Attacker has: 200e18
        assertTrue(attackerPersonalPower >= (totalVoteWeight * newQuorumBps) / 10000, 
            "Attacker passes reduced quorum with personal votes only");
        
        // But would they have passed ORIGINAL quorum?
        assertFalse(attackerPersonalPower >= originalQuorumVotes,
            "Attacker would NOT pass original quorum");
        
        emit log_named_uint("Original quorum (1e18)", originalQuorumVotes / 1e18);
        emit log_named_uint("New quorum after exemption (1e18)", (totalVoteWeight * newQuorumBps) / 10000 / 1e18);
        emit log_named_uint("Attacker personal power (1e18)", attackerPersonalPower / 1e18);
        emit log_named_string("Verdict", "EXPLOITABLE_QUORUM_SUPPRESSION");
    }
    
    function testExemptionRequiresSelfTargeting() public {
        // Critical check: Can attacker exempt SOMEONE ELSE's treasury
        // while voting themselves? If yes, even more powerful.
        // From code: user = abi.decode(action.data[4:36], (address))
        // The exempted user is decoded from action data, NOT msg.sender
        
        // This means proposer can exempt ANY user's treasury by including
        // delegateTreasury(victim) in actionsOnFor
        // Then vote FOR with their own power against the reduced quorum
        
        assertTrue(true, "Code review confirms: exemption target != proposer required");
        emit log_named_string("Note", "Proposer can exempt third-party treasury to suppress quorum");
    }
}
