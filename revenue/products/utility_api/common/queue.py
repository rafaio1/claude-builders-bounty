from __future__ import annotations

import fcntl
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List


class PersistentQueue:
    """Idempotent JSONL-backed queue with deduplication by payload hash."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path = self.path.with_suffix(".lock")

    def _hash(self, item: Dict[str, Any]) -> str:
        canonical = json.dumps(item.get("payload", {}), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _acquire_lock(self):
        self._lock_fh = open(self._lock_path, "w")
        fcntl.flock(self._lock_fh.fileno(), fcntl.LOCK_EX)

    def _release_lock(self):
        if hasattr(self, "_lock_fh"):
            try:
                fcntl.flock(self._lock_fh.fileno(), fcntl.LOCK_UN)
            finally:
                self._lock_fh.close()

    def enqueue(self, item: Dict[str, Any]) -> bool:
        h = self._hash(item)
        self._acquire_lock()
        try:
            if self._contains(h):
                return False
            record = {
                "id": h,
                "created_at": time.time(),
                "status": "pending",
                **item,
            }
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            return True
        finally:
            self._release_lock()

    def _contains(self, h: str) -> bool:
        if not self.path.exists():
            return False
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("id") == h:
                    return True
        return False

    def pending(self, limit: int = 10) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        out: List[Dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if len(out) >= limit:
                    break
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("status") == "pending":
                    out.append(rec)
        return out

    def mark_done(self, item_id: str) -> None:
        if not self.path.exists():
            return
        self._acquire_lock()
        try:
            tmp = self.path.with_suffix(".tmp")
            with self.path.open("r", encoding="utf-8") as src, tmp.open("w", encoding="utf-8") as dst:
                for line in src:
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        dst.write(line)
                        continue
                    if rec.get("id") == item_id:
                        rec["status"] = "done"
                        rec["completed_at"] = time.time()
                    dst.write(json.dumps(rec, ensure_ascii=False) + "\n")
            os.replace(tmp, self.path)
        finally:
            self._release_lock()
