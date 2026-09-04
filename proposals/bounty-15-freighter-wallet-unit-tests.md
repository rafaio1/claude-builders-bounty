# Bounty Proposal: Add Unit Tests for Freighter Wallet Helpers

- **Bounty**: [$80] Add unit tests for the Freighter wallet helpers in `lib/stellar/freighter.ts`
- **Source**: https://github.com/Movalabs-crew/mova-store/issues/15
- **Type**: discovery_proposal
- **Date**: 2026-09-04
- **Status**: Discovery Complete — Ready for Implementation

## Summary

The bounty requests unit tests for the Freighter wallet connector. The target file was located at `/Agentic/workspace/pr-email-actions/ophirpay/src/lib/wallets/freighter.ts` (not `lib/stellar/freighter.ts` as stated in the bounty title — the actual path uses a `wallets` directory under `lib`).

## Target File Analysis

**File**: `src/lib/wallets/freighter.ts` (111 lines)
**Exports**: `freighterConnector` (implements `WalletConnector` interface from `./types`)

### Functions/Methods Requiring Test Coverage

| Method | Lines | Key Branches to Cover |
|---|---|---|
| `getFreighterApi()` | 24–27 | `window` undefined (SSR), `window.freighter` present, absent |
| `isAvailable()` | 35–37 | Returns `true` when API exists, `false` otherwise |
| `connect()` | 39–50 | Success path, missing API throws, returns `{ publicKey, network }` |
| `disconnect()` | 52–57 | Removes localStorage key when `window` defined; no-op in SSR |
| `signTransaction()` | 59–66 | Delegates to API with opts, throws when API missing |
| `signMessage()` | 68–77 | Handles string return (old API), object return (new API), null signature throws, missing API throws |
| `getAddress()` | 79–88 | Connected → returns address, not connected → null, error → null, no API → null |
| `getNetwork()` | 90–99 | Connected → returns network, not connected → null, error → null, no API → null |
| `isConnected()` | 101–109 | Delegates to API, catches errors → false, no API → false |

### Dependencies to Mock

- `window.freighter` (the browser extension API)
- `window.localStorage` (for `disconnect()`)
- `typeof window` (for SSR guard)

## Existing Test Infrastructure

- **Framework**: Vitest + jsdom environment
- **Setup**: `vitest.setup.ts` imports `@testing-library/jest-dom/vitest`
- **Config**: `vite.config.ts` defines test environment and aliases (`@` → `./src`)
- **Convention**: Tests live in `src/__tests__/` with `*.test.ts` suffix
- **Note**: `src/lib/wallets/**` is currently **excluded** from coverage thresholds in `vite.config.ts`. This exclusion should be updated when tests are added.

## Proposed Test File

**Path**: `src/__tests__/freighter.test.ts`

### Test Cases (18 tests minimum)

```
describe("freighterConnector")
├── describe("isAvailable")
│   ├── returns true when window.freighter exists
│   └── returns false when window.freighter is undefined
├── describe("connect")
│   ├── calls requestAccess then getAddress and getNetwork
│   ├── returns { publicKey, network } on success
│   └── throws descriptive error when Freighter not installed
├── describe("disconnect")
│   ├── removes ophirpay-wallet-connected from localStorage
│   └── does not throw in SSR (window undefined)
├── describe("signTransaction")
│   ├── delegates xdr and opts to freighter.signTransaction
│   ├── passes network and networkPassphrase from opts
│   └── throws when Freighter not found
├── describe("signMessage")
│   ├── returns messageSignature from object response (new API)
│   ├── returns bare string response (old API)
│   ├── throws when signature is falsy
│   └── throws when Freighter not found
├── describe("getAddress")
│   ├── returns address when connected
│   ├── returns null when not connected
│   ├── returns null on API error
│   └── returns null when API unavailable
├── describe("getNetwork")
│   ├── returns network when connected
│   ├── returns null when not connected
│   ├── returns null on API error
│   └── returns null when API unavailable
└── describe("isConnected")
    ├── returns true when API reports connected
    ├── returns false when API reports disconnected
    ├── returns false on API error
    └── returns false when API unavailable
```

## Implementation Notes

1. **Mock pattern**: Use `vi.stubGlobal("window", ...)` or direct property assignment on `globalThis.window` to inject/remove the `freighter` API between tests.
2. **SSR simulation**: Temporarily delete `globalThis.window` to test SSR guards, restore in `afterEach`.
3. **localStorage mock**: jsdom provides `localStorage` natively; verify `removeItem` is called with the correct key.
4. **Coverage config update**: Remove `"src/lib/wallets/**"` from the `coverage.exclude` array in `vite.config.ts` once tests pass.
5. **No external dependencies**: All mocks are inline; no need for `@stellar/freighter-api` or similar packages.

## Acceptance Criteria

- [ ] All 18+ test cases pass with `pnpm test src/__tests__/freighter.test.ts`
- [ ] ≥80% line, branch, and function coverage on `src/lib/wallets/freighter.ts`
- [ ] `src/lib/wallets/**` removed from coverage exclusions in `vite.config.ts`
- [ ] No modifications to `freighter.ts` source code (pure test addition)
- [ ] Tests follow existing conventions (Vitest, `describe`/`it` blocks, SPDX header)

## Risk Assessment

- **Low risk**: Pure test addition, no source changes.
- **SSR edge cases**: The `typeof window === "undefined"` guards require careful mock teardown to avoid leaking state between tests.
- **API shape drift**: The dual return type of `signMessage` (string vs object) reflects real-world Freighter API evolution; both paths must be tested.