from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentic.config import Settings
from agentic.improve import (
    ImprovePipeline,
    apply_files,
    canonical_proposal_key,
    eval_traces,
    is_allowed_path,
    merge_proposals,
    normalize_item,
    parse_loop_unit_limits,
    pick_pending,
    scan_forbidden,
)
from agentic.improve_git import ImproveGit


class FakeGhost:
    def __init__(self, *, verdict: str = "approve") -> None:
        self.verdict = verdict
        self.calls: list[str] = []

    def map_improvements(self, prompt: str) -> dict:
        self.calls.append("map")
        assert "AGENTIC_LIVE_TRADE" in prompt
        return {
            "summary": "playwright e kill switch são o gargalo",
            "bottlenecks": [
                {
                    "title": "Documentar intervalo do loop",
                    "priority": 1,
                    "rationale": "interval systemd pouco visível",
                    "change": "nota no CURRENT",
                    "files_hint": ["improve/CURRENT.md"],
                    "never": ["trade live", "secrets"],
                }
            ],
            "improvements": [],
        }

    def review_improvement(self, prompt: str) -> dict:
        self.calls.append("review")
        return {"verdict": self.verdict, "reason": "patch pequeno e defensivo", "risks": []}


def _fake_implement(root: Path):
    def implement(prompt: str) -> dict:
        assert "Documentar intervalo" in prompt or "PROPOSTA" in prompt
        note = root / "improve" / "NOTE.md"
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text("intervalo do loop\n", encoding="utf-8")
        return {
            "ok": True,
            "summary": "SUMMARY: nota de otimização",
            "output": "SUMMARY: nota de otimização",
            "returncode": 0,
            "model": "test-model",
        }

    return implement


def _settings(root: Path) -> Settings:
    return Settings(
        root=root,
        lock_path=root / ".agentic.lock",
        ghostcli_api_key="test",
        ghostcli_base_url="https://ghost.invalid/v1",
        ghostcli_model="test-model",
        ghostcli_orchestrator_model="test-orch",
        interval_seconds=90,
        live_trade=False,
    )


def _repo(root: Path) -> ImproveGit:
    git = ImproveGit(root)
    git.ensure_repo()
    (root / "README.md").write_text("root\n", encoding="utf-8")
    (root / "improve").mkdir(parents=True, exist_ok=True)
    (root / "src" / "agentic").mkdir(parents=True, exist_ok=True)
    (root / "src" / "agentic" / "__init__.py").write_text("", encoding="utf-8")
    (root / ".gitignore").write_text(
        ".agentic-improve.lock\n.agentic.lock\n.env\ndata/\n",
        encoding="utf-8",
    )
    git.add("README.md", ".gitignore", "src/agentic/__init__.py")
    git.commit("init")
    return git


def test_path_and_content_gates() -> None:
    assert is_allowed_path("src/agentic/loop.py")
    assert is_allowed_path("improve/ledger.json")
    assert is_allowed_path("internal/load-env.sh")
    assert is_allowed_path("ARO.md")
    assert not is_allowed_path(".env")
    assert not is_allowed_path("data/status.json")
    assert not is_allowed_path("../etc/passwd")
    assert scan_forbidden("AGENTIC_LIVE_TRADE=1") is not None
    assert scan_forbidden("BYBIT_API_KEY=abcd1234567890secret") is not None
    assert scan_forbidden("GHOSTCLI_API_KEY=test") is None
    assert scan_forbidden("GHOSTCLI_API_KEY=REDACTED") is None
    assert scan_forbidden("print('ok')") is None


def test_scan_forbidden_allows_live_trade_refusal() -> None:
    assert scan_forbidden("AGENTIC_LIVE_TRADE=1") is not None
    assert (
        scan_forbidden(
            'raise RuntimeError("AGENTIC_LIVE_TRADE=1 recusado; o loop não opera Bybit")'
        )
        is None
    )
    assert scan_forbidden("não ligue AGENTIC_LIVE_TRADE=1 em produção") is None
    assert scan_forbidden("nem ligue AGENTIC_LIVE_TRADE=1.") is None
    assert scan_forbidden("Rejeite se: exploits/PoC, AGENTIC_LIVE_TRADE=1, secrets") is None


def test_scan_forbidden_added_lines_ignores_context() -> None:
    from agentic.improve import scan_forbidden_added_lines

    diff = (
        "--- a/src/agentic/x.py\n"
        "+++ b/src/agentic/x.py\n"
        "@@ -1,3 +1,4 @@\n"
        " existing wordlist mention stays\n"
        "+print('safe change')\n"
        " keep\n"
    )
    assert scan_forbidden_added_lines(diff) is None
    bad = (
        "--- a/x.py\n+++ b/x.py\n@@ -1 +1,2 @@\n keep\n+AGENTIC_LIVE_TRADE=1\n"
    )
    assert scan_forbidden_added_lines(bad) is not None


def test_apply_files_rejects_new_loop_script(tmp_path: Path) -> None:
    try:
        apply_files(
            tmp_path,
            [{"path": "src/agentic/loop.sh", "content": "#!/bin/bash\necho hi\n"}],
        )
    except ValueError as exc:
        assert "morto" in str(exc) or "novo" in str(exc)
    else:
        raise AssertionError("deveria recusar loop.sh novo")


def test_apply_files_rejects_secrets(tmp_path: Path) -> None:
    target = tmp_path / "src" / "agentic" / "x.py"
    target.parent.mkdir(parents=True)
    target.write_text("ok\n", encoding="utf-8")
    try:
        apply_files(
            tmp_path,
            [{"path": "src/agentic/x.py", "content": "GHOSTCLI_API_KEY=gk-live-reallooking-secret99"}],
        )
    except ValueError as exc:
        assert "recusado" in str(exc)
    else:
        raise AssertionError("deveria recusar segredo")


def test_parse_loop_unit_limits_reads_execstart(tmp_path: Path) -> None:
    unit = tmp_path / "deploy" / "agentic-loop.service"
    unit.parent.mkdir(parents=True)
    unit.write_text(
        "[Service]\n"
        "Environment=AGENTIC_LIVE_TRADE=0\n"
        "ExecStart=/opt/python -m agentic loop --interval 90\n",
        encoding="utf-8",
    )
    limits = parse_loop_unit_limits(tmp_path)
    assert limits["interval"] == 90
    assert limits["live_trade_disabled"] is True


def test_merge_proposals_does_not_revive_applied() -> None:
    ledger = {"proposals": []}
    first = normalize_item(
        {"title": "Saúde playwright", "priority": 1, "rationale": "x", "change": "y"},
        kind="bottleneck",
        map_id="m1",
    )
    assert first is not None
    merge_proposals(ledger, [first])
    ledger["proposals"][0]["status"] = "applied"
    again = normalize_item(
        {"title": "Saúde playwright", "priority": 1, "rationale": "x", "change": "y"},
        kind="bottleneck",
        map_id="m2",
    )
    assert again is not None
    added = merge_proposals(ledger, [again])
    assert added == []
    assert ledger["proposals"][0]["status"] == "applied"


def test_canonical_key_collapses_similar_titles() -> None:
    assert canonical_proposal_key("Throughput do loop baixo para backlog", "bottleneck") == (
        canonical_proposal_key("Throughput do loop baixo demais para backlog", "bottleneck")
    )


def test_map_develop_review_applies_on_primary(tmp_path: Path) -> None:
    git = _repo(tmp_path)
    settings = _settings(tmp_path)
    ghost = FakeGhost()
    pipeline = ImprovePipeline(
        settings,
        git=git,
        ghost=ghost,
        implementer=_fake_implement(tmp_path),
        tester=lambda: {"ok": True, "output": "ok"},
        restarter=lambda files: {"restarted": ["agentic-loop.service"], "note": "", "errors": []},
    )
    mapped = pipeline.map()
    assert mapped["added"]
    assert git.current_branch() in {"main", "master"}
    developed = pipeline.develop()
    assert developed["status"] == "in_review"
    assert developed.get("via") == "claude_cli+ghostcli"
    assert git.current_branch() in {"main", "master"}
    reviewed = pipeline.review()
    assert reviewed["status"] == "applied"
    assert reviewed["applied"] is True
    assert git.current_branch() in {"main", "master"}
    assert (tmp_path / "improve" / "NOTE.md").is_file()


def test_review_reject_does_not_merge(tmp_path: Path) -> None:
    git = _repo(tmp_path)
    settings = _settings(tmp_path)
    pipeline = ImprovePipeline(
        settings,
        git=git,
        ghost=FakeGhost(verdict="reject"),
        implementer=_fake_implement(tmp_path),
        tester=lambda: {"ok": True, "output": "ok"},
        restarter=lambda files: {"restarted": [], "note": "", "errors": []},
    )
    pipeline.map()
    pipeline.develop()
    reviewed = pipeline.review()
    assert reviewed["applied"] is False
    assert reviewed["status"] in {"requeued", "rejected"}
    assert not (tmp_path / "improve" / "NOTE.md").exists() or git.current_branch() in {
        "main",
        "master",
    }


def test_pick_pending_prefers_review_feedback() -> None:
    ledger = {
        "proposals": [
            {"id": "b", "status": "pending", "priority": 1, "review_feedback": ""},
            {"id": "a", "status": "pending", "priority": 2, "review_feedback": "corrija o teste"},
        ]
    }
    picked = pick_pending(ledger)
    assert picked is not None
    assert picked["id"] == "a"


def test_eval_traces_metrics(tmp_path: Path) -> None:
    """eval_traces cruza ledger com traces e devolve métricas de eficácia."""
    ledger = {
        "proposals": [
            {
                "id": "p1",
                "status": "approved",
                "theme": "ai",
                "review_feedback": "",
                "history": [],
            },
            {
                "id": "p2",
                "status": "requeued",
                "theme": "engine",
                "review_feedback": "refatorar loop",
                "history": [{"event": "requeued"}],
            },
            {
                "id": "p3",
                "status": "rejected",
                "theme": "ai",
                "review_feedback": "prompt vago",
                "history": [],
            },
        ]
    }
    imp_dir = tmp_path / "improve"
    imp_dir.mkdir()
    (imp_dir / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
    traces_dir = imp_dir / "traces"
    traces_dir.mkdir()
    (traces_dir / "20260817T000000Z_aaa.json").write_text(
        json.dumps({"method": "develop_improvement", "parsed_summary": '{"summary":"ok"}'}),
        encoding="utf-8",
    )
    (traces_dir / "20260817T000001Z_bbb.json").write_text(
        json.dumps({"method": "review_improvement", "parsed_summary": '{"verdict":"reject"}'}),
        encoding="utf-8",
    )
    result = eval_traces(tmp_path)
    assert result["proposals_total"] == 3
    assert result["with_review_feedback"] == 2
    assert result["feedback_coverage_pct"] == pytest.approx(66.7, abs=0.1)
    assert result["requeues"] == 1
    assert result["requeue_rate_pct"] == pytest.approx(33.3, abs=0.1)
    assert result["verdicts"]["approved"] == 1
    assert result["verdicts"]["requeued"] == 1
    assert result["themes"]["ai"] == 2
    assert result["traces"]["files"] == 2
    assert result["traces"]["methods"]["develop_improvement"] == 1
    assert result["traces"]["parse_fail_recent"] == 0
