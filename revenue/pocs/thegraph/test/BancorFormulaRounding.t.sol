// SPDX-License-Identifier: MIT
pragma solidity ^0.7.6;
pragma abicoder v2;

import "forge-std/Test.sol";
import "src/bancor/BancorFormula.sol";

contract BancorFormulaRoundingTest is Test {
    BancorFormula public formula;

    function setUp() public {
        formula = new BancorFormula();
    }

    // Vector: Check for rounding errors in calculatePurchaseReturn
    // when reserve balance is small relative to supply, or vice versa.
    // Specifically looking for cases where returned amount > expected due to integer division truncation favoring the caller.
    function testPurchaseReturnRoundingEdge() public {
        uint256 supply = 1e18;
        uint256 reserveBalance = 1e18;
        uint32 reserveWeight = 500000; // 50%
        uint256 depositAmount = 1 wei;

        uint256 returnAmount = formula.calculatePurchaseReturn(
            supply,
            reserveBalance,
            reserveWeight,
            depositAmount
        );
        
        // In a fair system, returnAmount should be proportional.
        // With 50% weight, deposit of 1 wei into 1e18 pool should yield ~1 wei.
        // If returnAmount > depositAmount (adjusted for weight), it's a potential exploit.
        assertLe(returnAmount, depositAmount, "Return exceeds deposit in minimal case");
    }

    // Vector: Large deposit vs small reserve
    function testLargeDepositSmallReserve() public {
        uint256 supply = 1e24;
        uint256 reserveBalance = 1e18;
        uint32 reserveWeight = 500000;
        uint256 depositAmount = 1e20;

        uint256 returnAmount = formula.calculatePurchaseReturn(
            supply,
            reserveBalance,
            reserveWeight,
            depositAmount
        );
        
        // Sanity check: ensure no overflow/revert and result is non-zero
        assertGt(returnAmount, 0);
    }
}
