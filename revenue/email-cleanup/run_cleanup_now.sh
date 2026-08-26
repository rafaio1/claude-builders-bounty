#!/bin/bash
# Immediate GitHub email cleanup via Gmail API
# Uses pre-generated script with fallback to manual filter import

CLEANUP_DIR="/Agentic/revenue/email-cleanup"
LOG_FILE="/Agentic/logs/revenue/github_cleanup_$(date +%Y%m%d_%H%M%S).log"

echo "=== GitHub Email Cleanup - $(date -u) ===" | tee "$LOG_FILE"

# Check if OAuth credentials exist
if [ -f "$CLEANUP_DIR/credentials.json" ]; then
    echo "[AUTO] Running programmatic cleanup..." | tee -a "$LOG_FILE"
    cd "$CLEANUP_DIR" && python3 github_cleanup.py 2>&1 | tee -a "$LOG_FILE"
else
    echo "[MANUAL] OAuth credentials not found. Generating import instructions..." | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
    echo "To clean your Gmail NOW:" | tee -a "$LOG_FILE"
    echo "1. Open https://mail.google.com/#settings/filters" | tee -a "$LOG_FILE"
    echo "2. Click 'Import filters' at bottom" | tee -a "$LOG_FILE"
    echo "3. Upload: $CLEANUP_DIR/github_filters.xml" | tee -a "$LOG_FILE"
    echo "4. Check all 3 filters and click 'Create filters'" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
    echo "Filter contents:" | tee -a "$LOG_FILE"
    cat "$CLEANUP_DIR/github_filters.xml" | tee -a "$LOG_FILE"
fi

echo "=== Cleanup process finished ===" | tee -a "$LOG_FILE"
