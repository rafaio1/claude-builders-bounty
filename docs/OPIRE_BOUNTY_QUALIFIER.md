# Opire code-bounty qualifier

`tools/opire_bounty_qualifier.py` is a read-only discovery and qualification
lane. It replaces generic `bounty`-label guessing with official evidence.

Every run reads the official Opire `rewards` API using the `NOBODY` filter,
then audits at most one previously unseen reward against live GitHub data. It
requires all of the following before calling a record `qualified`:

- a canonical public GitHub issue and an official USD-cent Opire reward;
- zero Opire trying/claimer users and no `/try`, `/claim`, or linked PR found;
- open, unlocked, unassigned issue written by a repository authority;
- public, non-fork, non-archived, licensed and recently active repository;
- at least one recent merged PR, CI, tests, and a testable scope;
- no mandatory physical-device, hardware, proprietary API, or video evidence;
- a bounded value suitable for automatic review.

The cache makes scans incremental. Results and manifests are atomically written
mode `0600` under `/Agentic/state`. GitHub authentication is read from the
existing `gh` configuration; the token is never logged or passed on the command
line.

Qualification is not permission to claim or start implementation. The output
keeps `application_allowed`, `implementation_allowed`, and
`revenue_recognition_allowed` false. Before a claim, the operator must verify
the user's Opire OAuth, terms/age, Stripe Connect payout, and revalidate the
reward and competition. Only a rewarded and settled payout may enter realized
revenue.

The systemd timer runs every 30 minutes. Inspect it with:

```sh
systemctl status agentic-opire-bounty-qualifier.timer
journalctl -u agentic-opire-bounty-qualifier.service -n 50 --no-pager
python3 -m json.tool /Agentic/state/opire_bounty_qualifications.json
```
