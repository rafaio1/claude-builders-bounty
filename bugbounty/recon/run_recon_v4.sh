#!/bin/bash
set -e
export PATH=$PATH:/root/go/bin
OUTDIR="/Agentic/bugbounty/recon/results"
LOGFILE="$OUTDIR/expanded_run_v4.log"

# Single target deep scan to validate pipeline end-to-end
TARGET="shopify.com"
SAFE_NAME="shopify_com"

echo "[*] Starting Deep Recon V4 on $TARGET ($(date -u +%Y-%m-%dT%H:%M:%SZ))..." | tee "$LOGFILE"

echo "[+] Enumerating subdomains (all sources)..." | tee -a "$LOGFILE"
subfinder -d $TARGET -silent -all -o $OUTDIR/subs_${SAFE_NAME}.txt 2>/dev/null || true
SUB_COUNT=$(wc -l < $OUTDIR/subs_${SAFE_NAME}.txt 2>/dev/null || echo 0)
echo "  -> Found $SUB_COUNT subdomains" | tee -a "$LOGFILE"

if [ "$SUB_COUNT" -gt 0 ]; then
    echo "[+] Probing live hosts with tech detection..." | tee -a "$LOGFILE"
    httpx -l $OUTDIR/subs_${SAFE_NAME}.txt \
      -silent -tech-detect -status-code -title \
      -follow-redirects -timeout 7 -threads 20 \
      -o $OUTDIR/live_${SAFE_NAME}.txt 2>/dev/null || true
    
    LIVE_COUNT=$(wc -l < $OUTDIR/live_${SAFE_NAME}.txt 2>/dev/null || echo 0)
    echo "  -> $LIVE_COUNT live hosts" | tee -a "$LOGFILE"
    
    if [ "$LIVE_COUNT" -gt 0 ]; then
        echo "[+] Running Nuclei critical/high scan (rate-limited)..." | tee -a "$LOGFILE"
        nuclei -l $OUTDIR/live_${SAFE_NAME}.txt \
          -severity critical,high \
          -rate-limit 30 -timeout 8 -retries 1 \
          -bulk-size 25 -c 10 \
          -o $OUTDIR/nuclei_${SAFE_NAME}.txt \
          -silent 2>/dev/null || true
        
        FOUND=$(wc -l < $OUTDIR/nuclei_${SAFE_NAME}.txt 2>/dev/null || echo 0)
        echo "  -> $FOUND potential findings" | tee -a "$LOGFILE"
        
        if [ "$FOUND" -gt 0 ]; then
            echo "[!] FINDINGS:" | tee -a "$LOGFILE"
            cat $OUTDIR/nuclei_${SAFE_NAME}.txt | tee -a "$LOGFILE"
        fi
    else
        echo "[-] No live hosts found for $TARGET" | tee -a "$LOGFILE"
    fi
else
    echo "[-] No subdomains enumerated for $TARGET" | tee -a "$LOGFILE"
fi

echo "[*] V4 Cycle Complete ($(date -u +%Y-%m-%dT%H:%M:%SZ))" | tee -a "$LOGFILE"
