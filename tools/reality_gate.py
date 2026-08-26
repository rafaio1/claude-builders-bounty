#!/usr/bin/env python3
"""
Reality-Gate Agent: Validates financial entries before ledger registration.
Blocks simulated/hallucinated revenue by requiring external evidence.

Usage:
  python reality_gate.py --validate <transaction_json>
  python reality_gate.py --audit-ledger /Agentic/data/aro/ledger.jsonl
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

EVIDENCE_DIR = Path("/Agentic/data/aro/evidence")
LEDGER_PATH = Path("/Agentic/data/aro/ledger.jsonl")

def has_valid_evidence(txn: dict) -> tuple[bool, str]:
    """Check if transaction has verifiable external evidence."""
    kind = txn.get("kind", "")
    
    # Only validate income/collect types
    if kind not in ("collect", "income", "payout_received"):
        return True, "non_financial_entry"
    
    ref = str(txn.get("reference", "")).lower()
    cid = str(txn.get("contract_id", "")).lower()
    source = str(txn.get("source", "")).lower()
    
    # Block known simulation markers
    sim_markers = ["sim", "bootstrap", "sample", "test", "interno", "mock"]
    for marker in sim_markers:
        if marker in ref or marker in cid:
            return False, f"simulation_marker:{marker}"
    
    # Require evidence file or verified transaction ID
    evidence_file = EVIDENCE_DIR / f"{cid}.json"
    if evidence_file.exists():
        try:
            ev = json.loads(evidence_file.read_text())
            if ev.get("verified"):
                return True, "evidence_verified"
        except:
            pass
    
    # Check for external transaction ID format (Wise/Bybit/PayPal)
    ext_id = txn.get("external_txn_id") or txn.get("wise_transaction_id")
    if ext_id and len(str(ext_id)) > 8:
        return True, "external_id_present"
    
    return False, "no_evidence"

def audit_ledger(ledger_path: Path) -> dict:
    """Audit existing ledger entries and return cleanup report."""
    valid = []
    invalid = []
    
    if not ledger_path.exists():
        return {"error": "ledger_not_found"}
    
    for line in ledger_path.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            txn = json.loads(line)
        except:
            continue
        
        is_valid, reason = has_valid_evidence(txn)
        entry = {
            "contract_id": txn.get("contract_id"),
            "amount": txn.get("amount"),
            "kind": txn.get("kind"),
            "reason": reason
        }
        
        if is_valid:
            valid.append(entry)
        else:
            invalid.append(entry)
    
    return {
        "audit_date": datetime.now(timezone.utc).isoformat(),
        "total_entries": len(valid) + len(invalid),
        "valid_entries": len(valid),
        "invalid_entries": len(invalid),
        "invalid_details": invalid[:20],
        "action": "void_invalid_entries" if invalid else "ledger_clean"
    }

if __name__ == "__main__":
    if "--audit-ledger" in sys.argv:
        result = audit_ledger(LEDGER_PATH)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif "--validate" in sys.argv:
        idx = sys.argv.index("--validate")
        if idx + 1 < len(sys.argv):
            try:
                txn = json.loads(sys.argv[idx + 1])
                valid, reason = has_valid_evidence(txn)
                print(json.dumps({"valid": valid, "reason": reason}))
            except Exception as e:
                print(json.dumps({"error": str(e)}))
    else:
        print("Usage: reality_gate.py --audit-ledger | --validate <json>")
