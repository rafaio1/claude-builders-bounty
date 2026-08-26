 from __future__ import annotations
 
 import time
 from typing import Any, Dict, List, Tuple
 
 from ..common.queue import PersistentQueue
 from ..common.validation import validate_cron_payload
 
 
 class LocalScheduler:
     def __init__(self, queue_path: str) -> None:
         self.queue = PersistentQueue(queue_path)
 
     def schedule(self, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
         ok, reason = validate_cron_payload(payload)
         if not ok:
             return False, {"error": reason}
         item = {
             "type": "cron_job",
             "payload": payload,
             "scheduled_at": time.time(),
         }
         accepted = self.queue.enqueue(item)
         if not accepted:
             return False, {"error": "duplicate_job"}
         return True, {"queued": True, "id": item["id"], "local_safe": True}
 
     def pending(self, limit: int = 10) -> List[Dict[str, Any]]:
         return self.queue.pending(limit)
 
     def complete(self, job_id: str) -> None:
         self.queue.mark_done(job_id)
