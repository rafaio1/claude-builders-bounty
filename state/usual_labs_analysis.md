# Usual Labs Security Analysis — FINAL STATUS: NO EXPLOITABLE VECTORS FOUND

## Date: 2026-08-30
## Target: Sherlock $16M Bounty Program
## Verdict: PIVOT REQUIRED — All candidates invalidated by PoC or code review

---

## ❌ Candidate #1: Rounding Loss in SwapperEngine — INVALIDATED
**Test:** `test/UsualRoundingLoss.t.sol` (Foundry, 1000 micro-orders at adversarial WAD price)
**Result:** Dust profit = 0 wei. `Math.mulDiv(wadAmount, wadPrice, 1e18, Floor)` produces no cumulative loss because USDC→WAD conversion (`*1e12`) is exact. Sum of individual floors == bulk floor.
**Conclusion:** No exploitable asymmetry. Rounding favors neither provider nor requester at scale.

## ❌ Candidate #2: Oracle Staleness Bypass — INVALIDATED
**Code Review:** `AbstractOracle._checkDepegPrice()` enforces `maxDepegThreshold` (basis points) on EVERY `getPrice()` call, independent of timeout.
**Implication:** Even with max 7-day timeout, USDC price must remain within depeg band (e.g., ±50bps). Stale price ≠ drifted price. No arbitrage window exists for inflated USD0 minting.
**Conclusion:** Timeout extends validity duration, not price deviation tolerance. Not exploitable.

## ⚪ Candidate #3: Reentrancy in withdrawUSDC — INFORMATIONAL ONLY
USDC mainnet has no ERC-777 hooks. `nonReentrant` modifier present. No cross-function risk. Max bounty: Informational ($1k-$5k), not worth submission effort vs opportunity cost.

---

## ACTION TAKEN
- Marked Usual Labs as EXHAUSTED in bounty_pipeline.json
- Pivoting to parallel capital generation tracks (see rapid_vectors.md)
- No further cycles allocated to Usual Labs unless new contract version deployed

## LESSONS LEARNED
- Always validate rounding hypotheses with Foundry before deep analysis
- Oracle timeout ≠ price drift tolerance; check depeg guards first
- Micro-bounty platforms (Algora/Opire/Drips) require human KYC — agent cannot complete autonomously
