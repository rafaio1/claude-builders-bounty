# Solana Ecosystem Auto-Updating Report & Interactive Dashboard

**Target Bounty:** Superteam Canada ($1,000 USDG)
**Status:** Scaffolded (Draft Architecture)
**Deadline:** ~24h remaining

## Concept
A Streamlit-based dashboard that aggregates key Solana ecosystem metrics via Dune Analytics API and on-chain RPC, providing an auto-updating weekly report for the Canadian Solana community.

## Proposed Tech Stack
- **Frontend:** Streamlit (Python)
- **Data Sources:** 
  - Dune Analytics API (TVL, DEX Volume, Active Addresses)
  - Solana RPC (Staking yield, TPS)
  - Coingecko API (Price, Market Cap)
- **Auto-Update:** GitHub Actions cron job to refresh cached JSON data every 6h
- **Deployment:** Streamlit Cloud or Vercel

## Key Metrics to Track
1. Total Value Locked (TVL) in Canadian-focused protocols
2. Weekly DEX volume trends
3. New wallet creation rate
4. Developer activity (GitHub commits for top Solana projects)
5. Staking participation rate

## Next Steps
- [ ] Verify exact submission requirements from bounty listing (site currently returning errors)
- [ ] Obtain Dune Analytics API key
- [ ] Build data ingestion pipeline
- [ ] Create visualization components
- [ ] Write accompanying analysis report

## Notes
- Superteam Earn site experiencing intermittent 500/404 errors; will retry scraping later
- Focusing on modular architecture to allow quick adaptation if requirements differ
