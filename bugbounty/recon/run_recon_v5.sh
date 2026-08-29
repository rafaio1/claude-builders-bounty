#!/bin/bash
set -e
export PATH=$PATH:/root/go/bin
OUTDIR="/Agentic/bugbounty/recon/results"
LOGFILE="$OUTDIR/expanded_run_v5.log"

# Pivot to API/Mobile/Less-WAF targets and government/edu (often less protected)
TARGETS=(
  "api.stripe.com"
  "api.twilio.com"
  "api.github.com"
  "nasa.gov"
  "irs.gov"
  "dod.gov"
  "usps.com"
  "amtrak.com"
)

echo "[*] Starting Strategic Recon V5 - API & Gov Focus ($(date -u +%Y-%m-%dT%H:%M:%SZ))..." | tee "$LOGFILE"

for TARGET in "${TARGETS[@]}"; do
    SAFE_NAME=$(echo $TARGET | sed 's/[^a-zA-Z0-9]/_/g')
    
    echo "[+] Processing $TARGET..." | tee -a "$LOGFILE"
    
    # For APIs, skip subfinder if it's already a specific endpoint, otherwise enum
    if [[ "$TARGET" == *.*.* ]]; then
        echo "$TARGET" > $OUTDIR/subs_${SAFE_NAME}.txt
    else
        subfinder -d $TARGET -silent -all -o $OUTDIR/subs_${SAFE_NAME}.txt 2>/dev/null || true
    fi
    
    SUB_COUNT=$(wc -l < $OUTDIR/subs_${SAFE_NAME}.txt 2>/dev/null || echo 0)
    echo "  -> $SUB_COUNT targets" | tee -a "$LOGFILE"
    
    if [ "$SUB_COUNT" -gt 0 ]; then
        httpx -l $OUTDIR/subs_${SAFE_NAME}.txt \
          -silent -tech-detect -status-code -title \
          -follow-redirects -timeout 8 -threads 15 \
          -o $OUTDIR/live_${SAFE_NAME}.txt 2>/dev/null || true
        
        LIVE_COUNT=$(wc -l < $OUTDIR/live_${SAFE_NAME}.txt 2>/dev/null || echo 0)
        echo "  -> $LIVE_COUNT responsive" | tee -a "$LOGFILE"
        
        if [ "$LIVE_COUNT" -gt 0 ]; then
            nuclei -l $OUTDIR/live_${SAFE_NAME}.txt \
              -severity critical,high \
              -rate-limit 20 -timeout 10 -retries 1 \
              -bulk-size 15 -c 5 \
              -tags cve,rce,sqli,ssrf,takeover,auth-bypass \
              -o $OUTDIR/nuclei_${SAFE_NAME}.txt \
              -silent 2>/dev/null || true
            
            FOUND=$(wc -l < $OUTDIR/nuclei_${SAFE_NAME}.txt 2>/dev/null || echo 0)
            echo "  -> $FOUND findings" | tee -a "$LOGFILE"
            
            if [ "$FOUND" -gt 0 ]; then
                cat $OUTDIR/nuclei_${SAFE_NAME}.txt | tee -a "$LOGFILE"
            fi
        fi
    fi
done

echo "[*] V5 Cycle Complete ($(date -u +%Y-%m-%dT%H:%M:%SZ))" | tee -a "$LOGFILE"
