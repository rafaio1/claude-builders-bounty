from __future__ import annotations

import json
import re
from dataclasses import dataclass
from http.cookies import SimpleCookie
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults

import pytest

from agentic.portal import (
    COOKIE_NAME,
    PortalApp,
    PortalConfig,
    hash_password,
)


PASSWORD = "correct horse battery staple"
SENSITIVE = "token-super-secreto-nao-renderizar"


@dataclass
class ClientResponse:
    status: str
    headers: list[tuple[str, str]]
    body: bytes

    def header(self, name: str) -> str:
        lowered = name.lower()
        return next((value for key, value in self.headers if key.lower() == lowered), "")

    def json(self) -> dict:
        return json.loads(self.body.decode("utf-8"))


def request(
    app: PortalApp,
    path: str,
    *,
    method: str = "GET",
    form: dict[str, str] | None = None,
    cookie: str = "",
    host: str = "127.0.0.1:8767",
) -> ClientResponse:
    body = urlencode(form or {}).encode("utf-8") if form is not None else b""
    environ: dict[str, object] = {}
    setup_testing_defaults(environ)
    environ.update(
        {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "SERVER_NAME": "127.0.0.1",
            "SERVER_PORT": "8767",
            "HTTP_HOST": host,
            "REMOTE_ADDR": "127.0.0.1",
            "wsgi.input": BytesIO(body),
            "CONTENT_LENGTH": str(len(body)),
            "CONTENT_TYPE": "application/x-www-form-urlencoded",
        }
    )
    if cookie:
        environ["HTTP_COOKIE"] = cookie
    captured: dict[str, object] = {}

    def start_response(status, headers, exc_info=None):
        captured["status"] = status
        captured["headers"] = headers

    response_body = b"".join(app(environ, start_response))
    return ClientResponse(str(captured["status"]), list(captured["headers"]), response_body)


def session_cookie(response: ClientResponse) -> str:
    parsed = SimpleCookie()
    parsed.load(response.header("Set-Cookie"))
    return f"{COOKIE_NAME}={parsed[COOKIE_NAME].value}"


def csrf_token(response: ClientResponse) -> str:
    match = re.search(rb'name="csrf_token" value="([^"]+)"', response.body)
    assert match is not None
    return match.group(1).decode("ascii")


@pytest.fixture
def state_path(tmp_path: Path) -> Path:
    payload = {
        "schema_version": 1,
        "generated_at": "2026-08-16T14:00:00+00:00",
        "stats": {
            "programs_total": 3,
            "findings_total": 0,
            "reports_ready": 1,
            "submissions_total": 0,
            "engine_status": "Em observação",
            "last_run": "agora",
            "last_run_iso": "2026-08-16T14:00:00+00:00",
            "next_action": "Configurar payout",
            "api_token": SENSITIVE,
        },
        "findings": [
            {
                "id": 1,
                "title": "Corrijo um bug",
                "program": "offer-bugfix-api",
                "severity": "info",
                "status": "draft",
                "updated_at": "agora",
            }
        ],
        "activity": [{"title": "ciclo", "detail": "observe", "time": "agora", "status": "info"}],
        "programs": [{"handle": "playwright", "name": "playwright", "status": "Presente"}],
        "heartbeat": {"status": "healthy", "engine_status": "running", "last_activity": "2026-08-16T14:00:00+00:00"},
        "messages": [
            {
                "id": "msg1msg1msg1",
                "role": "owner",
                "author": "rafaio",
                "body": "status?",
                "time": "agora",
                "datetime": "2026-08-16T14:00:00+00:00",
            }
        ],
        "improve": {"counts": {"total": 0, "active": 0}, "proposals": []},
        "integrity": {"ok": True, "status": "ok", "summary": "ok", "failed": [], "checks": []},
        "ai_eval": {"ok": True, "status": "ok", "summary": "ok", "passed": 2, "failed": 0, "total": 2, "cases": []},
    }
    path = tmp_path / "state.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture
def app(state_path: Path, tmp_path: Path) -> PortalApp:
    config = PortalConfig(
        state_path=state_path,
        password_hash=hash_password(
            PASSWORD,
            algorithm="pbkdf2_sha256",
            iterations=100_000,
            salt=b"0123456789abcdef",
        ),
        username="rafaio",
        display_name="Rafaio",
        inbox_path=tmp_path / "inbox.jsonl",
    )
    return PortalApp(config)


def login(app: PortalApp) -> str:
    page = request(app, "/login")
    logged = request(
        app,
        "/login",
        method="POST",
        form={
            "csrf_token": csrf_token(page),
            "username": "rafaio",
            "password": PASSWORD,
        },
        cookie=session_cookie(page),
    )
    assert logged.status.startswith("303")
    return session_cookie(logged)


def test_login_required_and_dashboard_hides_secrets(app: PortalApp) -> None:
    denied = request(app, "/")
    assert denied.status.startswith("303")
    cookie = login(app)
    dash = request(app, "/", cookie=cookie)
    assert dash.status.startswith("200")
    assert b"Agentic" in dash.body
    assert SENSITIVE.encode() not in dash.body
    assert b"Falar com o ARO" in dash.body


def test_message_requires_csrf_and_appends_inbox(app: PortalApp, tmp_path: Path) -> None:
    cookie = login(app)
    dash = request(app, "/", cookie=cookie)
    token = csrf_token(dash)
    bad = request(
        app,
        "/message",
        method="POST",
        form={"csrf_token": "nope", "body": "ola agente"},
        cookie=cookie,
    )
    assert bad.status.startswith("403")
    ok = request(
        app,
        "/message",
        method="POST",
        form={"csrf_token": token, "body": "preciso do status do ciclo"},
        cookie=cookie,
    )
    assert ok.status.startswith("303")
    inbox = (tmp_path / "inbox.jsonl").read_text(encoding="utf-8")
    assert "preciso do status do ciclo" in inbox
    assert PASSWORD not in inbox
