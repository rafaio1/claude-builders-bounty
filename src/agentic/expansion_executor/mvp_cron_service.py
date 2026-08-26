 """MVP horizontal: cron service health check (read-only, no account/capital)."""
 from __future__ import annotations
 
 import json
 import subprocess
 from datetime import datetime, timezone
 from pathlib import Path
 from typing import Dict, List
 
 
 def check_cron_services(units: List[str] | None = None) -> Dict:
     """Verify systemd timer/service status without mutating state."""
     targets = units or [
         "agentic-improve-dev.timer",
         "agentic-improve-map.timer",
         "agentic-improve-review.timer",
         "agentic-integrity.timer",
     ]
     results: List[Dict] = []
     for unit in targets:
         try:
             active = subprocess.run(
                 ["systemctl", "is-active", unit],
                 capture_output=True, text=True, timeout=5,
             )
             next_elapse = subprocess.run(
                 ["systemctl", "show", "-p", "NextElapse", "--value", unit],
                 capture_output=True, text=True, timeout=5,
             )
             results.append({
                 "unit": unit,
                 "active": active.stdout.strip(),
                 "next_elapse": next_elapse.stdout.strip() or "n/a",
             })
         except Exception as exc:  # noqa: BLE001
             results.append({"unit": unit, "active": "error", "error": str(exc)})
     return {
         "checked_at": datetime.now(timezone.utc).isoformat(),
         "mvp": "cron_service_health_check",
         "risk": "read_only_no_account_no_capital",
         "results": results,
     }
 
 
 def write_mvp_report(output_path: str, units: List[str] | None = None) -> Dict:
     report = check_cron_services(units)
     Path(output_path).parent.mkdir(parents=True, exist_ok=True)
     with open(output_path, "w", encoding="utf-8") as fh:
         json.dump(report, fh, indent=2, ensure_ascii=False)
     return report
