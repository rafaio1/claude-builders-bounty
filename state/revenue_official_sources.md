# Official bounty source notes - 2026-08-27

Use these as connector inputs, not as proof of a payable work order. Every candidate must be revalidated at ingestion time.

## Algora

- Official SDK: `https://github.com/algora-io/sdk` (`@algora/sdk`, bounty list query).
- Official bounty board example: `https://algora.io/projectdiscovery/bounties?status=open`.
- Hard gate requires the Algora bounty record plus the linked GitHub issue to be open, unrewarded, claimable, and compatible with the repository contribution policy.
- The board currently labels ProjectDiscovery Nuclei issues #6674 and #6532 as open, but both linked GitHub issues are closed; #6674 is also marked rewarded. Reject both. A platform board alone is insufficient.
- Claim count must reduce probability/EV. Do not start highly contested work unless expected value per engineering hour remains positive after duplication risk.

## Opire

- Official lifecycle: `https://docs.opire.dev/rewards/lifecycle`.
- Official app: `https://app.opire.dev/home`.
- Lifecycle is try -> implement -> PR -> claim -> creator selects/pays -> Stripe payout, commonly 1-7 business days after payment.
- Terms state the bounty creator, not Opire, is responsible for payment. Apply conservative payer-history probability.
- Public listings include obviously implausible or stale amounts. Never trust displayed amount alone. Require an official reward identifier, linked open GitHub issue, creator identity, command/claim availability, current status, supported payout eligibility, and maintainer acceptance path.
- Opire pays through Stripe; do not claim Wise/crypto routing unless the user's verified payout configuration supports it.

## Connector contract

1. Use official SDK/API/page and linked GitHub API; no generic keyword scraping.
2. Store immutable source URLs, platform reward ID, observed timestamp, amount/currency, claim count and linked issue state.
3. Revalidate immediately before claim, implementation start and PR publication.
4. A PR URL, candidate comment or internal JSON is never bounty evidence.
5. Reject closed/rewarded/stale issues, self-created repos, inactive maintainers, unsupported payout, implausible amounts and missing claim path.
6. Import only as `lead_pending_claim_validation`; the Revenue Manager promotes after all gates.
