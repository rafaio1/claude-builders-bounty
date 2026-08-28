"""Verify revenue workflow checkpoints against the official GitHub API.

The caller supplies only a work-order context and an evidence URL.  Actor,
receipt identifier, timestamp and digest are derived here from the API response;
they are never accepted as assertions from an agent.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


GITHUB_API_BASE = "https://api.github.com"
GITHUB_HOST = "github.com"
ACTION_ACTORS = {
    "claim_confirmed": "revenue_generator",
    "tests_passed": "revenue_generator",
    "pr_published": "integrator",
    "review_approved": "reviewer",
    "delivery_accepted": "contador",
}
ACTION_EXPECTED_STATUS = {
    "claim_confirmed": "queued",
    "tests_passed": "in_progress",
    "pr_published": "under_review",
    "review_approved": "integration_ready",
    "delivery_accepted": "published",
}
SHA_RE = re.compile(r"^[0-9a-f]{40,64}$")


class EvidenceVerificationError(ValueError):
    """Official evidence is missing, stale, contradictory or out of scope."""


@dataclass(frozen=True)
class VerifiedEvidence:
    action_type: str
    evidence_url: str
    receipt_id: str
    payload_sha256: str
    observed_at: str
    actor_alias: str
    expected_from_status: str
    work_order_version: int
    repo_key: str
    issue_number: int | None
    pr_number: int | None
    head_sha: str | None
    metadata: dict[str, Any]

    def record(self) -> dict[str, Any]:
        return asdict(self)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _github_get(api_path: str) -> Any:
    """Read one official API resource; tests replace this private transport."""
    if not api_path.startswith("/") or ".." in api_path:
        raise EvidenceVerificationError("invalid GitHub API path")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "agentic-revenue-evidence/1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(f"{GITHUB_API_BASE}{api_path}", headers=headers)
    try:
        with urlopen(request, timeout=20) as response:
            if response.status != 200:
                raise EvidenceVerificationError(
                    f"GitHub API returned HTTP {response.status}"
                )
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise EvidenceVerificationError(
            f"GitHub API returned HTTP {error.code}"
        ) from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise EvidenceVerificationError("GitHub API evidence unavailable") from error


def _parse_repo_resource(url: str) -> tuple[str, str, str, int, str]:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").casefold() != GITHUB_HOST
        or len(parts) < 4
        or parts[2] not in {"issues", "pull"}
        or not parts[3].isdigit()
    ):
        raise EvidenceVerificationError("evidence must be a canonical GitHub issue or PR URL")
    return parts[0], parts[1], parts[2], int(parts[3]), parsed.fragment


def _parse_run(url: str) -> tuple[str, str, int]:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").casefold() != GITHUB_HOST
        or len(parts) != 5
        or parts[2:4] != ["actions", "runs"]
        or not parts[4].isdigit()
    ):
        raise EvidenceVerificationError("test evidence must be a canonical Actions run URL")
    return parts[0], parts[1], int(parts[4])


def _same_repo(repo_key: str, owner: str, repo: str) -> None:
    if f"{owner}/{repo}".casefold() != repo_key.casefold():
        raise EvidenceVerificationError("evidence belongs to a different repository")


def _same_html_url(api_url: Any, evidence_url: str, *, allow_fragment: bool = False) -> None:
    left = urlparse(str(api_url or ""))
    right = urlparse(evidence_url)
    if (left.scheme, left.netloc.casefold(), left.path.rstrip("/")) != (
        right.scheme,
        right.netloc.casefold(),
        right.path.rstrip("/"),
    ):
        raise EvidenceVerificationError("official API URL does not match evidence URL")
    if not allow_fragment and right.fragment:
        raise EvidenceVerificationError("unexpected evidence URL fragment")


def _prior(prior_actions: Mapping[str, Mapping[str, Any]], action: str) -> Mapping[str, Any]:
    value = prior_actions.get(action)
    if not value:
        raise EvidenceVerificationError(f"missing prior verified action: {action}")
    metadata = value.get("metadata")
    if not isinstance(metadata, Mapping):
        raise EvidenceVerificationError(f"prior action metadata invalid: {action}")
    return metadata


def _issue_linked(body: str, repo_key: str, issue_number: int) -> bool:
    escaped_repo = re.escape(repo_key)
    patterns = (
        rf"(?<![\w#])#{issue_number}(?!\d)",
        rf"(?<![\w/]){escaped_repo}#{issue_number}(?!\d)",
        rf"https://github\.com/{escaped_repo}/issues/{issue_number}(?!\d)",
    )
    return any(re.search(pattern, body, flags=re.IGNORECASE) for pattern in patterns)


def _require_sha(value: Any) -> str:
    sha = str(value or "").casefold()
    if not SHA_RE.fullmatch(sha):
        raise EvidenceVerificationError("official evidence has an invalid commit SHA")
    return sha


def _verified(
    *,
    action_type: str,
    evidence_url: str,
    receipt_id: str,
    status: str,
    version: int,
    repo_key: str,
    issue_number: int | None,
    pr_number: int | None,
    head_sha: str | None,
    metadata: dict[str, Any],
) -> VerifiedEvidence:
    canonical_payload = {
        "action_type": action_type,
        "evidence_url": evidence_url,
        "receipt_id": receipt_id,
        "expected_from_status": status,
        "work_order_version": version,
        "repo_key": repo_key.casefold(),
        "issue_number": issue_number,
        "pr_number": pr_number,
        "head_sha": head_sha,
        "metadata": metadata,
    }
    return VerifiedEvidence(
        action_type=action_type,
        evidence_url=evidence_url,
        receipt_id=receipt_id,
        payload_sha256=_canonical_digest(canonical_payload),
        observed_at=_iso_now(),
        actor_alias=ACTION_ACTORS[action_type],
        expected_from_status=status,
        work_order_version=version,
        repo_key=repo_key,
        issue_number=issue_number,
        pr_number=pr_number,
        head_sha=head_sha,
        metadata=metadata,
    )


def verify_github_evidence(
    action_type: str,
    evidence_url: str,
    context: Mapping[str, Any],
    prior_actions: Mapping[str, Mapping[str, Any]],
) -> VerifiedEvidence:
    """Return only facts independently confirmed by GitHub's official API."""
    if action_type not in ACTION_ACTORS:
        raise EvidenceVerificationError("unsupported action type")
    repo_key = str(context.get("repo_key") or "")
    status = str(context.get("work_order_status") or "")
    version = int(context.get("work_order_version") or 0)
    if status != ACTION_EXPECTED_STATUS[action_type]:
        raise EvidenceVerificationError("action does not match current work-order status")
    monetizable_login = str(context.get("monetizable_login") or "").casefold()
    if not repo_key or not monetizable_login:
        raise EvidenceVerificationError("work-order context is incomplete")

    source_owner, source_repo, source_kind, source_number, _ = _parse_repo_resource(
        str(context.get("source_url") or "")
    )
    _same_repo(repo_key, source_owner, source_repo)
    if source_kind != "issues":
        raise EvidenceVerificationError("build opportunity source must be a GitHub issue")

    if action_type == "claim_confirmed":
        owner, repo, kind, issue_number, _ = _parse_repo_resource(evidence_url)
        _same_repo(repo_key, owner, repo)
        if kind != "issues" or issue_number != source_number:
            raise EvidenceVerificationError("claim evidence does not match the bounty issue")
        issue = _github_get(f"/repos/{owner}/{repo}/issues/{issue_number}")
        if not isinstance(issue, Mapping):
            raise EvidenceVerificationError("GitHub issue response is invalid")
        _same_html_url(issue.get("html_url"), evidence_url)
        assignees = {
            str(item.get("login") or "").casefold()
            for item in issue.get("assignees") or []
            if isinstance(item, Mapping)
        }
        if str(issue.get("state") or "").casefold() != "open":
            raise EvidenceVerificationError("bounty issue is not open")
        if monetizable_login not in assignees:
            raise EvidenceVerificationError("monetizable account is not assigned to the issue")
        node_id = str(issue.get("node_id") or issue.get("id") or "")
        updated_at = str(issue.get("updated_at") or "")
        if not node_id or not updated_at:
            raise EvidenceVerificationError("issue assignment lacks stable official identifiers")
        metadata = {
            "issue_number": issue_number,
            "issue_node_id": node_id,
            "assigned_login": monetizable_login,
            "state": "open",
            "updated_at": updated_at,
        }
        return _verified(
            action_type=action_type,
            evidence_url=str(issue["html_url"]),
            receipt_id=f"github-assignment:{node_id}:{updated_at}",
            status=status,
            version=version,
            repo_key=repo_key,
            issue_number=issue_number,
            pr_number=None,
            head_sha=None,
            metadata=metadata,
        )

    if action_type == "tests_passed":
        owner, repo, run_id = _parse_run(evidence_url)
        _same_repo(repo_key, owner, repo)
        run = _github_get(f"/repos/{owner}/{repo}/actions/runs/{run_id}")
        if not isinstance(run, Mapping):
            raise EvidenceVerificationError("GitHub Actions response is invalid")
        _same_html_url(run.get("html_url"), evidence_url)
        api_repo = run.get("repository") or {}
        if str(api_repo.get("full_name") or "").casefold() != repo_key.casefold():
            raise EvidenceVerificationError("Actions run repository mismatch")
        if str(run.get("status") or "").casefold() != "completed":
            raise EvidenceVerificationError("test run is not complete")
        if str(run.get("conclusion") or "").casefold() != "success":
            raise EvidenceVerificationError("test run did not succeed")
        head_sha = _require_sha(run.get("head_sha"))
        metadata = {
            "run_id": int(run.get("id") or run_id),
            "run_attempt": int(run.get("run_attempt") or 1),
            "head_sha": head_sha,
            "event": str(run.get("event") or ""),
            "conclusion": "success",
        }
        return _verified(
            action_type=action_type,
            evidence_url=str(run["html_url"]),
            receipt_id=f"github-actions:{metadata['run_id']}:{metadata['run_attempt']}",
            status=status,
            version=version,
            repo_key=repo_key,
            issue_number=source_number,
            pr_number=None,
            head_sha=head_sha,
            metadata=metadata,
        )

    owner, repo, kind, pr_number, fragment = _parse_repo_resource(evidence_url)
    _same_repo(repo_key, owner, repo)
    if kind != "pull":
        raise EvidenceVerificationError("evidence must reference a pull request")
    pull = _github_get(f"/repos/{owner}/{repo}/pulls/{pr_number}")
    if not isinstance(pull, Mapping):
        raise EvidenceVerificationError("GitHub pull request response is invalid")
    _same_html_url(pull.get("html_url"), evidence_url, allow_fragment=True)
    base_repo = (pull.get("base") or {}).get("repo") or {}
    if str(base_repo.get("full_name") or "").casefold() != repo_key.casefold():
        raise EvidenceVerificationError("pull request base repository mismatch")
    author_login = str((pull.get("user") or {}).get("login") or "").casefold()
    if author_login != monetizable_login:
        raise EvidenceVerificationError("pull request is not owned by the monetizable account")
    head_sha = _require_sha((pull.get("head") or {}).get("sha"))

    if action_type == "pr_published":
        tests = _prior(prior_actions, "tests_passed")
        if head_sha != str(tests.get("head_sha") or "").casefold():
            raise EvidenceVerificationError("published PR head does not match passed tests")
        if bool(pull.get("draft")):
            raise EvidenceVerificationError("pull request is still a draft")
        if str(pull.get("state") or "").casefold() != "open":
            raise EvidenceVerificationError("pull request is not open")
        if not _issue_linked(str(pull.get("body") or ""), repo_key, source_number):
            raise EvidenceVerificationError("pull request does not link the bounty issue")
        metadata = {
            "pr_number": pr_number,
            "pr_node_id": str(pull.get("node_id") or pull.get("id") or ""),
            "head_sha": head_sha,
            "author_login": author_login,
            "issue_number": source_number,
            "draft": False,
        }
        if not metadata["pr_node_id"]:
            raise EvidenceVerificationError("pull request lacks a stable official identifier")
        return _verified(
            action_type=action_type,
            evidence_url=str(pull["html_url"]),
            receipt_id=f"github-pr:{metadata['pr_node_id']}:{head_sha}",
            status=status,
            version=version,
            repo_key=repo_key,
            issue_number=source_number,
            pr_number=pr_number,
            head_sha=head_sha,
            metadata=metadata,
        )

    published = _prior(prior_actions, "pr_published")
    if int(published.get("pr_number") or 0) != pr_number:
        raise EvidenceVerificationError("PR evidence does not match the published PR")
    if str(published.get("head_sha") or "").casefold() != head_sha:
        raise EvidenceVerificationError("PR head changed after verified tests/publication")

    if action_type == "review_approved":
        match = re.fullmatch(r"pullrequestreview-(\d+)", fragment)
        if not match:
            raise EvidenceVerificationError("review evidence must identify one GitHub review")
        review_id = int(match.group(1))
        review = _github_get(
            f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews/{review_id}"
        )
        if not isinstance(review, Mapping):
            raise EvidenceVerificationError("GitHub review response is invalid")
        reviewer_login = str((review.get("user") or {}).get("login") or "").casefold()
        author_association = str(review.get("author_association") or "").upper()
        if str(review.get("state") or "").casefold() != "approved":
            raise EvidenceVerificationError("external review is not APPROVED")
        if not reviewer_login or reviewer_login == monetizable_login:
            raise EvidenceVerificationError("approval is not from an independent account")
        if author_association not in {"OWNER", "MEMBER", "COLLABORATOR"}:
            raise EvidenceVerificationError("approver is not an authorized maintainer")
        if _require_sha(review.get("commit_id")) != head_sha:
            raise EvidenceVerificationError("approval applies to a different commit")
        submitted_at = str(review.get("submitted_at") or "")
        if not submitted_at:
            raise EvidenceVerificationError("review lacks an official submission timestamp")
        metadata = {
            "pr_number": pr_number,
            "review_id": review_id,
            "reviewer_login": reviewer_login,
            "author_association": author_association,
            "head_sha": head_sha,
            "state": "APPROVED",
            "submitted_at": submitted_at,
        }
        return _verified(
            action_type=action_type,
            evidence_url=f"{pull['html_url']}#pullrequestreview-{review_id}",
            receipt_id=f"github-review:{review_id}:{head_sha}",
            status=status,
            version=version,
            repo_key=repo_key,
            issue_number=source_number,
            pr_number=pr_number,
            head_sha=head_sha,
            metadata=metadata,
        )

    review = _prior(prior_actions, "review_approved")
    if int(review.get("pr_number") or 0) != pr_number:
        raise EvidenceVerificationError("accepted PR does not match approved PR")
    merged_by = str((pull.get("merged_by") or {}).get("login") or "").casefold()
    merged_at = str(pull.get("merged_at") or "")
    if not bool(pull.get("merged")) or not merged_at:
        raise EvidenceVerificationError("pull request has not been merged")
    if not merged_by or merged_by == monetizable_login:
        raise EvidenceVerificationError("delivery lacks independent maintainer acceptance")
    metadata = {
        "pr_number": pr_number,
        "head_sha": head_sha,
        "merged_at": merged_at,
        "merged_by": merged_by,
        "merge_commit_sha": _require_sha(pull.get("merge_commit_sha")),
    }
    return _verified(
        action_type=action_type,
        evidence_url=str(pull["html_url"]),
        receipt_id=f"github-merge:{pr_number}:{metadata['merge_commit_sha']}",
        status=status,
        version=version,
        repo_key=repo_key,
        issue_number=source_number,
        pr_number=pr_number,
        head_sha=head_sha,
        metadata=metadata,
    )
