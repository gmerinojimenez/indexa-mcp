import httpx
import pytest

from indexa_mcp.client import (
    BASE_URL,
    Endpoint,
    IndexaClient,
    IndexaError,
    normalize_account,
    validate_token,
)

TOKEN = "secret-token-value"


def make_client(handler):
    return IndexaClient(TOKEN, transport=httpx.MockTransport(handler))


async def test_sends_only_get_with_auth_header():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    client = make_client(handler)
    assert await client.get(Endpoint.PORTFOLIO, "abc12345") == {"ok": True}
    await client.aclose()
    (request,) = seen
    assert request.method == "GET"
    assert str(request.url) == f"{BASE_URL}/accounts/ABC12345/portfolio"
    assert request.headers["X-AUTH-TOKEN"] == TOKEN


async def test_every_endpoint_is_get_and_under_base_url():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])

    client = make_client(handler)
    for endpoint in Endpoint:
        await client.get(endpoint, "ABC12345" if endpoint.needs_account else None)
    assert len(seen) == len(Endpoint)
    assert {r.method for r in seen} == {"GET"}
    assert all(str(r.url).startswith(BASE_URL + "/") for r in seen)


@pytest.mark.parametrize(
    "bad", ["", "  ", "../x", "ABC/portfolio", "AB", "A" * 17, "ABC 123", "ABC?x=1", "ñandú12"]
)
def test_rejects_bad_account_numbers(bad):
    with pytest.raises(IndexaError):
        normalize_account(bad)


async def test_account_required_for_account_endpoints():
    client = make_client(lambda r: httpx.Response(200, json={}))
    with pytest.raises(IndexaError):
        await client.get(Endpoint.ACCOUNT)


async def test_redirects_are_not_followed():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        return httpx.Response(302, headers={"Location": "https://evil.example/steal"})

    client = make_client(handler)
    with pytest.raises(IndexaError) as exc:
        await client.get(Endpoint.USER)
    assert calls == ["api.indexacapital.com"]
    assert "evil" not in str(exc.value)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 423, 429, 500, 503])
async def test_errors_do_not_leak_token_or_body(status):
    client = make_client(
        lambda r: httpx.Response(status, text=f"debug: token={TOKEN} internal-detail")
    )
    with pytest.raises(IndexaError) as exc:
        await client.get(Endpoint.USER)
    assert TOKEN not in str(exc.value)
    assert "internal-detail" not in str(exc.value)
    assert str(status) in str(exc.value)


async def test_network_error_is_sanitized():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"boom {TOKEN}", request=request)

    client = make_client(handler)
    with pytest.raises(IndexaError) as exc:
        await client.get(Endpoint.USER)
    assert TOKEN not in str(exc.value)


async def test_timeout_is_reported():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = make_client(handler)
    with pytest.raises(IndexaError, match="timed out"):
        await client.get(Endpoint.USER)


async def test_oversized_response_is_rejected(monkeypatch):
    monkeypatch.setattr("indexa_mcp.client.MAX_RESPONSE_BYTES", 100)
    client = make_client(lambda r: httpx.Response(200, content=b"[" + b"1," * 200 + b"1]"))
    with pytest.raises(IndexaError, match="size limit"):
        await client.get(Endpoint.USER)


async def test_invalid_json_is_rejected():
    client = make_client(lambda r: httpx.Response(200, content=b"<html>"))
    with pytest.raises(IndexaError, match="not valid JSON"):
        await client.get(Endpoint.USER)


@pytest.mark.parametrize("token", [None, "", "   ", "a b", "tok\nen", "tökén"])
def test_validate_token_rejects_bad(token):
    with pytest.raises(IndexaError) as exc:
        validate_token(token)
    if token and token.strip():
        assert token not in str(exc.value)


def test_validate_token_strips():
    assert validate_token("  abc.def  ") == "abc.def"
