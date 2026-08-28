# Algora code-bounty qualifier

`tools/algora_bounty_qualifier.py` is the read-only replacement for the legacy
Algora scraper. It does not comment, run `/attempt`, claim, fork, create a pull
request, mutate the revenue ledger, or recognize advertised value as revenue.

Each run reads the most recently updated first 100 rows in a deliberately
bounded GitHub Search slice, then audits at most three uncached candidates. GitHub
Search is discovery only. A candidate is qualified only when all of these gates
pass:

- the comment author is the official `algora-pbc[bot]` account with the known
  GitHub Bot id and schema;
- every active bounty component has an unambiguous USD amount and sponsor;
- every sponsor's public Algora board contains the same open issue and amount;
- no component is withdrawn, malformed, or already awarded;
- there is no active/pending attempt, claim, assignee, or linked pull request;
- the issue is open and unlocked in a public, active, non-fork repository;
- license, CI, tests, recent merged-PR history, and a testable scope are proven;
- value and GitHub rate budgets remain inside bounded automatic-review limits.

Multiple sponsor components are summed in integer cents. A `Reward` link in an
attempt table is treated as a pending reward action, never as an award. Only a
separate official bot award comment proves an award. Struck-through bounty
headers are treated as withdrawn. A missing or conflicting Algora board fails
closed.

The discovery query is intentionally a prioritization slice, not a claim that
the entire Algora market was audited. Stable rejections are cached for seven
days, while source failures are retried after 30 minutes; any GitHub activity
changes the candidate key and forces a fresh audit. This lets later timer cycles
drain the slice without repeatedly spending GitHub quota. Results, cache, and
the completion manifest are written atomically with mode `0600` under
`/Agentic/state`.

Qualification is still not permission to act. Every output keeps
`application_allowed`, `implementation_allowed`, and
`revenue_recognition_allowed` false. Before any `/attempt`, a separate executor
must verify Algora OAuth, age/country/payout eligibility and revalidate the
issue, board, amount, attempts, claims, awards, and pull requests within 60
seconds. Only a settled payout enters realized revenue.

The systemd timer runs every 30 minutes and uses the existing authenticated
GitHub CLI configuration through a read-only bind. Inspect it with:

```sh
systemctl status agentic-algora-bounty-qualifier.timer
journalctl -u agentic-algora-bounty-qualifier.service -n 50 --no-pager
python3 -m json.tool /Agentic/state/algora_bounty_qualifications.json
```
