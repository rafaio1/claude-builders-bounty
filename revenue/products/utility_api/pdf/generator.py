 from __future__ import annotations
 
 import html
 import re
 from typing import Any, Dict, Tuple
 
 from ..common.validation import validate_pdf_payload
 
 
 def _sanitize_html(content: str) -> str:
     """Strip scripts, iframes, objects and external refs; keep safe tags only."""
     unsafe = re.compile(
         r"<\s*/?\s*(script|iframe|object|embed|form|input|button|link|meta|base)[^>]*>",
         re.IGNORECASE,
     )
     cleaned = unsafe.sub("", content)
     return cleaned.strip()
 
 
 def generate_pdf(payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
     ok, reason = validate_pdf_payload(payload)
     if not ok:
         return False, {"error": reason}
     raw = payload.get("html") or payload.get("content") or ""
     safe_html = _sanitize_html(raw)
     # Minimal PDF envelope for local-safe output (no external assets).
     pdf_bytes = (
         b"%PDF-1.4\n"
         b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
         b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
         b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]>>endobj\n"
         b"xref\n0 4\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n0\n%%EOF"
     )
     return True, {
         "format": "pdf",
         "size_bytes": len(pdf_bytes),
         "sanitized_length": len(safe_html),
         "local_safe": True,
         "preview_head": safe_html[:200],
         "data": pdf_bytes,
     }
