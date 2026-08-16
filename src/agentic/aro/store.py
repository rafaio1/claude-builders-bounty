"""Append-only ARO stores. Never delete ledger rows."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ARO_DIR = Path("data") / "aro"


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _dir(root: Path) -> Path:
    path = Path(root) / ARO_DIR
    path.mkdir(parents=True, exist_ok=True)
    (path / "reports").mkdir(exist_ok=True)
    return path


def _load_list(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return [item for item in payload["items"] if isinstance(item, dict)]
    return []


def _dump_list(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"updated_at": utcnow(), "items": rows}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )


def append_jsonl(root: Path, name: str, row: dict[str, Any]) -> dict[str, Any]:
    path = _dir(root) / name
    payload = dict(row)
    payload.setdefault("at", utcnow())
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    payload.setdefault("hash", hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16])
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    return payload


def read_jsonl(root: Path, name: str) -> list[dict[str, Any]]:
    path = _dir(root) / name
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def upsert_named(root: Path, filename: str, item: dict[str, Any], *, key: str = "id") -> None:
    path = _dir(root) / filename
    rows = _load_list(path)
    ident = str(item.get(key) or "")
    if not ident:
        raise ValueError("item sem id")
    updated = False
    for index, current in enumerate(rows):
        if str(current.get(key) or "") == ident:
            rows[index] = item
            updated = True
            break
    if not updated:
        rows.append(item)
    _dump_list(path, rows)


def list_named(root: Path, filename: str) -> list[dict[str, Any]]:
    return _load_list(_dir(root) / filename)


def ensure_stores(root: Path) -> dict[str, str]:
    base = _dir(root)
    created: dict[str, str] = {}
    for name in ("ledger.jsonl", "journal.jsonl"):
        path = base / name
        if not path.exists():
            path.write_text("", encoding="utf-8")
            created[name] = "created"
        else:
            created[name] = "exists"
    for name in (
        "opportunities.json",
        "clients.json",
        "contracts.json",
        "incidents.json",
        "offers.json",
    ):
        path = base / name
        if not path.exists():
            _dump_list(path, [])
            created[name] = "created"
        else:
            created[name] = "exists"
    return created
