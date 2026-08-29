#!/bin/bash
set -e
export PATH=$PATH:/root/go/bin
OUTDIR="/Agentic/bugbounty/recon/results"

# Expanded high-value public program scopes (placeholders for automation framework)
TARGETS=(
  "https://bugcrowd.com"
  "https://yahoo.com"
  "https://paypal.com"
  "https://shopify.com"
  "https://airbnb.com"
)

echo "[*] Starting Expanded BugBounty Recon Cycle ($(date -u +%Y-%m-%dT%H:%M:%SZ))..."
for TARGET in "${TARGETS[@]}"; do
    SAFE_NAME=$(echo $TARGET | sed 's/[^a-zA-Z0-9]/_/g')
    
    # Skip if already processed in this cycle to save time/resources
    if [ -f "$OUTDIR/nuclei_${SAFE_NAME}.txt" ] && [ -s "$OUTDIR/nuclei_${SAFE_NAME}.txt" ]; then
        echo "[~] Skipping $TARGET (already scanned)"
        continue
    fi

    echo "[+] Enumerating subdomains for $TARGET..."
    subfinder -d $(echo $TARGET | sed 's|https\?://||') -silent -o $OUTDIR/subs_${SAFE_NAME}.txt 2>/dev/null || true
    
    echo "[+] Probing live hosts..."
    if [ -f "$OUTDIR/subs_${SAFE_NAME}.txt" ] && [ -s "$OUTDIR/subs_${SAFE_NAME}.txt" ]; then
        httpx -l $OUTDIR/subs_${SAFE_NAME}.txt -silent -o $OUTDIR/live_${SAFE_NAME}.txt 2>/dev/null || true
    fi
    
    echo "[+] Running Nuclei critical/high templates..."
    if [ -f "$OUTDIR/live_${SAFE_NAME}.txt" ] && [ -s "$OUTDIR/live_${SAFE_NAME}.txt" ]; then
        nuclei -l $OUTDIR/live_${SAFE_NAME}.txt -severity critical,high -o $OUTDIR/nuclei_${SAFE_NAME}.txt -silent -timeout 10 2>/dev/null || true
    else
        echo "[-] No live hosts found for $TARGET"
    fi
done
echo "[*] Expanded recon cycle complete."
