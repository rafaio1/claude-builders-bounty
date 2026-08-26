from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
import base64
import io

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "revenue", "products"))

from utility_api.common.queue import PersistentQueue
from utility_api.common.validation import (
    validate_pdf_payload,
    validate_image_payload,
    validate_cron_payload,
)
from utility_api.pdf.generator import generate_pdf
from utility_api.image.optimizer import optimize_image
from utility_api.cron.scheduler import LocalScheduler


from PIL import Image

def test_queue_idempotency(tmp_path):
    q = PersistentQueue(str(tmp_path / "q.jsonl"))
    item = {"type": "test", "payload": {"x": 1}}
    assert q.enqueue(item) is True
    assert q.enqueue(item) is False
    pending = q.pending(limit=5)
    assert len(pending) == 1
    q.mark_done(pending[0]["id"])
    assert q.pending(limit=5) == []


def test_pdf_validation_blocks_external_assets():
    ok, reason = validate_pdf_payload({"html": "<p>ok</p>", "external_assets": True})
    assert ok is False
    assert "external_assets_forbidden" in reason


def test_pdf_generation_sanitizes_and_stays_local_safe():
    ok, result = generate_pdf({"html": "<script>bad()</script><p>hi</p>"})
    assert ok is True
    assert result["local_safe"] is True
    assert "<script>" not in result["preview_head"]
    assert result["size_bytes"] > 0
    pdf_bytes = result["data"]
    assert pdf_bytes.startswith(b"%PDF-1.4")
    assert b"%%EOF" in pdf_bytes
    # Validate with pdfinfo and extract text with pdftotext
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name
    try:
        info = subprocess.run(["/usr/bin/pdfinfo", tmp_path], capture_output=True, timeout=10)
        assert info.returncode == 0, f"pdfinfo failed: {info.stderr.decode()}"
        txt = subprocess.run(["/usr/bin/pdftotext", tmp_path, "-"], capture_output=True, timeout=10)
        assert txt.returncode == 0, f"pdftotext failed: {txt.stderr.decode()}"
        extracted = txt.stdout.decode("utf-8", errors="replace")
        assert "hi" in extracted.lower(), f"text 'hi' not found in extracted: {extracted!r}"
    finally:
        os.unlink(tmp_path)


def test_image_validation_blocks_remote_url():
    ok, reason = validate_image_payload({"data": b"x", "remote_url": "http://evil"})
    assert ok is False
    assert "remote_fetch_forbidden" in reason


def test_image_optimizer_real_resize_and_metrics():
    buf = io.BytesIO()
    Image.new("RGB", (200, 100), color="blue").save(buf, format="PNG")
    b64_in = base64.b64encode(buf.getvalue()).decode("ascii")
    ok, result = optimize_image({"data": b64_in, "format": "png", "max_width": 50, "max_height": 50})
    assert ok is True
    assert result["local_safe"] is True
    assert result["input_bytes"] > 0
    assert result["output_bytes"] > 0
    assert result["original_size"] == [200, 100]
    assert result["final_size"][0] <= 50 and result["final_size"][1] <= 50
    assert result["resized"] is True
    out_img = Image.open(io.BytesIO(result["data"]))
    assert out_img.size[0] <= 50 and out_img.size[1] <= 50
    assert out_img.format == "PNG"


def test_cron_validation_blocks_external_webhook():
    ok, reason = validate_cron_payload(
        {"schedule": "* * * * *", "target": "local.echo", "webhook_url": "https://x"}
    )
    assert ok is False
    assert "external_webhook_forbidden" in reason


def test_scheduler_enqueue_and_pending(tmp_path):
    s = LocalScheduler(str(tmp_path / "cron.jsonl"))
    ok, res = s.schedule({"schedule": "*/5 * * * *", "target": "local.noop"})
    assert ok is True
    assert res["queued"] is True
    jobs = s.pending(limit=5)
    assert len(jobs) == 1
    s.complete(jobs[0]["id"])
    assert s.pending(limit=5) == []


def test_scheduler_rejects_invalid_cron_expression(tmp_path):
    s = LocalScheduler(str(tmp_path / "cron_bad.jsonl"))
    ok, res = s.schedule({"schedule": "not a cron", "target": "local.noop"})
    assert ok is False
    assert "invalid_cron_expression" in res.get("error", "")


def _wait_for_http(url: str, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


def test_server_health_and_endpoints(tmp_path):
    port = 18769
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(ROOT, "revenue", "products")
    env["UTILITY_API_PORT"] = str(port)
    env["UTILITY_API_QUEUE"] = str(tmp_path / "srv_q.jsonl")
    proc = subprocess.Popen(
        [sys.executable, "-m", "utility_api.server"],
        cwd=os.path.join(ROOT, "revenue", "products"),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        assert _wait_for_http(f"{base}/health"), "server did not become ready"
        with urllib.request.urlopen(f"{base}/health") as r:
            health = json.loads(r.read().decode("utf-8"))
        assert health["status"] == "ready"
        assert health["components"]["pdf"]["ok"] is True

        req = urllib.request.Request(
            f"{base}/pdf",
            data=json.dumps({"html": "<p>hello</p>"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as r:
            pdf_res = json.loads(r.read().decode("utf-8"))
        assert pdf_res["local_safe"] is True

        bad_req = urllib.request.Request(
            f"{base}/cron",
            data=json.dumps({"schedule": "* * * * *", "target": "t", "webhook_url": "http://x"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(bad_req)
            assert False, "expected 400 for external webhook"
        except urllib.error.HTTPError as e:
            assert e.code == 400
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
