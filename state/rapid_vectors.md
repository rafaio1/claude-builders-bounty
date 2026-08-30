# Rapid Payout Vectors (Parallel Track)

## Objective: Generate fast capital while bounty triage is pending
**Date:** 2026-08-30
**Infrastructure Available:** Bybit API (live), Wise (R$100 BRL), GhostCLI orchestration

---

## Vector 1: Bybit Spot Arbitrage (USDC/USDT Peg Gaps)
- **Mechanism:** Monitor USDC/USDT spread on Bybit spot. When deviation > 0.15%, execute round-trip arb.
- **Capital Required:** $500-$2k USDT (need to fund from Wise → Kraken → Bybit)
- **Expected Return:** 0.1-0.3% per cycle, 5-20 cycles/day during volatility
- **Risk:** Low (same-exchange, no withdrawal risk)
- **Status:** ⚠️ BLOCKED — Current Wise balance R$100 (~$18 USD) insufficient for meaningful arb. Need seed capital injection or bounty payout first.

## Vector 2: Sherlock Quick-Triage Bounties (Sub-$5k tier)
- **Mechanism:** Target "Low" and "Informational" severity findings in active contests. These get triaged in 48-72h vs weeks for Medium+.
- **Target Contests:** Check `revenue/sherlock_opportunities/` for active deadlines < 7 days.
- **Expected Payout:** $500-$3k per valid finding, paid within 2 weeks of contest end.
- **Action Now:** Scan current Sherlock contests for near-deadline opportunities where our Usual Labs analysis can be repurposed.

## Vector 3: Algora/Drips Open Source Micro-Bounties
- **Mechanism:** Claim pre-qualified bounties in `state/algora_bounty_qualifications_success.json` and `state/drips_github_qualifications_success.json`.
- **Expected Payout:** $50-$500 per PR, merged and paid within days.
- **Action Now:** Cross-reference qualified bounties with workspace repos that already have partial work.

## Vector 4: Galxe/Layer3 Quest Completion (Existing State)
- **Mechanism:** Execute quests already tracked in `revenue/galxe_opportunities/` and `revenue/layer3_opportunities/`.
- **Expected Payout:** Airdrop points + small token rewards ($10-$100 equivalent).
- **Note:** Low individual value but compounds; uses existing automation infrastructure.

## Immediate Priority Order
1. **Algora/Drips micro-bounties** — fastest path to first dollars, no capital needed
2. **Sherlock quick-triage** — leverage current Usual Labs analysis momentum
3. **Galxe/Layer3 quests** — background automation, passive accumulation
4. **Bybit arb** — REQUIRES CAPITAL INFUSION, defer until $500+ available

## Capital Flow Target
Wise (BRL) → Kraken (USDC) → Bybit (trading) → Kraken (withdraw) → Wise (USD/EUR)
