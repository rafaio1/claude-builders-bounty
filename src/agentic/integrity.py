from __future__ import annotations

import json
import fnmatch
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentic.improve import LEDGER_PATH, ineffective_paths, load_json
from agentic.improve_git import ImproveGit

LOOP_UNIT = Path("deploy") / "agentic-loop.service"
EXPECTED_UNITS = (
    "agentic-loop.service",
    "bughunter-improve-map.timer",
    "bughunter-improve-dev.timer",
    "bughunter-improve-review.timer",
    "agentic-integrity.timer",
    "agentic-portal.service",
    "agentic-portal-snapshot.timer",
)
RUNTIME_STATE_PATTERNS = (
    "config/*_scanner.json",
    "config/*_state.json",
    "config/defi_platforms.json",
    "config/gitcoin_grants.json",
    "config/vuln_report_config.json",
    "data/aro/bounty_ledger.json",
    "data/aro/pr_revenue_queue.json",
    "revenue/hats_opportunities/*.json",
    "revenue/layer3_opportunities/*.json",
    "revenue/rabbithole_opportunities/*.json",
)
KILL_SWITCH_RE = re.compile(r"^Environment=AGENTIC_LIVE_TRADE=0\s*$", re.M)
EXEC_START_RE = re.compile(r"^ExecStart=(.+)$", re.M)


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def empty_integrity() -> dict[str, Any]:
    return {
        "ok": True,
        "status": "missing",
        "generated_at": "",
        "summary": "Integridade ainda não rodou",
        "failed": [],
        "checks": [],
        "total": 0,
    }


def _check(check_id: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"id": check_id, "ok": bool(ok), "detail": detail[:400]}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _exec_start(text: str) -> str:
    match = EXEC_START_RE.search(text or "")
    return (match.group(1).strip() if match else "")


def is_runtime_state_path(path: str) -> bool:
    normalized = str(path or "").replace("\\", "/")
    return any(fnmatch.fnmatchcase(normalized, pattern) for pattern in RUNTIME_STATE_PATTERNS)


def _systemctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["systemctl", *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )


def run_integrity(
    root: Path,
    *,
    git: ImproveGit | None = None,
    systemd: bool = True,
    installed_loop: Path | None = None,
) -> dict[str, Any]:
    root = Path(root)
    git = git or ImproveGit(root)
    checks: list[dict[str, Any]] = []

    def add(check_id: str, ok: bool, detail: str) -> None:
        checks.append(_check(check_id, ok, detail))

    if not git.is_repo() or not git.has_commits():
        add("git_repo", False, "repositório git ausente ou sem commits")
    else:
        primary = git.primary_branch()
        current = git.current_branch()
        add(
            "git_primary",
            current == primary,
            f"HEAD={current or 'vazio'} primary={primary}",
        )
        dirty_paths = git.dirty_paths()
        runtime_dirty = [path for path in dirty_paths if is_runtime_state_path(path)]
        source_dirty = [path for path in dirty_paths if path not in runtime_dirty]
        if source_dirty:
            add(
                "git_clean",
                False,
                "main suja; GhostCLI: proposta Restaurar git_clean "
                "(não reset --hard, não .env/data). " + "\n".join(source_dirty),
            )
        elif runtime_dirty:
            add(
                "git_clean",
                True,
                f"source tree limpa; {len(runtime_dirty)} arquivo(s) de estado operacional isolado(s)",
            )
        else:
            add("git_clean", True, "working tree limpa")

    unit_text = _read(root / LOOP_UNIT)
    exec_start = _exec_start(unit_text)
    add(
        "loop_unit_exists",
        bool(unit_text),
        str(root / LOOP_UNIT) if unit_text else f"{LOOP_UNIT} ausente",
    )
    add(
        "loop_kill_switch",
        bool(KILL_SWITCH_RE.search(unit_text)),
        "AGENTIC_LIVE_TRADE=0 na unit do repositório",
    )
    add(
        "loop_entrypoint",
        " -m agentic loop " in f" {exec_start} " or exec_start.endswith(" -m agentic loop"),
        exec_start or "ExecStart ausente",
    )
    add(
        "loop_not_shell_script",
        "loop.sh" not in exec_start and "src/agentic/loop.sh" not in unit_text,
        "ExecStart não aponta para loop.sh",
    )

    dead_scripts = sorted(
        str(path.relative_to(root))
        for path in (root / "src" / "agentic").glob("*.sh")
        if path.is_file()
    )
    add(
        "no_dead_loop_sh",
        not dead_scripts,
        "sem scripts em src/agentic" if not dead_scripts else ", ".join(dead_scripts),
    )

    installed = installed_loop or Path("/etc/systemd/system/agentic-loop.service")
    if systemd:
        if installed.is_file():
            installed_text = _read(installed)
            add(
                "installed_kill_switch",
                bool(KILL_SWITCH_RE.search(installed_text)),
                "unit instalada mantém AGENTIC_LIVE_TRADE=0",
            )
            add(
                "installed_matches_repo",
                _exec_start(installed_text) == exec_start,
                "ExecStart instalado igual ao da main",
            )
        else:
            add("installed_loop_unit", False, "unit instalada ausente")
    else:
        add("installed_loop_unit", True, "unit instalada ignorada neste check")

    ledger = load_json(root / LEDGER_PATH, {"proposals": []})
    proposals = [
        item for item in ledger.get("proposals") or [] if isinstance(item, dict)
    ]
    stuck = [
        str(item.get("id"))
        for item in proposals
        if str(item.get("status") or "") == "developing"
        and not str(item.get("branch") or "").strip()
    ]
    add(
        "ledger_claims",
        not stuck,
        "claims com branch" if not stuck else "developing sem branch: " + ", ".join(stuck),
    )

    if git.is_repo() and git.has_commits():
        primary = git.primary_branch()
        dead_branches: list[str] = []
        for name in git.list_branches("improve/dev/"):
            if git.is_merged(name, primary):
                continue
            changed = git.diff_names(primary, name)
            if ineffective_paths(changed):
                dead_branches.append(name)
        add(
            "no_dead_dev_branch",
            not dead_branches,
            "branches de develop sem scripts mortos"
            if not dead_branches
            else "script morto em " + ", ".join(dead_branches),
        )

    if systemd and shutil.which("systemctl"):
        missing: list[str] = []
        for unit in EXPECTED_UNITS:
            probe = _systemctl("is-active", unit)
            if probe.returncode != 0:
                missing.append(f"{unit}={(probe.stdout or probe.stderr or 'inactive').strip()}")
        add(
            "services_active",
            not missing,
            "units esperadas ativas" if not missing else "; ".join(missing),
        )
    else:
        add("services_active", True, "systemd ignorado neste check")

    aro_pkg = root / "src" / "agentic" / "aro"
    if aro_pkg.is_dir():
        from agentic.aro.constitution import OWNER_SHARE_RATE, constitution_intact

        intact, detail = constitution_intact(root)
        add("aro_constitution", intact, str(detail))
        add(
            "aro_share_rate",
            OWNER_SHARE_RATE == 0.20,
            f"OWNER_SHARE_RATE={OWNER_SHARE_RATE}",
        )
        stop_unit = bool(KILL_SWITCH_RE.search(unit_text))
        add(
            "aro_no_live_trade",
            stop_unit,
            "ARO não opera Bybit; kill switch do loop permanece 0",
        )
    else:
        add("aro_constitution", True, "ARO ausente neste tree")

    failed = [item["id"] for item in checks if not item["ok"]]
    ok = not failed
    return {
        "ok": ok,
        "status": "ok" if ok else "failed",
        "generated_at": utcnow(),
        "summary": (
            "Integridade ok"
            if ok
            else (
                f"{len(failed)} check(s) falharam"
                + (
                    " — working tree suja na main; GhostCLI: proposta Restaurar git_clean; "
                    "não reset --hard nem commitar .env/secrets"
                    if "git_clean" in failed
                    else ""
                )
            )
        ),
        "failed": failed,
        "checks": checks,
        "total": len(checks),
    }


def write_integrity(payload: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return path


def default_report_path(root: Path) -> Path:
    return Path(root) / "data" / "integrity.json"


def run_and_store(
    root: Path,
    *,
    git: ImproveGit | None = None,
    systemd: bool = True,
    path: Path | None = None,
) -> dict[str, Any]:
    report = run_integrity(root, git=git, systemd=systemd)
    write_integrity(report, path or default_report_path(root))
    return report
