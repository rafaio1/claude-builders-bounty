# Ethena StakedUSDe: Potential Donation Attack Vector via MIN_SHARES Bypass

## Severity: Medium (Conditional)
## Protocol: Ethena
## Contract: StakedUSDe.sol / StakedUSDeV2.sol
## Max Bounty: $3,000,000 (Immunefi)

## Summary
The `StakedUSDe` contract implements a `MIN_SHARES = 1 ether` check to prevent donation attacks (first depositor inflation). However, this protection may be insufficient or bypassable under specific conditions related to the 8-hour vesting period and the interaction with `StakedUSDeV2` cooldown mechanics.

## Vulnerability Details

### 1. MIN_SHARES Check Logic
```solidity
uint256 private constant MIN_SHARES = 1 ether;

function _checkMinShares() internal view {
    uint256 _totalSupply = totalSupply();
    if (_totalSupply > 0 && _totalSupply < MIN_SHARES) revert MinSharesViolation();
}
```
This check runs after `_deposit` and `_withdraw`. It prevents the total supply from existing in a "danger zone" between 0 and 1e18 shares.

### 2. Vesting Period Interaction
`totalAssets()` subtracts `getUnvestedAmount()`:
```solidity
function totalAssets() public view override returns (uint256) {
    return IERC20(asset()).balanceOf(address(this)) - getUnvestedAmount();
}
```
During the 8-hour vesting period, `totalAssets` is artificially lower than the actual balance. If a donation occurs *during* vesting, the share price calculation `(assets + 1) / (supply + 1)` uses the reduced `totalAssets`, potentially allowing more severe inflation once vesting completes and assets "unlock".

### 3. Cooldown Withdrawal Path (StakedUSDeV2)
In `StakedUSDeV2.cooldownAssets` and `cooldownShares`, assets are moved to the `USDeSilo` escrow:
```solidity
_withdraw(msg.sender, address(silo), msg.sender, assets, shares);
```
The `_checkMinShares` hook fires here. If a user cools down their entire position leaving only dust < 1e18 shares, the transaction reverts. This is correct behavior. **However**, if multiple users coordinate or if rounding in `previewWithdraw` leaves exactly `MIN_SHARES` while actual redeemable value differs due to vesting, edge cases may exist.

### 4. Redistribution Bypass Risk
`redistributeLockedAmount` burns from a blacklisted user and mints to another:
```solidity
uint256 usdeToVest = previewRedeem(amountToDistribute);
_burn(from, amountToDistribute);
if (to == address(0)) {
    _updateVestingAmount(usdeToVest);
} else {
    _mint(to, amountToDistribute);
}
```
When `to == address(0)`, shares are burned but NO new shares are minted. The underlying assets are added to `vestingAmount`. This reduces `totalSupply` without reducing `totalAssets` (after vesting). If this operation brings `totalSupply` below `MIN_SHARES` while `totalAssets` remains high, subsequent depositors could face extreme share inflation when vesting unlocks.

**Note:** `_checkMinShares` is NOT called in `redistributeLockedAmount`. This is a potential gap.

## Proof of Concept Outline
1. Attacker deposits `MIN_SHARES` (1e18) worth of assets to initialize pool.
2. Admin blacklists attacker as `FULL_RESTRICTED_STAKER_ROLE`.
3. Admin calls `redistributeLockedAmount(attacker, address(0))`.
4. Shares burned → `totalSupply = 0`. Assets enter vesting.
5. During vesting, `totalAssets = 0` (all unvested). Pool appears empty.
6. Victim deposits small amount → receives shares at 1:1 ratio.
7. Vesting completes → `totalAssets` jumps to include redistributed amount.
8. Victim's shares now represent fraction of much larger asset pool → loss of funds.

## Impact
- Loss of user funds via share inflation after admin-initiated redistribution to address(0).
- Requires admin cooperation (blacklist + redistribute), reducing likelihood.
- If exploitable without full admin collusion (e.g., via governance proposal manipulation in DeXe meta-gov), severity increases to High/Critical.

## Recommended Fix
Add `_checkMinShares()` call at end of `redistributeLockedAmount` when `to == address(0)`, or ensure `totalSupply` never drops below `MIN_SHARES` unless `totalAssets` is also zero.

## Status: DRAFT - REQUIRES POC VALIDATION
