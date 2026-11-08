"""Minimal read-only HTTP client for the Indexa Capital API.

Security properties, enforced here and nowhere else:

* Only ``GET`` is ever sent. The client has no method that takes an HTTP verb.
* Only the endpoints in :class:`Endpoint` are reachable. Callers pass an
  endpoint plus an already-validated account number; they never pass a path.
* The base URL is a constant (HTTPS). It cannot be overridden through the
  environment, so the token cannot be redirected to another host.
* Redirects are never followed, so the token is not replayed to a host named by
  a 30x response.
* Responses are streamed and capped in size.
* Error messages never contain the token, request headers or response bodies.
"""

from __future__ import annotations

import enum
import json
import re
from typing import Any

import httpx

BASE_URL = "https://api.indexacapital.com"
AUTH_HEADER = "X-AUTH-TOKEN"
REQUEST_TIMEOUT_SECONDS = 20.0
MAX_RESPONSE_BYTES = 5 * 1024 * 1024

_ACCOUNT_RE = re.compile(r"^[A-Z0-9]{4,16}$")


class IndexaError(Exception):
    """Error whose message is safe to show to the model and the user."""


class Endpoint(enum.Enum):
    """Closed whitelist of readable endpoints (all ``GET``)."""

    USER = "/users/me"
    ACCOUNT = "/accounts/{account}"
    PORTFOLIO = "/accounts/{account}/portfolio"
    PERFORMANCE = "/accounts/{account}/performance"
    FEES = "/accounts/{account}/fees"
    CASH_TRANSACTIONS = "/accounts/{account}/cash-transactions"
    INSTRUMENT_TRANSACTIONS = "/accounts/{account}/instrument-transactions"
    PENDING_TRANSACTIONS = "/accounts/{account}/pending-transactions"
    FISCAL_RESULTS = "/accounts/{account}/fiscal-results"

    @property
    def needs_account(self) -> bool:
        return "{account}" in self.value


def normalize_account(account: str) -> str:
    """Return the upper-cased account number or raise :class:`IndexaError`."""
    code = account.strip().upper() if isinstance(account, str) else ""
    if not _ACCOUNT_RE.fullmatch(code):
        raise IndexaError(
            "Invalid account number: expected 4-16 letters/digits (e.g. ABC12345). "
            "Use indexa_list_accounts to see yours."
        )
    return code


def validate_token(token: str | None) -> str:
    """Return a clean token or raise :class:`IndexaError` (never echoes it)."""
    if token is None or not token.strip():
        raise IndexaError(
            "INDEXA_API_TOKEN is not set. Generate a token in the Indexa web app "
            "(User settings > Applications) and export it as INDEXA_API_TOKEN."
        )
    token = token.strip()
    if not token.isascii() or any(c.isspace() or ord(c) < 33 for c in token):
        raise IndexaError("INDEXA_API_TOKEN contains invalid characters.")
    return token


_STATUS_MESSAGES = {
    400: "Indexa rejected the request (HTTP 400).",
    401: "Indexa rejected the token (HTTP 401). It may be invalid or revoked.",
    403: "Indexa denied access (HTTP 403). The token may lack permission.",
    404: "Resource not found (HTTP 404). Check the account number.",
    423: "The account is locked (HTTP 423).",
    429: "Indexa rate limit reached (HTTP 429). Wait and retry.",
}


class IndexaClient:
    """Read-only client. Create once and reuse; close with :meth:`aclose`."""

    def __init__(self, token: str, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._http = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={AUTH_HEADER: validate_token(token), "Accept": "application/json"},
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=False,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get(self, endpoint: Endpoint, account: str | None = None) -> Any:
        """GET a whitelisted endpoint and return the decoded JSON body."""
        if endpoint.needs_account:
            if account is None:
                raise IndexaError("This endpoint requires an account number.")
            path = endpoint.value.format(account=normalize_account(account))
        else:
            path = endpoint.value

        try:
            async with self._http.stream("GET", path) as response:
                if response.status_code != 200:
                    message = _STATUS_MESSAGES.get(
                        response.status_code,
                        f"Indexa returned HTTP {response.status_code}.",
                    )
                    raise IndexaError(message)
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise IndexaError("Indexa response exceeded the size limit.")
        except httpx.TimeoutException:
            raise IndexaError("Request to Indexa timed out.") from None
        except httpx.HTTPError:
            raise IndexaError("Could not reach the Indexa API.") from None

        try:
            return json.loads(body)
        except ValueError:
            raise IndexaError("Indexa returned a response that is not valid JSON.") from None
