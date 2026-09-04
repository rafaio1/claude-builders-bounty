# Cosmos Bug Bounty — Discovery Proposal

**Date:** 2026-09-04
**Provider:** ghostcli-auto[1m]
**Type:** discovery_proposal
**Source:** https://immunefi.com/bug-bounty/cosmos/information/
**Status:** research_complete — ready for target selection and PoC development

## Program Summary

| Field | Value |
|---|---|
| Project | Cosmos (Cosmos Stack) |
| Platform | Immunefi |
| Max Bounty | $50,000 (flat) |
| Vault Funds | $50,034.23 (0.02 ETH + 50k USDC) |
| Vault Address | `0x1E01F5357572677a533432aCcC66dbDC0e0Db957` |
| Live Since | 22 June 2026 |
| Last Updated | 27 August 2026 |
| Triage | Immunefi |
| KYC | Required |
| PoC | Required (4-node local network, end-to-end) |
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

## In-Scope Assets (23 total)

### Core Protocol
- **Cosmos SDK** — baseapp, crypto, types, store; modules x/auth, x/bank, x/staking, x/slashing, x/evidence, x/distribution, x/mint (other maintained modules accepted per Release Family Policy)
- **ibc-go** — IBC Core (02-client, 03-connection, 04-channel, 05-port, 23-commitment, 24-host), Application Modules (transfer, 27-interchain-accounts), Light Clients (06-solomachine, 07-tendermint, 08-wasm, 09-localhost), Middleware (29-fee, callbacks)
- **CometBFT** — consensus engine
- **iavl** — Merkle tree library (iaviewer app excluded unless underlying lib bug)

### CosmWasm Stack
- wasmd (x/wasm module only)
- wasmvm
- rust-optimizer
- cw-utils, cw-storage-plus, serde-json-wasm

### Hermes Relayer (Rust crates)
- ibc-relayer, ibc-relayer-cli, ibc-relayer-rest, ibc-telemetry, ibc-chain-registry

### Wallet / Ledger
- ledger-cosmos

### Other
- Cosmos EVM (x/precisebank EXCLUDED — unmaintained)
- Gaia (reference impl only; Hub-specific features out-of-scope)

## High-Value Impact Targets

| Impact | Severity | Notes |
|---|---|---|
| Unauthorized minting/burning of user funds | Critical | Downgradable if one-time, limited amount, optional module, or governance-reversible |
| Chain halt / liveness failure | High | Downgradable to Medium if optional module, contrived trigger, or recoverable on restart |
| Non-determinism / consensus fork / AppHash divergence | High | Downgradable if optional module, version mismatch, or contrived trigger |
| Theft / unauthorized extraction of funds | High | — |
| Permanent locking/freezing of funds or clients | High | — |
| Loss of cryptoeconomic security | High | — |
| Supply inflation / accounting corruption | Medium | — |
| Privilege escalation / authorization bypass | Medium | — |
| Single-node crash / resource-exhaustion DoS | Medium | OOM requires >16 GB memory increase |

## Severity Downgrade Conditions (Program-Wide)

- Race condition with timing not in attacker's control → −1 severity
- Attacker must be in permissioned set (active validator, restricted deployer) → −1
- Requires governance action → −1
- Requires ≥⅓ validator collusion → −1
- Easily recoverable with built-in tooling → −1
- Requires malicious relayer → −1
- Cosmos team retains full discretion for additional downgrades with stated reasoning

## PoC Requirements

- Self-contained bash script spinning up a 4-node local network
- Vulnerability demonstrated end-to-end from external perspective
- Malicious node injection allowed (single instance) but impact must be against whole network
- Unit tests, integration tests, and written descriptions alone are NOT valid PoCs
- Must target released/tagged code per Cosmos Release Family Policy

## Out-of-Scope Exclusions (Key)

- Web vulnerabilities (XSS, CSRF, CORS, headers, TLS)
- Third-party services/websites
- Scanner-only / informational reports
- Architectural critiques without exploitability
- User misconfiguration against documented procedures
- Centralization risks
- Attacks requiring honest users to interact with malicious chain/channel/contract directly
- Issues in unmaintained modules: x/group, x/circuit, x/crisis, x/nft, x/precisebank
- Gaia Hub-specific features
- Testing against live mainnet/public testnets (PROHIBITED)

## Known Issues (Ineligible)

- Ledger Cosmos app item count int8_t overflow (fixed in PR #203, 5 Aug 2026)

## Recommended Research Vectors

1. **IBC Light Client Misbehaviour Handling** — Test 07-tendermint and 08-wasm light client update/misbehaviour paths for state corruption or client freezing edge cases
2. **CosmWasm x/wasm Module Boundaries** — Fuzz message dispatch, contract instantiation, and reply handling for privilege escalation or unauthorized state mutation
3. **Interchain Accounts (ICA) Host Channel Logic** — Probe packet timeout and callback execution ordering for fund-freezing or reentrancy vectors
4. **Staking/Distribution Accounting** — Audit delegation/unbonding edge cases under slash events for supply inflation or double-counting
5. **CometBFT Consensus Edge Cases** — Investigate vote extension handling and precommit aggregation for non-determinism triggers
6. **Hermes Relayer Key Management** — Audit ibc-relayer credential storage and signing paths for key compromise vectors

## Next Steps

1. Select one research vector from above
2. Set up local 4-node testnet with tagged release versions
3. Develop end-to-end PoC per program requirements
4. Submit via https://bugs.immunefi.com/dashboard/new-submission

## Compliance Notes

- Responsible Publication: Category 3 (Approval Required)
- Pay-to-submit fee applies (USDC, on-chain, non-refundable)
- Response SLA: Critical 2w ack / 5w resolution; High 2w/3w; Medium 2w/6w; Low 2w/8w
- No testing on live networks

**No claim or submission has been filed.** This document serves as a discovery record only.
