from __future__ import annotations

import os
import subprocess
from pathlib import Path


GIT_NAME = "Agentic Improve"
GIT_EMAIL = "agentic-improve@localhost"


class GitError(RuntimeError):
    pass


class ImproveGit:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["GIT_AUTHOR_NAME"] = GIT_NAME
        env["GIT_AUTHOR_EMAIL"] = GIT_EMAIL
        env["GIT_COMMITTER_NAME"] = GIT_NAME
        env["GIT_COMMITTER_EMAIL"] = GIT_EMAIL
        env.pop("GIT_DIR", None)
        env.pop("GIT_WORK_TREE", None)
        command = [
            "git",
            "-c",
            f"user.name={GIT_NAME}",
            "-c",
            f"user.email={GIT_EMAIL}",
            *args,
        ]
        completed = subprocess.run(
            command,
            cwd=self.root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if check and completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise GitError(f"git {' '.join(args)} falhou: {detail[:800]}")
        return completed

    def is_repo(self) -> bool:
        return (self.root / ".git").exists()

    def ensure_repo(self) -> None:
        if self.is_repo():
            return
        init = self.run("init", "-b", "main", check=False)
        if init.returncode != 0:
            self.run("init")
            current = self.current_branch()
            if current and current != "main":
                self.run("branch", "-M", "main", check=False)

    def current_branch(self) -> str:
        completed = self.run("rev-parse", "--abbrev-ref", "HEAD", check=False)
        if completed.returncode != 0:
            return ""
        return (completed.stdout or "").strip()

    def primary_branch(self) -> str:
        for name in ("main", "master"):
            probe = self.run("show-ref", "--verify", "--quiet", f"refs/heads/{name}", check=False)
            if probe.returncode == 0:
                return name
        current = self.current_branch()
        return current or "main"

    def has_commits(self) -> bool:
        probe = self.run("rev-parse", "--verify", "HEAD", check=False)
        return probe.returncode == 0

    def _status_lines(self) -> list[str]:
        completed = self.run("status", "--porcelain")
        return [line for line in (completed.stdout or "").splitlines() if line.strip()]

    @staticmethod
    def _path_from_status(line: str) -> str:
        raw = line[3:].strip().strip('"') if len(line) >= 4 else line.strip()
        if " -> " in raw:
            raw = raw.split(" -> ", 1)[-1].strip().strip('"')
        return raw

    @staticmethod
    def _runtime_noise(line: str) -> bool:
        path = ImproveGit._path_from_status(line)
        name = path.rsplit("/", 1)[-1]
        if path in {"lock", ".agentic.lock"} or name == "lock":
            return True
        if name.startswith(".agentic") and name.endswith(".lock"):
            return True
        if name.endswith((".sqlite3", ".sqlite3-wal", ".sqlite3-shm")):
            return True
        if "__pycache__" in path.split("/") or name.endswith((".pyc", ".pyo")):
            return True
        if path == ".env" or path.startswith(".env.") or path.startswith(".venv/"):
            return True
        if path == "data" or path.startswith("data/"):
            return True
        return False

    def dirty_paths(self) -> list[str]:
        paths: list[str] = []
        for line in self._status_lines():
            if self._runtime_noise(line):
                continue
            path = self._path_from_status(line)
            if path and path not in paths:
                paths.append(path)
        return paths

    def dirty(self) -> bool:
        return any(not self._runtime_noise(line) for line in self._status_lines())

    def status_text(self) -> str:
        lines = [line for line in self._status_lines() if not self._runtime_noise(line)]
        return "\n".join(lines).strip()

    def checkout(self, branch: str, *, create: bool = False) -> None:
        # Safety: never mutate shared worktree HEAD when running in isolated context
        # IMPROVE_NO_CHECKOUT=1 disables all checkout operations to prevent
        # concurrent agents from losing their working tree state.
        import os as _os
        if _os.environ.get("IMPROVE_NO_CHECKOUT") == "1":
            # In no-checkout mode, branch creation uses git branch instead of checkout -B
            if create:
                # Create branch without switching to it
                self.run("branch", "-f", branch, check=False)
            # Skip checkout entirely - caller must use GIT_WORK_TREE or similar
            return
        if create:
            self.run("checkout", "-B", branch)
            return
        self.run("checkout", branch)

    def branch_exists(self, name: str) -> bool:
        probe = self.run("show-ref", "--verify", "--quiet", f"refs/heads/{name}", check=False)
        return probe.returncode == 0

    def add(self, *paths: str) -> None:
        if not paths:
            return
        self.run("add", "--", *paths)

    def commit(self, message: str) -> bool:
        if not self.dirty():
            return False
        self.run("commit", "-m", message)
        return True

    def merge_ff_or_no_ff(self, branch: str, message: str) -> None:
        self.run("merge", "--no-ff", "--no-edit", "-m", message, branch)

    def abort_merge(self) -> None:
        self.run("merge", "--abort", check=False)

    def delete_branch(self, name: str, *, force: bool = False) -> None:
        flag = "-D" if force else "-d"
        self.run("branch", flag, name, check=False)

    def diff_stat(self, base: str, head: str = "HEAD") -> str:
        completed = self.run("diff", "--stat", f"{base}...{head}", check=False)
        return (completed.stdout or "")[:4000]

    def diff_names(self, base: str, head: str = "HEAD") -> list[str]:
        completed = self.run("diff", "--name-only", f"{base}...{head}", check=False)
        return [line.strip() for line in (completed.stdout or "").splitlines() if line.strip()]

    def diff_text(self, base: str, head: str = "HEAD", *, limit: int = 12000) -> str:
        completed = self.run("diff", f"{base}...{head}", check=False)
        text = completed.stdout or ""
        if len(text) <= limit:
            return text
        return text[:limit] + "\n…[diff truncado]\n"

    def list_branches(self, prefix: str) -> list[str]:
        completed = self.run("for-each-ref", "--format=%(refname:short)", "refs/heads")
        names = [line.strip() for line in (completed.stdout or "").splitlines() if line.strip()]
        return [name for name in names if name.startswith(prefix)]

    def is_merged(self, branch: str, into: str) -> bool:
        completed = self.run("merge-base", "--is-ancestor", branch, into, check=False)
        return completed.returncode == 0

    def reset_worktree(self) -> None:
        self.run("reset", "--hard", "HEAD", check=False)
        self.run(
            "clean",
            "-fd",
            "--",
            "src",
            "tests",
            "improve",
            "deploy",
            "scripts",
            "internal",
            check=False,
        )
