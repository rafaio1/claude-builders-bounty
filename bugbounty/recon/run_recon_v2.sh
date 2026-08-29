#!/bin/bash
set -e
export PATH=$PATH:/root/go/bin
OUTDIR="/Agentic/bugbounty/recon/results"
LOGFILE="$OUTDIR/expanded_run_v2.log"

# High-value public programs with broad scopes and high bounties
TARGETS=(
  "yahoo.com"
  "paypal.com"
  "shopify.com"
  "airbnb.com"
  "uber.com"
)

echo "[*] Starting Expanded Recon V2 ($(date -u +%Y-%m-%dT%H:%M:%SZ))..." | tee -a "$LOGFILE"

for TARGET in "${TARGETS[@]}"; do
    SAFE_NAME=$(echo $TARGET | sed 's/[^a-zA-Z0-9]/_/g')
    
    echo "[+] Processing $TARGET..." | tee -a "$LOGFILE"
    
    # Subdomain enumeration (limit to 100 for speed in automated cycle)
    subfinder -d $TARGET -silent -nW -o $OUTDIR/subs_${SAFE_NAME}.txt 2>/dev/null || true
    
    # Probe live hosts with tech detection
    if [ -f "$OUTDIR/subs_${SAFE_NAME}.txt" ] && [ -s "$OUTDIR/subs_${SAFE_NAME}.txt" ]; then
        httpx -l $OUTDIR/subs_${SAFE_NAME}.txt -silent -tech-detect -status-code -title -o $OUTDIR/live_${SAFE_NAME}.txt 2>/dev/null || true
        
        # Run nuclei critical/high with rate limit to avoid bans
        if [ -f "$OUTDIR/live_${SAFE_NAME}.txt" ] && [ -s "$OUTDIR/live_${SAFE_NAME}.txt" ]; then
            nuclei -l $OUTDIR/live_${SAFE_NAME}.txt \
              -severity critical,high \
              -rate-limit 50 \
              -timeout 8 \
              -retries 1 \
              -o $OUTDIR/nuclei_${SAFE_NAME}.txt \
              -silent 2>/dev/null || true
            
            FOUND=$(wc -l < $OUTDIR/nuclei_${SAFE_NAME}.txt 2>/dev/null || echo 0)
            echo "  -> Found $FOUND potential issues for $TARGET" | tee -a "$LOGFILE"
        else
            echo "  -> No live hosts for $TARGET" | tee -a "$LOGFILE"
        fi
    else
        echo "  -> No subdomains found for $TARGET" | tee -a "$LOGFILE"
    fi
done

echo "[*] V2 Cycle Complete ($(date -u +%Y-%m-%dT%H:%M:%SZ))" | tee -a "$LOGFILE"
