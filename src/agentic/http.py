from __future__ import annotations

import time
from typing import Any

import requests


class RateLimiter:
    def __init__(self, min_interval: float) -> None:
        self.min_interval = max(0.0, min_interval)
        self._last: float | None = None

    def wait(self) -> None:
        now = time.monotonic()
        if self._last is None or self.min_interval <= 0:
            self._last = now
            return
        delay = self.min_interval - (now - self._last)
        if delay > 0:
            time.sleep(delay)
            now = time.monotonic()
        self._last = now


class HttpError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    limiter: RateLimiter,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = 60.0,
    retries: int = 5,
) -> tuple[int, Any, dict[str, str]]:
    last_error = "unknown error"
    last_status: int | None = None
    for attempt in range(1, retries + 1):
        limiter.wait()
        try:
            response = session.request(
                method,
                url,
                params=params,
                json=json_body,
                timeout=timeout,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            last_error = type(exc).__name__
            if attempt < retries:
                time.sleep(min(30.0, attempt * 2))
                continue
            break
        last_status = response.status_code
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "2")
            try:
                wait = min(60.0, max(1.0, float(retry_after)))
            except ValueError:
                wait = 2.0
            last_error = "rate limited"
            if attempt < retries:
                time.sleep(wait)
                continue
        elif 500 <= response.status_code < 600:
            last_error = f"HTTP {response.status_code}"
            if attempt < retries:
                time.sleep(min(30.0, attempt * 2))
                continue
        else:
            try:
                payload = response.json() if response.content else None
            except ValueError as exc:
                raise HttpError("invalid JSON", status_code=response.status_code) from exc
            return response.status_code, payload, dict(response.headers)
        last_error = f"HTTP {response.status_code}"
    raise HttpError(
        f"{method} {url} failed after retries: {last_error}",
        status_code=last_status,
    )
