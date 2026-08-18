# block-destructive-hook

A Claude Code `pre-tool-use` hook that intercepts dangerous bash commands before execution.

## Installation

```bash
curl -o ~/.claude/hooks/block-destructive.sh https://raw.githubusercontent.com/rafaio1/block-destructive-hook/main/block-destructive.sh && chmod +x ~/.claude/hooks/block-destructive.sh
```

Or manually:

```bash
mkdir -p ~/.claude/hooks
cp block-destructive.sh ~/.claude/hooks/
chmod +x ~/.claude/hooks/block-destructive.sh
```

## Blocked Patterns

- `rm -rf` / `rm -fr` (recursive force delete)
- `DROP TABLE` (destructive SQL DDL)
- `git push --force` / `git push -f` (force-push)
- `TRUNCATE` (table truncation)
- `DELETE FROM` without `WHERE` clause (unbounded delete)

## Logging

All blocked attempts are logged to `~/.claude/hooks/blocked.log` with:
- UTC timestamp
- Project path
- Attempted command
- Block reason

## Behavior

- Non-blocking for safe commands (exit 0)
- Blocks destructive commands (exit 1 + JSON decision)
- Prints explanation to stderr so Claude understands why
- Does not interfere with normal bash usage
