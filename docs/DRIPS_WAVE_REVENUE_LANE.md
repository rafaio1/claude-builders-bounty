# Drips Wave revenue lane

`tools/drips_wave_scanner.py` is a read-only discovery and revalidation stage
for the official Stellar Drips Wave program. It deliberately does **not** log
in, accept terms, complete KYC, apply to an issue, write code, or submit a pull
request.

## Financial contract

- The active Wave's USD budget is a shared pool, not the bounty amount of an
  individual issue.
- Points do not have a fixed USD value and are never booked as revenue.
- Every candidate and every scan report `realized_revenue_usd: 0.0` until a
  canonical provider or wallet transaction is independently reconciled.
- A candidate is only a lead. It cannot become an implementation task merely
  because it ranks highly.

## Official evidence

The scanner reads only these public HTTPS surfaces:

- `GET https://wave-api.drips.network/api/wave-programs/<program-id>`
- `GET https://wave-api.drips.network/api/wave-programs/<program-id>/waves`
- `GET https://wave-api.drips.network/api/issues?...`
- `GET https://wave-api.drips.network/api/issues/<issue-id>`

The program identity is pinned to the Stellar program UUID and slug. Exactly
one active Wave must cover the current UTC time, and the program must report
`paused: false`.

## Bounded scan and ranking

The default cycle reads five recent pages of 50 issues. The public request uses
the official filters for unassigned issues without applications or pull
requests that are eligible for and included in the program. It is intentionally
reported as a bounded window; `global_market_complete` remains false whenever
the API advertises another page. The scanner never claims that the bounded
window represents the entire market.

An issue is excluded when it is closed, assigned on either Drips or GitHub,
has any pending application, already has a linked PR or completion, belongs to
another program, lacks Points, or has inconsistent GitHub repository evidence.
The highest-ranked records are fetched again from their canonical per-issue
endpoint immediately before being written. Ranking is deterministic and uses
Points per coarse complexity unit, issue freshness, and an acceptance-criteria
clarity bonus. It is prioritization, not a payment estimate.

## Lifecycle gates

The persisted workflow is:

1. `application_candidate` — public state is open, unassigned and has zero
   pending applications after detail revalidation.
2. `application_ready` — only after the user personally accepts the current
   terms, authenticates with GitHub and completes KYC; the issue must be
   revalidated again. A separate executor must also prove a healthy live GitHub
   issue/repository, non-trivial scope, remaining user and organization quota,
   no account restriction or self-owned issue, and a valid Turnstile challenge.
3. `application_submitted` — requires a durable Drips/GitHub application
   receipt. No implementation starts in this state.
4. `assigned` — requires the official Drips detail to name `rafaio1` as the
   assigned applicant or equivalent maintainer assignment evidence.
5. `implementing` -> `pr_submitted` -> `merged` — each transition requires its
   own Git/test/PR/maintainer receipt.
6. `points_awarded` -> `payout_available` -> `settled` — Points remain
   non-financial. Only the final provider or wallet transaction can create
   realized revenue.

The scanner implements stage 1 and emits the remaining gates as false. The
OAuth, terms and KYC stages are intentionally personal and are not represented
by a server-side cookie or copied browser credential.

## Runtime artifacts

- `/Agentic/state/drips_wave_candidates.json` — candidate queue and policy.
- `/Agentic/state/drips_wave_candidates_success.json` — completion manifest.

Discovery consumers must require the same `run_id` and `source_hash`, plus
manifest `status=complete`, `drips_detail_evidence_complete=true`, and a future
`valid_until`. The scanner intentionally publishes
`github_live_evidence_complete=false` and `candidate_evidence_complete=false`:
an application executor must cross-check the live GitHub issue/repository and
all authenticated identity/quota gates. A failed collection replaces the
manifest with `status=failed`, so a stale success cannot be mistaken for a
current scan.

Run manually:

```bash
python3 /Agentic/tools/drips_wave_scanner.py --pages 5 --top 10
```

The systemd timer performs the same bounded scan every ten minutes. Each
successful snapshot expires after twelve minutes (or at the Wave end, whichever
comes first). It uses no LLM and therefore does not consume GhostCLI or Codex
tokens.
