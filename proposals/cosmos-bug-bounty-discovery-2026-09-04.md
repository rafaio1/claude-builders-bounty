# Cosmos Bug Bounty Program — Discovery Proposal

**Date:** 2026-09-04
**Program:** Cosmos (Immunefi)
**Type:** discovery_proposal
**Status:** Active / In-Scope Analysis Complete

## Program Summary

The Cosmos bug bounty program on Immunefi is **active**, live since 22 June 2026 and last updated 27 August 2026. It offers up to **$50,000** for Critical blockchain/DLT vulnerabilities, with funds backed by an on-chain vault ($50,039.87 available). The program follows **Primacy of Rules** and requires **KYC**, **PoC for all severities**, and is **triaged by Immunefi**.

## Scope Highlights (23 Assets)

### Blockchain/DLT Core
- **Cosmos SDK**: `baseapp`, `crypto`, `types`, `store`; modules `x/auth`, `x/bank`, `x/staking`, `x/slashing`, `x/evidence`, `x/distribution`, `x/mint` (other maintained modules accepted per Release Family Policy)
- **ibc-go**: IBC Core (02-client through 24-host), Application Modules (transfer, 27-interchain-accounts), Light Clients (06-solomachine, 07-tendermint, 08-wasm, 09-localhost), Middleware (29-fee, callbacks)
- **CometBFT** (consensus engine)
- **CosmWasm**: `wasmd` (x/wasm module only), `wasmvm`, `cw-utils`, `cw-storage-plus`, `serde-json-wasm`, `rust-optimizer`
- **Hermes Relayer**: `ibc-relayer`, `ibc-relayer-cli`, `ibc-relayer-rest`, `ibc-telemetry`, `ibc-chain-registry`
- **Ledger Cosmos app** (`cosmos/ledger-cosmos`)
- **iavl** library (not iaviewer app itself)

### Explicitly Out-of-Scope
- Gaia Hub-specific features and third-party modules
- `x/group`, `x/circuit`, `x/crisis`, `x/nft` (unmaintained per cosmos-sdk#25090)
- `x/precisebank` in Cosmos EVM (unmaintained)
- Web app vulns (XSS, CSRF, headers, TLS, CORS)
- Governance misconfiguration-only issues
- Scanner/informational reports without demonstrated impact
- Attacks requiring >1/3 validator collusion, governance action, or malicious relayer
- OOM reports below 16 GB memory threshold
- Chain rollbacks, attack investment exceeding impact, financial risk to attacker

## Reward Structure

| Severity | Reward | Key Impacts |
|----------|--------|-------------|
| Critical | $50,000 flat | Unauthorized minting/burning; Permanent freezing (hardfork required) |
| High | $12,500 flat | Chain halt/liveness failure; Consensus fork/AppHash divergence; Permanent locking of funds/clients; Theft/unauthorized extraction; Loss of cryptoeconomic security; Relayer key/wallet compromise |
| Medium | $2,500 flat | Supply inflation/accounting corruption; Single-node crash/resource-exhaustion DoS; Privilege escalation/auth bypass; Tx censorship/mempool manipulation; Supply-chain/CI-CD/RCE; Signing-display tamper/blind signing; Relayer fund exhaustion (economic griefing); Relayer liveness failure |
| Low | $1,000 flat | Information disclosure |

## PoC Requirements (Strict)

All severities require a working PoC. For Medium/High/Critical:
1. Must spin up a **local 4-node network**
2. Vulnerability demonstrated from an **external perspective** against the running network
3. Ideal format: self-contained bash script that spins up the network, applies modifications, and runs CLI commands proving the attack
4. Unit tests, integration tests, and written descriptions alone are **not accepted**

## Severity Downgrade Conditions

Reports may be downgraded one level if:
- Attack requires race condition outside attacker's control
- Attacker must be in permissioned set (active validator, restricted chain deployer)
- Requires governance action (on-chain parameter change)
- Requires ≥1/3 validator collusion
- Easily recoverable with built-in tooling
- Requires malicious relayer behavior

Additional discretionary downgrades apply per Cosmos team with stated reasoning.

## Known Issues (Not Eligible)

- Ledger Cosmos app: item count vs int8_t index mismatch (fixed in ledger-cosmos#203, 5 Aug 2026)

## SLA

| Severity | Ack + Triage | Resolution + Payment |
|----------|-------------|---------------------|
| Critical | 2 weeks | 5 weeks |
| High | 2 weeks | 3 weeks |
| Medium | 2 weeks | 6 weeks |
| Low | 2 weeks | 8 weeks |

## Submission Notes

- Pay-to-submit fee applies (USDC, on-chain, non-refundable, paid to Immunefi)
- Responsible Publication: Category 3 (Approval Required)
- Only released/tagged code under Cosmos Release Family Policy is eligible
- Testing must be on local forks/test clusters only — never mainnet or public testnets

## References

- Program page: https://immunefi.com/bug-bounty/cosmos/information/
- Scope: https://immunefi.com/bug-bounty/cosmos/scope/
- Security policy: https://github.com/cosmos/security/blob/main/SECURITY.md
- Release Family Policy: https://docs.cosmos.network/sdk/latest/release-family
- Audit reports: https://docs.cosmos.network/sdk/latest/security/audits
- Vault address: 0x1E01F5357572677a533432aCcC66dbDC0e0Db957