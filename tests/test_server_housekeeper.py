#!/usr/bin/env python3
"""Testes unitarios para server_housekeeper.py (sem IA em runtime)."""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# Garante import do modulo local
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import server_housekeeper as hk


@pytest.fixture
def tmp_workspace(tmp_path: Path, monkeypatch):
    """Cria workspace temporario e redefine constantes do housekeeper."""
    root = tmp_path / "Agentic"
    workspace = root / "workspace"
    var = root / "var" / "housekeeper"
    workspace.mkdir(parents=True)
    var.mkdir(parents=True)

    monkeypatch.setattr(hk, "ROOT", root)
    monkeypatch.setattr(hk, "WORKSPACE", workspace)
    monkeypatch.setattr(hk, "MANIFEST_DIR", var)
    monkeypatch.setattr(hk, "LOCK_PATH", var / ".lock")
    return workspace


def test_is_protected_root_and_git(tmp_workspace: Path):
    assert hk.is_protected(hk.ROOT) is True
    assert hk.is_protected(hk.WORKSPACE) is True
    git_dir = tmp_workspace / "project" / ".git"
    git_dir.mkdir(parents=True)
    assert hk.is_protected(git_dir) is True
    ledger = tmp_workspace / "ledger"
    ledger.mkdir()
    assert hk.is_protected(ledger) is True


def test_find_cache_targets_respects_allowlist(tmp_workspace: Path):
    nm = tmp_workspace / "proj1" / "node_modules"
    nm.mkdir(parents=True)
    (nm / "pkg").mkdir()
    pycache = tmp_workspace / "proj2" / "__pycache__"
    pycache.mkdir(parents=True)
    protected_cache = tmp_workspace / "src" / "node_modules"
    protected_cache.mkdir(parents=True)  # 'src' eh protegido
    outside = tmp_workspace.parent / "outside_node_modules"
    outside.mkdir(parents=True)

    targets = hk.find_cache_targets()
    paths = {t[0] for t in targets}
    assert nm in paths
    assert pycache in paths
    assert protected_cache not in paths
    assert outside not in paths


def test_safe_size_ignores_symlinks(tmp_workspace: Path):
    d = tmp_workspace / "sizedir"
    d.mkdir()
    f = d / "file.txt"
    f.write_bytes(b"x" * 1024)
    link = d / "link.txt"
    link.symlink_to(f)
    assert hk.safe_size(d) == 1024


def test_run_dryrun_does_not_delete(tmp_workspace: Path):
    cache = tmp_workspace / "proj" / "node_modules"
    cache.mkdir(parents=True)
    (cache / "dep").write_bytes(b"data")
    # Forca idade antiga
    old_ts = 1000000000
    os.utime(cache, (old_ts, old_ts))

    report = hk.run_housekeeping(apply=False, max_age_days=1, skip_docker=True)
    assert cache.exists()
    assert any(e.action == "dry_run" and str(cache) in e.path for e in report.entries)


def test_run_apply_removes_old_cache(tmp_workspace: Path):
    cache = tmp_workspace / "proj" / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "mod.pyc").write_bytes(b"bytecode")
    old_ts = 1000000000
    os.utime(cache, (old_ts, old_ts))

    report = hk.run_housekeeping(apply=True, max_age_days=1, skip_docker=True)
    assert not cache.exists()
    assert report.freed_bytes > 0
    assert any(e.action == "removed" for e in report.entries)


def test_high_ticket_duplicates_report_only(tmp_workspace: Path):
    ht = tmp_workspace / "high-ticket"
    ht.mkdir(parents=True)
    # Duplicados no top-level: mesmo tamanho
    (ht / "data_a.json").write_bytes(b"dup")
    (ht / "data_b.json").write_bytes(b"dup")
    (ht / "unique.json").write_bytes(b"unique")
    # Subdir deve ser ignorado pela funcao top-level only
    sub = ht / "lotes" / "batch1"
    sub.mkdir(parents=True)
    (sub / "data.json").write_bytes(b"dup")

    dups = hk.analyze_high_ticket_duplicates()
    assert len(dups) >= 1
    assert dups[0]["count"] == 2
    assert dups[0]["proposal"].startswith("definir_retencao")
    # Arquivos permanecem
    assert (ht / "data_a.json").exists()
    assert (ht / "data_b.json").exists()


def test_lock_prevents_concurrent_runs(tmp_workspace: Path):
    assert hk.acquire_lock() is True
    assert hk.acquire_lock() is False
    hk.release_lock()
    assert hk.acquire_lock() is True
    hk.release_lock()


def test_manifest_written_with_entries(tmp_workspace: Path):
    cache = tmp_workspace / "proj" / "target"
    cache.mkdir(parents=True)
    old_ts = 1000000000
    os.utime(cache, (old_ts, old_ts))

    report = hk.run_housekeeping(apply=False, max_age_days=1, skip_docker=True)
    manifest = hk.write_manifest(report, "test")
    assert manifest.exists()
    lines = manifest.read_text().strip().splitlines()
    header = json.loads(lines[0])
    assert header["mode"] == "dry_run"
    assert len(lines) >= 2  # header + pelo menos uma entrada
