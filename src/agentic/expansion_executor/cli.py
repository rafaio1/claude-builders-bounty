"""CLI entrypoint for expansion executor (systemd oneshot)."""
from __future__ import annotations

import argparse
import json
import sys

from .executor import ExpansionExecutor


def main() -> None:
    parser = argparse.ArgumentParser(description="Expansion Executor")
    parser.add_argument("--proposals", required=True)
    parser.add_argument("--verdicts", required=True)
    parser.add_argument("--state-output", required=True)
    parser.add_argument("--queue-output", required=True)
    parser.add_argument("--max-per-cycle", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true", default=False)
    args = parser.parse_args()

    executor = ExpansionExecutor(
        proposals_path=args.proposals,
        verdicts_path=args.verdicts,
        state_output=args.state_output,
        queue_output=args.queue_output,
        max_per_cycle=args.max_per_cycle,
        dry_run=args.dry_run,
    )
    summary = executor.run()
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
