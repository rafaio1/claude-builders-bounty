# GitHub Claim Alert Monitor

This monitor provides operational awareness for claim assignment, claim release,
and objective claim deadlines. It is intentionally separate from the financial
Telegram gate: a claim, escrow, bounty, or promised reward is not realized
revenue.

## Sources and actions

- Reads at most 50 recent participating GitHub notifications per cycle.
- Fetches at most 30 official issue or pull-request resources.
- Recognizes bot-confirmed assignment/release and dated action requests.
- Sends at most five new Telegram alerts in one run.
- Does not comment, claim, submit, merge, transfer funds, or mark notifications
  as read.
- Retries Telegram delivery at most three times and never retries GitHub 401/403
  indefinitely.

The server-side monitor uses `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` from
`/Agentic/.env`. Secret values are never written to the state or repository.

## State

`/Agentic/state/github_claim_alert_state.json` stores event fingerprints,
active deadlines, and sent reminders. Writes are atomic and mode `0600`.
Known deadlines produce one reminder at each crossed threshold: 24 hours,
6 hours, and 1 hour. A final expiry alert asks for official-state verification.

## Email channel

Email monitoring is a separate Codex heartbeat because the valid Gmail
connection is local to Codex; the legacy server OAuth currently returns
`invalid_grant`. The heartbeat searches bounded recent mail, confirms events at
their official source, deduplicates by fingerprint in Gmail Sent, emails `me`,
and notifies the Codex task only for a new actionable event.

## Verification

```bash
python3 -m pytest -q tests/test_github_claim_alert_monitor.py
systemd-analyze verify deploy/systemd/agentic-github-claim-alert.service \
  deploy/systemd/agentic-github-claim-alert.timer
systemctl start agentic-github-claim-alert.service
systemctl enable --now agentic-github-claim-alert.timer
systemctl status agentic-github-claim-alert.timer --no-pager
```
