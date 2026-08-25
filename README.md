# Pre-Tool-Use Hook: Block Destructive Bash Commands

> 🏆 Submission for [Bounty #3](https://github.com/claude-builders-bounty/claude-builders-bounty/issues/3) ($100)

A Claude Code `pre-tool-use` hook that intercepts and blocks dangerous bash commands before execution, with comprehensive logging.

## Features

- ✅ **Blocks Destructive Patterns**: `rm -rf`, `DROP TABLE`, `git push --force`, `TRUNCATE`, `DELETE FROM` without WHERE, and more
- ✅ **Comprehensive Logging**: Every blocked attempt logged to `~/.claude/hooks/blocked.log` with timestamp, command, reason, and project path
- ✅ **Clear User Feedback**: Explains why the command was blocked and suggests safer alternatives
- ✅ **Fail-Open Design**: If input can't be parsed, allows execution (never breaks legitimate workflows)
- ✅ **Easy Installation**: One-command install script included

## Installation

```bash
# Clone or download this directory, then:
chmod +x install.sh
./install.sh
```

Or manually:
```bash
mkdir -p ~/.claude/hooks
cp hooks/pre_tool_use_block_destructive.py ~/.claude/hooks/
chmod +x ~/.claude/hooks/pre_tool_use_block_destructive.py
```

## Blocked Patterns

| Category | Pattern | Risk |
|----------|---------|------|
| File Deletion | `rm -rf`, `rm -r /absolute/path`, `shred` | Irreversible data loss |
| Database | `DROP TABLE/DATABASE`, `TRUNCATE`, `DELETE FROM x;`, `DELETE FROM x WHERE 1=1` | Mass data destruction |
| Git | `git push --force`, `git reset --hard`, `git clean -fd` | History overwrite / uncommitted loss |
| System | `dd if=... of=/dev/`, `mkfs.*`, `chmod 777 /` | Disk wipe / filesystem format / security hole |

## Log Format

Blocked attempts are appended to `~/.claude/hooks/blocked.log`:
```
[2026-08-25T12:30:00+00:00] BLOCKED | Reason: rm -rf: recursive force delete | Path: /home/user/project | Command: rm -rf node_modules/
```

## Acceptance Criteria Checklist

- [x] Hook follows Claude Code hooks format (`~/.claude/hooks/`)
- [x] Blocks: `rm -rf`, `DROP TABLE`, `git push --force`, `TRUNCATE`, `DELETE FROM` without WHERE
- [x] Logs every blocked attempt to `~/.claude/hooks/blocked.log` with timestamp, command, project path
- [x] Displays clear message explaining why the command was blocked
- [x] Install script included for easy setup

## How It Works

1. Claude Code invokes the hook before executing any Bash/shell tool
2. Hook reads JSON input from stdin containing `tool_name` and `input.command`
3. Command is checked against regex patterns for destructive operations
4. If matched: logs to file, prints explanation to stderr, exits with code 2 (blocks execution)
5. If safe: exits with code 0 (allows execution)

## Uninstall

```bash
rm ~/.claude/hooks/pre_tool_use_block_destructive.py
```

## License

MIT

---

*Built for the Claude Builders Bounty community · August 2026*
