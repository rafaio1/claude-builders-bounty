# Drips GitHub qualification lane

`tools/drips_github_qualifier.py` consumes the current, matching and unexpired
Drips discovery snapshot. It audits at most one previously unseen candidate per
cycle using only public GitHub `GET` requests. No token, `.env`, LLM or browser
session is loaded.

## Why this stage exists

The Drips API can change from zero to one or more applications within seconds.
It can also carry stale GitHub fields, inflated complexity, missing repository
paths or old completed work. A Drips detail response therefore proves only a
discovery lead; it does not prove that applying or starting code is safe.

This lane validates:

- exact public, non-fork, non-archived repository identity;
- live open and unassigned GitHub issue identity;
- complete issue comments and a bounded timeline;
- no `wave:application-id` comment or linked pull-request activity;
- Drips points against any GitHub `100/150/200-points` label;
- declared complexity against broad integration/coverage/benchmark scope;
- complete default-branch tree and grounded referenced files/directories;
- detectable license, CI, tests, recent push and recent merged-PR history;
- testable acceptance criteria and enough Wave deadline margin.

Any ambiguity rejects the candidate. A score of 75 is considered technically
qualified only after every hard gate passes. Even a technically qualified item
keeps these fields false:

- `application_allowed`
- `implementation_allowed`
- `automation_eligible`

Identity, current terms, KYC, Turnstile, authenticated quotas, a final
just-in-time Drips/GitHub revalidation and maintainer assignment remain separate
mandatory gates.

## Rate and cache contract

The server IP has a shared unauthenticated GitHub allowance. Every cycle first
checks `/rate_limit`, refuses to start unless at least 16 public requests remain
(leaving roughly ten after an audit), and audits at most one
new candidate. One audit uses six public reads: repository, issue, comments,
timeline, recursive tree and recent closed pull requests.

Qualified receipts are reused for at most 15 minutes; rejected receipts for at
most 60 minutes. Output validity never extends beyond the source Drips
snapshot. The cache is bounded to 200 entries and all files are written
atomically with mode `0600`.

## Artifacts

- `/Agentic/state/drips_github_qualifications.json`
- `/Agentic/state/drips_github_qualifications_success.json`
- `/Agentic/state/drips_github_qualification_cache.json`

Consumers require `status=complete`, matching `run_id` and `source_hash`, and a
future `valid_until`. Points have no fixed USD value and realized revenue stays
US$0 until canonical settlement evidence exists.
