// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import {Math} from "openzeppelin-contracts/utils/math/Math.sol";

contract UsualRoundingLossTest is Test {
    uint256 constant SCALAR_ONE = 1e18;

    // Replicate normalize.sol logic exactly
    function tokenAmountToWad(uint256 tokenAmount, uint8 tokenDecimals) internal pure returns (uint256) {
        return tokenAmount * (10 ** uint256(18 - tokenDecimals));
    }

    function wadAmountByPrice(uint256 wadAmount, uint256 wadPrice) internal pure returns (uint256) {
        return Math.mulDiv(wadAmount, wadPrice, SCALAR_ONE, Math.Rounding.Floor);
    }

    function getUsd0WadEquivalent(uint256 usdcNative, uint256 usdcWadPrice) internal pure returns (uint256) {
        uint256 usdcWad = tokenAmountToWad(usdcNative, 6);
        return wadAmountByPrice(usdcWad, usdcWadPrice);
    }

    function test_RoundingDustAccumulation() public pure {
        // Simulate worst-case price: repeating decimal in WAD that maximizes floor loss
        // e.g., 0.999999999999999999... -> use a prime-ish WAD price
        uint256 adversarialPrice = 999999999999999999; // just under 1e18
        
        uint256 totalUsdcNative = 0;
        uint256 totalUsd0Spent = 0;
        
        // Simulate 1000 micro-orders at minimum (100 USDC each)
        uint256 microOrderSize = 100e6; // 100 USDC in native decimals
        uint256 numOrders = 1000;
        
        for (uint256 i = 0; i < numOrders; i++) {
            uint256 usd0ForThisOrder = getUsd0WadEquivalent(microOrderSize, adversarialPrice);
            totalUsd0Spent += usd0ForThisOrder;
            totalUsdcNative += microOrderSize;
        }
        
        // Calculate what fair value should be (single bulk calculation)
        uint256 fairUsd0Bulk = getUsd0WadEquivalent(totalUsdcNative, adversarialPrice);
        
        // The dust profit = fair bulk - sum of individual floors
        // If sum of floors < bulk, attacker profits
        uint256 dustProfit = fairUsd0Bulk > totalUsd0Spent ? fairUsd0Bulk - totalUsd0Spent : 0;
        
        emit log_named_uint("Total USDC matched (native)", totalUsdcNative);
        emit log_named_uint("Sum of individual USD0 spends", totalUsd0Spent);
        emit log_named_uint("Fair bulk USD0 equivalent", fairUsd0Bulk);
        emit log_named_uint("Dust profit (USD0 wei)", dustProfit);
        emit log_named_uint("Dust profit (USD0 units)", dustProfit / 1e18);
        
        // Key assertion: does batching small orders save USD0 vs one big order?
        // If totalUsd0Spent < fairUsd0Bulk, the rounding vector is real
        assertLe(totalUsd0Spent, fairUsd0Bulk, "Floor rounding should never exceed bulk");
    }

    function test_SingleVsBatchEquivalence() public pure {
        // Test if single large order == sum of small orders at exact 1:1 price
        uint256 exactPrice = 1e18; // Perfect 1:1
        uint256 smallOrder = 100e6;
        uint256 numOrders = 100;
        
        uint256 sumSmall = 0;
        for (uint256 i = 0; i < numOrders; i++) {
            sumSmall += getUsd0WadEquivalent(smallOrder, exactPrice);
        }
        uint256 singleLarge = getUsd0WadEquivalent(smallOrder * numOrders, exactPrice);
        
        emit log_named_uint("Sum of 100x100 USDC at 1:1", sumSmall);
        emit log_named_uint("Single 10000 USDC at 1:1", singleLarge);
        
        assertEq(sumSmall, singleLarge, "At exact 1:1, no rounding loss expected");
    }
}
