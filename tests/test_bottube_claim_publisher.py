from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("upload_existing_agent_video.py")
if not MODULE_PATH.exists():
    MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "bottube_claim_publisher.py"
MODULE_SPEC = importlib.util.spec_from_file_location("bottube_claim_publisher", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"could not load publisher module from {MODULE_PATH}")
publisher = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(publisher)


class FakeResponse:
    def __init__(self, status_code: int, payload: object | None = None) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, gets: list[FakeResponse], posts: list[FakeResponse]) -> None:
        self.headers: dict[str, str] = {}
        self._gets = list(gets)
        self._posts = list(posts)
        self.get_calls: list[tuple[tuple, dict]] = []
        self.post_calls: list[tuple[tuple, dict]] = []

    def get(self, *args, **kwargs) -> FakeResponse:
        self.get_calls.append((args, kwargs))
        return self._gets.pop(0)

    def post(self, *args, **kwargs) -> FakeResponse:
        self.post_calls.append((args, kwargs))
        return self._posts.pop(0)


def probe_payload(
    *,
    duration: object = "7.750000",
    width: int = 720,
    height: int = 720,
    format_name: str = "mov,mp4,m4a,3gp,3g2,mj2",
    streams: list[dict] | None = None,
) -> dict:
    return {
        "format": {"duration": duration, "format_name": format_name},
        "streams": streams
        if streams is not None
        else [{"codec_type": "video", "width": width, "height": height}],
    }


def completed(payload: object, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    stdout = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.CompletedProcess(["ffprobe"], returncode, stdout=stdout, stderr="")


class PreflightTests(unittest.TestCase):
    def test_valid_mp4_returns_deterministic_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory, "evidence.mp4")
            content = b"deterministic-video-bytes"
            video.write_bytes(content)
            runner = mock.Mock(return_value=completed(probe_payload()))

            result = publisher.preflight_video(video, runner=runner)

            self.assertEqual(result["sha256"], hashlib.sha256(content).hexdigest())
            self.assertEqual(result["size_bytes"], len(content))
            self.assertEqual(result["duration_seconds"], "7.750000")
            self.assertEqual((result["width"], result["height"]), (720, 720))
            command = runner.call_args.args[0]
            self.assertEqual(command[0], "ffprobe")
            self.assertEqual(command[-1], str(video.resolve()))
            self.assertEqual(runner.call_args.kwargs["timeout"], 20)

    def test_size_gate_runs_before_ffprobe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory, "large.mp4")
            video.write_bytes(b"x" * (publisher.MAX_FILE_BYTES + 1))
            runner = mock.Mock()

            with self.assertRaisesRegex(publisher.PreflightError, "exceeds"):
                publisher.preflight_video(video, runner=runner)

            runner.assert_not_called()

    def test_invalid_probe_results_fail_closed(self) -> None:
        invalid = {
            "too long": probe_payload(duration="8.000001"),
            "wrong dimensions": probe_payload(width=1280, height=720),
            "not mp4": probe_payload(format_name="matroska,webm"),
            "two video streams": probe_payload(
                streams=[
                    {"codec_type": "video", "width": 720, "height": 720},
                    {"codec_type": "video", "width": 720, "height": 720},
                ]
            ),
            "invalid json": "not-json",
        }
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory, "evidence.mp4")
            video.write_bytes(b"bytes")
            for label, payload in invalid.items():
                with self.subTest(label=label):
                    with self.assertRaises(publisher.PreflightError):
                        publisher.preflight_video(
                            video,
                            runner=mock.Mock(return_value=completed(payload)),
                        )

    def test_ffprobe_failure_is_a_closed_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory, "evidence.mp4")
            video.write_bytes(b"bytes")
            runner = mock.Mock(return_value=completed({}, returncode=9))
            with self.assertRaisesRegex(publisher.PreflightError, "exit code 9"):
                publisher.preflight_video(video, runner=runner)


class PublisherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.video = self.root / "evidence.mp4"
        self.video.write_bytes(b"video")
        self.env = self.root / ".env"
        self.env.write_text("BOTTUBE_API_KEY=" + "k" * 32 + "\n", encoding="utf-8")
        self.state = self.root / "state" / "publication.json"
        self.preflight = {
            "path": str(self.video.resolve()),
            "sha256": hashlib.sha256(b"video").hexdigest(),
            "size_bytes": 5,
            "duration_seconds": "7.75",
            "width": 720,
            "height": 720,
            "container": "mp4",
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def argv(self) -> list[str]:
        return [
            "--video",
            str(self.video),
            "--env",
            str(self.env),
            "--state",
            str(self.state),
            "--title",
            "Unique evidence",
            "--description",
            "Verified evidence",
            "--scene-description",
            "A deterministic terminal transcript",
            "--tags",
            "rust,tests",
        ]

    def test_preflight_only_does_not_create_a_session(self) -> None:
        factory = mock.Mock()
        output = io.StringIO()
        with mock.patch.object(publisher, "preflight_video", return_value=self.preflight):
            with contextlib.redirect_stdout(output):
                result = publisher.main(
                    ["--video", str(self.video), "--preflight-only"],
                    session_factory=factory,
                )

        self.assertEqual(result, 0)
        factory.assert_not_called()
        self.assertEqual(json.loads(output.getvalue()), self.preflight)

    def test_exact_title_duplicate_stops_before_any_post(self) -> None:
        session = FakeSession(
            [
                FakeResponse(200, {"agent_name": "orca"}),
                FakeResponse(
                    200,
                    {"videos": [{"title": "Unique evidence", "video_id": "prior"}]},
                ),
            ],
            [],
        )
        with mock.patch.object(publisher, "preflight_video", return_value=self.preflight):
            with self.assertRaisesRegex(SystemExit, "already exists"):
                publisher.main(self.argv(), session_factory=lambda: session)

        self.assertEqual(session.post_calls, [])
        self.assertFalse(self.state.exists())

    def test_success_requires_screening_and_public_page_then_saves_state(self) -> None:
        session = FakeSession(
            [
                FakeResponse(200, {"agent_name": "orca"}),
                FakeResponse(200, {"videos": []}),
                FakeResponse(200, {"version": "1.1"}),
                FakeResponse(200, None),
            ],
            [
                FakeResponse(200, {}),
                FakeResponse(
                    201,
                    {
                        "video_id": "video-1",
                        "watch_url": "/watch/video-1",
                        "screening": {"status": "passed"},
                    },
                ),
            ],
        )
        output = io.StringIO()
        with mock.patch.object(publisher, "preflight_video", return_value=self.preflight):
            with contextlib.redirect_stdout(output):
                result = publisher.main(self.argv(), session_factory=lambda: session)

        self.assertEqual(result, 0)
        summary = json.loads(output.getvalue())
        self.assertEqual(summary["live_url"], "https://bottube.ai/watch/video-1")
        self.assertEqual(summary["artifact_sha256"], self.preflight["sha256"])
        saved = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(saved["_artifact_preflight"], self.preflight)
        self.assertEqual(saved["_request"]["title"], "Unique evidence")
        self.assertEqual(len(session.post_calls), 2)

    def test_failed_screening_is_held_and_never_checked_as_public(self) -> None:
        session = FakeSession(
            [
                FakeResponse(200, {"agent_name": "orca"}),
                FakeResponse(200, {"videos": []}),
                FakeResponse(200, {"version": "1.1"}),
            ],
            [
                FakeResponse(200, {}),
                FakeResponse(
                    201,
                    {
                        "video_id": "held-1",
                        "watch_url": "/watch/held-1",
                        "screening": {"status": "held"},
                    },
                ),
            ],
        )
        with mock.patch.object(publisher, "preflight_video", return_value=self.preflight):
            with self.assertRaisesRegex(SystemExit, "not screened as passed"):
                publisher.main(self.argv(), session_factory=lambda: session)

        held = self.state.with_name("publication-held.json")
        self.assertTrue(held.exists())
        self.assertEqual(len(session.get_calls), 3)

    def test_artifact_change_stops_before_remote_mutation(self) -> None:
        changed = dict(self.preflight, sha256="0" * 64)
        session = FakeSession(
            [
                FakeResponse(200, {"agent_name": "orca"}),
                FakeResponse(200, {"videos": []}),
                FakeResponse(200, {"version": "1.1"}),
            ],
            [],
        )
        with mock.patch.object(
            publisher,
            "preflight_video",
            side_effect=[self.preflight, changed],
        ):
            with self.assertRaisesRegex(SystemExit, "changed between"):
                publisher.main(self.argv(), session_factory=lambda: session)

        self.assertEqual(session.post_calls, [])

    def test_existing_state_prevents_overwrite_and_network_access(self) -> None:
        self.state.parent.mkdir()
        self.state.write_text("{}\n", encoding="utf-8")
        factory = mock.Mock()
        with mock.patch.object(publisher, "preflight_video", return_value=self.preflight):
            with self.assertRaisesRegex(SystemExit, "refusing to overwrite"):
                publisher.main(self.argv(), session_factory=factory)
        factory.assert_not_called()

    def test_cross_origin_watch_url_is_rejected(self) -> None:
        session = FakeSession(
            [
                FakeResponse(200, {"agent_name": "orca"}),
                FakeResponse(200, {"videos": []}),
                FakeResponse(200, {"version": "1.1"}),
            ],
            [
                FakeResponse(200, {}),
                FakeResponse(
                    201,
                    {
                        "video_id": "video-1",
                        "watch_url": "https://attacker.invalid/watch/video-1",
                        "screening": {"status": "passed"},
                    },
                ),
            ],
        )
        with mock.patch.object(publisher, "preflight_video", return_value=self.preflight):
            with self.assertRaisesRegex(SystemExit, "outside the trusted"):
                publisher.main(self.argv(), session_factory=lambda: session)
        self.assertEqual(len(session.get_calls), 3)


if __name__ == "__main__":
    unittest.main()
