---
bounty: "[Bounty: $90] Reconcile the divergent mainnet RPC defaults across code and docs"
issue: https://github.com/Movalabs-crew/mova-store/issues/108
type: discovery_proposal
status: analysis_complete
date: 2026-09-04
---

# Discovery Proposal: Reconcile Divergent Mainnet RPC Defaults

## Summary

Three locations in the `mova-store` codebase specify two different default mainnet Soroban RPC endpoints. This proposal documents the exact divergence, recommends a single canonical default, and provides the precise changes needed to satisfy the bounty acceptance criteria.

## Current State — The Divergence

| Location | Default Mainnet RPC | Line(s) |
|---|---|---|
| `lib/stellar/config.ts` | `https://soroban-rpc.stellar.org` | L22–24 (fallback when `NEXT_PUBLIC_STELLAR_RPC_URL` is unset and `IS_MAINNET === true`) |
| `lib/env.ts` | `https://soroban-rpc.mainnet.stellar.gateway.fm` | L57 (`STELLAR_DEFAULTS.mainnet.rpcUrl`) |
| `docs/MAINNET_DEPLOYMENT.md` | `https://soroban-rpc.mainnet.stellar.gateway.fm` | L153 (env-var example in Step 6) |

### Why This Matters

- **Silent misconfiguration**: When `NEXT_PUBLIC_STELLAR_RPC_URL` is omitted from `.env.local`, `config.ts` silently resolves to the SDF public endpoint while `env.ts` resolves to Gateway.fm. Modules that import from one file vs. the other will talk to different RPCs in the same process.
- **Operator confusion**: The deployment guide tells operators to set the Gateway.fm URL, implying it is the canonical choice, yet `config.ts` disagrees. An operator who skips the env var (trusting "the default") gets a different backend than the docs promise.
- **Debugging surface**: Rate limits, latency, and uptime differ between the two providers. Inconsistent defaults make production incidents harder to reproduce.

## Recommended Canonical Default

**Adopt `https://soroban-rpc.stellar.org` as the single canonical mainnet RPC default.**

### Rationale

1. **First-party provider**: The SDF-hosted endpoint is the reference implementation; it has no third-party dependency and is the most commonly cited endpoint in Stellar/Soroban documentation.
2. **Already used by `config.ts`**: This file is the older, more widely imported module (it exports `RPC_URL`, `NETWORK_PASSPHRASE`, contract IDs, and `SUPPORTED_TOKENS`). Changing it would touch more downstream consumers.
3. **Gateway.fm is a valid alternative, not a default**: Operators who prefer Gateway.fm (or any other provider) should explicitly set `NEXT_PUBLIC_STELLAR_RPC_URL`. The docs should present this as an *option*, not the implicit default.

> **Alternative considered**: Adopting Gateway.fm everywhere. Rejected because it introduces a third-party dependency for out-of-the-box deployments and contradicts the existing `config.ts` default that most modules already rely on.

## Required Changes

### 1. `lib/env.ts` — Align the default

```diff
 const STELLAR_DEFAULTS = {
   // …
   mainnet: {
-    rpcUrl: "https://soroban-rpc.mainnet.stellar.gateway.fm",
+    rpcUrl: "https://soroban-rpc.stellar.org",
     networkPassphrase: "Public Global Stellar Network ; September 2015",
     // …
   },
 };
```

No other changes in this file; `loadStellarConfig()` already falls through to `defaults.rpcUrl` via `getEnv()`.

### 2. `lib/stellar/config.ts` — No change needed

The existing fallback on lines 22–24 already uses `https://soroban-rpc.stellar.org`. Verify only that no other hardcoded URL exists elsewhere in the file (confirmed: none).

### 3. `docs/MAINNET_DEPLOYMENT.md` — Document the actual default, offer Gateway.fm as optional

Replace the Step 6 env-var block (~L148–163) with:

```markdown
## Step 6: Configure the Frontend

Update your `.env.local` (or production environment variables):

\`\`\`bash
# Switch to mainnet
NEXT_PUBLIC_STELLAR_NETWORK=mainnet

# Mainnet RPC endpoint
# Default (if omitted): https://soroban-rpc.stellar.org
# Uncomment below to use Gateway.fm instead:
# NEXT_PUBLIC_STELLAR_RPC_URL=https://soroban-rpc.mainnet.stellar.gateway.fm

# Mainnet passphrase
NEXT_PUBLIC_STELLAR_NETWORK_PASSPHRASE=Public Global Stellar Network ; September 2015

# Your deployed mainnet contract
NEXT_PUBLIC_CHECKOUT_CONTRACT_ID=<YOUR_MAINNET_CONTRACT_ID>

# Mainnet USDC contract ID
NEXT_PUBLIC_USDC_CONTRACT_ID=<MAINNET_USDC_CONTRACT_ID>

# Mainnet native XLM SAC
NEXT_PUBLIC_NATIVE_ASSET_CONTRACT_ID=CAS3J7GYLGXMF6TDJBBYYSE3HQ6BBSMLNUQ34T6TZMYMW2EVH34XOWMA
\`\`\`
```

This makes the doc match the code's actual default and surfaces Gateway.fm as an explicit opt-in.

## Acceptance Criteria Verification

| Criterion | How It Is Met |
|---|---|
| `config.ts` and `env.ts` resolve the same mainnet RPC when the env var is unset | Both now fall back to `https://soroban-rpc.stellar.org` |
| `MAINNET_DEPLOYMENT.md` documents the endpoint the code actually defaults to | Doc states the default is `https://soroban-rpc.stellar.org` and shows Gateway.fm as a commented-out alternative |

## Risk Assessment

- **Low risk**: Only default values change; any deployment that already sets `NEXT_PUBLIC_STELLAR_RPC_URL` explicitly is unaffected.
- **Regression check**: Search for any test fixtures or CI configs that assert the Gateway.fm URL as the expected default; update them to match.
- **Rollback**: Single-commit revert restores the prior state if an unexpected issue surfaces.

## Estimated Effort

~15 minutes of code changes + testing. Well within the bounty ETA of 24 hours.