from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any, Dict, List, Tuple

from ..common.queue import PersistentQueue
from ..common.validation import validate_cron_payload

_CRON_TOKEN_RE = re.compile(r"^(\*|[0-9]+(-[0-9]+)?(,[0-9]+(-[0-9]+)?)*)$")


class LocalScheduler:
    def __init__(self, queue_path: str) -> None:
        self.queue = PersistentQueue(queue_path)

    @staticmethod
    def _validate_cron_expression(expr: str) -> bool:
        """Basic 5-field cron validation; no seconds, no special strings."""
        parts = expr.strip().split()
        if len(parts) != 5:
            return False
        return all(_CRON_TOKEN_RE.match(p) for p in parts)

    def schedule(self, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        ok, reason = validate_cron_payload(payload)
        if not ok:
            return False, {"error": reason}
        if not self._validate_cron_expression(payload.get("schedule", "")):
            return False, {"error": "invalid_cron_expression"}
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        job_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        item = {
            "id": job_id,
            "type": "cron_job",
            "payload": payload,
            "scheduled_at": time.time(),
        }
        accepted = self.queue.enqueue(item)
        if not accepted:
            return False, {"error": "duplicate_job"}
        return True, {"queued": True, "id": job_id, "local_safe": True}

    def pending(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self.queue.pending(limit)

    def complete(self, job_id: str) -> None:
        self.queue.mark_done(job_id)
