#!/usr/bin/env bash
# Install Claude Code pre-tool-use hook for blocking destructive commands
set -euo pipefail

HOOK_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/hooks/pre_tool_use_block_destructive.py"
HOOK_DIR="$HOME/.claude/hooks"
HOOK_DEST="$HOOK_DIR/pre_tool_use_block_destructive.py"

echo "📦 Installing Claude Code destructive-command safety hook..."

mkdir -p "$HOOK_DIR"
cp "$HOOK_SRC" "$HOOK_DEST"
chmod +x "$HOOK_DEST"

echo "✅ Hook installed to: $HOOK_DEST"
echo ""
echo "Blocked patterns:"
echo "  • rm -rf, shred"
echo "  • DROP TABLE/DATABASE, TRUNCATE, DELETE FROM without WHERE"
echo "  • git push --force, git reset --hard, git clean -fd"
echo "  • dd to /dev/, mkfs, chmod 777 on root paths"
echo ""
echo "Blocked attempts are logged to: $HOOK_DIR/blocked.log"
echo ""
echo "To uninstall: rm $HOOK_DEST"
