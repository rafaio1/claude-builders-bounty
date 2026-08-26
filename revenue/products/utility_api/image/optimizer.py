 from __future__ import annotations
 
 from typing import Any, Dict, Tuple
 
 from ..common.validation import validate_image_payload
 
 
 def optimize_image(payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
     ok, reason = validate_image_payload(payload)
     if not ok:
         return False, {"error": reason}
     data = payload.get("data")
     fmt = (payload.get("format") or "png").lower()
     max_width = int(payload.get("max_width") or 1920)
     max_height = int(payload.get("max_height") or 1920)
     if isinstance(data, str):
         raw = data.encode("utf-8")
     else:
         raw = bytes(data)
     # Local-safe stub: echo metadata without external libs or network.
     return True, {
         "format": fmt,
         "input_bytes": len(raw),
         "max_width": max_width,
         "max_height": max_height,
         "local_safe": True,
         "note": "optimization_stub_no_external_deps",
     }
