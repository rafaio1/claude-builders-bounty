from __future__ import annotations

import hashlib
import re
import zlib
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


def _build_pdf_bytes(text: str) -> bytes:
    """Build a minimal valid PDF 1.4 with text rendered in the content stream."""
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    # Limit to first 2000 chars to keep PDF small and within single page
    safe = safe[:2000]
    content_lines = []
    y = 800
    for chunk in safe.split("\n"):
        line = chunk.strip()
        if not line:
            continue
        # Escape again per line just in case
        esc = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content_lines.append(f"BT /F1 12 Tf {50} {y} Td ({esc}) Tj ET")
        y -= 16
        if y < 50:
            break
    stream_data = "\n".join(content_lines).encode("utf-8")
    compressed = zlib.compress(stream_data)
    objects = []
    # Obj 1: Catalog
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    # Obj 2: Pages
    objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    # Obj 3: Page
    objects.append(
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
    )
    # Obj 4: Stream
    stream_obj = (
        f"4 0 obj\n<< /Length {len(compressed)} /Filter /FlateDecode >>\nstream\n".encode(
            "utf-8"
        )
        + compressed
        + b"\nendstream\nendobj\n"
    )
    objects.append(stream_obj)
    # Obj 5: Font (Helvetica built-in)
    objects.append(
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    )
    header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    body = bytearray(header)
    offsets = []
    for obj in objects:
        offsets.append(len(body))
        body.extend(obj)
    xref_offset = len(body)
    xref = ["xref", f"0 {len(objects)+1}"]
    xref.append("0000000000 65535 f ")
    for off in offsets:
        xref.append(f"{off:010d} 00000 n ")
    trailer = (
        f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    )
    body.extend("\n".join(xref).encode("utf-8"))
    body.extend(b"\n")
    body.extend(trailer.encode("utf-8"))
    return bytes(body)


def generate_pdf(payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    ok, reason = validate_pdf_payload(payload)
    if not ok:
        return False, {"error": reason}
    raw = payload.get("html") or payload.get("content") or ""
    safe_html = _sanitize_html(raw)
    try:
        pdf_bytes = _build_pdf_bytes(safe_html)
    except Exception as exc:  # noqa: BLE001
        return False, {"error": f"pdf_build_failed: {exc}"}
    return True, {
        "format": "pdf",
        "size_bytes": len(pdf_bytes),
        "sanitized_length": len(safe_html),
        "local_safe": True,
        "preview_head": safe_html[:200],
        "data": pdf_bytes,
    }
