# GitHub Claim Alert Monitor

This monitor provides operational awareness for claim assignment, release,
deadlines, maintainer decisions, and payment-status messages. It is
intentionally separate from the financial ledger: a claim, escrow balance,
internal credit, bounty, or promised reward is not realized revenue.

## Sources and actions

- Reads at most 50 recent participating GitHub notifications per cycle.
- Polls comments for known active claims with a durable per-claim cursor.
- Uses at most 30 GitHub API fetches in one cycle and rotates bounded active
  claims so one busy item cannot starve the others.
- Accepts assignment and release events only from a bot. A release must name
  the configured GitHub login directly.
- Accepts human action, acceptance, rejection, and payment-status events only
  from GitHub users associated as `OWNER`, `MEMBER`, or `COLLABORATOR`.
- Sends at most five Telegram operational alerts in one run.
- Does not comment, claim, submit, merge, transfer funds, mark notifications as
  read, or write to the financial ledger.
- Uses finite retries. GitHub or Telegram failures never become an infinite
  retry loop.

The server-side monitor uses `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` from
`/Agentic/.env`. Secret values are never written to state or the repository.

## Durable state and delivery

`/Agentic/state/github_claim_alert_state.json` stores claim state, event
history, cursors, delivered fingerprints, and a persistent Telegram outbox.
Writes are atomic and mode `0600`.

New GitHub events are written to history and the outbox before Telegram is
called. A delivery failure leaves the item pending for a later cycle. The
monitor does not advance the global notification checkpoint after an
incomplete GitHub poll, and a comment without a usable timestamp does not
advance that claim's cursor.

Terminal claims remain in history rather than disappearing. Financial stages
are monotonic, but even a platform message saying payment was confirmed remains
`settlement_candidate_requires_reconciliation`; an independent transaction and
balance reconciliation is required before revenue can be recorded.

Date-only deadlines are interpreted as the inclusive end of that UTC day.
Known deadlines produce one reminder at each crossed threshold: 24 hours,
6 hours, and 1 hour. A final expiry alert requests official-state verification.

## Email channel

Email monitoring is a separate Codex heartbeat because the valid Gmail
connection is local to Codex; the legacy server OAuth currently returns
`invalid_grant`. The heartbeat searches bounded recent mail, confirms events at
their official source, deduplicates by fingerprint in Gmail Sent, emails `me`,
and notifies the Codex task only for a new actionable event.

## Verification

```bash
python3 -m pytest -q tests/test_github_claim_alert_monitor.py
python3 tools/github_claim_alert_monitor.py --login rafaio1 --dry-run
systemd-analyze verify deploy/systemd/agentic-github-claim-alert.service \
  deploy/systemd/agentic-github-claim-alert.timer
systemctl start agentic-github-claim-alert.service
systemctl enable --now agentic-github-claim-alert.timer
systemctl status agentic-github-claim-alert.timer --no-pager
```
