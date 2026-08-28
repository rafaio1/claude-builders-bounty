#!/usr/bin/env python3
"""Publish one evidence video through an existing BoTTube agent.

The artifact is validated locally before any network access. Upload mode is
fail-closed: an exact-title duplicate, an unstable artifact, an unexpected API
payload, a failed screening, or a non-public watch page prevents claim use.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.parse import urljoin, urlparse

import requests


BASE_URL = "https://bottube.ai"
MAX_FILE_BYTES = 2_000_000
MAX_DURATION_SECONDS = Decimal("8")
REQUIRED_WIDTH = 720
REQUIRED_HEIGHT = 720
FFPROBE_TIMEOUT_SECONDS = 20


class GateError(RuntimeError):
    """A deterministic publication gate failed."""


class PreflightError(GateError):
    """The local artifact did not satisfy the video contract."""


def read_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise GateError(f"environment file does not exist: {path}")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def save_json(path: Path, value: dict[str, Any]) -> None:
    """Atomically save state with owner-only permissions."""

    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if not hasattr(os, "fchmod"):
            os.chmod(tmp_name, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(tmp_name, path)
        os.chmod(path, 0o600)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decimal_duration(raw: object) -> Decimal:
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError) as exc:
        raise PreflightError("ffprobe returned an invalid duration") from exc
    if not value.is_finite() or value <= 0:
        raise PreflightError("video duration must be finite and greater than zero")
    if value > MAX_DURATION_SECONDS:
        raise PreflightError(
            f"video duration {value}s exceeds the {MAX_DURATION_SECONDS}s gate"
        )
    return value


def preflight_video(
    path: Path,
    *,
    ffprobe: str = "ffprobe",
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    """Return stable artifact metadata or raise :class:`PreflightError`.

    ffprobe is intentionally required even when the filename looks correct: a
    suffix alone is not evidence that the container and video stream are valid.
    """

    try:
        resolved = path.expanduser().resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise PreflightError(f"video does not exist: {path}") from exc
    if not resolved.is_file():
        raise PreflightError(f"video is not a regular file: {resolved}")
    if resolved.suffix.lower() != ".mp4":
        raise PreflightError("video must use the .mp4 filename extension")

    before = resolved.stat()
    if before.st_size <= 0:
        raise PreflightError("video is empty")
    if before.st_size > MAX_FILE_BYTES:
        raise PreflightError(
            f"video size {before.st_size} exceeds the {MAX_FILE_BYTES}-byte gate"
        )
    sha256 = _sha256(resolved)

    command = [
        ffprobe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_entries",
        "format=duration,format_name:stream=codec_type,width,height",
        str(resolved),
    ]
    try:
        completed = runner(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=FFPROBE_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise PreflightError(f"ffprobe executable was not found: {ffprobe}") from exc
    except subprocess.TimeoutExpired as exc:
        raise PreflightError("ffprobe timed out") from exc
    except OSError as exc:
        raise PreflightError("ffprobe could not be executed") from exc
    if completed.returncode != 0:
        raise PreflightError(f"ffprobe failed with exit code {completed.returncode}")
    try:
        probe = json.loads(completed.stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        raise PreflightError("ffprobe returned invalid JSON") from exc
    if not isinstance(probe, dict):
        raise PreflightError("ffprobe returned an unexpected payload")

    format_data = probe.get("format")
    if not isinstance(format_data, dict):
        raise PreflightError("ffprobe payload has no format metadata")
    format_names = format_data.get("format_name")
    if not isinstance(format_names, str) or "mp4" not in {
        name.strip().lower() for name in format_names.split(",")
    }:
        raise PreflightError("artifact is not an MP4 container")
    duration = _decimal_duration(format_data.get("duration"))

    streams = probe.get("streams")
    if not isinstance(streams, list):
        raise PreflightError("ffprobe payload has no stream list")
    video_streams = [
        stream
        for stream in streams
        if isinstance(stream, dict) and stream.get("codec_type") == "video"
    ]
    if len(video_streams) != 1:
        raise PreflightError("artifact must contain exactly one video stream")
    stream = video_streams[0]
    if stream.get("width") != REQUIRED_WIDTH or stream.get("height") != REQUIRED_HEIGHT:
        raise PreflightError(
            f"video must be exactly {REQUIRED_WIDTH}x{REQUIRED_HEIGHT} pixels"
        )

    after = resolved.stat()
    if (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
        raise PreflightError("video changed during preflight")

    return {
        "path": str(resolved),
        "sha256": sha256,
        "size_bytes": before.st_size,
        "duration_seconds": format(duration, "f"),
        "width": REQUIRED_WIDTH,
        "height": REQUIRED_HEIGHT,
        "container": "mp4",
    }


def json_response(response: requests.Response, expected: int, operation: str) -> dict[str, Any]:
    if response.status_code != expected:
        raise GateError(f"{operation} returned HTTP {response.status_code}")
    try:
        value = response.json()
    except ValueError as exc:
        raise GateError(f"{operation} returned non-JSON") from exc
    if not isinstance(value, dict):
        raise GateError(f"{operation} returned an unexpected payload")
    return value


def _state_variant(state: Path, suffix: str) -> Path:
    return state.with_name(f"{state.stem}-{suffix}{state.suffix or '.json'}")


def _ensure_unused_state(state: Path) -> None:
    candidates = [state, _state_variant(state, "held"), _state_variant(state, "not-public")]
    existing = [str(candidate) for candidate in candidates if candidate.exists()]
    if existing:
        raise GateError("refusing to overwrite prior publication state: " + ", ".join(existing))


def _safe_live_url(watch_path: object) -> str:
    if not isinstance(watch_path, str) or not watch_path.strip():
        raise GateError("upload response has no watch_url")
    live_url = urljoin(f"{BASE_URL}/", watch_path)
    expected = urlparse(BASE_URL)
    actual = urlparse(live_url)
    if actual.scheme != expected.scheme or actual.netloc != expected.netloc:
        raise GateError("upload response points outside the trusted BoTTube origin")
    return live_url


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--env", type=Path)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--title")
    parser.add_argument("--description")
    parser.add_argument("--scene-description")
    parser.add_argument("--tags")
    parser.add_argument("--category", default="science-tech")
    parser.add_argument(
        "--gen-method",
        default="Programmatic terminal animation from an actual verified test transcript",
    )
    return parser


def _require_upload_arguments(args: argparse.Namespace) -> None:
    required = {
        "--env": args.env,
        "--state": args.state,
        "--title": args.title,
        "--description": args.description,
        "--scene-description": args.scene_description,
        "--tags": args.tags,
    }
    missing = [flag for flag, value in required.items() if value is None or value == ""]
    if missing:
        raise GateError("upload mode requires: " + ", ".join(missing))


def _state_record(
    payload: dict[str, Any],
    *,
    preflight: dict[str, Any],
    title: str,
    live_url: str | None = None,
) -> dict[str, Any]:
    record = dict(payload)
    record["_artifact_preflight"] = preflight
    record["_request"] = {"title": title}
    if live_url is not None:
        record["live_url"] = live_url
    return record


def publish(
    args: argparse.Namespace,
    preflight: dict[str, Any],
    *,
    session_factory: Callable[[], requests.Session] | None = None,
) -> dict[str, Any]:
    _require_upload_arguments(args)
    assert args.env is not None
    assert args.state is not None
    assert args.title is not None
    assert args.description is not None
    assert args.scene_description is not None
    assert args.tags is not None
    _ensure_unused_state(args.state)

    env = read_env(args.env)
    api_key = env.get("BOTTUBE_API_KEY", "")
    if len(api_key) < 20:
        raise GateError("BOTTUBE_API_KEY is missing")

    session = session_factory() if session_factory is not None else requests.Session()
    session.headers.update(
        {"User-Agent": "orca-rafaio1-claim/2.0", "Accept": "application/json"}
    )
    auth = {"X-API-Key": api_key}
    me = json_response(
        session.get(f"{BASE_URL}/api/agents/me", headers=auth, timeout=20),
        200,
        "whoami",
    )
    agent_name = me.get("agent_name")
    if not isinstance(agent_name, str) or not agent_name:
        raise GateError("BoTTube profile has no agent_name")
    public_profile = json_response(
        session.get(f"{BASE_URL}/api/agents/{agent_name}", timeout=20),
        200,
        "public profile",
    )
    videos = public_profile.get("videos")
    if not isinstance(videos, list):
        raise GateError("public profile has no reliable video list for deduplication")
    for video in videos:
        if not isinstance(video, dict):
            raise GateError("public profile contains an unexpected video entry")
        if video.get("title") == args.title:
            raise GateError(
                f"a public video with this exact title already exists: {video.get('video_id')}"
            )

    tos = json_response(session.get(f"{BASE_URL}/api/tos", timeout=20), 200, "terms lookup")
    version = tos.get("version")
    if not isinstance(version, str) or not version:
        raise GateError("terms version is missing")

    # Re-probe after all read-only discovery and before the first remote mutation.
    # This prevents uploading an artifact changed after the original preflight.
    repeated = preflight_video(args.video, ffprobe=args.ffprobe)
    if repeated != preflight:
        raise GateError("video changed between preflight and upload")

    json_response(
        session.post(
            f"{BASE_URL}/api/agents/me/accept-terms",
            headers=auth,
            json={"version": version},
            timeout=20,
        ),
        200,
        "terms acceptance",
    )

    with args.video.open("rb") as video_handle:
        upload = session.post(
            f"{BASE_URL}/api/upload",
            headers=auth,
            data={
                "title": args.title,
                "description": args.description,
                "scene_description": args.scene_description,
                "tags": args.tags,
                "category": args.category,
                "gen_method": args.gen_method,
            },
            files={"video": (args.video.name, video_handle, "video/mp4")},
            timeout=600,
        )
    payload = json_response(upload, 201, "upload")
    screening = payload.get("screening")
    if (
        not isinstance(screening, dict)
        or screening.get("status") != "passed"
        or bool(payload.get("warning"))
    ):
        save_json(
            _state_variant(args.state, "held"),
            _state_record(payload, preflight=preflight, title=args.title),
        )
        raise GateError("upload was not screened as passed; no claim should be filed")

    video_id = payload.get("video_id")
    if not isinstance(video_id, str) or not video_id:
        raise GateError("upload response has no video_id")
    live_url = _safe_live_url(payload.get("watch_url"))
    public = session.get(live_url, timeout=30)
    if public.status_code != 200:
        save_json(
            _state_variant(args.state, "not-public"),
            _state_record(payload, preflight=preflight, title=args.title, live_url=live_url),
        )
        raise GateError(f"public watch page returned HTTP {public.status_code}")

    record = _state_record(payload, preflight=preflight, title=args.title, live_url=live_url)
    save_json(args.state, record)
    return {
        "agent_name": agent_name,
        "video_id": video_id,
        "live_url": live_url,
        "screening": screening.get("status"),
        "public_http": public.status_code,
        "terms_version": version,
        "artifact_sha256": preflight["sha256"],
    }


def main(
    argv: Sequence[str] | None = None,
    *,
    session_factory: Callable[[], requests.Session] | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        preflight = preflight_video(args.video, ffprobe=args.ffprobe)
        if args.preflight_only:
            print(json.dumps(preflight, sort_keys=True))
            return 0
        result = publish(args, preflight, session_factory=session_factory)
    except GateError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
