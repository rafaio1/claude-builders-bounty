#!/usr/bin/env python3
import time
from datetime import datetime, timezone
print(f"[{datetime.now(timezone.utc).isoformat()}] Service Agent: Scanning AgentMail for gigs...")
time.sleep(3600)  # Scan every hour
