#!/usr/bin/env python3
"""Deterministic RustChain bounty reconciliation for the Agentic ledger.

Only public provider evidence is accepted. Provider acknowledgements are reconciled
against confirmed entries from the public RustChain wallet history. A uniquely
attributed credit is recorded as ``wallet_received``; conversion to an exchange or
fiat remains a separate state and is never inferred from a wallet receipt.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


SCHEMA_VERSION = 2
RECONCILER_VERSION = "rustchain-public-evidence-v2"
RECOVERY_POLICY_VERSION = "autonomous-recovery-v2"
WALLET = "RTC1e9bf7a2a60aac9bcbc5a0df0c65e9501e932861"
BALANCE_URL = f"https://rustchain.org/wallet/balance?miner_id={WALLET}"
HISTORY_BASE_URL = "https://rustchain.org/wallet/history"
HISTORY_PAGE_SIZE = 200
HISTORY_URL = f"{HISTORY_BASE_URL}?miner_id={WALLET}&limit={HISTORY_PAGE_SIZE}&offset=0"
HISTORY_DOCUMENTATION_REVISION = "e9a4793889ce2958863039e0e2d40733cbb7f206"
HISTORY_DOCUMENTATION_URL = (
    "https://github.com/Scottcjn/Rustchain/blob/"
    f"{HISTORY_DOCUMENTATION_REVISION}/docs/API.md"
)
CONFIRMATION_DELAY = timedelta(hours=24)
ATTRIBUTION_MAX_SKEW = timedelta(minutes=15)
SELF_EMAIL = "rafaelantunes137@gmail.com"
HTTP_TIMEOUT_SECONDS = 25

ISSUE_CLAIMS = (
    (5463673644, "https://github.com/Scottcjn/ram-coffers/issues/691"),
    (5463675166, "https://github.com/Scottcjn/beacon-skill/issues/921"),
    (5463676827, "https://github.com/Scottcjn/grazer-skill/issues/344"),
    (5463678966, "https://github.com/Scottcjn/llama-cpp-power8/issues/39"),
)
ISSUE_PROVIDER_COMMENT_ID = 5464599807
PR_EVIDENCE = (
    (8295, 5464266722, 5.0),
    (8289, 5463304541, 5.0),
)


class EvidenceError(RuntimeError):
    """Raised when public evidence does not match the required facts."""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(value: str, length: int = 16) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def canonical_json_hash(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def rustchain_entries_hash(entries: list[dict[str, Any]]) -> str:
    selected = [row for row in entries if isinstance(row, dict) and target_entry(row)]
    selected.sort(key=lambda row: str(row.get("bounty_key") or ""))
    return canonical_json_hash(selected)


def fetch_json(url: str) -> Any:
    if url.startswith("https://api.github.com/") and Path("/usr/bin/gh").exists():
        endpoint = url.removeprefix("https://api.github.com")
        try:
            result = subprocess.run(
                ["/usr/bin/gh", "api", endpoint],
                text=True,
                capture_output=True,
                check=False,
                timeout=HTTP_TIMEOUT_SECONDS,
            )
            if result.returncode == 0:
                try:
                    return json.loads(result.stdout)
                except json.JSONDecodeError:
                    pass
        except subprocess.TimeoutExpired:
            pass
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json, application/json",
            "User-Agent": "agentic-rustchain-reconciler/1",
        },
    )
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        return json.load(response)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def parse_utc(value: str) -> datetime:
    raw = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
    except ValueError as exc:
        raise EvidenceError(f"invalid public evidence timestamp: {raw[:80]}") from exc
    if parsed.tzinfo is None:
        raise EvidenceError("public evidence timestamp is not timezone-aware")
    return parsed.astimezone(timezone.utc)


def unix_timestamp_iso(value: int) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def wallet_history_url(offset: int) -> str:
    return (
        f"{HISTORY_BASE_URL}?miner_id={WALLET}"
        f"&limit={HISTORY_PAGE_SIZE}&offset={offset}"
    )


def collect_wallet_history(fetcher: Callable[[str], Any]) -> dict[str, Any]:
    transactions: list[dict[str, Any]] = []
    expected_total: int | None = None
    offset = 0
    source_urls: list[str] = []
    while expected_total is None or offset < expected_total:
        require(offset <= 9800, "wallet history exceeds the public pagination limit")
        source_url = wallet_history_url(offset)
        page = fetcher(source_url)
        source_urls.append(source_url)
        require(isinstance(page, dict), "wallet history response is not an object")
        require(page.get("ok") is True, "wallet history response is not successful")
        require(str(page.get("miner_id") or "") == WALLET, "wallet history returned another miner_id")
        page_rows = page.get("transactions")
        require(isinstance(page_rows, list), "wallet history transactions are not a list")
        try:
            page_total = int(page.get("total"))
        except (TypeError, ValueError) as exc:
            raise EvidenceError("wallet history total is invalid") from exc
        require(page_total >= 0, "wallet history total is negative")
        if expected_total is None:
            expected_total = page_total
        require(page_total == expected_total, "wallet history changed during pagination")
        require(len(page_rows) <= HISTORY_PAGE_SIZE, "wallet history page exceeds requested limit")
        if offset < expected_total:
            require(bool(page_rows), "wallet history pagination ended before total")
        transactions.extend(row for row in page_rows if isinstance(row, dict))
        require(len(transactions) == offset + len(page_rows), "wallet history contains non-object rows")
        offset += len(page_rows)
        require(offset <= expected_total, "wallet history returned more rows than total")
        if expected_total == 0:
            break
    require(expected_total is not None, "wallet history total is unavailable")
    require(len(transactions) == expected_total, "wallet history response is incomplete")
    payload = {
        "ok": True,
        "miner_id": WALLET,
        "total": expected_total,
        "transactions": transactions,
    }
    return {
        **payload,
        "source_url": HISTORY_URL,
        "source_urls": source_urls,
        "documentation_url": HISTORY_DOCUMENTATION_URL,
        "documentation_revision": HISTORY_DOCUMENTATION_REVISION,
        "response_sha256": canonical_json_hash(payload),
    }


def confirmed_incoming_transfers(history: dict[str, Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(history.get("transactions") or []):
        if str(row.get("type") or "") != "transfer_in":
            continue
        transfer_status = str(row.get("status") or "").strip().lower()
        if transfer_status in {"voided", "reversed", "failed", "cancelled", "canceled"}:
            continue
        require(
            transfer_status in {"", "confirmed", "settled", "completed", "success"},
            f"wallet history transfer {index} has unknown status {transfer_status!r}",
        )
        txid = str(row.get("tx_hash") or "").lower()
        require(bool(re.fullmatch(r"[0-9a-f]{32,64}", txid)), f"wallet history transfer {index} has invalid tx_hash")
        require(txid not in seen, f"wallet history repeats tx_hash {txid}")
        seen.add(txid)
        sender = str(row.get("from") or "")
        if sender != "founder_community":
            continue
        try:
            amount = float(row.get("amount"))
            epoch = int(row.get("epoch"))
            timestamp = int(row.get("timestamp"))
        except (TypeError, ValueError) as exc:
            raise EvidenceError(f"wallet history transfer {txid} has invalid numeric fields") from exc
        require(amount > 0 and epoch >= 0 and timestamp > 0, f"wallet history transfer {txid} has invalid values")
        reason = str(row.get("reason") or "")
        if reason:
            require(reason == f"transfer_in:{sender}:{txid}", f"wallet history transfer {txid} reason disagrees")
        normalized.append(
            {
                "txid": txid,
                "amount": amount,
                "asset": "RTC",
                "epoch": epoch,
                "timestamp": timestamp,
                "received_at": unix_timestamp_iso(timestamp),
                "from": sender,
                "type": "transfer_in",
                "confirmation_status": "confirmed_immutable_ledger",
                "source_url": str(history.get("source_url") or HISTORY_URL),
            }
        )
    return normalized


def uniquely_attribute_receipts(
    history: dict[str, Any],
    *,
    provider_confirmed_at: str,
    amount_each: float,
    count: int,
) -> dict[str, Any]:
    provider_time = parse_utc(provider_confirmed_at)
    expected_time = provider_time + CONFIRMATION_DELAY
    matches = [
        row
        for row in confirmed_incoming_transfers(history)
        if abs(float(row["amount"]) - amount_each) < 0.0000001
        and abs(datetime.fromtimestamp(int(row["timestamp"]), tz=timezone.utc) - expected_time)
        <= ATTRIBUTION_MAX_SKEW
    ]
    require(
        len(matches) == count,
        f"wallet history attribution expected {count} x {amount_each:g} RTC, found {len(matches)}",
    )
    matches.sort(key=lambda row: (int(row["timestamp"]), str(row["txid"])))
    received_amount = sum(float(row["amount"]) for row in matches)
    require(abs(received_amount - amount_each * count) < 0.0000001, "wallet receipt total disagrees")
    return {
        "amount_received": received_amount,
        "asset": "RTC",
        "wallet_received_at": max(str(row["received_at"]) for row in matches),
        "transactions": matches,
        "txids": [str(row["txid"]) for row in matches],
        "attribution": {
            "method": "provider_confirmation_plus_public_immutable_ledger_24h_window",
            "provider_confirmed_at": provider_time.isoformat().replace("+00:00", "Z"),
            "expected_confirmation_at": expected_time.isoformat().replace("+00:00", "Z"),
            "max_skew_seconds": int(ATTRIBUTION_MAX_SKEW.total_seconds()),
            "matched_transaction_count": len(matches),
        },
        "wallet_history_sha256": str(history.get("response_sha256") or ""),
        "wallet_history_url": str(history.get("source_url") or HISTORY_URL),
        "wallet_history_documentation_url": str(
            history.get("documentation_url") or HISTORY_DOCUMENTATION_URL
        ),
        "wallet_history_documentation_revision": str(
            history.get("documentation_revision") or HISTORY_DOCUMENTATION_REVISION
        ),
    }


def issue_comment_url(comment_id: int) -> str:
    return (
        "https://api.github.com/repos/Scottcjn/rustchain-bounties/"
        f"issues/comments/{comment_id}"
    )


def pr_url(number: int) -> str:
    return f"https://api.github.com/repos/Scottcjn/Rustchain/pulls/{number}"


def pr_comment_url(comment_id: int) -> str:
    return f"https://api.github.com/repos/Scottcjn/Rustchain/issues/comments/{comment_id}"


def collect_public_evidence(fetcher: Callable[[str], Any] = fetch_json) -> dict[str, Any]:
    balance = fetcher(BALANCE_URL)
    require(isinstance(balance, dict), "wallet balance response is not an object")
    require(str(balance.get("miner_id")) == WALLET, "wallet balance returned another miner_id")
    try:
        amount_i64 = int(balance["amount_i64"])
        amount_rtc = float(balance["amount_rtc"])
    except (KeyError, TypeError, ValueError) as exc:
        raise EvidenceError("wallet balance fields are missing or invalid") from exc
    require(amount_i64 >= 0 and amount_rtc >= 0, "wallet balance is negative")
    require(abs(amount_rtc - amount_i64 / 1_000_000) < 0.0000005, "wallet balance units disagree")
    history = collect_wallet_history(fetcher)

    claim_evidence: list[dict[str, Any]] = []
    for comment_id, contribution_url in ISSUE_CLAIMS:
        row = fetcher(issue_comment_url(comment_id))
        require(isinstance(row, dict), f"claim comment {comment_id} is not an object")
        body = str(row.get("body") or "")
        require(str((row.get("user") or {}).get("login")) == "rafaio1", f"claim {comment_id} has another actor")
        require(WALLET in body, f"claim {comment_id} does not bind the canonical wallet")
        require(contribution_url in body, f"claim {comment_id} does not identify the expected contribution")
        claim_evidence.append(
            {
                "evidence_type": "public_claim_submission",
                "source_url": str(row.get("html_url") or ""),
                "provider_actor": "rafaio1",
                "observed_at": str(row.get("created_at") or ""),
                "receive_address": WALLET,
                "contribution_url": contribution_url,
            }
        )

    issue_confirmation = fetcher(issue_comment_url(ISSUE_PROVIDER_COMMENT_ID))
    require(isinstance(issue_confirmation, dict), "issue provider comment is not an object")
    issue_body = str(issue_confirmation.get("body") or "")
    require(str((issue_confirmation.get("user") or {}).get("login")) == "Scottcjn", "issue payout actor is not maintainer")
    require("@rafaio1" in issue_body, "issue payout confirmation does not identify rafaio1")
    require(bool(re.search(r"\b4\s+RTC\s+paid\b", issue_body, re.IGNORECASE)), "issue payout confirmation does not state 4 RTC paid")
    require("four genuine doc-suggestion issues" in issue_body, "issue payout evidence lost its acceptance rationale")
    issue_provider = {
        "evidence_type": "provider_payout_confirmation",
        "source_url": str(issue_confirmation.get("html_url") or ""),
        "provider_actor": "Scottcjn",
        "observed_at": str(issue_confirmation.get("created_at") or ""),
        "confirmed_amount": 4.0,
        "asset": "RTC",
        "confirmation_text_sha256": hashlib.sha256(issue_body.encode("utf-8")).hexdigest(),
    }

    prs: dict[int, dict[str, Any]] = {}
    for number, comment_id, reward in PR_EVIDENCE:
        pull = fetcher(pr_url(number))
        reward_comment = fetcher(pr_comment_url(comment_id))
        require(isinstance(pull, dict) and isinstance(reward_comment, dict), f"PR {number} evidence is not an object")
        require(int(pull.get("number") or 0) == number, f"PR {number} API returned another number")
        require(str((pull.get("user") or {}).get("login")) == "rafaio1", f"PR {number} has another author")
        require(pull.get("merged") is True and bool(pull.get("merged_at")), f"PR {number} is not publicly merged")
        body = str(reward_comment.get("body") or "")
        require(str((reward_comment.get("user") or {}).get("login")) == "github-actions[bot]", f"PR {number} reward actor changed")
        require(WALLET in body, f"PR {number} reward does not bind the canonical wallet")
        require(bool(re.search(rf"\b{int(reward)}\s+RTC\b", body, re.IGNORECASE)), f"PR {number} reward amount changed")
        require("sent to" in body.lower(), f"PR {number} reward is not provider-confirmed")
        prs[number] = {
            "number": number,
            "created_at": str(pull.get("created_at") or ""),
            "merged_at": str(pull.get("merged_at") or ""),
            "pr_url": str(pull.get("html_url") or ""),
            "merge_commit_sha": str(pull.get("merge_commit_sha") or ""),
            "provider_confirmed_at": str(reward_comment.get("created_at") or ""),
            "provider_confirmation_url": str(reward_comment.get("html_url") or ""),
            "reward": reward,
            "provider_text_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        }

    receipts = {
        "issue_254": uniquely_attribute_receipts(
            history,
            provider_confirmed_at=str(issue_provider["observed_at"]),
            amount_each=1.0,
            count=len(claim_evidence),
        ),
        "prs": {
            number: uniquely_attribute_receipts(
                history,
                provider_confirmed_at=str(prs[number]["provider_confirmed_at"]),
                amount_each=float(prs[number]["reward"]),
                count=1,
            )
            for number in (8295, 8289)
        },
    }
    all_txids = [
        *receipts["issue_254"]["txids"],
        *receipts["prs"][8295]["txids"],
        *receipts["prs"][8289]["txids"],
    ]
    require(len(all_txids) == len(set(all_txids)), "one wallet transfer was attributed to more than one bounty")
    mapped_amount = float(receipts["issue_254"]["amount_received"]) + sum(
        float(receipts["prs"][number]["amount_received"]) for number in (8295, 8289)
    )
    require(abs(mapped_amount - 14.0) < 0.0000001, "mapped wallet receipt total is not 14 RTC")

    return {
        "wallet": {
            "miner_id": WALLET,
            "amount_i64": amount_i64,
            "amount_rtc": amount_rtc,
            "source_url": BALANCE_URL,
        },
        "wallet_history": history,
        "wallet_receipts": receipts,
        "issue_254": {
            "claims": claim_evidence,
            "provider": issue_provider,
        },
        "prs": prs,
    }


RECOVERY_STEPS = [
    f"O monitor autonomo revalida saldo e historico nativos nos endpoints publicos {BALANCE_URL} e {HISTORY_URL}.",
    "O reconciliador preserva os txids, valores, epochs e horarios que comprovam o credito na carteira RTC controlada pelo sistema.",
    "O cofre automatizado preserva as credenciais RTC sob custodia e impede que seed, mnemonic ou chave privada sejam criados, registrados ou transmitidos pelo ledger, GitHub, email ou Telegram.",
    "O roteador mantem a conversao como pendente e conserva RTC na carteira nativa enquanto ativo, rede, minimos e compatibilidade nao forem verificados deterministicamente; isto nao recusa nem devolve o bounty.",
    "O reconciliador de rota continua descobrindo RTC para wRTC, swap, deposito em exchange e resgate Wise, e so executa uma rota completa quando cada etapa, taxa, quantidade e endereco corrente estiverem verificados.",
    "Telegram e email notificam o credito recebido ou uma trava terminal real; verificacoes rotineiras de conversao pendente permanecem silenciosas e nao atribuem acao humana.",
]


def common_entry(
    *,
    bounty_key: str,
    repo: str,
    issue_or_pr: str,
    amount: float,
    submitted_at: str,
    provider_confirmed_at: str,
    provider_url: str,
    provider_evidence: list[dict[str, Any]],
    receipt: dict[str, Any],
) -> dict[str, Any]:
    transactions = [dict(row) for row in receipt["transactions"]]
    txids = [str(value) for value in receipt["txids"]]
    wallet_evidence = [
        {
            "evidence_type": "public_wallet_history_receipt",
            "source_url": str(receipt["wallet_history_url"]),
            "provider_actor": "rustchain_public_immutable_ledger",
            "observed_at": str(row["received_at"]),
            "receive_address": WALLET,
            "txid": str(row["txid"]),
            "amount": float(row["amount"]),
            "asset": "RTC",
            "epoch": int(row["epoch"]),
            "from": str(row["from"]),
            "confirmation_status": "confirmed_immutable_ledger",
        }
        for row in transactions
    ]
    return {
        "schema_version": "1.0",
        "ledger_id": stable_id(bounty_key),
        "bounty_key": bounty_key,
        "platform": "github",
        "repo": repo,
        "issue_or_pr": issue_or_pr,
        "reward_asset": "RTC",
        "expected_amount": amount,
        "expected_currency": "RTC",
        "chain": "rustchain",
        "network": "rustchain-native",
        "rail_id": "rustchain_native_wallet",
        "receive_address": WALLET,
        "address": WALLET,
        "address_source": "public_bounty_submission",
        "ownership_proof_status": "public_claim_target_and_wallet_receipt",
        "address_validated_at": submitted_at,
        "provider_payout_url": provider_url,
        "memo_or_tag": None,
        "deposit_minimum": None,
        "destination_restrictions": [
            "RTC is received and held on the native RustChain wallet",
            "conversion waits for a deterministic end-to-end supported route",
        ],
        "status": "wallet_received",
        "timestamps": {
            "created_at": submitted_at,
            "submitted_at": submitted_at,
            "provider_confirmed_at": provider_confirmed_at,
            "wallet_received_at": str(receipt["wallet_received_at"]),
        },
        "provider_evidence": [*provider_evidence, *wallet_evidence],
        "provider_confirmed_amount": amount,
        "txid": txids[0] if len(txids) == 1 else None,
        "txids": txids,
        "wallet_transactions": transactions,
        "wallet_history_url": str(receipt["wallet_history_url"]),
        "wallet_history_sha256": str(receipt["wallet_history_sha256"]),
        "wallet_history_documentation_url": str(receipt["wallet_history_documentation_url"]),
        "wallet_history_documentation_revision": str(
            receipt["wallet_history_documentation_revision"]
        ),
        "wallet_receipt_attribution": dict(receipt["attribution"]),
        "amount_received": float(receipt["amount_received"]),
        "confirmations": None,
        "confirmation_status": "confirmed_immutable_ledger",
        "action_required": False,
        "human_action": "none",
        "autonomous_recovery": True,
        "informational_notifications_only": True,
        "recovery_policy_revision": RECOVERY_POLICY_VERSION,
        "recovery_steps": list(RECOVERY_STEPS),
        "notification_outbox": [],
        "conversion_status": "pending",
        "bybit_route_status": "conversion_pending",
        "wise_route_status": "conversion_pending",
        "blockers": [],
        "source_revision": RECONCILER_VERSION,
        "financial_write_authority": RECONCILER_VERSION,
    }


def build_entries(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    issue = evidence["issue_254"]
    claim_rows = issue["claims"]
    provider = issue["provider"]
    entries = [
        common_entry(
            bounty_key="github|Scottcjn/rustchain-bounties|254",
            repo="Scottcjn/rustchain-bounties",
            issue_or_pr="254",
            amount=4.0,
            submitted_at=min(str(row["observed_at"]) for row in claim_rows),
            provider_confirmed_at=str(provider["observed_at"]),
            provider_url=str(provider["source_url"]),
            provider_evidence=[*claim_rows, provider],
            receipt=evidence["wallet_receipts"]["issue_254"],
        )
    ]
    for number in (8295, 8289):
        row = evidence["prs"][number]
        entries.append(
            common_entry(
                bounty_key=f"github|Scottcjn/Rustchain|{number}",
                repo="Scottcjn/Rustchain",
                issue_or_pr=str(number),
                amount=float(row["reward"]),
                submitted_at=str(row["created_at"]),
                provider_confirmed_at=str(row["provider_confirmed_at"]),
                provider_url=str(row["provider_confirmation_url"]),
                provider_evidence=[
                    {
                        "evidence_type": "merged_pull_request",
                        "source_url": str(row["pr_url"]),
                        "provider_actor": "Scottcjn/Rustchain",
                        "observed_at": str(row["merged_at"]),
                        "merge_commit_sha": str(row["merge_commit_sha"]),
                    },
                    {
                        "evidence_type": "provider_payout_confirmation",
                        "source_url": str(row["provider_confirmation_url"]),
                        "provider_actor": "github-actions[bot]",
                        "observed_at": str(row["provider_confirmed_at"]),
                        "confirmed_amount": float(row["reward"]),
                        "asset": "RTC",
                        "receive_address": WALLET,
                        "confirmation_text_sha256": str(row["provider_text_sha256"]),
                    },
                ],
                receipt=evidence["wallet_receipts"]["prs"][number],
            )
        )
    return entries


def notification_item(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "created_at": entry["timestamps"]["wallet_received_at"],
        "alert_class": "wallet_received",
        "terminal_blocked": False,
        "action_required": False,
        "human_action": "none",
        "informational": True,
        "autonomous_recovery": True,
        "recovery_policy_revision": RECOVERY_POLICY_VERSION,
        "ledger_id": entry["ledger_id"],
        "bounty_key": entry["bounty_key"],
        "status": "wallet_received",
        "asset": "RTC",
        "amount": entry["amount_received"],
        "network": "rustchain-native",
        "receive_address": WALLET,
        "memo": None,
        "minimum": None,
        "deadline": None,
        "txid": entry.get("txid"),
        "txids": entry["txids"],
        "wallet_history_url": entry["wallet_history_url"],
        "wallet_history_sha256": entry["wallet_history_sha256"],
        "evidence": [
            row
            for row in entry["provider_evidence"]
            if row.get("evidence_type") == "public_wallet_history_receipt"
        ],
        "blockers": [],
        "recovery_steps": entry["recovery_steps"],
        "source_revision": RECONCILER_VERSION,
    }


def recovery_body(item: dict[str, Any]) -> str:
    blockers = [str(row.get("type") or row) for row in item.get("blockers") or []]
    steps = [str(step).strip() for step in item.get("recovery_steps") or [] if str(step).strip()]
    steps_text = "\n".join(f"{index}. {step}" for index, step in enumerate(steps, 1))
    return (
        "BOUNTY RECEBIDO NA CARTEIRA\n"
        "Acao humana: nenhuma.\n"
        f"Ledger: {item.get('ledger_id')}\nBounty: {item.get('bounty_key')}\nEstado: {item.get('status')}\n"
        f"Ativo/valor recebido: {item.get('asset')} {item.get('amount')}\n"
        f"Rede: {item.get('network')}\nRail publico: {item.get('receive_address')}\n"
        f"Txids: {', '.join(str(value) for value in item.get('txids') or [])}\n"
        f"Historico publico: {item.get('wallet_history_url')}\n"
        f"Bloqueios: {', '.join(blockers) if blockers else 'nenhum para recebimento'}\n"
        f"Etapas automaticas do sistema:\n{steps_text}\n"
        "O credito RTC esta confirmado na carteira. Conversao, exchange e Wise permanecem etapas separadas e "
        "nao sao contabilizadas como receita realizada antes da reconciliacao de cada transferencia."
    )


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    os.chmod(temp, 0o600)
    os.replace(temp, path)


def atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temp, path)


def jsonl_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(descriptor, (json.dumps(payload, ensure_ascii=True, separators=(",", ":")) + "\n").encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def target_entry(row: dict[str, Any]) -> bool:
    key = str(row.get("bounty_key") or "")
    repo = str(row.get("repo") or "").lower()
    item = str(row.get("issue_or_pr") or "")
    if key in {
        "github|Scottcjn/rustchain-bounties|254",
        "github|Scottcjn/Rustchain|8295",
        "github|Scottcjn/Rustchain|8289",
        "unknown|rustchain/rustchain|254|idx21",
    }:
        return True
    return (item == "254" and repo == "rustchain/rustchain") or (item in {"8295", "8289"} and repo == "scottcjn/rustchain")


def reconcile(root: Path, evidence: dict[str, Any], *, now: str | None = None) -> dict[str, Any]:
    now = now or utcnow()
    data = root / "data/aro"
    ledger_path = data / "bounty_receive_ledger.json"
    archive = data / "archive"
    notifications = data / "inbox/notifications_outbox.jsonl"
    email_outbox = data / "inbox/email_outbox.jsonl"
    sidecar_path = data / "rustchain_reconciliation.json"

    ledger = load_json(ledger_path)
    require(isinstance(ledger, dict) and isinstance(ledger.get("entries"), list), "canonical receive ledger has invalid shape")
    desired = build_entries(evidence)

    notification_pairs: list[tuple[dict[str, Any], str]] = []
    for entry in desired:
        item = notification_item(entry)
        event_id = canonical_json_hash(item)
        entry["notification_outbox"] = [
            {"channel": "telegram_recovery", "event_id": event_id},
            {"channel": "email_recovery", "event_id": event_id},
        ]
        notification_pairs.append((item, event_id))

    current_targets = {str(row.get("bounty_key")): row for row in ledger["entries"] if isinstance(row, dict) and target_entry(row)}
    material_entries: list[dict[str, Any]] = []
    for entry in desired:
        prior = current_targets.get(entry["bounty_key"])
        material = dict(entry)
        if isinstance(prior, dict):
            material["reconciled_at"] = prior.get("reconciled_at") or now
            material["updated_at"] = prior.get("updated_at") or now
            if material != prior:
                material["updated_at"] = now
        else:
            material["reconciled_at"] = now
            material["updated_at"] = now
        material_entries.append(material)

    other_entries = [row for row in ledger["entries"] if not (isinstance(row, dict) and target_entry(row))]
    new_entries = other_entries + material_entries
    changed = new_entries != ledger["entries"]
    if changed:
        archive.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = archive / f"bounty_receive_ledger-pre-rustchain-{stamp}-{os.getpid()}.json"
        shutil.copy2(ledger_path, backup)
        os.chmod(backup, 0o600)
        ledger["entries"] = new_entries
        ledger["updated_at"] = now
        atomic_json(ledger_path, ledger)
    else:
        backup = None

    existing_notifications = {canonical_json_hash(row) for row in jsonl_rows(notifications)}
    existing_email_ids = {str(row.get("event_id") or "") for row in jsonl_rows(email_outbox)}
    queued_notifications = 0
    queued_emails = 0
    for item, event_id in notification_pairs:
        if event_id not in existing_notifications:
            append_jsonl(notifications, item)
            existing_notifications.add(event_id)
            queued_notifications += 1
        if event_id not in existing_email_ids:
            append_jsonl(
                email_outbox,
                {
                    "schema_version": 1,
                    "event_id": event_id,
                    "created_at": now,
                    "to": SELF_EMAIL,
                    "subject": f"Bounty recebido na carteira: {item['bounty_key']}",
                    "body": recovery_body(item),
                    "delivery_status": "queued",
                },
            )
            existing_email_ids.add(event_id)
            queued_emails += 1

    ledger_bytes = ledger_path.read_bytes()
    mapped_total = sum(float(row["amount_received"]) for row in material_entries)
    mapped_transaction_count = sum(len(row["txids"]) for row in material_entries)
    wallet_balance = float(evidence["wallet"]["amount_rtc"])
    sidecar = {
        "schema_version": SCHEMA_VERSION,
        "source_revision": RECONCILER_VERSION,
        "status": "verified_wallet_history",
        "observed_at": now,
        "wallet": evidence["wallet"],
        "wallet_history_url": str(evidence["wallet_history"]["source_url"]),
        "wallet_history_sha256": str(evidence["wallet_history"]["response_sha256"]),
        "canonical_bounty_keys": [row["bounty_key"] for row in material_entries],
        "provider_confirmed_total": {"asset": "RTC", "amount": mapped_total, "entry_count": len(material_entries)},
        "wallet_received_total": {
            "asset": "RTC",
            "amount": mapped_total,
            "entry_count": len(material_entries),
            "transaction_count": mapped_transaction_count,
        },
        "wallet_receipts": [
            {
                "bounty_key": row["bounty_key"],
                "amount_received": row["amount_received"],
                "asset": "RTC",
                "wallet_received_at": row["timestamps"]["wallet_received_at"],
                "txids": row["txids"],
                "wallet_history_url": row["wallet_history_url"],
                "wallet_history_sha256": row["wallet_history_sha256"],
                "attribution": row["wallet_receipt_attribution"],
            }
            for row in material_entries
        ],
        "settled_total": {"asset": "RTC", "amount": 0.0, "entry_count": 0},
        "settlement_scope": "conversion_exchange_and_fiat_only",
        "balance_not_mapped_to_these_records_rtc": wallet_balance - mapped_total,
        "current_balance_minus_mapped_historical_receipts_rtc": wallet_balance - mapped_total,
        "realized_revenue_written": False,
        "conversion_status": "pending",
        "bybit_route_status": "conversion_pending",
        "wise_route_status": "conversion_pending",
        "direct_transfer_performed": False,
        "wallet_receipts_recorded": True,
        "autonomous_recovery": True,
        "human_action_required": False,
        "recovery_policy_revision": RECOVERY_POLICY_VERSION,
        "monitor_timer": "agentic-rustchain-reconciler.timer",
        "ledger_sha256": hashlib.sha256(ledger_bytes).hexdigest(),
        "rustchain_entries_sha256": rustchain_entries_hash(ledger["entries"]),
        "ledger_changed": changed,
        "backup_path": str(backup) if backup else None,
        "queued_notification_count": queued_notifications,
        "queued_email_count": queued_emails,
        "evidence_urls": [
            BALANCE_URL,
            HISTORY_URL,
            HISTORY_DOCUMENTATION_URL,
            evidence["issue_254"]["provider"]["source_url"],
            evidence["prs"][8295]["provider_confirmation_url"],
            evidence["prs"][8289]["provider_confirmation_url"],
        ],
    }
    atomic_json(sidecar_path, sidecar)
    refresh_authority_snapshot(root, ledger_path)
    return sidecar


def refresh_authority_snapshot(root: Path, ledger_path: Path) -> None:
    """Refresh guard snapshots only after they have been explicitly bootstrapped."""
    configured = os.environ.get("AGENTIC_LEDGER_AUTHORITY_DIR", "").strip()
    if configured:
        authority = Path(configured)
    elif root.resolve() == Path("/Agentic"):
        authority = Path("/var/lib/agentic/ledger-authority")
    else:
        authority = root / "var/lib/agentic/ledger-authority"
    manifest_path = authority / "authoritative_manifest.json"
    if not manifest_path.exists():
        return
    realized = root / "data/aro/realized_revenue_ledger.jsonl"
    ledger_snapshot = authority / "authoritative_bounty_receive_ledger.json"
    realized_snapshot = authority / "authoritative_realized_revenue_ledger.jsonl"
    atomic_bytes(ledger_snapshot, ledger_path.read_bytes())
    atomic_bytes(realized_snapshot, realized.read_bytes() if realized.exists() else b"")
    atomic_json(
        manifest_path,
        {
            "schema_version": 1,
            "updated_at": utcnow(),
            "writer": RECONCILER_VERSION,
            "bounty_receive_ledger_sha256": hashlib.sha256(ledger_snapshot.read_bytes()).hexdigest(),
            "realized_revenue_ledger_sha256": hashlib.sha256(realized_snapshot.read_bytes()).hexdigest(),
        },
    )


def write_failure_state(root: Path, error: Exception) -> None:
    path = root / "state/rustchain_reconciliation_state.json"
    atomic_json(
        path,
        {
            "schema_version": SCHEMA_VERSION,
            "source_revision": RECONCILER_VERSION,
            "status": "public_evidence_unavailable_fail_closed",
            "checked_at": utcnow(),
            "error_type": type(error).__name__,
            "error": str(error)[:1000],
            "ledger_mutated": False,
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="/Agentic")
    parser.add_argument("--lock", default="/run/agentic-financial-ledger.lock")
    parser.add_argument("--authority-dir", default=os.environ.get("AGENTIC_LEDGER_AUTHORITY_DIR"))
    args = parser.parse_args()
    root = Path(args.root)
    if args.authority_dir:
        os.environ["AGENTIC_LEDGER_AUTHORITY_DIR"] = args.authority_dir
    lock_path = Path(args.lock)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with lock_path.open("w", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            evidence = collect_public_evidence()
            result = reconcile(root, evidence)
    except BlockingIOError:
        print("RUSTCHAIN_RECONCILE_SKIPPED lock_busy")
        return 0
    except Exception as exc:
        try:
            write_failure_state(root, exc)
        except Exception:
            pass
        print(f"RUSTCHAIN_RECONCILE_ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
