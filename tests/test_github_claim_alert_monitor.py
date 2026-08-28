from __future__ import annotations

import json
import os
import stat
import sys
from datetime import datetime, timezone
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
    author_association: str | None = None,
    comment_id: int = 5_456_549_653,
) -> dict:
    if author_association is None:
        author_association = "NONE" if author_type == "Bot" else "MEMBER"
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
        "author_association": author_association,
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
        (
            'claim deadline_date: "2026-09-04"',
            "2026-09-04T23:59:59Z",
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
        "@rafaio1 Claim released after deadline. Reclaim freely with /claim.",
        "@rafaio1 认领已释放，可以重新认领。",
    ],
)
def test_classify_released_claim(body: str) -> None:
    event = monitor.classify_event(_notification(), _latest(body))

    assert event is not None
    assert event["kind"] == "claim_released"


def test_bot_release_for_another_claimant_does_not_close_ours() -> None:
    latest = _latest(
        "@another-user Claim released after deadline. Reclaim freely with /claim."
    )

    assert monitor.classify_event(_notification(), latest) is None


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


def test_classify_explicit_maintainer_acceptance_in_rtc() -> None:
    latest = _latest(
        "@rafaio1 Your BoTTube deliverable is accepted for 15 RTC. Payment follows separately.",
        login="maintainer",
        author_type="User",
    )

    event = monitor.classify_event(_notification(), latest)

    assert event is not None
    assert event["kind"] == "claim_accepted"
    assert event["author_association"] == "MEMBER"
    assert event["potential_reward"] == "15 RTC"
    assert event["revenue_status"] == "accepted_not_settled"


def test_trusted_acceptance_without_repeating_amount_preserves_known_reward() -> None:
    event = monitor.classify_event(
        _notification(),
        _latest(
            "@rafaio1 Your claim deliverable is accepted and approved.",
            login="maintainer",
            author_type="User",
            author_association="OWNER",
            comment_id=5_456_549_654,
        ),
    )

    assert event is not None
    assert event["kind"] == "claim_accepted"
    assert event["potential_reward"] is None

    state = monitor.default_state()
    key = "github|mxx1111/spare-cycles|19"
    state["active_claims"][key] = {
        "platform": "github",
        "repository": "mxx1111/spare-cycles",
        "identifier": "19",
        "title": "Claim",
        "url": "https://github.com/mxx1111/spare-cycles/issues/19",
        "status": "active",
        "potential_reward": "30 TP",
    }

    monitor._register_event(state, event, "2026-08-28T20:00:00Z")

    claim = state["active_claims"][key]
    assert claim["status"] == "accepted"
    assert claim["potential_reward"] == "30 TP"
    assert claim["revenue_status"] == "accepted_not_settled"


def test_classify_payment_queued_but_not_settled() -> None:
    latest = _latest(
        "@rafaio1 Payout queued: 15 RTC, pending_id 4101. Confirmation follows later.",
        login="maintainer",
        author_type="User",
    )

    event = monitor.classify_event(_notification(), latest)

    assert event is not None
    assert event["kind"] == "payment_queued"
    assert event["revenue_status"] == "payment_pending_not_settled"


def test_classify_provider_confirmation_as_reconciliation_candidate() -> None:
    latest = _latest(
        "@rafaio1 Confirmed on-chain: 15 RTC, tx 0123456789abcdef.",
        login="maintainer",
        author_type="User",
    )

    event = monitor.classify_event(_notification(), latest)

    assert event is not None
    assert event["kind"] == "payment_confirmed"
    assert event["revenue_status"] == "settlement_candidate_requires_reconciliation"
    assert "ainda não é receita realizada" in monitor.format_telegram_message(event)


def test_classify_rejection_before_acceptance_words() -> None:
    latest = _latest(
        "@rafaio1 This submission is not accepted; the claim is rejected.",
        login="maintainer",
        author_type="User",
    )

    event = monitor.classify_event(_notification(), latest)

    assert event is not None
    assert event["kind"] == "claim_rejected"
    assert event["revenue_status"] == "rejected_not_revenue"


def test_own_submission_comment_cannot_self_accept() -> None:
    latest = _latest(
        "@rafaio1 Submitting one accepted-format claim for 15 RTC.",
        login="rafaio1",
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


@pytest.mark.parametrize(
    "body",
    [
        "@rafaio1 Your deliverable is accepted for 15 RTC.",
        "@rafaio1 Payout queued: 15 RTC, pending_id 4101.",
        "@rafaio1 Payment confirmed on-chain: 15 RTC, tx abcdef012345.",
        "@rafaio1 This submission is rejected and not accepted.",
        "Action required: claim deadline is 2026-09-01T15:30:00Z.",
    ],
)
def test_untrusted_human_cannot_create_operational_or_financial_event(body: str) -> None:
    latest = _latest(
        body,
        login="drive-by-contributor",
        author_type="User",
        author_association="CONTRIBUTOR",
    )

    assert monitor.classify_event(_notification(), latest) is None


@pytest.mark.parametrize("association", ["OWNER", "MEMBER", "COLLABORATOR"])
def test_trusted_human_associations_can_create_action_event(association: str) -> None:
    latest = _latest(
        "Action required: claim deadline_date: 2026-09-04.",
        login="maintainer",
        author_type="User",
        author_association=association,
    )

    event = monitor.classify_event(_notification(), latest)

    assert event is not None
    assert event["kind"] == "action_required"
    assert event["deadline"] == "2026-09-04T23:59:59Z"
    assert event["author_association"] == association


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


def test_deadline_date_is_normalized_in_state_and_drives_reminder() -> None:
    state = monitor.default_state()
    state["active_claims"]["github|owner/repo|7"] = {
        "platform": "github",
        "repository": "owner/repo",
        "identifier": "7",
        "title": "Claim",
        "url": "https://github.com/owner/repo/issues/7",
        "deadline_date": "2026-09-04",
        "status": "active",
    }

    alerts = monitor._deadline_events(
        state,
        datetime(2026, 9, 4, 23, 30, tzinfo=timezone.utc),
    )

    claim = state["active_claims"]["github|owner/repo|7"]
    assert claim["deadline_date"] == "2026-09-04"
    assert claim["deadline"] == "2026-09-04T23:59:59Z"
    assert [event["kind"] for event in alerts] == ["deadline_reminder"]
    assert alerts[0]["deadline"] == "2026-09-04T23:59:59Z"


def test_incremental_comments_and_outbox_survive_telegram_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = tmp_path / "claim-state.json"
    state = monitor.default_state()
    state["active_claims"]["github|mxx1111/spare-cycles|19"] = {
        "schema_version": monitor.SCHEMA_VERSION,
        "platform": "github",
        "repository": "mxx1111/spare-cycles",
        "identifier": "19",
        "title": "30 TP bounty for sparepack",
        "url": "https://github.com/mxx1111/spare-cycles/issues/19",
        "status": "active",
        "source_id": "100",
        "source_created_at": "2026-08-28T18:00:00Z",
        "comment_cursor": {
            "last_comment_id": 100,
            "last_comment_created_at": "2026-08-28T18:00:00Z",
        },
    }
    monitor.save_state(state_path, state)
    comments = [
        _latest(
            "Routine CI update.",
            login="maintainer",
            author_type="User",
            comment_id=101,
        ),
        _latest(
            "@rafaio1 Payout queued: 30 TP, pending_id 4101.",
            login="maintainer",
            author_type="User",
            comment_id=102,
        ),
        _latest(
            "@rafaio1 This claim is rejected and the deliverable is not accepted.",
            login="maintainer",
            author_type="User",
            author_association="COLLABORATOR",
            comment_id=103,
        ),
    ]

    def fake_gh_api(endpoint: str, timeout: int = 30):
        del timeout
        if endpoint.startswith("notifications?"):
            return []
        if endpoint.startswith("repos/mxx1111/spare-cycles/issues/19/comments?"):
            return comments
        raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr(monitor, "_gh_api", fake_gh_api)
    monkeypatch.setattr(monitor, "_telegram_send", lambda *_args, **_kwargs: False)

    with pytest.raises(RuntimeError, match="Telegram operational alert delivery failed"):
        monitor.run_monitor(state_path, tmp_path / "missing.env", "rafaio1")

    persisted = monitor.load_state(state_path)
    claim = persisted["active_claims"]["github|mxx1111/spare-cycles|19"]
    assert claim["comment_cursor"]["last_comment_id"] == 103
    assert claim["status"] == "rejected"
    assert claim["closed_at"]
    assert [item["source_id"] for item in claim["history"]] == ["102", "103"]
    assert {item["source_id"] for item in persisted["event_history"].values()} == {
        "102",
        "103",
    }
    assert len(persisted["outbox"]) == 2
    assert all(
        item["delivery_status"] == "pending"
        for item in persisted["outbox"].values()
    )
    assert persisted["last_poll_at"] is not None

    monkeypatch.setattr(monitor, "_telegram_send", lambda *_args, **_kwargs: True)
    assert monitor.run_monitor(state_path, tmp_path / "missing.env", "rafaio1") == 0

    delivered = monitor.load_state(state_path)
    assert len(delivered["seen"]) == 2
    assert all(
        item["delivery_status"] == "delivered"
        for item in delivered["outbox"].values()
    )
    assert all(
        item["delivery_status"] == "delivered"
        for item in delivered["event_history"].values()
    )
    assert delivered["active_claims"]["github|mxx1111/spare-cycles|19"]["status"] == "rejected"


def test_latest_notification_does_not_jump_existing_comment_cursor() -> None:
    state = monitor.default_state()
    key = "github|mxx1111/spare-cycles|19"
    state["active_claims"][key] = {
        "platform": "github",
        "repository": "mxx1111/spare-cycles",
        "identifier": "19",
        "title": "Claim",
        "url": "https://github.com/mxx1111/spare-cycles/issues/19",
        "status": "active",
        "comment_cursor": {
            "last_comment_id": 100,
            "last_comment_created_at": "2026-08-28T18:00:00Z",
        },
    }
    event = monitor.classify_event(
        _notification(),
        _latest(
            "@rafaio1 Payout queued: 30 TP, pending_id 4101.",
            login="maintainer",
            author_type="User",
            comment_id=200,
        ),
    )
    assert event is not None

    monitor._register_event(state, event, "2026-08-28T20:00:00Z")

    assert state["active_claims"][key]["comment_cursor"]["last_comment_id"] == 100


def test_local_deadline_elapsed_keeps_polling_and_can_later_be_accepted() -> None:
    state = monitor.default_state()
    key = "github|mxx1111/spare-cycles|19"
    state["active_claims"][key] = {
        "schema_version": monitor.SCHEMA_VERSION,
        "platform": "github",
        "repository": "mxx1111/spare-cycles",
        "identifier": "19",
        "title": "Claim",
        "url": "https://github.com/mxx1111/spare-cycles/issues/19",
        "deadline": "2026-08-28T18:00:00Z",
        "status": "active",
        "source_id": "100",
        "source_created_at": "2026-08-28T17:00:00Z",
        "reminders_sent": [],
    }
    expired = monitor._deadline_events(
        state,
        datetime(2026, 8, 28, 18, 1, tzinfo=timezone.utc),
    )
    assert len(expired) == 1
    monitor._register_event(state, expired[0], "2026-08-28T18:01:00Z")

    elapsed = state["active_claims"][key]
    assert elapsed["status"] == "deadline_elapsed_pending_verification"
    assert elapsed["operational_status"] == "deadline_elapsed_pending_verification"
    assert monitor._claim_is_active(elapsed)

    accepted = monitor.classify_event(
        _notification(),
        _latest(
            "@rafaio1 Your claim is accepted for 30 TP.",
            login="maintainer",
            author_type="User",
            author_association="OWNER",
            comment_id=101,
        ),
    )
    assert accepted is not None
    monitor._register_event(state, accepted, "2026-08-28T18:02:00Z")

    claim = state["active_claims"][key]
    assert claim["status"] == "accepted"
    assert claim["financial_stage"] == 1
    assert claim["revenue_status"] == "accepted_not_settled"
    assert "closed_at" not in claim


def test_financial_stage_does_not_regress_on_action_or_older_acceptance() -> None:
    state = monitor.default_state()
    confirmed = monitor.classify_event(
        _notification(),
        _latest(
            "@rafaio1 Payment confirmed on-chain: 30 TP, tx abcdef012345.",
            login="maintainer",
            author_type="User",
            author_association="OWNER",
            comment_id=300,
        ),
    )
    assert confirmed is not None
    monitor._register_event(state, confirmed, "2026-08-28T20:00:00Z")

    action = monitor.classify_event(
        _notification(),
        _latest(
            "Action required: claim deadline is 2026-09-01T15:30:00Z.",
            login="maintainer",
            author_type="User",
            author_association="MEMBER",
            comment_id=301,
        ),
    )
    assert action is not None
    monitor._register_event(state, action, "2026-08-28T20:01:00Z")

    key = "github|mxx1111/spare-cycles|19"
    after_action = state["active_claims"][key]
    assert after_action["status"] == "payment_reported_requires_reconciliation"
    assert after_action["operational_status"] == "action_required"
    assert after_action["financial_stage"] == 3
    assert (
        after_action["revenue_status"]
        == "settlement_candidate_requires_reconciliation"
    )

    older_acceptance = monitor.classify_event(
        _notification(),
        _latest(
            "@rafaio1 Your claim is accepted for 30 TP.",
            login="maintainer",
            author_type="User",
            author_association="COLLABORATOR",
            comment_id=302,
        ),
    )
    assert older_acceptance is not None
    monitor._register_event(state, older_acceptance, "2026-08-28T20:02:00Z")

    claim = state["active_claims"][key]
    assert claim["status"] == "payment_reported_requires_reconciliation"
    assert claim["financial_stage"] == 3
    assert claim["last_financial_event"] == "payment_confirmed"
    assert claim["revenue_status"] == "settlement_candidate_requires_reconciliation"


def test_load_legacy_v1_seen_event_is_not_requeued(
    tmp_path: Path,
) -> None:
    event = monitor.classify_event(
        _notification(),
        _latest(
            "Claim confirmed for @rafaio1. Deadline: 2026-08-30T18:59:03Z."
        ),
    )
    assert event is not None
    event_id = monitor.fingerprint(event)
    state_path = tmp_path / "legacy-state.json"
    legacy = {
        "schema_version": monitor.SCHEMA_VERSION,
        "last_poll_at": "2026-08-28T19:00:00Z",
        "seen": {
            event_id: {
                "sent_at": "2026-08-28T19:01:00Z",
                "kind": "claim_confirmed",
                "url": event["url"],
            }
        },
        "active_claims": {},
        "updated_at": "2026-08-28T19:01:00Z",
    }
    state_path.write_text(json.dumps(legacy), encoding="utf-8")

    loaded = monitor.load_state(state_path)

    assert loaded["event_history"] == {}
    assert loaded["outbox"] == {}
    assert loaded["active_claim_poll_offset"] == 0
    assert not monitor._register_event(loaded, event, "2026-08-28T20:00:00Z")
    assert loaded["outbox"] == {}
    assert loaded["event_history"][event_id]["delivery_status"] == "delivered"
    assert (
        loaded["event_history"][event_id]["delivered_at"]
        == "2026-08-28T19:01:00Z"
    )


def test_malformed_active_claims_type_fails_with_value_error(tmp_path: Path) -> None:
    state_path = tmp_path / "malformed-state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": monitor.SCHEMA_VERSION,
                "last_poll_at": None,
                "seen": {},
                "active_claims": [],
                "updated_at": None,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="malformed claim alert state"):
        monitor.load_state(state_path)


def test_pending_outbox_is_delivered_even_when_github_is_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = tmp_path / "claim-state.json"
    state = monitor.default_state()
    event = monitor.classify_event(
        _notification(),
        _latest(
            "Claim confirmed for @rafaio1. Deadline: 2026-08-30T18:59:03Z."
        ),
    )
    assert event is not None
    monitor._register_event(state, event, "2026-08-28T19:00:00Z")
    monitor.save_state(state_path, state)
    sends: list[str] = []
    monkeypatch.setattr(
        monitor,
        "_telegram_send",
        lambda text, *_args, **_kwargs: sends.append(text) is None,
    )
    monkeypatch.setattr(
        monitor,
        "_gh_api",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("github down")),
    )

    with pytest.raises(RuntimeError, match="github down"):
        monitor.run_monitor(state_path, tmp_path / "missing.env", "rafaio1")

    persisted = monitor.load_state(state_path)
    assert len(sends) == 1
    assert all(
        item["delivery_status"] == "delivered"
        for item in persisted["outbox"].values()
    )


def test_failed_latest_fetch_does_not_advance_global_poll_cursor(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = tmp_path / "claim-state.json"
    state = monitor.default_state()
    state["last_poll_at"] = "2026-08-28T18:00:00Z"
    monitor.save_state(state_path, state)

    def fake_gh_api(endpoint: str, timeout: int = 30):
        del timeout
        if endpoint.startswith("notifications?"):
            return [_notification()]
        raise RuntimeError("transient latest failure")

    monkeypatch.setattr(monitor, "_gh_api", fake_gh_api)
    monkeypatch.setattr(monitor, "_telegram_send", lambda *_args, **_kwargs: True)

    assert monitor.run_monitor(state_path, tmp_path / "missing.env", "rafaio1") == 0

    persisted = monitor.load_state(state_path)
    assert persisted["last_poll_at"] == "2026-08-28T18:00:00Z"
    assert persisted["notification_cursors"] == {}
    assert persisted["event_history"] == {}


def test_fetch_budget_exhaustion_does_not_advance_global_poll_cursor(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = tmp_path / "claim-state.json"
    state = monitor.default_state()
    state["last_poll_at"] = "2026-08-28T18:00:00Z"
    monitor.save_state(state_path, state)
    monkeypatch.setattr(monitor, "MAX_FETCHES", 1)
    monkeypatch.setattr(
        monitor,
        "_gh_api",
        lambda endpoint, timeout=30: [_notification()]
        if endpoint.startswith("notifications?")
        else pytest.fail(f"unexpected detail fetch: {endpoint}"),
    )
    monkeypatch.setattr(monitor, "_telegram_send", lambda *_args, **_kwargs: True)

    assert monitor.run_monitor(state_path, tmp_path / "missing.env", "rafaio1") == 0

    persisted = monitor.load_state(state_path)
    assert persisted["last_poll_at"] == "2026-08-28T18:00:00Z"
    assert persisted["notification_cursors"] == {}


def test_pending_telegram_failure_does_not_block_new_github_event_persistence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = tmp_path / "claim-state.json"
    state = monitor.default_state()
    confirmed = monitor.classify_event(
        _notification(),
        _latest(
            "Claim confirmed for @rafaio1. Deadline: 2026-08-30T18:59:03Z. Reward: 30 TP."
        ),
    )
    assert confirmed is not None
    monitor._register_event(state, confirmed, "2026-08-28T19:00:00Z")
    monitor.save_state(state_path, state)
    accepted_comment = _latest(
        "@rafaio1 Your claim deliverable is accepted and approved.",
        login="maintainer",
        author_type="User",
        author_association="OWNER",
        comment_id=200,
    )

    def fake_gh_api(endpoint: str, timeout: int = 30):
        del timeout
        if endpoint.startswith("notifications?"):
            return [_notification()]
        if endpoint.startswith("repos/mxx1111/spare-cycles/issues/19/comments?"):
            return []
        if endpoint.endswith("issues/comments/5456549653"):
            return accepted_comment
        if endpoint == "repos/mxx1111/spare-cycles/issues/19":
            return {"body": "Reward: 30 TP."}
        raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr(monitor, "_gh_api", fake_gh_api)
    monkeypatch.setattr(monitor, "_telegram_send", lambda *_args, **_kwargs: False)

    with pytest.raises(RuntimeError, match="Telegram operational alert delivery failed"):
        monitor.run_monitor(state_path, tmp_path / "missing.env", "rafaio1")

    persisted = monitor.load_state(state_path)
    assert len(persisted["event_history"]) == 2
    assert {item["kind"] for item in persisted["event_history"].values()} == {
        "claim_confirmed",
        "claim_accepted",
    }
    assert len(persisted["outbox"]) == 2
    assert persisted["last_poll_at"] is not None
    assert persisted["notification_cursors"]


def test_release_clears_current_financial_fields_consistently() -> None:
    state = monitor.default_state()
    queued = monitor.classify_event(
        _notification(),
        _latest(
            "@rafaio1 Payout queued: 30 TP, pending_id 4101.",
            login="maintainer",
            author_type="User",
            author_association="OWNER",
            comment_id=400,
        ),
    )
    released = monitor.classify_event(
        _notification(),
        _latest(
            "@rafaio1 Claim released after deadline. Reclaim freely with /claim.",
            comment_id=401,
        ),
    )
    assert queued is not None and released is not None
    monitor._register_event(state, queued, "2026-08-28T20:00:00Z")
    monitor._register_event(state, released, "2026-08-28T20:01:00Z")

    claim = state["active_claims"]["github|mxx1111/spare-cycles|19"]
    assert claim["status"] == "released"
    assert claim["financial_stage"] == 0
    assert "financial_status" not in claim
    assert "revenue_status" not in claim
    assert "last_financial_event" not in claim
    assert claim["closed_at"] == "2026-08-28T20:01:00Z"
    assert not monitor._claim_is_active(claim)
    assert [item["kind"] for item in claim["history"]] == [
        "payment_queued",
        "claim_released",
    ]


def test_dry_run_polls_read_only_without_telegram_secrets_or_state_write(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    state_path = tmp_path / "claim-state.json"
    state = monitor.default_state()
    event = monitor.classify_event(
        _notification(),
        _latest(
            "Claim confirmed for @rafaio1. Deadline: 2026-08-30T18:59:03Z."
        ),
    )
    assert event is not None
    monitor._register_event(state, event, "2026-08-28T19:00:00Z")
    monitor.save_state(state_path, state)
    before = state_path.read_bytes()
    github_calls: list[str] = []
    accepted_comment = _latest(
        "@rafaio1 Your claim deliverable is accepted and approved.",
        login="maintainer",
        author_type="User",
        author_association="OWNER",
        comment_id=200,
    )

    def fake_gh_api(endpoint: str, timeout: int = 30):
        del timeout
        github_calls.append(endpoint)
        if endpoint.startswith("notifications?"):
            return [_notification()]
        if endpoint.startswith("repos/mxx1111/spare-cycles/issues/19/comments?"):
            return []
        if endpoint.endswith("issues/comments/5456549653"):
            return accepted_comment
        if endpoint == "repos/mxx1111/spare-cycles/issues/19":
            return {"body": "Reward: 30 TP."}
        raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr(monitor, "_gh_api", fake_gh_api)
    monkeypatch.setattr(
        monitor,
        "_load_env",
        lambda *_args, **_kwargs: pytest.fail("dry-run read Telegram secrets"),
    )

    assert monitor.run_monitor(
        state_path,
        tmp_path / "missing.env",
        "rafaio1",
        dry_run=True,
    ) == 0

    assert state_path.read_bytes() == before
    assert github_calls
    assert github_calls[0].startswith("notifications?")
    output = capsys.readouterr().out
    assert "CLAIM CONFIRMADA" in output
    assert "CLAIM ACEITA" in output


def test_comment_without_timestamp_preserves_incremental_cursor(
    monkeypatch,
) -> None:
    state = monitor.default_state()
    key = "github|mxx1111/spare-cycles|19"
    state["active_claims"][key] = {
        "platform": "github",
        "repository": "mxx1111/spare-cycles",
        "identifier": "19",
        "title": "Claim",
        "url": "https://github.com/mxx1111/spare-cycles/issues/19",
        "status": "active",
        "comment_cursor": {
            "last_comment_id": 100,
            "last_comment_created_at": "2026-08-28T18:00:00Z",
        },
    }
    malformed = _latest(
        "@rafaio1 Your claim is accepted.",
        login="maintainer",
        author_type="User",
        author_association="OWNER",
        comment_id=101,
    )
    malformed.pop("created_at")
    malformed.pop("updated_at")
    monkeypatch.setattr(monitor, "_gh_api", lambda *_args, **_kwargs: [malformed])

    candidates, fetches = monitor._poll_active_claim_comments(
        state,
        "rafaio1",
        datetime(2026, 8, 28, 20, 0, tzinfo=timezone.utc),
        fetch_budget=1,
    )

    claim = state["active_claims"][key]
    assert candidates == []
    assert fetches == 1
    assert claim["comment_cursor"]["last_comment_id"] == 100
    assert (
        claim["comment_cursor"]["last_comment_created_at"]
        == "2026-08-28T18:00:00Z"
    )
    assert "cursor preserved" in claim["last_comment_poll_error"]
