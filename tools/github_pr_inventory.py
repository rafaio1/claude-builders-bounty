#!/usr/bin/env python3
"""Build a complete, evidence-gated inventory of one GitHub author's PRs.

The collector deliberately splits GitHub search by state so each query remains
below GitHub's 1,000-result search cap.  It treats the author's own PR text as
untrusted revenue metadata: only repository maintainers or known marketplace
bots can create a payment-promise signal, and even that signal is never booked
as realized revenue.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
import uuid
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_AUTHOR = "rafaio1"
DEFAULT_INVENTORY_PATH = Path("/Agentic/state/github_pr_inventory.json")
DEFAULT_FOLLOWUP_PATH = Path("/Agentic/state/github_pr_followups.json")
DEFAULT_MANIFEST_PATH = Path("/Agentic/state/github_pr_inventory_success.json")
SCHEMA_VERSION = "3.0"
AUTHORITATIVE_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
PLATFORM_BOTS = frozenset(
    {
        "algora-pbc",
        "opire",
        "opire-bot",
        "issuehunt",
        "issuehunt-bot",
    }
)
PAYMENT_KEYWORDS = re.compile(
    r"\b(?:bount(?:y|ies)|reward|payout|payment|paid|compensat(?:e|ion))\b",
    re.IGNORECASE,
)
MONEY_AMOUNT = re.compile(
    r"(?:[$€£]\s*\d[\d,.]*(?:\.\d{1,2})?|"
    r"\b\d[\d,.]*(?:\.\d{1,2})?\s*(?:USD|USDT|USDC|EUR|GBP|BRL)\b)",
    re.IGNORECASE,
)
NEGATIVE_PAYMENT = re.compile(
    r"\b(?:no|not|without)\s+(?:a\s+)?(?:cash\s+|monetary\s+)?"
    r"(?:bounty|reward|payment|compensation|value)\b|"
    r"\b(?:no\s+bounty\s+program(?:me)?|unpaid|volunteer(?:ed|ing)?|"
    r"not\s+remunerated|non[- ]monetary|no\s+cash\s+value|"
    r"(?:is(?:n'?t|\s+not)|not)\s+eligible|does(?:n'?t|\s+not)\s+qualify|already\s+claimed|"
    r"paid\s+to\s+(?:someone|another|the\s+other)|cancelled|canceled|duplicate)\b",
    re.IGNORECASE,
)
PAYMENT_PROMISE = re.compile(
    r"(?:\b(?:will|shall|we(?:'ll|\s+will)|can)\s+pay\b.{0,100}"
    r"(?:[$€£]\s*\d|\d[\d,.]*\s*(?:USD|USDT|USDC|EUR|GBP|BRL)\b))|"
    r"(?:\b(?:bounty|reward|payout|payment)\b.{0,60}"
    r"(?:\b(?:is|of|pays?|worth|amount|approved|awarded)\b.{0,30})?"
    r"(?:[$€£]\s*\d|\d[\d,.]*\s*(?:USD|USDT|USDC|EUR|GBP|BRL)\b))|"
    r"(?:(?:[$€£]\s*\d|\d[\d,.]*\s*(?:USD|USDT|USDC|EUR|GBP|BRL)\b)"
    r".{0,40}\b(?:bounty|reward|payout|payment)\b)",
    re.IGNORECASE | re.DOTALL,
)
AWARD_SIGNAL = re.compile(
    r"\b(?:awarded|award\s+approved|payout\s+approved|payment\s+approved|"
    r"accepted\s+(?:for|as)|winner|will\s+receive|we(?:'ll|\s+will)\s+pay)\b",
    re.IGNORECASE,
)
ACTIONABLE_TEXT = re.compile(
    r"\b(?:changes?\s+requested|"
    r"(?:please|could\s+you|can\s+you|need(?:s|ed)?\s+to|must)\s+"
    r"(?:fix|update|change|add|remove|rename|replace|rebase|resolve|"
    r"run|write|include|correct|adjust|test)\b|"
    r"(?:is|are)\s+(?:failing|incorrect|wrong)\b)",
    re.IGNORECASE,
)
ACTIONABLE_CJK = re.compile(
    r"(?:需要|请|缺少|缺的是|修改|修复|添加|补充|更改).{0,24}"
    r"(?:测试|代码|消息|文档|实现|配置|名称|错误)",
    re.IGNORECASE,
)
NO_ACTION_TEXT = re.compile(
    r"\b(?:no\s+(?:changes?|action)\s+(?:needed|required)|looks?\s+good|"
    r"tests?\s+(?:look|are)\s+good|please\s+wait|nothing\s+to\s+change)\b",
    re.IGNORECASE,
)
TERMINAL_REJECTION = re.compile(
    r"\b(?:later\s+duplicate|duplicate\s+(?:submission|claim|attempt)|"
    r"not\s+forwarding|not\s+accepting|selected\s+another|"
    r"another\s+(?:candidate|submission)\s+(?:was|is)\s+selected|"
    r"not\s+(?:the\s+)?(?:primary\s+)?payout\s+candidate)\b",
    re.IGNORECASE,
)
QUERY_PARTITIONS = (
    ("merged", "is:pr author:{author} is:merged"),
    ("open", "is:pr author:{author} is:open"),
    ("closed_unmerged", "is:pr author:{author} is:closed -is:merged"),
)
FOLLOWUP_PRIORITY = {
    "settlement_validation_required": 0,
    "merge_followup": 1,
    "technical_followup": 2,
    "payment_validation_required": 3,
    "evidence_review_required": 4,
}
MAX_GITHUB_ATTEMPTS = 4


GRAPHQL_QUERY = r"""
query($searchQuery: String!, $cursor: String) {
  search(query: $searchQuery, type: ISSUE, first: 25, after: $cursor) {
    issueCount
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on PullRequest {
        id
        number
        title
        url
        state
        isDraft
        createdAt
        updatedAt
        closedAt
        mergedAt
        bodyText
        reviewDecision
        author { login }
        repository {
          nameWithOwner
          isArchived
          isFork
          pushedAt
          updatedAt
        }
        comments(last: 20) {
          totalCount
          nodes {
            author { login }
            authorAssociation
            bodyText
            createdAt
            lastEditedAt
            url
          }
        }
        reviews(last: 20) {
          totalCount
          nodes {
            author { login }
            authorAssociation
            state
            bodyText
            submittedAt
            lastEditedAt
            url
          }
        }
        closingIssuesReferences(first: 10) {
          totalCount
          nodes {
            number
            title
            url
            state
            bodyText
            createdAt
            lastEditedAt
            authorAssociation
            author { login }
            repository { nameWithOwner }
            comments(last: 20) {
              totalCount
              nodes {
                author { login }
                authorAssociation
                bodyText
                createdAt
                lastEditedAt
                url
              }
            }
          }
        }
      }
    }
  }
}
"""

GRAPHQL_COUNT_QUERY = r"""
query($mergedQuery: String!, $openQuery: String!, $closedQuery: String!) {
  merged: search(query: $mergedQuery, type: ISSUE, first: 1) { issueCount }
  open: search(query: $openQuery, type: ISSUE, first: 1) { issueCount }
  closed_unmerged: search(query: $closedQuery, type: ISSUE, first: 1) { issueCount }
}
"""


class InventoryError(RuntimeError):
    """The GitHub inventory could not be proven complete."""


class InventoryDriftError(InventoryError):
    """The GitHub state changed while the partitioned snapshot was collected."""


def iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _nodes(container: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if not isinstance(container, Mapping):
        return []
    value = container.get("nodes")
    if not isinstance(value, list):
        return []
    return [node for node in value if isinstance(node, Mapping)]


def _login(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(value.get("login") or "")
    return ""


def _association(value: Any) -> str:
    return str(value or "").upper()


def _excerpt(text: Any, limit: int = 280) -> str:
    compact = " ".join(str(text or "").split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def _is_authoritative(login: str, association: str) -> bool:
    return association in AUTHORITATIVE_ASSOCIATIONS or login.casefold() in PLATFORM_BOTS


def _event(
    *,
    source: str,
    login: str,
    association: str,
    body: Any,
    timestamp: Any,
    url: Any,
    review_state: str | None = None,
    authority_kind: str | None = None,
) -> dict[str, Any]:
    return {
        "source": source,
        "login": login,
        "association": association,
        "body": str(body or ""),
        "timestamp": str(timestamp or ""),
        "url": str(url or ""),
        "review_state": review_state,
        "authority_kind": authority_kind,
    }


def _iter_authoritative_events(
    pr: Mapping[str, Any], expected_author: str
) -> Iterable[dict[str, Any]]:
    for comment in _nodes(pr.get("comments")):
        login = _login(comment.get("author"))
        association = _association(comment.get("authorAssociation"))
        if login.casefold() == expected_author.casefold():
            continue
        if _is_authoritative(login, association):
            yield _event(
                source="pr_comment",
                login=login,
                association=association,
                body=comment.get("bodyText"),
                timestamp=comment.get("lastEditedAt") or comment.get("createdAt"),
                url=comment.get("url"),
                authority_kind="platform_bot"
                if login.casefold() in PLATFORM_BOTS
                else "maintainer",
            )

    for review in _nodes(pr.get("reviews")):
        login = _login(review.get("author"))
        association = _association(review.get("authorAssociation"))
        if login.casefold() == expected_author.casefold():
            continue
        if _is_authoritative(login, association):
            yield _event(
                source="pr_review",
                login=login,
                association=association,
                body=review.get("bodyText"),
                timestamp=review.get("lastEditedAt") or review.get("submittedAt"),
                url=review.get("url"),
                review_state=str(review.get("state") or "").upper(),
                authority_kind="platform_bot"
                if login.casefold() in PLATFORM_BOTS
                else "maintainer",
            )

    for issue in _nodes(pr.get("closingIssuesReferences")):
        login = _login(issue.get("author"))
        association = _association(issue.get("authorAssociation"))
        if (
            login.casefold() != expected_author.casefold()
            and _is_authoritative(login, association)
        ):
            yield _event(
                source="linked_issue_body",
                login=login,
                association=association,
                body=issue.get("bodyText"),
                timestamp=issue.get("lastEditedAt") or issue.get("createdAt"),
                url=issue.get("url"),
                authority_kind="platform_bot"
                if login.casefold() in PLATFORM_BOTS
                else "maintainer",
            )
        for comment in _nodes(issue.get("comments")):
            login = _login(comment.get("author"))
            association = _association(comment.get("authorAssociation"))
            if login.casefold() == expected_author.casefold():
                continue
            if _is_authoritative(login, association):
                yield _event(
                    source="linked_issue_comment",
                    login=login,
                    association=association,
                    body=comment.get("bodyText"),
                    timestamp=comment.get("lastEditedAt") or comment.get("createdAt"),
                    url=comment.get("url"),
                    authority_kind="platform_bot"
                    if login.casefold() in PLATFORM_BOTS
                    else "maintainer",
                )


def _safe_evidence(event: Mapping[str, Any], kind: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "source": event.get("source"),
        "author": event.get("login"),
        "association": event.get("association"),
        "timestamp": event.get("timestamp"),
        "url": event.get("url"),
        "excerpt": _excerpt(event.get("body")),
    }


def evidence_coverage(pr: Mapping[str, Any]) -> dict[str, Any]:
    """Report whether every queried evidence connection fit inside its window."""
    details: dict[str, Any] = {}
    complete = True
    for name in ("comments", "reviews", "closingIssuesReferences"):
        connection = pr.get(name)
        returned = len(_nodes(connection if isinstance(connection, Mapping) else None))
        raw_count = connection.get("totalCount") if isinstance(connection, Mapping) else None
        try:
            reported = int(raw_count) if raw_count is not None else returned
        except (TypeError, ValueError):
            reported = returned
            complete = False
        connection_complete = reported == returned
        complete = complete and connection_complete
        details[name] = {
            "reported": reported,
            "returned": returned,
            "complete": connection_complete,
        }

    issue_comment_windows = []
    for issue in _nodes(pr.get("closingIssuesReferences")):
        comments = issue.get("comments")
        returned = len(_nodes(comments if isinstance(comments, Mapping) else None))
        raw_count = comments.get("totalCount") if isinstance(comments, Mapping) else None
        try:
            reported = int(raw_count) if raw_count is not None else returned
        except (TypeError, ValueError):
            reported = returned
            complete = False
        window_complete = reported == returned
        complete = complete and window_complete
        issue_comment_windows.append(
            {
                "url": issue.get("url"),
                "reported": reported,
                "returned": returned,
                "complete": window_complete,
            }
        )
    details["linked_issue_comments"] = issue_comment_windows
    details["complete"] = complete
    return details


def classify_pr(pr: Mapping[str, Any], *, expected_author: str = DEFAULT_AUTHOR) -> dict[str, Any]:
    """Classify one PR without trusting author-supplied bounty text."""
    events = list(_iter_authoritative_events(pr, expected_author))
    positive: list[dict[str, Any]] = []
    negative: list[dict[str, Any]] = []
    actionable: list[dict[str, Any]] = []
    approved: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    created_at = str(pr.get("createdAt") or "")

    for event in events:
        body = str(event.get("body") or "")
        if NEGATIVE_PAYMENT.search(body):
            negative.append(event)
        if (
            event.get("authority_kind") == "maintainer"
            and event.get("source") in {"pr_comment", "pr_review"}
            and TERMINAL_REJECTION.search(body)
        ):
            rejected.append(event)
        if (
            PAYMENT_KEYWORDS.search(body)
            and MONEY_AMOUNT.search(body)
            and PAYMENT_PROMISE.search(body)
            and not NEGATIVE_PAYMENT.search(body)
        ):
            positive.append(event)
        review_state = str(event.get("review_state") or "").upper()
        if review_state == "APPROVED":
            approved.append(event)
        is_current_pr_feedback = (
            event.get("authority_kind") == "maintainer"
            and event.get("source") in {"pr_comment", "pr_review"}
            and bool(event.get("timestamp"))
            and bool(created_at)
            and str(event.get("timestamp")) >= created_at
        )
        if is_current_pr_feedback and (
            review_state == "CHANGES_REQUESTED"
            or (
                (ACTIONABLE_TEXT.search(body) or ACTIONABLE_CJK.search(body))
                and not NO_ACTION_TEXT.search(body)
            )
        ):
            actionable.append(event)

    def event_order(event: Mapping[str, Any]) -> str:
        return str(event.get("timestamp") or "")

    latest_positive = max(positive, key=event_order, default=None)
    latest_negative = max(negative, key=event_order, default=None)
    latest_rejection = max(rejected, key=event_order, default=None)
    negated = bool(
        latest_negative
        and (
            latest_positive is None
            or event_order(latest_negative) >= event_order(latest_positive)
        )
    )
    coverage = evidence_coverage(pr)
    payment_signal = bool(latest_positive and not negated and coverage["complete"])

    review_decision = str(pr.get("reviewDecision") or "").upper()
    if not coverage["complete"] and review_decision != "CHANGES_REQUESTED":
        actionable = []
    formal_approval = review_decision == "APPROVED" and bool(approved)
    latest_approval = max(approved, key=event_order, default=None)
    latest_action = max(actionable, key=event_order, default=None)

    significant = [
        ("payment", latest_positive),
        ("approval", latest_approval),
        ("action", latest_action),
        ("rejection", latest_rejection),
    ]
    significant = [(kind, event) for kind, event in significant if event]
    current_kind = (
        max(significant, key=lambda item: event_order(item[1]))[0]
        if significant
        else None
    )
    rejection_current = current_kind == "rejection"
    action_current = current_kind == "action" or review_decision == "CHANGES_REQUESTED"

    state = str(pr.get("state") or "UNKNOWN").upper()
    merged = bool(pr.get("mergedAt"))
    closed_unmerged = state == "CLOSED" and not merged

    if closed_unmerged:
        classification = "closed_unmerged"
    elif merged and payment_signal:
        classification = "settlement_validation_required"
    elif merged and not coverage["complete"]:
        classification = "evidence_review_required"
    elif merged:
        classification = "ordinary_merged"
    elif state == "OPEN" and rejection_current:
        classification = "rejected_or_duplicate"
    elif state == "OPEN" and action_current:
        classification = "technical_followup"
    elif state == "OPEN" and payment_signal and formal_approval:
        classification = "merge_followup"
    elif state == "OPEN" and payment_signal:
        classification = "payment_validation_required"
    elif state == "OPEN" and not coverage["complete"]:
        classification = "evidence_review_required"
    elif state == "OPEN":
        classification = "ordinary_open"
    else:
        classification = "unknown_state"

    author_login = _login(pr.get("author"))
    body = str(pr.get("bodyText") or "")
    author_self_claim_ignored = bool(
        author_login.casefold() == expected_author.casefold()
        and (PAYMENT_KEYWORDS.search(body) or MONEY_AMOUNT.search(body))
    )

    return {
        "classification": classification,
        "payment_promise": {
            "authoritative": payment_signal,
            "negated": negated,
            "award_or_acceptance_signal": bool(
                payment_signal
                and latest_positive
                and AWARD_SIGNAL.search(str(latest_positive.get("body") or ""))
            ),
            "ambiguous_truncated": bool(not coverage["complete"]),
            "evidence": _safe_evidence(latest_positive, "payment_promise")
            if payment_signal and latest_positive
            else None,
            "negative_evidence": _safe_evidence(latest_negative, "payment_negation")
            if latest_negative
            else None,
        },
        "formal_approval": {
            "present": formal_approval,
            "review_decision": review_decision or None,
            "evidence": _safe_evidence(max(approved, key=event_order), "approval")
            if formal_approval
            else None,
        },
        "actionable_feedback": {
            "present": bool(action_current),
            "evidence": _safe_evidence(latest_action, "feedback")
            if action_current and latest_action
            else None,
        },
        "terminal_rejection": {
            "present": bool(rejection_current),
            "historical": bool(latest_rejection),
            "evidence": _safe_evidence(latest_rejection, "terminal_rejection")
            if latest_rejection
            else None,
        },
        "author_self_claim_ignored": author_self_claim_ignored,
        "evidence_coverage": coverage,
        "realized_revenue": False,
    }


def execute_graphql(document: str, variables: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = {"query": document, "variables": dict(variables)}
    last_error: BaseException | None = None
    for attempt in range(1, MAX_GITHUB_ATTEMPTS + 1):
        try:
            result = subprocess.run(
                ["gh", "api", "graphql", "--input", "-"],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            last_error = error
        else:
            if result.returncode == 0:
                try:
                    response = json.loads(result.stdout)
                except json.JSONDecodeError as error:
                    raise InventoryError("GitHub GraphQL returned invalid JSON") from error
                if not isinstance(response, Mapping) or response.get("errors"):
                    raise InventoryError("GitHub GraphQL returned errors")
                return response
            last_error = InventoryError("GitHub GraphQL command returned non-zero")

        if attempt < MAX_GITHUB_ATTEMPTS:
            time.sleep(min(2 ** (attempt - 1), 8))

    raise InventoryError(
        f"GitHub GraphQL request failed after {MAX_GITHUB_ATTEMPTS} attempts"
    ) from last_error


def run_graphql(search_query: str, cursor: str | None) -> Mapping[str, Any]:
    return execute_graphql(
        GRAPHQL_QUERY,
        {"searchQuery": search_query, "cursor": cursor},
    )


def count_snapshot(author: str) -> dict[str, int]:
    queries = {
        partition: template.format(author=author)
        for partition, template in QUERY_PARTITIONS
    }
    response = execute_graphql(
        GRAPHQL_COUNT_QUERY,
        {
            "mergedQuery": queries["merged"],
            "openQuery": queries["open"],
            "closedQuery": queries["closed_unmerged"],
        },
    )
    data = response.get("data")
    if not isinstance(data, Mapping):
        raise InventoryError("GitHub count snapshot missing")
    result: dict[str, int] = {}
    for partition in ("merged", "open", "closed_unmerged"):
        value = data.get(partition)
        if not isinstance(value, Mapping):
            raise InventoryError(f"GitHub count missing for {partition}")
        try:
            result[partition] = int(value.get("issueCount"))
        except (TypeError, ValueError) as error:
            raise InventoryError(f"GitHub count invalid for {partition}") from error
    return result


def collect_partition(search_query: str) -> tuple[list[Mapping[str, Any]], int, int]:
    cursor: str | None = None
    nodes: list[Mapping[str, Any]] = []
    expected_count: int | None = None
    page_count = 0
    while True:
        page_count += 1
        response = run_graphql(search_query, cursor)
        search = response.get("data", {}).get("search")
        if not isinstance(search, Mapping):
            raise InventoryError("GitHub GraphQL search payload missing")
        try:
            issue_count = int(search.get("issueCount"))
        except (TypeError, ValueError) as error:
            raise InventoryError("GitHub GraphQL issueCount missing") from error
        if issue_count >= 1000:
            raise InventoryError("GitHub query reached the 1,000-result search cap")
        if expected_count is None:
            expected_count = issue_count
        elif issue_count != expected_count:
            raise InventoryError("GitHub search changed during pagination")

        nodes.extend(_nodes(search))
        page_info = search.get("pageInfo")
        if not isinstance(page_info, Mapping):
            raise InventoryError("GitHub GraphQL pageInfo missing")
        if not page_info.get("hasNextPage"):
            break
        next_cursor = page_info.get("endCursor")
        if not next_cursor or next_cursor == cursor:
            raise InventoryError("GitHub pagination cursor did not advance")
        cursor = str(next_cursor)

    if expected_count is None or len(nodes) != expected_count:
        raise InventoryError(
            f"GitHub inventory incomplete: expected {expected_count}, collected {len(nodes)}"
        )
    return nodes, expected_count, page_count


def _linked_issues(pr: Mapping[str, Any]) -> list[dict[str, Any]]:
    result = []
    for issue in _nodes(pr.get("closingIssuesReferences")):
        repository = issue.get("repository")
        result.append(
            {
                "repo": str(repository.get("nameWithOwner") or "")
                if isinstance(repository, Mapping)
                else "",
                "number": issue.get("number"),
                "title": _excerpt(issue.get("title"), 180),
                "url": issue.get("url"),
                "state": issue.get("state"),
            }
        )
    return result


def serialize_pr(pr: Mapping[str, Any], partition: str, author: str) -> dict[str, Any]:
    repository = pr.get("repository")
    if not isinstance(repository, Mapping):
        raise InventoryError("PR repository metadata missing")
    repo = str(repository.get("nameWithOwner") or "")
    if not repo or not pr.get("number") or not pr.get("url"):
        raise InventoryError("PR identity metadata missing")
    classified = classify_pr(pr, expected_author=author)
    return {
        "repo": repo,
        "number": int(pr["number"]),
        "title": _excerpt(pr.get("title"), 240),
        "url": str(pr["url"]),
        "state": str(pr.get("state") or "UNKNOWN").upper(),
        "partition": partition,
        "is_draft": bool(pr.get("isDraft")),
        "created_at": pr.get("createdAt"),
        "updated_at": pr.get("updatedAt"),
        "closed_at": pr.get("closedAt"),
        "merged_at": pr.get("mergedAt"),
        "author": _login(pr.get("author")),
        "repository": {
            "is_archived": bool(repository.get("isArchived")),
            "is_fork": bool(repository.get("isFork")),
            "pushed_at": repository.get("pushedAt"),
            "updated_at": repository.get("updatedAt"),
        },
        "linked_issues": _linked_issues(pr),
        **classified,
    }


def inventory_source_hash(
    author: str,
    query_stats: list[Mapping[str, Any]],
    prs: Mapping[str, Mapping[str, Any]],
) -> str:
    canonical = json.dumps(
        {
            "author": author,
            "queries": query_stats,
            "prs": dict(sorted(prs.items())),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _build_inventory_once(author: str) -> tuple[dict[str, Any], dict[str, Any]]:
    counts_before = count_snapshot(author)
    prs: dict[str, dict[str, Any]] = {}
    query_stats = []
    for partition, template in QUERY_PARTITIONS:
        search_query = template.format(author=author)
        nodes, expected_count, pages = collect_partition(search_query)
        for raw in nodes:
            serialized = serialize_pr(raw, partition, author)
            key = f"{serialized['repo']}#{serialized['number']}"
            if key in prs:
                raise InventoryError(f"duplicate PR across partitions: {key}")
            prs[key] = serialized
        query_stats.append(
            {
                "partition": partition,
                "query": search_query,
                "reported_count": expected_count,
                "collected_count": len(nodes),
                "pages": pages,
            }
        )

    classification_counts: dict[str, int] = {}
    for pr in prs.values():
        classification = str(pr["classification"])
        classification_counts[classification] = classification_counts.get(classification, 0) + 1

    partition_counts = {
        stat["partition"]: int(stat["collected_count"])
        for stat in query_stats
    }
    counts_after = count_snapshot(author)
    if counts_before != counts_after or partition_counts != counts_after:
        raise InventoryDriftError(
            "GitHub PR state changed during partitioned inventory collection"
        )
    generated_at = iso_now()
    run_id = uuid.uuid4().hex
    source_hash = inventory_source_hash(author, query_stats, prs)
    evidence_complete = all(
        bool(pr["evidence_coverage"]["complete"]) for pr in prs.values()
    )
    inventory = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "source_hash": source_hash,
        "generated_at": generated_at,
        "author": author,
        "inventory_complete": True,
        "evidence_complete": evidence_complete,
        "revenue_policy": {
            "author_body_is_payment_evidence": False,
            "payment_promise_is_realized_revenue": False,
            "settlement_requires_provider_evidence": True,
        },
        "queries": query_stats,
        "count_snapshots": {
            "before": counts_before,
            "after": counts_after,
        },
        "stats": {
            "total_prs": len(prs),
            "merged": partition_counts.get("merged", 0),
            "open": partition_counts.get("open", 0),
            "closed_unmerged": partition_counts.get("closed_unmerged", 0),
            "classification_counts": dict(sorted(classification_counts.items())),
        },
        "prs": dict(sorted(prs.items())),
    }

    followup_items = []
    for key, pr in prs.items():
        classification = str(pr["classification"])
        if classification not in FOLLOWUP_PRIORITY:
            continue
        followup_items.append(
            {
                "key": key,
                "classification": classification,
                "priority": FOLLOWUP_PRIORITY[classification],
                "repo": pr["repo"],
                "number": pr["number"],
                "title": pr["title"],
                "url": pr["url"],
                "state": pr["state"],
                "merged_at": pr["merged_at"],
                "authoritative_payment_promise": pr["payment_promise"]["authoritative"],
                "award_or_acceptance_signal": pr["payment_promise"]["award_or_acceptance_signal"],
                "payment_evidence": pr["payment_promise"]["evidence"],
                "evidence_complete": pr["evidence_coverage"]["complete"],
                "formal_approval": pr["formal_approval"]["present"],
                "approval_evidence": pr["formal_approval"]["evidence"],
                "feedback_evidence": pr["actionable_feedback"]["evidence"],
                "realized_revenue": False,
            }
        )
    followup_items.sort(
        key=lambda item: (
            int(item["priority"]),
            not bool(item["authoritative_payment_promise"]),
            str(item["repo"]).casefold(),
            int(item["number"]),
        )
    )
    followups = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "source_hash": source_hash,
        "generated_at": inventory["generated_at"],
        "author": author,
        "inventory_complete": True,
        "evidence_complete": evidence_complete,
        "realized_revenue_usd": 0.0,
        "count": len(followup_items),
        "items": followup_items,
    }
    return inventory, followups


def build_inventory(author: str = DEFAULT_AUTHOR) -> tuple[dict[str, Any], dict[str, Any]]:
    last_error: InventoryDriftError | None = None
    for attempt in range(2):
        try:
            return _build_inventory_once(author)
        except InventoryDriftError as error:
            last_error = error
            if attempt == 0:
                time.sleep(2)
    raise InventoryDriftError("GitHub inventory drifted twice") from last_error


def atomic_json_write(path: Path, payload: Mapping[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--author", default=DEFAULT_AUTHOR)
    parser.add_argument("--inventory-output", default=str(DEFAULT_INVENTORY_PATH))
    parser.add_argument("--followup-output", default=str(DEFAULT_FOLLOWUP_PATH))
    parser.add_argument("--manifest-output", default=str(DEFAULT_MANIFEST_PATH))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not re.fullmatch(r"[A-Za-z0-9-]+", args.author):
        raise SystemExit("invalid GitHub author")
    inventory, followups = build_inventory(args.author)
    manifest_path = Path(args.manifest_output)
    manifest_base = {
        "schema_version": SCHEMA_VERSION,
        "run_id": inventory["run_id"],
        "source_hash": inventory["source_hash"],
        "inventory_output": str(Path(args.inventory_output).resolve()),
        "followup_output": str(Path(args.followup_output).resolve()),
        "inventory_complete": True,
        "evidence_complete": inventory["evidence_complete"],
    }
    atomic_json_write(
        manifest_path,
        {**manifest_base, "status": "writing", "started_at": iso_now()},
    )
    atomic_json_write(Path(args.inventory_output), inventory)
    atomic_json_write(Path(args.followup_output), followups)
    atomic_json_write(
        manifest_path,
        {**manifest_base, "status": "complete", "completed_at": iso_now()},
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "author": args.author,
                "stats": inventory["stats"],
                "followup_count": followups["count"],
                "realized_revenue_usd": 0.0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
