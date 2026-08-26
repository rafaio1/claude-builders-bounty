#!/bin/bash
# Bulk purge for GitHub notification flood
# Uses Gmail filter XML + IMAP fallback for immediate relief

CLEANUP_DIR="/Agentic/revenue/email-cleanup"
LOG="/Agentic/logs/revenue/bulk_purge_$(date +%Y%m%d_%H%M%S).log"

echo "=== BULK GITHUB EMAIL PURGE - $(date -u) ===" | tee "$LOG"

# 1. Generate aggressive filter for ClankerNation/OpenAgents specifically
cat > "$CLEANUP_DIR/github_aggressive_filters.xml" << 'XML'
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:apps="http://schemas.google.com/apps/2006">
  <entry>
    <title>GitHub Flood - ClankerNation Auto-Delete</title>
    <apps:property name="hasTheWord" value="ClankerNation OR OpenAgents OR PR #5871 OR feat(api): add WebSocket"/>
    <apps:property name="from" value="github.com"/>
    <apps:property name="shouldTrash" value="true"/>
    <apps:property name="shouldNeverSpam" value="false"/>
  </entry>
  <entry>
    <title>GitHub PR Notifications - Auto Archive</title>
    <apps:property name="subject" value="Re: ["/>
    <apps:property name="from" value="notifications@github.com"/>
    <apps:property name="shouldArchive" value="true"/>
    <apps:property name="shouldMarkAsRead" value="true"/>
    <apps:property name="label" value="GitHub/Archived"/>
  </entry>
  <entry>
    <title>GitHub All Notifications - Skip Inbox</title>
    <apps:property name="from" value="noreply@github.com"/>
    <apps:property name="shouldNeverSendSpam" value="true"/>
    <apps:property name="shouldAlwaysMarkAsImportant" value="false"/>
    <apps:property name="label" value="GitHub/Bulk"/>
  </entry>
</feed>
XML

echo "[OK] Aggressive filters generated: $CLEANUP_DIR/github_aggressive_filters.xml" | tee -a "$LOG"

# 2. Check if IMAP credentials available for instant purge
if [ -n "$GMAIL_USER" ] && [ -n "$GMAIL_APP_PASSWORD" ]; then
    echo "[AUTO] Running IMAP bulk delete..." | tee -a "$LOG"
    python3 "$CLEANUP_DIR/imap_cleanup.py" 2>&1 | tee -a "$LOG"
else
    echo "[MANUAL] IMAP credentials not set. Import filters manually:" | tee -a "$LOG"
    echo "  1. Open https://mail.google.com/#settings/filters" | tee -a "$LOG"
    echo "  2. Click 'Import filters'" | tee -a "$LOG"
    echo "  3. Upload: $CLEANUP_DIR/github_aggressive_filters.xml" | tee -a "$LOG"
    echo "  4. Confirm all 3 rules" | tee -a "$LOG"
fi

# 3. Generate one-click search link for manual bulk delete
echo "" | tee -a "$LOG"
echo "=== MANUAL BULK DELETE LINKS (Open in browser) ===" | tee -a "$LOG"
echo "https://mail.google.com/mail/u/0/#search/from%3Agithub.com+ClankerNation" | tee -a "$LOG"
echo "https://mail.google.com/mail/u/0/#search/from%3Anotifications%40github.com+subject%3ARe%3A+%5B" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "Select all → Delete forever to clear existing flood" | tee -a "$LOG"

echo "=== PURGE SETUP COMPLETE ===" | tee -a "$LOG"
