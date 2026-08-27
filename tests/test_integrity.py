from __future__ import annotations

from pathlib import Path

from agentic.integrity import run_integrity
from agentic.improve_git import ImproveGit


def test_integrity_detects_kill_switch_and_entrypoint(tmp_path: Path) -> None:
    git = ImproveGit(tmp_path)
    git.ensure_repo()
    (tmp_path / "README.md").write_text("ok\n", encoding="utf-8")
    unit = tmp_path / "deploy" / "agentic-loop.service"
    unit.parent.mkdir(parents=True)
    unit.write_text(
        "[Service]\n"
        "Environment=AGENTIC_LIVE_TRADE=0\n"
        "ExecStart=/root/Agentic/.venv/bin/python -m agentic loop --interval 90\n",
        encoding="utf-8",
    )
    git.add("README.md", "deploy/agentic-loop.service")
    git.commit("init")
    report = run_integrity(tmp_path, git=git, systemd=False)
    ids = {item["id"]: item["ok"] for item in report["checks"]}
    assert ids["git_clean"] is True
    assert ids["loop_kill_switch"] is True
    assert ids["loop_entrypoint"] is True
    assert ids["loop_not_shell_script"] is True
    assert report["ok"] is True


def test_integrity_fails_without_kill_switch(tmp_path: Path) -> None:
    git = ImproveGit(tmp_path)
    git.ensure_repo()
    (tmp_path / "README.md").write_text("ok\n", encoding="utf-8")
    git.add("README.md")
    git.commit("init")
    unit = tmp_path / "deploy" / "agentic-loop.service"
    unit.parent.mkdir(parents=True)
    unit.write_text(
        "[Service]\nExecStart=/opt/python -m agentic loop\n",
        encoding="utf-8",
    )
    report = run_integrity(tmp_path, git=git, systemd=False)
    assert "loop_kill_switch" in report["failed"]


def test_integrity_separates_runtime_state_from_source_drift(tmp_path: Path) -> None:
    git = ImproveGit(tmp_path)
    git.ensure_repo()
    (tmp_path / "README.md").write_text("ok\n", encoding="utf-8")
    unit = tmp_path / "deploy" / "agentic-loop.service"
    unit.parent.mkdir(parents=True)
    unit.write_text(
        "[Service]\n"
        "Environment=AGENTIC_LIVE_TRADE=0\n"
        "ExecStart=/opt/python -m agentic loop\n",
        encoding="utf-8",
    )
    runtime = tmp_path / "config" / "algora_scanner.json"
    runtime.parent.mkdir(parents=True)
    runtime.write_text('{"last_scan": null}\n', encoding="utf-8")
    git.add("README.md", "deploy/agentic-loop.service", "config/algora_scanner.json")
    git.commit("init")

    runtime.write_text('{"last_scan": "now"}\n', encoding="utf-8")
    report = run_integrity(tmp_path, git=git, systemd=False)
    ids = {item["id"]: item for item in report["checks"]}
    assert ids["git_clean"]["ok"] is True
    assert "estado operacional" in ids["git_clean"]["detail"]
    assert report["ok"] is True

    (tmp_path / "README.md").write_text("source drift\n", encoding="utf-8")
    report = run_integrity(tmp_path, git=git, systemd=False)
    assert "git_clean" in report["failed"]
