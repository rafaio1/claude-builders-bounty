 from __future__ import annotations
 
 import json
 from pathlib import Path
 from typing import Dict, List, Tuple
 
 from .models import Proposal
 
 
 def load_proposals(path: Path) -> Dict[str, Proposal]:
     proposals: Dict[str, Proposal] = {}
     if not path.exists():
         return proposals
     with path.open("r", encoding="utf-8") as fh:
         for line in fh:
             line = line.strip()
             if not line:
                 continue
             try:
                 data = json.loads(line)
             except json.JSONDecodeError:
                 continue
             pid = data.get("proposal_id")
             if not pid:
                 continue
             ts = data.get("timestamp", "")
             existing = proposals.get(pid)
             if existing and existing.timestamp >= ts:
                 continue
             proposals[pid] = Proposal(
                 proposal_id=pid,
                 timestamp=ts,
                 title=data.get("title", ""),
                 category=data.get("category", ""),
                 tier=data.get("tier", ""),
                 max_cost_usd=float(data.get("max_cost_usd", 0) or 0),
                 evidence=list(data.get("evidence") or []),
                 raw=data,
             )
     return proposals
 
 
 def load_verdicts(path: Path) -> List[Dict]:
     verdicts: List[Dict] = []
     if not path.exists():
         return verdicts
     with path.open("r", encoding="utf-8") as fh:
         for line in fh:
             line = line.strip()
             if not line:
                 continue
             try:
                 data = json.loads(line)
             except json.JSONDecodeError:
                 continue
             if not data.get("proposal_id"):
                 continue
             verdicts.append(data)
     return verdicts
 
 
 def latest_verdict(verdicts: List[Dict]) -> Dict[str, Dict]:
     best: Dict[str, Dict] = {}
     for v in verdicts:
         pid = v["proposal_id"]
         ts = v.get("timestamp", "")
         cur = best.get(pid)
         if cur is None or ts > cur.get("timestamp", ""):
             best[pid] = v
     return best
