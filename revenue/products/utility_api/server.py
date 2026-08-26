from __future__ import annotations

import json
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict

from .pdf.generator import generate_pdf
from .image.optimizer import optimize_image
from .cron.scheduler import LocalScheduler

QUEUE_PATH = os.environ.get("UTILITY_API_QUEUE", "/tmp/utility_api_queue.jsonl")
HOST = "127.0.0.1"
PORT = int(os.environ.get("UTILITY_API_PORT", "8769"))

_scheduler = LocalScheduler(QUEUE_PATH)
_started_at = time.time()


def _health_status() -> Dict[str, Any]:
    pdf_ok, _ = generate_pdf({"html": "<p>probe</p>"})
    img_ok, _ = optimize_image({"data": b"", "format": "png"})
    cron_ok = True
    try:
        _scheduler.pending(limit=1)
    except Exception:
        cron_ok = False
    ready = bool(pdf_ok and img_ok and cron_ok)
    return {
        "status": "ready" if ready else "degraded",
        "components": {
            "pdf": {"ok": pdf_ok},
            "image": {"ok": img_ok},
            "cron": {"ok": cron_ok},
        },
        "uptime_seconds": round(time.time() - _started_at, 2),
        "host": HOST,
        "port": PORT,
    }


class Handler(BaseHTTPRequestHandler):
    def _json_response(self, code: int, body: Dict[str, Any]) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:
        if self.path == "/health":
            status = _health_status()
            code = 200 if status["status"] == "ready" else 503
            self._json_response(code, status)
            return
        if self.path == "/ready":
            status = _health_status()
            code = 200 if status["status"] == "ready" else 503
            self._json_response(code, status)
            return
        self._json_response(404, {"error": "not_found"})

    def do_POST(self) -> None:
        try:
            body = self._read_json()
        except Exception as exc:
            self._json_response(400, {"error": "invalid_json", "detail": str(exc)})
            return
        if self.path == "/pdf":
            ok, result = generate_pdf(body)
            code = 200 if ok else 400
            safe = {k: v for k, v in result.items() if k != "data"}
            self._json_response(code, safe)
            return
        if self.path == "/image":
            ok, result = optimize_image(body)
            code = 200 if ok else 400
            self._json_response(code, result)
            return
        if self.path == "/cron":
            ok, result = _scheduler.schedule(body)
            code = 200 if ok else 400
            self._json_response(code, result)
            return
        self._json_response(404, {"error": "not_found"})

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def main() -> None:
    server = HTTPServer((HOST, PORT), Handler)
    print(f"utility-api listening on {HOST}:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
