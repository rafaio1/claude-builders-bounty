from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parent
REMOTE_TOOLS = HERE.parent / "tools"
sys.path.insert(0, str(REMOTE_TOOLS if REMOTE_TOOLS.exists() else HERE))

import github_claim_alert_monitor as monitor  # noqa: E402


def _notification(*, notification_id: str = "notification-1") -> dict:
    return {
        "id": notification_id,
        "reason": "mention",
        "unread": True,
        "updated_at": "2026-08-28T19:00:00Z",
        "subject": {
            "title": "30 TP bounty for sparepack",
            "type": "Issue",
            "url": "https://api.github.com/repos/mxx1111/spare-cycles/issues/19",
            "latest_comment_url": (
                "https://api.github.com/repos/mxx1111/spare-cycles/"
                "issues/comments/5456549653"
            ),
        },
        "repository": {
            "full_name": "mxx1111/spare-cycles",
            "html_url": "https://github.com/mxx1111/spare-cycles",
        },
    }


def _latest(
    body: str,
    *,
    login: str = "bounty-bot[bot]",
    author_type: str = "Bot",
    comment_id: int = 5_456_549_653,
) -> dict:
    return {
        "id": comment_id,
        "body": body,
        "created_at": "2026-08-28T18:59:05Z",
        "updated_at": "2026-08-28T18:59:05Z",
        "html_url": (
            "https://github.com/mxx1111/spare-cycles/issues/19"
            f"#issuecomment-{comment_id}"
        ),
        "user": {"login": login, "type": author_type},
    }


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Claim confirmed for @rafaio1. Deadline: 2026-08-30T18:59:03.669Z.",
            "2026-08-30T18:59:03.669Z",
        ),
        (
            "@rafaio1 认领成功。截止时间：2026-08-31T12:00:00Z。",
            "2026-08-31T12:00:00Z",
        ),
        ("There is no deadline in this routine comment.", None),
    ],
)
def test_parse_deadline_supports_english_chinese_and_absence(
    text: str, expected: str | None
) -> None:
    assert monitor.parse_deadline(text) == expected


def test_classify_confirmed_claim_in_english_from_bot() -> None:
    latest = _latest(
        "Claim confirmed for @rafaio1. "
        "Deadline: 2026-08-30T18:59:03.669Z. Reward: 30 TP (escrow)."
    )

    event = monitor.classify_event(_notification(), latest)

    assert event is not None
    assert event["kind"] == "claim_confirmed"
    assert event["deadline"] == "2026-08-30T18:59:03.669Z"
    assert event["url"] == latest["html_url"]


def test_classify_confirmed_claim_in_chinese_from_bot() -> None:
    latest = _latest(
        "✅ @rafaio1 认领成功。截止时间：2026-08-31T12:00:00Z。奖励：30 TP。"
    )

    event = monitor.classify_event(_notification(), latest)

    assert event is not None
    assert event["kind"] == "claim_confirmed"
    assert event["deadline"] == "2026-08-31T12:00:00Z"


@pytest.mark.parametrize(
    "body",
    [
        "Claim released after deadline. Reclaim freely with /claim.",
        "认领已释放，可以重新认领。",
    ],
)
def test_classify_released_claim(body: str) -> None:
    event = monitor.classify_event(_notification(), _latest(body))

    assert event is not None
    assert event["kind"] == "claim_released"


def test_classify_deadline_or_action_required() -> None:
    latest = _latest(
        "Action required: update the pull request before "
        "2026-09-01T15:30:00Z or the claim will expire.",
        login="maintainer",
        author_type="User",
    )

    event = monitor.classify_event(_notification(), latest)

    assert event is not None
    assert event["kind"] == "action_required"
    assert event["deadline"] == "2026-09-01T15:30:00Z"


def test_routine_comment_does_not_alert() -> None:
    latest = _latest(
        "Thanks for the update. CI is running and the maintainers will review it soon.",
        login="maintainer",
        author_type="User",
    )

    assert monitor.classify_event(_notification(), latest) is None


def test_human_comment_imitating_bot_cannot_confirm_assignment() -> None:
    latest = _latest(
        "Claim confirmed for @rafaio1. Deadline: 2026-08-30T18:59:03Z.",
        login="bounty-bot[bot]",
        author_type="User",
    )

    assert monitor.classify_event(_notification(), latest) is None


def test_fingerprint_is_deterministic_and_deadline_sensitive() -> None:
    event = {
        "kind": "claim_confirmed",
        "repository": "mxx1111/spare-cycles",
        "subject_id": "19",
        "deadline": "2026-08-30T18:59:03Z",
        "url": "https://github.com/mxx1111/spare-cycles/issues/19",
    }
    same_event_different_insertion_order = dict(reversed(tuple(event.items())))
    changed_deadline = {**event, "deadline": "2026-08-31T18:59:03Z"}

    first = monitor.fingerprint(event)

    assert first == monitor.fingerprint(same_event_different_insertion_order)
    assert first != monitor.fingerprint(changed_deadline)
    assert first


def test_save_state_is_atomic_and_round_trips(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / "claim-alert-state.json"
    state = {
        "version": 1,
        "seen": ["fingerprint-a"],
        "active_claims": {"mxx1111/spare-cycles#19": {"status": "active"}},
    }
    real_replace = os.replace
    replacements: list[tuple[Path, Path]] = []

    def recording_replace(source, destination) -> None:
        replacements.append((Path(source), Path(destination)))
        real_replace(source, destination)

    monkeypatch.setattr(monitor.os, "replace", recording_replace)

    monitor.save_state(state_path, state)

    assert replacements, "save_state must finish with an atomic os.replace"
    assert replacements[-1][1] == state_path
    assert monitor.load_state(state_path) == state
    assert json.loads(state_path.read_text(encoding="utf-8")) == state
    assert not [path for path in tmp_path.iterdir() if path != state_path]


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are Linux-only")
def test_save_state_uses_mode_0600_on_posix(tmp_path: Path) -> None:
    state_path = tmp_path / "claim-alert-state.json"

    monitor.save_state(state_path, {"version": 1, "seen": []})

    assert stat.S_IMODE(state_path.stat().st_mode) == 0o600


def test_telegram_message_escapes_untrusted_html() -> None:
    event = {
        "kind": "action_required",
        "title": "<b>Urgent</b> & review",
        "repository": "owner/repo<script>",
        "url": "https://example.test/issues/1?a=1&b=2",
        "deadline": "2026-09-01T15:30:00Z",
    }

    message = monitor.format_telegram_message(event)

    assert "<b>Urgent</b>" not in message
    assert "&lt;b&gt;Urgent&lt;/b&gt;" in message
    assert "repo&lt;script&gt;" in message
    assert "a=1&amp;b=2" in message


def test_potential_reward_is_explicitly_not_realized_revenue() -> None:
    event = {
        "kind": "claim_confirmed",
        "title": "30 TP bounty for sparepack",
        "repository": "mxx1111/spare-cycles",
        "url": "https://github.com/mxx1111/spare-cycles/issues/19",
        "deadline": "2026-08-30T18:59:03.669Z",
        "potential_reward": "30 TP",
    }

    message = monitor.format_telegram_message(event).casefold()

    assert "30 tp" in message
    assert "não é receita realizada" in message
