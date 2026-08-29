#!/bin/bash
set -e
export PATH=$PATH:/root/go/bin
OUTDIR="/Agentic/bugbounty/recon/results"
LOGFILE="$OUTDIR/expanded_run_v6.log"

# Focus: Recently launched or less-hardened programs with high bounties
# These are examples of targets that typically have weaker initial defenses
TARGETS=(
  "reddit.com"
  "gitlab.com"
  "mattermost.com"
  "sentry.io"
  "elastic.co"
)

echo "[*] Starting Strategic Recon V6 - New/Less-Hardened Programs ($(date -u +%Y-%m-%dT%H:%M:%SZ))..." | tee "$LOGFILE"

for TARGET in "${TARGETS[@]}"; do
    SAFE_NAME=$(echo $TARGET | sed 's/[^a-zA-Z0-9]/_/g')
    
    echo "[+] Processing $TARGET..." | tee -a "$LOGFILE"
    
    # Enumerate subdomains
    subfinder -d $TARGET -silent -all -o $OUTDIR/subs_${SAFE_NAME}.txt 2>/dev/null || true
    
    SUB_COUNT=$(wc -l < $OUTDIR/subs_${SAFE_NAME}.txt 2>/dev/null || echo 0)
    echo "  -> Found $SUB_COUNT subdomains" | tee -a "$LOGFILE"
    
    if [ "$SUB_COUNT" -gt 0 ]; then
        # Probe live hosts
        httpx -l $OUTDIR/subs_${SAFE_NAME}.txt \
          -silent -tech-detect -status-code -title \
          -follow-redirects -timeout 8 -threads 20 \
          -o $OUTDIR/live_${SAFE_NAME}.txt 2>/dev/null || true
        
        LIVE_COUNT=$(wc -l < $OUTDIR/live_${SAFE_NAME}.txt 2>/dev/null || echo 0)
        echo "  -> $LIVE_COUNT responsive hosts" | tee -a "$LOGFILE"
        
        if [ "$LIVE_COUNT" -gt 0 ]; then
            # Run nuclei with broader template set for newer programs
            nuclei -l $OUTDIR/live_${SAFE_NAME}.txt \
              -severity critical,high,medium \
              -rate-limit 40 -timeout 10 -retries 1 \
              -bulk-size 30 -c 15 \
              -tags cve,rce,sqli,ssrf,takeover,auth-bypass,misconfig,default-login \
              -o $OUTDIR/nuclei_${SAFE_NAME}.txt \
              -silent 2>/dev/null || true
            
            FOUND=$(wc -l < $OUTDIR/nuclei_${SAFE_NAME}.txt 2>/dev/null || echo 0)
            echo "  -> $FOUND potential findings" | tee -a "$LOGFILE"
            
            if [ "$FOUND" -gt 0 ]; then
                echo "[!] FINDINGS DETECTED:" | tee -a "$LOGFILE"
                cat $OUTDIR/nuclei_${SAFE_NAME}.txt | tee -a "$LOGFILE"
            fi
        else
            echo "[-] No responsive hosts for $TARGET" | tee -a "$LOGFILE"
        fi
    else
        echo "[-] No subdomains found for $TARGET" | tee -a "$LOGFILE"
    fi
done

echo "[*] V6 Cycle Complete ($(date -u +%Y-%m-%dT%H:%M:%SZ))" | tee -a "$LOGFILE"
