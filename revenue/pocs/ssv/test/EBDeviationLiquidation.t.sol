// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";

/**
 * @title SSV EB Deviation Liquidation -> Reactivation Drift Test
 * @notice Validates whether stale vUnits after _executeLiquidation causes
 *         double-counting of deviation on reactivate(), inflating daoTotalEthVUnits
 *         and operatorEthVUnits beyond their true baselines.
 *
 * Vector confirmed by code review:
 *   1. _executeLiquidation subtracts deviation from DAO/operator totals
 *      but DOES NOT clear seb.clusterEB[clusterId].vUnits
 *   2. reactivate() reads the stale vUnits, recomputes clusterDeviation,
 *      and adds it back to DAO/operator totals
 *   3. If no state change occurred between liquidation and reactivation,
 *      the deviation is correctly restored (no drift)
 *   4. DRIFT CONDITION: If validatorCount changes between liquidation and
 *      reactivation (e.g., via removeValidator on inactive cluster), the
 *      baseline changes but stale vUnits remains constant, causing mismatch
 *
 * This test simulates the accounting math directly without full deployment
 * to validate the drift condition rapidly.
 */
contract EBDeviationLiquidationTest is Test {
    uint64 constant BPS_DENOMINATOR = 10000;

    // Simulated storage
    uint64 daoTotalEthVUnits;
    mapping(uint64 => uint64) operatorEthVUnits;
    mapping(bytes32 => uint64) clusterEB_vUnits; // stale vUnits storage

    struct ClusterState {
        uint64 validatorCount;
        bool active;
        uint64 balance;
    }

    function simulateLiquidation(
        bytes32 clusterId,
        uint64 validatorCount,
        uint64[] memory operatorIds
    ) internal {
        uint64 vUnitsCluster = clusterEB_vUnits[clusterId];
        
        if (vUnitsCluster > 0) {
            uint64 baselineVUnits = validatorCount * BPS_DENOMINATOR;
            
            if (vUnitsCluster != baselineVUnits) {
                bool moreThanBaseline = vUnitsCluster > baselineVUnits;
                uint64 deviation = moreThanBaseline 
                    ? vUnitsCluster - baselineVUnits 
                    : baselineVUnits - vUnitsCluster;
                
                if (moreThanBaseline) {
                    daoTotalEthVUnits -= deviation;
                } else {
                    daoTotalEthVUnits += deviation;
                }
                
                for (uint256 i = 0; i < operatorIds.length; i++) {
                    if (moreThanBaseline) {
                        operatorEthVUnits[operatorIds[i]] -= deviation;
                    } else {
                        operatorEthVUnits[operatorIds[i]] += deviation;
                    }
                }
            }
        }
        // BUG: vUnits NOT cleared - this is the vulnerability
        // clusterEB_vUnits[clusterId] = 0; // <-- MISSING IN PROTOCOL
    }

    function simulateReactivation(
        bytes32 clusterId,
        uint64 validatorCount,
        uint64[] memory operatorIds
    ) internal returns (uint64 clusterDeviation) {
        uint64 vUnitsCluster = clusterEB_vUnits[clusterId]; // STALE VALUE
        uint64 baselineVUnits = validatorCount * BPS_DENOMINATOR;
        
        clusterDeviation = vUnitsCluster > baselineVUnits 
            ? vUnitsCluster - baselineVUnits 
            : 0;
        
        // Add deviation back to operators
        for (uint256 i = 0; i < operatorIds.length; i++) {
            operatorEthVUnits[operatorIds[i]] += clusterDeviation;
        }
        
        // Add deviation back to DAO
        if (clusterDeviation > 0) {
            daoTotalEthVUnits += clusterDeviation;
        }
    }

    function test_NoDrift_SameValidatorCount() public {
        // Setup: 4 validators with inflated EB (deviation = 40000)
        bytes32 clusterId = keccak256("cluster1");
        uint64 validatorCount = 4;
        uint64[] memory ops = new uint64[](2);
        ops[0] = 1; ops[1] = 2;
        
        uint64 baseline = validatorCount * BPS_DENOMINATOR; // 40000
        uint64 inflatedVUnits = baseline + 40000; // 80000 (2x inflation)
        
        // Initialize state
        daoTotalEthVUnits = 1000000;
        operatorEthVUnits[1] = 500000;
        operatorEthVUnits[2] = 500000;
        clusterEB_vUnits[clusterId] = inflatedVUnits;
        
        uint64 daoBefore = daoTotalEthVUnits;
        uint64 op1Before = operatorEthVUnits[1];
        
        // Liquidate then reactivate with SAME validator count
        simulateLiquidation(clusterId, validatorCount, ops);
        simulateReactivation(clusterId, validatorCount, ops);
        
        // Assert: No drift when validator count unchanged
        assertEq(daoTotalEthVUnits, daoBefore, "DAO vUnits should restore exactly");
        assertEq(operatorEthVUnits[1], op1Before, "Operator vUnits should restore exactly");
    }

    function test_DRIFT_ValidatorCountChangeAfterLiquidation() public {
        // THE EXPLOIT VECTOR:
        // 1. Cluster has 4 validators with inflated EB
        // 2. Liquidate (deviation subtracted, vUnits NOT cleared)
        // 3. Validator removed while inactive (validatorCount drops to 3)
        // 4. Reactivate: stale vUnits compared against NEW baseline (3 * BPS)
        //    creates LARGER deviation than originally subtracted
        
        bytes32 clusterId = keccak256("cluster_drift");
        uint64 initialValidators = 4;
        uint64 reducedValidators = 3;
        uint64[] memory ops = new uint64[](1);
        ops[0] = 1;
        
        uint64 initialBaseline = initialValidators * BPS_DENOMINATOR; // 40000
        uint64 inflatedVUnits = initialBaseline + 20000; // 60000 (deviation=20000)
        
        // Initialize
        daoTotalEthVUnits = 1000000;
        operatorEthVUnits[1] = 500000;
        clusterEB_vUnits[clusterId] = inflatedVUnits;
        
        // Step 1: Liquidate with 4 validators
        // Deviation = 60000 - 40000 = 20000 subtracted
        simulateLiquidation(clusterId, initialValidators, ops);
        uint64 daoAfterLiq = daoTotalEthVUnits; // Should be 980000
        
        // Step 2: Validator count changes while inactive (simulated)
        // In real protocol: removeValidator on inactive cluster
        // This changes baseline but NOT stale vUnits
        
        // Step 3: Reactivate with 3 validators
        // Stale vUnits = 60000, New baseline = 30000
        // New deviation = 60000 - 30000 = 30000 ADDED BACK
        // But only 20000 was subtracted! Net gain = 10000
        simulateReactivation(clusterId, reducedValidators, ops);
        
        uint64 expectedDaoWithoutDrift = daoAfterLiq + 20000; // 1000000
        uint64 actualDao = daoTotalEthVUnits; // Should be 1010000 if bug exists
        
        // THIS ASSERTION SHOULD FAIL IF THE BUG EXISTS
        // (proving the drift/exploit)
        if (actualDao != expectedDaoWithoutDrift) {
            emit log_named_uint("DRIFT DETECTED - DAO inflation", actualDao - expectedDaoWithoutDrift);
            emit log_named_uint("Original deviation subtracted", 20000);
            emit log_named_uint("Restored deviation with new baseline", 30000);
        }
        
        // For the PoC, we WANT this to show drift
        assertTrue(
            actualDao > expectedDaoWithoutDrift,
            "BUG CONFIRMED: Stale vUnits causes accounting inflation on validator count reduction"
        );
    }

    function test_ReactivationWithZeroVUnits_NoDoubleCount() public {
        // Edge case: what if vUnits was legitimately 0 before liquidation?
        bytes32 clusterId = keccak256("cluster_zero");
        uint64 validatorCount = 2;
        uint64[] memory ops = new uint64[](1);
        ops[0] = 1;
        
        daoTotalEthVUnits = 500000;
        operatorEthVUnits[1] = 250000;
        clusterEB_vUnits[clusterId] = 0; // No EB snapshot yet
        
        uint64 daoBefore = daoTotalEthVUnits;
        
        simulateLiquidation(clusterId, validatorCount, ops);
        simulateReactivation(clusterId, validatorCount, ops);
        
        // With vUnits=0, reactivate uses baseline as effectiveVUnits
        // and clusterDeviation=0, so no double counting
        assertEq(daoTotalEthVUnits, daoBefore, "Zero vUnits should not cause drift");
    }
}
