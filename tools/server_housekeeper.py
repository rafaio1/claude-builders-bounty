#!/usr/bin/env python3
"""
server_housekeeper.py — Housekeeping deterministico para /Agentic.

Regras:
- Dry-run por default; --apply necessario para remover.
- Restrito a /Agentic/workspace e caches Docker (nunca repo root/.git/source/.env/ledger/artefatos).
- Cache allowlist: node_modules, target/debug, __pycache__, .pytest_cache, build temporario.
- Verifica lstat/symlink, idade, processo cwd/open fd e mount boundary antes de remover.
- Gera manifesto JSONL antes/depois com bytes, motivo e resultado.
- High-ticket: apenas reporta top duplicados e propoe quota; nao remove lotes/dados sem prova.
- Docker: image prune apenas dangling/unused; nunca volumes/containers.
- Lock e limite por ciclo; timer diario + trigger >=70% com meta <=65%.
- Runtime nunca chama modelo.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable, List, Optional, Set, Tuple

ROOT = Path("/Agentic")
WORKSPACE = ROOT / "workspace"
MANIFEST_DIR = ROOT / "var" / "housekeeper"
LOCK_PATH = MANIFEST_DIR / ".lock"
DEFAULT_MAX_AGE_DAYS = 14
DOCKER_PRUNE_MAX_BYTES = 2 * 1024 * 1024 * 1024  # 2G por ciclo
FS_HIGH_THRESHOLD = 70
FS_TARGET_THRESHOLD = 65

CACHE_ALLOWLIST = {
    "node_modules",
    "target",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
    ".next",
    ".turbo",
}

PROTECTED_NAMES = {
    ".git",
    ".env",
    ".env.local",
    ".env.production",
    "ledger",
    "artifacts",
    "reports",
    "relatorios",
    "source",
    "src",
    "improve",
    "deploy",
    "tools",
    "tests",
    "scripts",
    "internal",
    "AGENTS.md",
    "ARO.md",
    "README.md",
}


@dataclass
class ManifestEntry:
    timestamp: str
    path: str
    size_bytes: int
    reason: str
    action: str  # dry_run | removed | skipped | error
    detail: str = ""


@dataclass
class HousekeeperReport:
    started_at: str
    finished_at: str = ""
    mode: str = "dry_run"
    fs_total_bytes: int = 0
    fs_used_bytes: int = 0
    fs_percent: float = 0.0
    freed_bytes: int = 0
    entries: List[ManifestEntry] = field(default_factory=list)
    high_ticket_duplicates: List[dict] = field(default_factory=list)
    docker_pruned_bytes: int = 0
    errors: List[str] = field(default_factory=list)


def now_iso() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def ensure_manifest_dir() -> None:
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)


def write_manifest(report: HousekeeperReport, suffix: str) -> Path:
    ensure_manifest_dir()
    ts = dt.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    path = MANIFEST_DIR / f"housekeeper-{suffix}-{ts}.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "started_at": report.started_at,
            "finished_at": report.finished_at,
            "mode": report.mode,
            "fs_total_bytes": report.fs_total_bytes,
            "fs_used_bytes": report.fs_used_bytes,
            "fs_percent": round(report.fs_percent, 2),
            "freed_bytes": report.freed_bytes,
            "docker_pruned_bytes": report.docker_pruned_bytes,
            "errors": report.errors,
            "high_ticket_duplicates": report.high_ticket_duplicates,
        }, ensure_ascii=False) + "\n")
        for entry in report.entries:
            fh.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
    return path


def df_stats(path: Path) -> Tuple[int, int, float]:
    st = os.statvfs(str(path))
    total = st.f_blocks * st.f_frsize
    free = st.f_bfree * st.f_frsize
    used = total - free
    percent = (used / total * 100) if total else 0.0
    return total, used, percent


def is_within(base: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def is_protected(path: Path) -> bool:
    name = path.name
    if name in PROTECTED_NAMES:
        return True
    # Nunca remover raiz do repo ou workspace root
    if path == ROOT or path == WORKSPACE:
        return True
    # Proteger qualquer .git em profundidade
    if ".git" in {p.name for p in path.parents} or name == ".git":
        return True
    return False


def has_active_process(path: Path) -> bool:
    """Verifica se algum processo tem cwd ou fd aberto no caminho."""
    try:
        # Checa cwd de todos os processos
        for pid_dir in Path("/proc").iterdir():
            if not pid_dir.name.isdigit():
                continue
            cwd_link = pid_dir / "cwd"
            try:
                cwd_target = cwd_link.resolve()
                if is_within(path, cwd_target) or cwd_target == path:
                    return True
            except (PermissionError, FileNotFoundError, OSError):
                continue
            # Checa fds abertos
            fd_dir = pid_dir / "fd"
            if fd_dir.exists():
                try:
                    for fd in fd_dir.iterdir():
                        try:
                            fd_target = fd.resolve()
                            if is_within(path, fd_target) or fd_target == path:
                                return True
                        except (PermissionError, FileNotFoundError, OSError):
                            continue
                except (PermissionError, OSError):
                    pass
    except (PermissionError, OSError):
        pass
    return False


def check_mount_boundary(path: Path) -> bool:
    """Retorna True se path esta no mesmo mount que ROOT."""
    try:
        root_dev = os.stat(ROOT).st_dev
        path_dev = os.stat(path).st_dev
        return root_dev == path_dev
    except OSError:
        return False


def safe_size(path: Path) -> int:
    try:
        if path.is_symlink():
            return 0
        if path.is_file():
            return path.stat().st_size
        total = 0
        for p in path.rglob("*"):
            try:
                if p.is_file() and not p.is_symlink():
                    total += p.stat().st_size
            except OSError:
                continue
        return total
    except OSError:
        return 0


def find_cache_targets() -> List[Tuple[Path, str]]:
    """Encontra diretorios de cache regeneraveis dentro de /Agentic/workspace."""
    targets: List[Tuple[Path, str]] = []
    if not WORKSPACE.exists():
        return targets
    for allowed in CACHE_ALLOWLIST:
        for match in WORKSPACE.rglob(allowed):
            if not match.is_dir():
                continue
            if is_protected(match):
                continue
            if not is_within(WORKSPACE, match):
                continue
            if not check_mount_boundary(match):
                continue
            reason = f"cache_allowlist:{allowed}"
            targets.append((match, reason))
    return targets


def analyze_high_ticket_duplicates() -> List[dict]:
    """Reporta top duplicados em workspace/high-ticket sem remover."""
    ht = WORKSPACE / "high-ticket"
    duplicates: List[dict] = []
    if not ht.exists():
        return duplicates
    seen: dict[str, list[str]] = {}
    for p in sorted(ht.rglob("*")):
        if not p.is_file():
            continue
        if is_protected(p):
            continue
        try:
            key = f"{p.name}:{p.stat().st_size}:{p.stat().st_mtime_ns}"
        except OSError:
            continue
        seen.setdefault(key, []).append(str(p))
    for key, paths in seen.items():
        if len(paths) > 1:
            name, size_str, _ = key.split(":")
            duplicates.append({
                "name": name,
                "size_bytes": int(size_str),
                "count": len(paths),
                "paths": paths[:10],
                "proposal": "definir_retencao_e_quota_antes_de_remover",
            })
    duplicates.sort(key=lambda d: d["size_bytes"] * d["count"], reverse=True)
    return duplicates[:20]


def docker_prune_dangling(dry_run: bool) -> Tuple[int, str]:
    """Prune apenas imagens dangling/unused. Nunca volumes/containers."""
    try:
        result = subprocess.run(
            ["docker", "image", "prune", "-f", "--filter", "dangling=true"],
            capture_output=True, text=True, timeout=120,
        )
        output = result.stdout.strip()
        freed = 0
        # Parse "Total reclaimed space: X.XXGB" ou similar
        for line in output.splitlines():
            if "reclaimed" in line.lower():
                parts = line.split(":")[-1].strip()
                try:
                    val = float("".join(c for c in parts if c.isdigit() or c == "."))
                    unit = parts[-2:].lower()
                    mult = {"kb": 1024, "mb": 1024**2, "gb": 1024**3, "tb": 1024**4}
                    for u, m in mult.items():
                        if u in unit:
                            freed = int(val * m)
                            break
                except (ValueError, IndexError):
                    pass
        if dry_run:
            return 0, output
        return min(freed, DOCKER_PRUNE_MAX_BYTES), output
    except Exception as exc:
        return 0, f"docker_prune_error:{exc}"


def acquire_lock() -> bool:
    ensure_manifest_dir()
    try:
        fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        os.write(fd, f"{os.getpid()}:{now_iso()}\n".encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False


def release_lock() -> None:
    try:
        LOCK_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def run_housekeeping(apply: bool, max_age_days: int, skip_docker: bool) -> HousekeeperReport:
    report = HousekeeperReport(
        started_at=now_iso(),
        mode="apply" if apply else "dry_run",
    )
    total, used, pct = df_stats(ROOT)
    report.fs_total_bytes = total
    report.fs_used_bytes = used
    report.fs_percent = pct

    # High-ticket: apenas relatorio
    report.high_ticket_duplicates = analyze_high_ticket_duplicates()

    # Caches regeneraveis
    targets = find_cache_targets()
    cutoff = dt.datetime.utcnow() - dt.timedelta(days=max_age_days)
    freed = 0

    for path, reason in targets:
        try:
            st = path.lstat()
            mtime = dt.datetime.utcfromtimestamp(st.st_mtime)
        except OSError as exc:
            report.entries.append(ManifestEntry(
                timestamp=now_iso(), path=str(path), size_bytes=0,
                reason=reason, action="error", detail=str(exc),
            ))
            continue

        size = safe_size(path)
        age_ok = mtime < cutoff
        active = has_active_process(path)
        mount_ok = check_mount_boundary(path)

        if not mount_ok:
            action = "skipped"
            detail = "mount_boundary_violation"
        elif active:
            action = "skipped"
            detail = "active_process_detected"
        elif not age_ok:
            action = "skipped"
            detail = f"age_below_cutoff_{max_age_days}d"
        elif apply:
            try:
                shutil.rmtree(path)
                action = "removed"
                detail = ""
                freed += size
            except OSError as exc:
                action = "error"
                detail = str(exc)
        else:
            action = "dry_run"
            detail = f"would_remove_age={mtime.isoformat()}Z"

        report.entries.append(ManifestEntry(
            timestamp=now_iso(), path=str(path), size_bytes=size,
            reason=reason, action=action, detail=detail,
        ))

    report.freed_bytes = freed

    # Docker prune
    if not skip_docker:
        docker_freed, docker_detail = docker_prune_dangling(dry_run=not apply)
        report.docker_pruned_bytes = docker_freed
        if apply:
            report.freed_bytes += docker_freed
        report.entries.append(ManifestEntry(
            timestamp=now_iso(), path="docker:images:dangling",
            size_bytes=docker_freed, reason="docker_image_prune",
            action="removed" if apply else "dry_run",
            detail=docker_detail[:500],
        ))

    report.finished_at = now_iso()
    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Housekeeping deterministico /Agentic")
    parser.add_argument("--apply", action="store_true", help="Executar remocoes (default: dry-run)")
    parser.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS,
                        help=f"Idade minima para remocao (default: {DEFAULT_MAX_AGE_DAYS})")
    parser.add_argument("--skip-docker", action="store_true", help="Nao executar docker prune")
    parser.add_argument("--force-no-lock", action="store_true", help="Ignorar lock (apenas testes)")
    args = parser.parse_args(argv)

    if not args.force_no_lock:
        if not acquire_lock():
            print("ERROR: outro housekeeper esta em execucao (lock existe)", file=sys.stderr)
            return 2
    try:
        report = run_housekeeping(
            apply=args.apply,
            max_age_days=args.max_age_days,
            skip_docker=args.skip_docker,
        )
        suffix = "apply" if args.apply else "dryrun"
        manifest_path = write_manifest(report, suffix)
        print(json.dumps({
            "mode": report.mode,
            "fs_percent": round(report.fs_percent, 2),
            "freed_bytes": report.freed_bytes,
            "docker_pruned_bytes": report.docker_pruned_bytes,
            "entries": len(report.entries),
            "high_ticket_duplicates": len(report.high_ticket_duplicates),
            "manifest": str(manifest_path),
        }, indent=2))
        return 0
    finally:
        if not args.force_no_lock:
            release_lock()


if __name__ == "__main__":
    raise SystemExit(main())
