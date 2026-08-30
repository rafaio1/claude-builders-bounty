# Usual Labs Deep Analysis Task ($16M Bounty)

## Objective
Find Critical severity vulnerabilities in USD0/USD0PP ecosystem.
Payout: Up to $16M USDC for >5% TVL loss or fund freeze >1yr.

## Scope (Ethereum Mainnet)
- USD0.sol, USD0PP.sol
- DaoCollateral.sol
- RegistryAccess.sol, RegistryContract.sol
- SwapperEngine.sol
- ClassicalOracle.sol
- TokenMapping.sol

## Attack Surface Priorities
1. Oracle manipulation in ClassicalOracle → price feed staleness/twap bypass
2. Collateral accounting drift in DaoCollateral during liquidation cascades
3. Swap slippage/rounding in SwapperEngine enabling arbitrage extraction
4. Access control gaps in RegistryAccess allowing unauthorized upgrades
5. TokenMapping whitelist bypass enabling toxic asset deposits

## Deliverables
- Invariant map for USD0 peg mechanism
- Top 3 candidate bugs with severity justification
- Foundry PoC if exploitable path confirmed
- Commit findings to git

## References
- Docs: https://tech.usual.money/overview/architecture
- Sherlock Rules: https://docs.sherlock.xyz/bug-bounties/post-launch-bounty/platform-rules
