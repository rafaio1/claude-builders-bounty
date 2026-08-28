"""Official provider verification for realized revenue.

Only provider APIs, never dashboard URLs or agent-supplied amounts, can create a
settled record.  Unsupported providers remain fail-closed.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class SettlementVerificationError(ValueError):
    """A provider payment could not be independently confirmed."""


class SettlementReversedError(SettlementVerificationError):
    """A previously valid provider payment has been partially or fully reversed."""


@dataclass(frozen=True)
class VerifiedSettlement:
    provider: str
    transaction_id: str
    verification_url: str
    verification_id: str
    verified_at: str
    verification_source: str
    provider_payload_sha256: str
    provider_status: str
    currency: str
    gross_amount: float
    fee_amount: float
    net_amount: float
    received_at: str
    metadata: dict[str, Any]

    def record(self) -> dict[str, Any]:
        return asdict(self)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _stripe_request(path: str, *, stripe_account: str | None = None) -> Mapping[str, Any]:
    secret = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY")
    if not secret:
        raise SettlementVerificationError("Stripe API credential unavailable")
    authorization = base64.b64encode(f"{secret}:".encode("utf-8")).decode("ascii")
    headers = {
        "Authorization": f"Basic {authorization}",
        "User-Agent": "agentic-revenue-settlement/1",
    }
    if stripe_account:
        headers["Stripe-Account"] = stripe_account
    request = Request(
        f"https://api.stripe.com/v1/{path.lstrip('/')}",
        headers=headers,
    )
    try:
        with urlopen(request, timeout=20) as response:
            if response.status != 200:
                raise SettlementVerificationError(
                    f"Stripe API returned HTTP {response.status}"
                )
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise SettlementVerificationError(
            f"Stripe API returned HTTP {error.code}"
        ) from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise SettlementVerificationError("Stripe payout evidence unavailable") from error
    if not isinstance(payload, Mapping):
        raise SettlementVerificationError("Stripe payout response is invalid")
    return payload


def _stripe_get(transfer_id: str) -> Mapping[str, Any]:
    return _stripe_request(f"transfers/{quote(transfer_id, safe='')}")


def _stripe_get_platform_balance_transaction(
    transaction_id: str,
) -> Mapping[str, Any]:
    return _stripe_request(
        f"balance_transactions/{quote(transaction_id, safe='')}"
    )


def _stripe_get_destination_payment(
    payment_id: str,
    destination_account: str,
) -> Mapping[str, Any]:
    return _stripe_request(
        f"charges/{quote(payment_id, safe='')}",
        stripe_account=destination_account,
    )


def _stripe_get_destination_balance_transaction(
    transaction_id: str,
    destination_account: str,
) -> Mapping[str, Any]:
    return _stripe_request(
        f"balance_transactions/{quote(transaction_id, safe='')}",
        stripe_account=destination_account,
    )


def verify_provider_settlement(
    provider: str,
    transaction_id: str,
    context: Mapping[str, Any],
) -> VerifiedSettlement:
    provider = str(provider or "").casefold()
    transaction_id = str(transaction_id or "").strip()
    if provider != "stripe":
        raise SettlementVerificationError("provider has no official verifier")
    if not transaction_id.startswith("tr_"):
        raise SettlementVerificationError("Stripe settlement must be an attributed transfer")
    transfer = _stripe_get(transaction_id)
    if str(transfer.get("object") or "") != "transfer":
        raise SettlementVerificationError("Stripe object is not a transfer")
    if str(transfer.get("id") or "") != transaction_id:
        raise SettlementVerificationError("Stripe transfer identifier mismatch")
    if not bool(transfer.get("livemode")):
        raise SettlementVerificationError("Stripe transfer is not live money")
    if bool(transfer.get("reversed")) or int(transfer.get("amount_reversed") or 0) != 0:
        raise SettlementReversedError("Stripe transfer was reversed")
    try:
        amount_minor = int(transfer.get("amount"))
        created_epoch = int(transfer.get("created"))
        expected_minor = int(round(float(context.get("expected_amount")) * 100))
    except (TypeError, ValueError) as error:
        raise SettlementVerificationError("Stripe transfer amount/date is invalid") from error
    currency = str(transfer.get("currency") or "").upper()
    expected_currency = str(context.get("expected_currency") or "").upper()
    if amount_minor <= 0 or amount_minor != expected_minor or currency != expected_currency:
        raise SettlementVerificationError("Stripe transfer amount/currency mismatch")
    expected_destination = str(context.get("expected_destination") or "").strip()
    destination = str(transfer.get("destination") or "").strip()
    if not expected_destination:
        raise SettlementVerificationError("Stripe destination account is not configured")
    if destination != expected_destination:
        raise SettlementVerificationError("Stripe transfer destination mismatch")
    metadata = transfer.get("metadata")
    if not isinstance(metadata, Mapping):
        raise SettlementVerificationError("Stripe transfer attribution metadata missing")
    required_metadata = {
        "agentic_work_order_id": str(context.get("work_order_id") or ""),
        "official_reward_id": str(context.get("official_reward_id") or ""),
        "payer_identity": str(context.get("payer_identity") or ""),
    }
    if any(not value for value in required_metadata.values()) or any(
        str(metadata.get(key) or "") != value
        for key, value in required_metadata.items()
    ):
        raise SettlementVerificationError("Stripe transfer is not attributed to this reward")
    destination_payment = str(transfer.get("destination_payment") or "")
    platform_balance_transaction = str(transfer.get("balance_transaction") or "")
    if not destination_payment or not platform_balance_transaction:
        raise SettlementVerificationError("Stripe transfer lacks financial transaction links")
    platform_balance = _stripe_get_platform_balance_transaction(
        platform_balance_transaction
    )
    if (
        str(platform_balance.get("id") or "") != platform_balance_transaction
        or str(platform_balance.get("object") or "") != "balance_transaction"
        or str(platform_balance.get("status") or "") != "available"
        or str(platform_balance.get("currency") or "").upper() != currency
        or abs(int(platform_balance.get("amount") or 0)) != amount_minor
        or str(platform_balance.get("source") or "") != transaction_id
    ):
        raise SettlementVerificationError(
            "Stripe platform balance transaction is not final or linked"
        )
    payment = _stripe_get_destination_payment(destination_payment, destination)
    destination_balance_transaction = str(payment.get("balance_transaction") or "")
    if (
        str(payment.get("id") or "") != destination_payment
        or str(payment.get("object") or "") != "charge"
        or not bool(payment.get("paid"))
        or bool(payment.get("refunded"))
        or int(payment.get("amount_refunded") or 0) != 0
        or int(payment.get("amount") or 0) != amount_minor
        or str(payment.get("currency") or "").upper() != currency
        or not destination_balance_transaction
    ):
        raise SettlementVerificationError(
            "Stripe destination payment is not final or linked"
        )
    destination_balance = _stripe_get_destination_balance_transaction(
        destination_balance_transaction,
        destination,
    )
    try:
        destination_amount_minor = int(destination_balance.get("amount"))
        net_minor = int(destination_balance.get("net"))
        available_on = int(destination_balance.get("available_on"))
    except (TypeError, ValueError) as error:
        raise SettlementVerificationError(
            "Stripe destination balance transaction is invalid"
        ) from error
    if (
        str(destination_balance.get("id") or "")
        != destination_balance_transaction
        or str(destination_balance.get("object") or "") != "balance_transaction"
        or str(destination_balance.get("status") or "") != "available"
        or str(destination_balance.get("currency") or "").upper() != currency
        or destination_amount_minor != amount_minor
        or net_minor <= 0
        or net_minor > destination_amount_minor
        or available_on > int(datetime.now(timezone.utc).timestamp())
        or str(destination_balance.get("source") or "") != destination_payment
    ):
        raise SettlementVerificationError(
            "Stripe destination balance is not available or linked"
        )
    received = datetime.fromtimestamp(created_epoch, timezone.utc)
    if received > datetime.now(timezone.utc):
        raise SettlementVerificationError("Stripe transfer timestamp is in the future")
    received_at = received.isoformat()
    canonical = {
        "id": transaction_id,
        "object": "transfer",
        "livemode": True,
        "amount": amount_minor,
        "currency": currency.casefold(),
        "created": created_epoch,
        "destination": destination,
        "destination_payment": destination_payment,
        "platform_balance_transaction": platform_balance_transaction,
        "destination_balance_transaction": destination_balance_transaction,
        "destination_net": net_minor,
        "destination_available_on": available_on,
        "metadata": required_metadata,
        "reversed": False,
        "amount_reversed": 0,
    }
    return VerifiedSettlement(
        provider="stripe",
        transaction_id=transaction_id,
        verification_url=f"https://dashboard.stripe.com/connect/transfers/{transaction_id}",
        verification_id=transaction_id,
        verified_at=_iso_now(),
        verification_source="stripe_transfer_api_v1",
        provider_payload_sha256=_digest(canonical),
        provider_status="succeeded",
        currency=currency,
        gross_amount=round(amount_minor / 100.0, 2),
        fee_amount=round((amount_minor - net_minor) / 100.0, 2),
        net_amount=round(net_minor / 100.0, 2),
        received_at=received_at,
        metadata={
            "livemode": True,
            "destination_account": destination,
            "destination_payment": destination_payment,
            "platform_balance_transaction": platform_balance_transaction,
            "destination_balance_transaction": destination_balance_transaction,
            "destination_available_on": available_on,
            "attribution": required_metadata,
        },
    )
