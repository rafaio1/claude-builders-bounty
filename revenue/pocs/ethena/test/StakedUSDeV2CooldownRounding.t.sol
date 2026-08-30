// SPDX-License-Identifier: GPL-3.0
pragma solidity 0.8.20;

import "forge-std/Test.sol";
import "ethena/StakedUSDeV2.sol";
import "ethena/USDe.sol";

contract StakedUSDeV2CooldownRoundingTest is Test {
    StakedUSDeV2 public vault;
    USDe public usde;
    address public admin = address(0xAD);
    address public rewarder = address(0xFEED);
    address public alice = address(0xA1);
    address public bob = address(0xB0B);

    function setUp() public {
        usde = new USDe(admin);
        vm.prank(admin);
        usde.setMinter(address(this));
        
        vault = new StakedUSDeV2(IERC20(address(usde)), rewarder, admin);
        
        // Fund accounts
        usde.mint(alice, 1000 ether);
        usde.mint(bob, 1000 ether);
        
        vm.prank(alice);
        usde.approve(address(vault), type(uint256).max);
        vm.prank(bob);
        usde.approve(address(vault), type(uint256).max);
    }

    /// @notice Test if cooldownAssets rounding can be exploited to extract value
    /// when totalAssets is artificially inflated relative to totalSupply
    function testCooldownRoundingExploit() public {
        // 1. Normal deposit to establish baseline
        vm.prank(alice);
        vault.deposit(100 ether, alice);
        
        // 2. Inflate assets via direct transfer (simulating donation or reward without vesting)
        // Note: In real scenario this would need to bypass vesting, but we test the math path
        usde.mint(address(vault), 1000 ether);
        
        // Force vesting to complete by warping time
        vm.warp(block.timestamp + 9 hours);
        
        uint256 totalAssetsBefore = vault.totalAssets();
        uint256 totalSupplyBefore = vault.totalSupply();
        
        console.log("Total Assets:", totalAssetsBefore);
        console.log("Total Supply:", totalSupplyBefore);
        console.log("Exchange Rate:", (totalAssetsBefore * 1e18) / totalSupplyBefore);
        
        // 3. Try to exploit rounding in cooldownAssets with small amount
        // previewWithdraw uses: shares = (assets * totalSupply + totalAssets - 1) / totalAssets
        // If assets is small relative to totalAssets, shares could round to 0
        // But notZero modifier prevents 0 shares
        
        uint256 smallAmount = 1 wei;
        uint256 previewShares = vault.previewWithdraw(smallAmount);
        console.log("Preview shares for 1 wei:", previewShares);
        
        // 4. Check if we can drain more than entitled via repeated small cooldowns
        // This tests the core hypothesis: does integer division favor the withdrawer?
        vm.prank(alice);
        try vault.cooldownAssets(smallAmount) {
            console.log("Cooldown succeeded");
            (uint104 cooldownEnd, uint152 underlyingAmount) = vault.cooldowns(alice);
            console.log("Locked underlying:", underlyingAmount);
        } catch Error(string memory reason) {
            console.log("Cooldown failed:", reason);
        }
    }
    
    /// @notice Test share inflation via redistributeLockedAmount to address(0)
    /// followed by immediate cooldown before MIN_SHARES check triggers
    function testRedistributeToZeroThenCooldown() public {
        // Grant admin the BLACKLIST_MANAGER_ROLE (keccak256("BLACKLIST_MANAGER_ROLE"))
        bytes32 BLACKLIST_MANAGER_ROLE = keccak256("BLACKLIST_MANAGER_ROLE");
        vm.prank(admin);
        vault.grantRole(BLACKLIST_MANAGER_ROLE, admin);

        // Setup: Alice has shares, gets blacklisted
        vm.prank(alice);
        vault.deposit(10 ether, alice);
        
        // Bob deposits to keep supply above MIN_SHARES after burn
        vm.prank(bob);
        vault.deposit(10 ether, bob);
        
        // Admin blacklists Alice fully
        vm.prank(admin);
        vault.addToBlacklist(alice, true);
        
        // Admin redistributes Alice's shares to address(0) -> burns them
        // This bypasses _checkMinShares because it calls _burn directly
        vm.prank(admin);
        vault.redistributeLockedAmount(alice, address(0));
        
        uint256 supplyAfterBurn = vault.totalSupply();
        console.log("Supply after burn:", supplyAfterBurn);
        
        // Now only Bob has shares. If supply < MIN_SHARES, next deposit might fail
        // or be exploitable. But V2 cooldown path also has _checkMinShares in _withdraw
        
        // Warp to allow vesting completion if needed
        vm.warp(block.timestamp + 9 hours);
        
        // Bob tries to cooldown - should trigger _checkMinShares if supply too low
        vm.prank(bob);
        try vault.cooldownAssets(5 ether) {
            console.log("Bob cooldown succeeded");
        } catch Error(string memory reason) {
            console.log("Bob cooldown failed:", reason);
        }
    }
}
