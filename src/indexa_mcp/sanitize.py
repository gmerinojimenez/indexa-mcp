"""Allow-list projections that keep personal data away from the model.

``/users/me`` and ``/accounts/{id}`` return national ID numbers, postal
addresses, holder names, contract and signature details and more. None of that is
needed to answer questions about investments, so we project the responses onto
an explicit allow-list instead of trying to block fields one by one: a field
Indexa adds in the future is dropped by default.
"""

from __future__ import annotations

from typing import Any

_ACCOUNT_FIELDS = (
    "account_number",
    "type",
    "account_type",
    "status",
    "currency",
    "risk",
    "expected_return",
    "style",
    "size",
    "funding",
    "funded_at",
    "created_at",
    "activated_at",
    "cancelled_at",
    "reconciled_until",
    "fee_free_amount",
    "num_holders",
)


def _pick(source: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {key: source[key] for key in fields if key in source}


def account_summary(account: Any) -> dict[str, Any]:
    if not isinstance(account, dict):
        return {}
    summary = _pick(account, _ACCOUNT_FIELDS)
    provider = account.get("provider")
    if isinstance(provider, dict) and "name" in provider:
        summary["provider"] = provider["name"]
    return summary


def user_summary(user: Any) -> dict[str, Any]:
    if not isinstance(user, dict):
        return {"accounts": []}
    accounts = user.get("accounts")
    return {
        "has_any_funded_account": user.get("has_any_funded_account"),
        "accounts": [account_summary(a) for a in accounts] if isinstance(accounts, list) else [],
    }


# Daily/weekly time series that make /performance ~160 KB. The summary keeps the
# figures people actually ask about (returns, volatility, history by month...).
_PERFORMANCE_SERIES = ("portfolios", "net_amounts", "cash_returns", "performance")


def performance_summary(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    summary = {k: v for k, v in data.items() if k not in _PERFORMANCE_SERIES}
    returns = summary.get("return")
    if isinstance(returns, dict):
        summary["return"] = {k: v for k, v in returns.items() if not isinstance(v, dict | list)}
    return summary


_INSTRUMENT_FIELDS = ("name", "isin_code", "identifier", "asset_class", "description")


def slim_record(item: Any) -> Any:
    """Shrink the verbose ``instrument`` object inside a transaction/lot record."""
    if isinstance(item, dict) and isinstance(item.get("instrument"), dict):
        return {**item, "instrument": _pick(item["instrument"], _INSTRUMENT_FIELDS)}
    return item
