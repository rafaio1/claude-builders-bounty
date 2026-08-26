from __future__ import annotations

from typing import Any, Dict, Tuple

MAX_PDF_PAYLOAD_BYTES = 512_000
MAX_IMAGE_PAYLOAD_BYTES = 2_097_152
ALLOWED_IMAGE_FORMATS = {"png", "jpeg", "webp"}


def validate_pdf_payload(payload: Dict[str, Any]) -> Tuple[bool, str]:
    content = payload.get("content") or payload.get("html")
    if not isinstance(content, str) or not content.strip():
        return False, "missing_or_empty_content"
    if len(content.encode("utf-8")) > MAX_PDF_PAYLOAD_BYTES:
        return False, f"payload_exceeds_{MAX_PDF_PAYLOAD_BYTES}_bytes"
    if payload.get("external_assets"):
        return False, "external_assets_forbidden_in_local_safe_mode"
    return True, "ok"


def validate_image_payload(payload: Dict[str, Any]) -> Tuple[bool, str]:
    data = payload.get("data")
    fmt = (payload.get("format") or "").lower()
    if not isinstance(data, (str, bytes)):
        return False, "missing_data"
    size = len(data) if isinstance(data, (bytes, str)) else 0
    if size > MAX_IMAGE_PAYLOAD_BYTES:
        return False, f"payload_exceeds_{MAX_IMAGE_PAYLOAD_BYTES}_bytes"
    if fmt and fmt not in ALLOWED_IMAGE_FORMATS:
        return False, f"unsupported_format_{fmt}"
    if payload.get("remote_url"):
        return False, "remote_fetch_forbidden_in_local_safe_mode"
    return True, "ok"


def validate_cron_payload(payload: Dict[str, Any]) -> Tuple[bool, str]:
    schedule = payload.get("schedule")
    target = payload.get("target")
    if not isinstance(schedule, str) or not schedule.strip():
        return False, "missing_schedule"
    if not isinstance(target, str) or not target.strip():
        return False, "missing_target"
    # Block any external webhook or callback URL
    for key in ("webhook_url", "callback_url", "notify_url"):
        if payload.get(key):
            return False, f"external_{key}_forbidden_in_local_safe_mode"
    if payload.get("webhook_url"):
        return False, "external_webhook_forbidden_in_local_safe_mode"
    return True, "ok"
