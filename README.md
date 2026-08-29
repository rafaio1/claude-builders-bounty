# Pre-Tool-Use Hook: Block Dangerous Bash Commands

A Claude Code `pre-tool-use` hook that intercepts and blocks dangerous bash commands before execution.

## Blocked Patterns
- `rm -rf` (recursive force delete)
- `DROP TABLE` (SQL destructive DDL)
- `git push --force` (history rewrite)
- `TRUNCATE` (SQL table wipe)
- `DELETE FROM` without `WHERE` clause (unconditional mass delete)

## Installation

```bash
# 1. Copy the hook to your Claude hooks directory
mkdir -p ~/.claude/hooks/pre-tool-use
cp block-dangerous.sh ~/.claude/hooks/pre-tool-use/
chmod +x ~/.claude/hooks/pre-tool-use/block-dangerous.sh

# 2. Verify installation
ls -la ~/.claude/hooks/pre-tool-use/block-dangerous.sh
```

## Logging

All blocked attempts are logged to `~/.claude/hooks/blocked.log` with format:
```
TIMESTAMP	REASON	PATH	COMMAND
```

## Behavior

- **Safe commands**: Pass through without interference
- **Dangerous commands**: Blocked with clear JSON reason message
- **Logging**: Every block is timestamped and recorded
- **Non-intrusive**: Only activates on bash tool calls

## Example Output

When a dangerous command is blocked, Claude receives:
```json
{"decision":"block","reason":"rm -rf is disabled by safety hook"}
```

## Testing

Test the hook manually:
```bash
echo '{"tool_input":{"command":"rm -rf /"}}' | ~/.claude/hooks/pre-tool-use/block-dangerous.sh
cat ~/.claude/hooks/blocked.log
```
