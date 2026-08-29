#!/bin/bash
set -e
export PATH=$PATH:/root/go/bin
OUTDIR="/Agentic/bugbounty/recon/results"
LOGFILE="$OUTDIR/expanded_run_v3.log"

# Focused high-bounty targets with known broad scopes
TARGETS=(
  "shopify.com"
  "airbnb.com"
  "uber.com"
  "paypal.com"
  "yahoo.com"
)

echo "[*] Starting Targeted Recon V3 ($(date -u +%Y-%m-%dT%H:%M:%SZ))..." | tee -a "$LOGFILE"

for TARGET in "${TARGETS[@]}"; do
    SAFE_NAME=$(echo $TARGET | sed 's/[^a-zA-Z0-9]/_/g')
    
    echo "[+] Processing $TARGET..." | tee -a "$LOGFILE"
    
    # Fast subdomain enum (all sources, but silent)
    subfinder -d $TARGET -silent -all -o $OUTDIR/subs_${SAFE_NAME}.txt 2>/dev/null || true
    
    SUB_COUNT=$(wc -l < $OUTDIR/subs_${SAFE_NAME}.txt 2>/dev/null || echo 0)
    echo "  -> Found $SUB_COUNT subdomains" | tee -a "$LOGFILE"
    
    if [ "$SUB_COUNT" -gt 0 ]; then
        # Probe with tech detection and filtering
        httpx -l $OUTDIR/subs_${SAFE_NAME}.txt \
          -silent -tech-detect -status-code -title \
          -follow-redirects -timeout 5 \
          -o $OUTDIR/live_${SAFE_NAME}.txt 2>/dev/null || true
        
        LIVE_COUNT=$(wc -l < $OUTDIR/live_${SAFE_NAME}.txt 2>/dev/null || echo 0)
        echo "  -> $LIVE_COUNT live hosts" | tee -a "$LOGFILE"
        
        if [ "$LIVE_COUNT" -gt 0 ]; then
            # Nuclei scan: critical/high only, rate-limited for safety
            nuclei -l $OUTDIR/live_${SAFE_NAME}.txt \
              -severity critical,high \
              -rate-limit 30 \
              -timeout 7 \
              -retries 1 \
              -bulk-size 25 \
              -c 10 \
              -o $OUTDIR/nuclei_${SAFE_NAME}.txt \
              -silent 2>/dev/null || true
            
            FOUND=$(wc -l < $OUTDIR/nuclei_${SAFE_NAME}.txt 2>/dev/null || echo 0)
            echo "  -> $FOUND potential findings" | tee -a "$LOGFILE"
            
            if [ "$FOUND" -gt 0 ]; then
                cat $OUTDIR/nuclei_${SAFE_NAME}.txt | tee -a "$LOGFILE"
            fi
        fi
    fi
done

echo "[*] V3 Cycle Complete ($(date -u +%Y-%m-%dT%H:%M:%SZ))" | tee -a "$LOGFILE"
