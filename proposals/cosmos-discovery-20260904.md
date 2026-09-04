---
name: cosmos-bounty-discovery
date: 2026-09-04
type: discovery_proposal
provider: ghostcli-auto[1m]
url: https://immunefi.com/bug-bounty/cosmos/information/
status: reviewed
---

# Cosmos Bug Bounty — Discovery Proposal

## Program Summary

| Field | Value |
|-------|-------|
| Project | Cosmos (Cosmos Labs) |
| Platform | Immunefi |
| Type | Blockchain / L1 / Services / Staking / Wallet / Validator |
| Languages | Go, Rust, Solidity, C/C++, CosmWasm |
| Max Bounty | $50,000 (flat) |
| Vault Funds | $50,035.50 (50k USDC + 0.02 ETH) |
| Live Since | 22 June 2026 |
| Last Updated | 27 August 2026 |
| Triage | Immunefi |
| KYC | Required |
| PoC | Required (all severities) |
| Primacy | Rules |
| Responsible Publication | Category 3 — Approval Required |
| Pay-to-Submit | Yes (USDC, non-refundable) |

## Reward Schedule (Blockchain/DLT)

| Severity | Reward | Notes |
|----------|--------|-------|
| Critical | $50,000 | Flat |
| High | $12,500 | Flat |
| Medium | $2,500 | Flat |
| Low | $1,000 | Flat |
| Informational | $0 | Not eligible |

## Response SLAs

| Severity | Ack + Triage | Resolution + Payment |
|----------|--------------|----------------------|
| Critical | 2 weeks | 5 weeks |
| High | 2 weeks | 3 weeks |
| Medium | 2 weeks | 6 weeks |
| Low | 2 weeks | 8 weeks |

## Scope Focus

- Distributed systems protocols, cryptography, smart contract platform, consensus algorithm, interoperability protocol (IBC).
- **In scope**: Source code for integral Cosmos Stack components.
- **Out of scope**: Web application vulnerabilities (XSS, CSRF, header misconfigs), third-party services, IT assets.
- Only released code tagged under the [Cosmos Release Family Policy](https://docs.cosmos.network/sdk/latest/release-family) is eligible. Code on main/master/dev branches is excluded.

## Key Constraints & Downgrade Conditions

Severity may be downgraded by one level if:
1. Attack requires a race condition with timing not in attacker's control.
2. Attacker must be in a permissioned set (e.g., active validator, restricted chain deployer).
3. Governance action required (e.g., on-chain parameter change).
4. Requires ≥1/3 validator collusion by voting power.
5. Easily recoverable with built-in tooling.
6. Requires malicious relayer behavior.

Cosmos retains full discretion for additional downgrades with stated reasoning.

## PoC Requirements (Strict)

- **All severities**: Working code PoC required; written descriptions alone are insufficient.
- **Medium/High/Critical**: Must demonstrate end-to-end on a **local 4-node network** from an external perspective.
  - Ideal: self-contained bash script that spins up the network, applies modifications, and runs CLI commands proving the attack.
  - Malicious node injection allowed for a single instance, but impact must be shown against the whole network.
- **Not accepted**: Unit tests, integration tests, theoretical writeups without working network-level PoC.
- Reports without valid PoC will not be rewarded.

## Known Issues (Excluded)

- Ledger Cosmos UI item count vs int8_t index range mismatch (fixed in [ledger-cosmos#203](https://github.com/cosmos/ledger-cosmos/pull/203)) — last updated 5 Aug 2026.

## Audit References

- Previous audits: <https://docs.cosmos.network/sdk/latest/security/audits> (as of 1 Jun 2026).
- Unpatched/unresolved issues from these audits are ineligible.

## Eligibility Notes

- Researchers employed by or contracted to the Cosmos team within 12 months preceding submission are ineligible.
- KYC required for payout.
- Pay-to-submit fee is paid to Immunefi (not Cosmos), non-refundable, and does not guarantee triage or reward.

## Feasibility Limitations (Immunefi Standard)

- Chain Rollbacks
- Pre-Impact Bug Monitoring
- Attack Investment Amount
- Attacks With Financial Risk To Attacker
- Impactful Attack → Griefing downgrade criteria

## Recommendation

This program is well-suited for researchers with Cosmos SDK / Tendermint / IBC expertise and local multi-node testnet infrastructure. The strict 4-node PoC requirement raises the bar significantly; proposals should budget time for environment setup and end-to-end demonstration. Focus areas with highest potential return: consensus edge cases, IBC packet handling, module authorization boundaries, and cross-module state machine transitions in released tags.

## Next Steps

1. Confirm access to a reproducible 4-node localnet harness (bash/docker/cometbft).
2. Select a released tag per Cosmos Release Family Policy as target version.
3. Identify candidate surface area (consensus, IBC, bank/staking/gov modules, CosmWasm runtime).
4. Draft finding with PoC script before submission via <https://bugs.immunefi.com/dashboard/new-submission>.
5. Ensure KYC readiness and pay-to-submit USDC availability.

## Status

Reviewed and documented. No canonical ledgers modified. Awaiting researcher assignment or further directive.