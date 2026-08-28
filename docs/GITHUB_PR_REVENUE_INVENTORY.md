# GitHub PR Revenue Inventory

`tools/github_pr_inventory.py` is the canonical, zero-LLM inventory for pull
requests authored by `rafaio1`. It exists to prevent old PR text, self-written
claim language, or symbolic bounty farms from becoming revenue forecasts.

## Contract

- GitHub search is split into `merged`, `open`, and `closed_unmerged` queries.
  Each query fails closed at GitHub's 1,000-result search cap and pagination is
  accepted only when the collected count exactly matches `issueCount`.
- Text written by `rafaio1` is never payment evidence, including comments or
  reviews where GitHub reports an elevated repository association.
- A payment signal needs an explicit monetary promise from a repository
  `OWNER`, `MEMBER`, `COLLABORATOR`, or a known marketplace bot. Negations,
  ineligibility, duplicate selection, payment to another person, and truncated
  evidence windows prevent promotion.
- A promise is not realized revenue. Merged work remains
  `settlement_validation_required` until the Revenue Control Plane verifies a
  provider transaction through its separate settlement contract.
- Technical feedback is limited to current PR comments/reviews from a
  maintainer. Linked issue specifications, positive approvals, and terminal
  duplicate/rejection messages do not create work.

The collector does not import leads into the Revenue Control Plane. Its output
is an evidence-gated discovery source only.

## Runtime artifacts

All generated files are mode `0600`, ignored by Git, and written atomically:

- `/Agentic/state/github_pr_inventory.json`: complete PR metadata plus bounded
  evidence and classifications.
- `/Agentic/state/github_pr_followups.json`: only actionable follow-ups.
- `/Agentic/state/github_pr_inventory_success.json`: completion manifest,
  written last. Consumers must require matching `run_id` and `source_hash` in
  all three files plus `status=complete` before using a run. The manifest is
  first invalidated with `status=writing`, so an interrupted publication cannot
  leave an older success pointer attached to newer partial files.

`inventory_complete` means every PR from the three disjoint search partitions
was collected. `evidence_complete` is separate and may be false when GitHub
reports more comments, reviews, or linked issues than the bounded evidence
window. Incomplete evidence can never create a payment signal.

## Service

`agentic-github-pr-inventory.timer` refreshes the inventory every six hours.
The service has bounded GitHub retries and never invokes Codex or GhostCLI.

Validation commands:

```bash
cd /Agentic
python3 -m pytest -q tests/test_github_pr_inventory.py
systemctl status agentic-github-pr-inventory.timer --no-pager
systemctl status agentic-github-pr-inventory.service --no-pager
journalctl -u agentic-github-pr-inventory.service -n 30 --no-pager
```

No dashboard, PR comment, or ledger keyword is proof of cash. Financial truth
continues to come only from the canonical settlement verifier and realized
revenue ledger.
