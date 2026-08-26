from __future__ import annotations

import base64
import io
from typing import Any, Dict, Tuple

from PIL import Image

from ..common.validation import validate_image_payload

MAX_IMAGE_DIMENSION = 8192
DECOMPRESSION_LIMIT = 64 * 1024 * 1024  # 64 MB uncompressed


def optimize_image(payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    ok, reason = validate_image_payload(payload)
    if not ok:
        return False, {"error": reason}
    raw_data = payload.get("data")
    fmt = (payload.get("format") or "png").lower()
    max_width = int(payload.get("max_width") or 1920)
    max_height = int(payload.get("max_height") or 1920)
    quality = int(payload.get("quality") or 85)
    try:
        if isinstance(raw_data, str):
            raw = base64.b64decode(raw_data)
        else:
            raw = bytes(raw_data)
    except Exception as exc:  # noqa: BLE001
        return False, {"error": f"invalid_base64_or_bytes: {exc}"}
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()  # force decompression to check limits
    except Exception as exc:  # noqa: BLE001
        return False, {"error": f"image_decode_failed: {exc}"}
    w, h = img.size
    if w > MAX_IMAGE_DIMENSION or h > MAX_IMAGE_DIMENSION:
        return False, {"error": f"dimension_exceeds_{MAX_IMAGE_DIMENSION}px"}
    channels = len(img.getbands())
    if w * h * channels > DECOMPRESSION_LIMIT:
        return False, {"error": "decompression_limit_exceeded"}
    orig_w, orig_h = w, h
    if w > max_width or h > max_height:
        ratio = min(max_width / w, max_height / h)
        new_w = max(1, int(w * ratio))
        new_h = max(1, int(h * ratio))
        img = img.resize((new_w, new_h), Image.LANCZOS)
    out_fmt = fmt.upper()
    if out_fmt == "JPG":
        out_fmt = "JPEG"
    buf = io.BytesIO()
    save_kwargs: Dict[str, Any] = {}
    if out_fmt == "JPEG":
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        save_kwargs["quality"] = quality
        save_kwargs["optimize"] = True
    elif out_fmt == "PNG":
        save_kwargs["optimize"] = True
    elif out_fmt == "WEBP":
        save_kwargs["quality"] = quality
    try:
        img.save(buf, format=out_fmt, **save_kwargs)
    except Exception as exc:  # noqa: BLE001
        return False, {"error": f"image_encode_failed: {exc}"}
    out_bytes = buf.getvalue()
    out_b64 = base64.b64encode(out_bytes).decode("ascii")
    return True, {
        "format": fmt,
        "input_bytes": len(raw),
        "output_bytes": len(out_bytes),
        "original_size": [orig_w, orig_h],
        "final_size": list(img.size),
        "resized": (orig_w, orig_h) != img.size,
        "local_safe": True,
        "data": out_bytes,
        "data_base64": out_b64,
    }
