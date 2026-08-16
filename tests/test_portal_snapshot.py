from __future__ import annotations

from pathlib import Path

from agentic.portal_snapshot import build_snapshot


def test_snapshot_maps_aro_without_secrets(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "status.json").write_text(
        '{"ok": true, "generated_at": "2026-08-16T14:00:00+00:00",'
        ' "tools": {"playwright": true, "ghostcli": true, "bybit_key": true,'
        ' "bybit_secret": true}, "aro": {"paused": false, "ready_for_outbound": false,'
        ' "next_action": "configure payout"}}',
        encoding="utf-8",
    )
    (tmp_path / "improve").mkdir()
    (tmp_path / "improve" / "ledger.json").write_text(
        '{"updated_at": "2026-08-16T14:00:00+00:00", "proposals": []}',
        encoding="utf-8",
    )
    reports = tmp_path / "data" / "aro" / "reports"
    reports.mkdir(parents=True)
    reports.joinpath("daily-2026-08-16.json").write_text(
        '{"offers": [{"id": "offer-bugfix-api", "title": "Corrijo um bug",'
        ' "status": "draft"}], "decision": {"next_action": "wait"}}',
        encoding="utf-8",
    )
    inbox = tmp_path / "inbox.jsonl"
    inbox.write_text(
        '{"id": "abcabcabcabc", "role": "owner", "author": "rafaio",'
        ' "body": "ola", "at": "2026-08-16T14:01:00+00:00"}\n',
        encoding="utf-8",
    )
    snapshot = build_snapshot(tmp_path, inbox=inbox)
    assert snapshot["schema_version"] == 1
    assert snapshot["stats"]["offers_total"] == 1
    assert snapshot["findings"][0]["title"] == "Corrijo um bug"
    assert snapshot["messages"][0]["body"] == "ola"
    blob = str(snapshot)
    assert "bybit_secret" not in blob
    assert "GHOSTCLI" not in blob
