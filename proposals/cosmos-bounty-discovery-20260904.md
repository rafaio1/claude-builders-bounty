# Cosmos Bug Bounty — Discovery Proposal

**Date:** 2026-09-04
**Provider:** ghostcli-auto[1m]
**Type:** discovery_proposal
**Source:** https://immunefi.com/bug-bounty/cosmos/information/
**Status:** Reviewed — No submission made (canonical ledgers untouched)

## Program Summary

| Field | Value |
|---|---|
| Project | Cosmos (Cosmos Stack) |
| Platform | Immunefi |
| Max Bounty | $50,000 (flat) |
| Vault Funds | $50,033.87 (0.02 ETH + 50k USDC) |
| Vault Address | `0x1E01F5357572677a533432aCcC66dbDC0e0Db957` |
| Live Since | 22 June 2026 |
| Last Updated | 27 August 2026 |
| Triage | Immunefi |
| KYC | Required |
| PoC | Required (all severities) |
| Primacy | Rules |
| Publication | Category 3 — Approval Required |
| Pay-to-Submit | Yes (USDC, on-chain, non-refundable) |

## Reward Schedule (Blockchain/DLT)

| Severity | Reward |
|---|---|
| Critical | $50,000 |
| High | $12,500 |
| Medium | $2,500 |
| Low | $1,000 |
| Informational | $0 |

## Response SLAs

| Severity | Ack + Triage | Resolution + Payment |
|---|---|---|
| Critical | 2 weeks | 5 weeks |
| High | 2 weeks | 3 weeks |
| Medium | 2 weeks | 6 weeks |
| Low | 2 weeks | 8 weeks |

## Scope Focus

- Distributed systems protocols, cryptography, smart contract platform, consensus algorithm, interoperability protocol (IBC).
- Languages: Go, Rust, Solidity, C/C++, CosmWasm.
- **Out of scope:** Web application vulnerabilities (XSS, CSRF, header misconfigs), third-party services, IT assets.
- Only released/tagged code under the Cosmos Release Family Policy is eligible.

## Key Submission Requirements

1. **PoC mandatory for all severities.** Written descriptions alone are insufficient.
2. **Medium/High/Critical PoCs must run against a local 4-node network** from an external perspective. Ideal format: self-contained bash script.
3. Unit tests, integration tests, and theoretical writeups are **not** accepted as standalone PoCs.
4. Reports without adequate detail may be closed or returned.
5. Pay-to-submit fee applies (USDC, paid to Immunefi, non-refundable).

## Severity Downgrade Conditions

- Race condition timing not attacker-controlled.
- Attacker must be in a permissioned set (e.g., active validator).
- Governance action required (e.g., parameter change).
- Validator collusion ≥ 1/3 voting power required.
- Easily recoverable via built-in tooling.
- Malicious relayer required.
- Cosmos team retains full discretion for additional downgrades with stated reasoning.

## Known Issues (Ineligible)

- Ledger Cosmos UI item count vs int8_t index range mismatch (fixed in PR #203, 5 Aug 2026).

## Feasibility Limitations

Standard Immunefi feasibility limitations apply: chain rollbacks, attack investment amount, financial risk to attacker, griefing downgrades, pre-impact bug monitoring.

## Assessment & Recommendation

This program is well-suited for protocol-level security research on the Cosmos Stack. The strict PoC requirements (4-node local network, end-to-end demonstration) raise the bar significantly but also reduce noise and increase reward certainty. Researchers should:

1. Set up a reproducible 4-node Cosmos SDK testnet before beginning research.
2. Focus on consensus, IBC, staking, governance, and module-level logic rather than web/app-layer issues.
3. Verify target code is tagged/released per the Release Family Policy before investing time.
4. Budget for the pay-to-submit fee and KYC timeline.
5. Review prior audits at https://docs.cosmos.network/sdk/latest/security/audits to avoid duplicate findings.

**No claim or submission has been filed.** This document serves as a discovery record only.
