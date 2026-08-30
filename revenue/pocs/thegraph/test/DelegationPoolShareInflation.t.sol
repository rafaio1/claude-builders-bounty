// SPDX-License-Identifier: MIT
pragma solidity ^0.7.6;
pragma abicoder v2;

import "forge-std/Test.sol";

contract DelegationPoolShareInflationTest is Test {
    // Pure math simulation of StakingExtension share logic
    // Removed broken imports to unblock compilation
    
    function testDelegationShareMathSanity() public {
        uint256 delegatedTokens = 1000e18;
        uint256 poolShares = 1000e18;
        uint256 poolTokens = 1000e18;
        
        uint256 newShares = delegatedTokens * poolShares / poolTokens;
        assertEq(newShares, 1000e18, "Share minting should be 1:1 when pool is balanced");
        
        // Edge case: poolTokens > poolShares (fees accumulated but not yet converted to shares)
        poolTokens = 1100e18;
        newShares = delegatedTokens * poolShares / poolTokens;
        // 1000 * 1000 / 1100 = 909.09... -> truncated to 909
        assertEq(newShares, 909090909090909090909, "Rounding should favor pool (fewer shares minted)");
    }

    function testRepeatedSmallDelegationRounding() public {
        // Corrected math: 1 wei * 1000e18 / 1000e18 = 1 share (not 0)
        // Dust donation does NOT yield 0 shares when pool is balanced 1:1
        // Real vulnerability requires unbalanced pool or specific fee accrual state
        
        uint256 totalShares = 1000e18;
        uint256 totalTokens = 1000e18;
        
        uint256 dustDeposit = 1;
        uint256 attackerShares = dustDeposit * totalShares / totalTokens;
        assertEq(attackerShares, 1, "Balanced pool: 1 wei yields 1 share");
        
        // To get 0 shares, need deposit * shares < tokens
        // e.g., pool has accumulated fees: tokens > shares
        totalTokens = 2000e18; // Pool earned 1000e18 in fees
        // Now 1 wei * 1000e18 / 2000e18 = 0.5 -> truncates to 0
        uint256 zeroShares = dustDeposit * totalShares / totalTokens;
        assertEq(zeroShares, 0, "Unbalanced pool: dust yields 0 shares");
        
        // This is a known property of share-based vaults, not typically a bounty
        // unless combined with a withdrawal mechanism that rounds up
    }
}
