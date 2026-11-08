import json

import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError

from indexa_mcp.client import IndexaClient
from indexa_mcp.server import build_server

USER = {
    "document": "12345678Z",
    "email": "me@example.com",
    "has_any_funded_account": True,
    "accounts": [
        {
            "account_number": "ABC12345",
            "type": "mutual",
            "status": "active",
            "risk": 7,
            "postal_address": {"street": "Calle Falsa 123"},
            "main_holder_name": "Nombre Apellido",
            "provider": {"name": "Indexa", "description": "x"},
            "contract": {"signature": "..."},
            "new_unknown_field": "x",
        }
    ],
}
CASH = [
    {"date": "2026-01-10", "amount": 100.0, "comments": "a"},
    {"date": "2026-03-05", "amount": 50.0, "comments": "b"},
    {"date": "2026-02-01T10:00:00", "amount": 10.0, "comments": "c"},
    {"date": "2025-12-31", "amount": 1.0, "comments": "d"},
]
ROUTES = {
    "/users/me": USER,
    "/accounts/ABC12345": USER["accounts"][0],
    "/accounts/ABC12345/portfolio": {"portfolio": {"total_amount": 1.0}},
    "/accounts/ABC12345/performance": {
        "history": {"2026-01-31": 1.0},
        "portfolios": [1] * 5,
        "net_amounts": {"a": 1},
        "performance": {"period": []},
        "return": {"pl": 5.0, "index": {"a": 1}, "total_amounts": [1, 2]},
    },
    "/accounts/ABC12345/fees": {"tot": 0.1},
    "/accounts/ABC12345/cash-transactions": CASH,
    "/accounts/ABC12345/instrument-transactions": CASH,
    "/accounts/ABC12345/pending-transactions": {"orders": []},
    "/accounts/ABC12345/fiscal-results": {
        "fiscal_results": [
            {"date": "2026-01-01", "amount": 1},
            {"date": "2026-02-01", "amount": 2},
        ],
        "total_fiscal_results": [{"amount": 3}],
    },
}


@pytest.fixture
def server():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = ROUTES.get(request.url.path)
        return httpx.Response(200, json=body) if body is not None else httpx.Response(404)

    client = IndexaClient("tok", transport=httpx.MockTransport(handler))
    srv = build_server(client)
    srv.requests = requests  # type: ignore[attr-defined]
    return srv


async def call(server, name, **args):
    _, structured = await server.call_tool(name, args)
    return structured


async def test_all_tools_declared_read_only(server):
    tools = await server.list_tools()
    assert len(tools) == 9
    for tool in tools:
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False


async def test_no_write_like_tool_names(server):
    names = {t.name for t in await server.list_tools()}
    assert all(n.startswith("indexa_get_") or n == "indexa_list_accounts" for n in names)


async def test_list_accounts_strips_personal_data(server):
    result = await call(server, "indexa_list_accounts")
    dumped = json.dumps(result)
    for leaked in (
        "12345678Z",
        "me@example.com",
        "Calle Falsa",
        "Nombre",
        "signature",
        "new_unknown",
    ):
        assert leaked not in dumped
    assert result["accounts"][0]["account_number"] == "ABC12345"
    assert result["accounts"][0]["provider"] == "Indexa"


async def test_get_account_strips_personal_data(server):
    result = await call(server, "indexa_get_account", account_number="abc12345")
    assert "postal_address" not in result and "main_holder_name" not in result
    assert result["status"] == "active"


async def test_passthrough_tools(server):
    assert (await call(server, "indexa_get_portfolio", account_number="ABC12345"))["portfolio"][
        "total_amount"
    ] == 1.0
    assert (await call(server, "indexa_get_fees", account_number="ABC12345"))["tot"] == 0.1
    perf = await call(server, "indexa_get_performance", account_number="ABC12345")
    assert perf == {"history": {"2026-01-31": 1.0}, "return": {"pl": 5.0}}
    await call(server, "indexa_get_pending_transactions", account_number="ABC12345")
    fiscal = await call(server, "indexa_get_fiscal_results", account_number="ABC12345")
    assert [i["amount"] for i in fiscal["items"]] == [2, 1]
    assert fiscal["totals"] == [{"amount": 3}]
    assert {r.method for r in server.requests} == {"GET"}


async def test_transactions_filter_sort_paginate(server):
    result = await call(server, "indexa_get_cash_transactions", account_number="ABC12345")
    assert [i["comments"] for i in result["items"]] == ["b", "c", "a", "d"]
    assert result["total"] == 4 and result["next_offset"] is None

    result = await call(
        server,
        "indexa_get_cash_transactions",
        account_number="ABC12345",
        date_from="2026-01-01",
        date_to="2026-02-01",
        limit=1,
    )
    assert result["total"] == 2
    assert [i["comments"] for i in result["items"]] == ["c"]
    assert result["next_offset"] == 1

    result = await call(
        server,
        "indexa_get_instrument_transactions",
        account_number="ABC12345",
        date_from="2026-01-01",
        date_to="2026-02-01",
        limit=1,
        offset=1,
    )
    assert [i["comments"] for i in result["items"]] == ["a"]
    assert result["next_offset"] is None


@pytest.mark.parametrize(
    "args",
    [
        {"date_from": "yesterday"},
        {"date_to": "2026-13-45"},
        {"date_from": "2026-05-01", "date_to": "2026-01-01"},
        {"limit": 0},
        {"limit": 201},
        {"offset": -1},
    ],
)
async def test_bad_pagination_args_rejected(server, args):
    with pytest.raises(ToolError):
        await call(server, "indexa_get_cash_transactions", account_number="ABC12345", **args)


async def test_bad_account_number_never_hits_network(server):
    with pytest.raises(ToolError):
        await call(server, "indexa_get_portfolio", account_number="../users/me")
    assert server.requests == []


async def test_api_error_surfaces_safe_message(server):
    with pytest.raises(ToolError, match="404"):
        await call(server, "indexa_get_portfolio", account_number="ZZZ99999")


async def test_instrument_detail_is_slimmed():
    big = {
        "date": "2026-01-01",
        "instrument": {"name": "Fund", "isin_code": "X", "noise": "n" * 50},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[big])

    srv = build_server(IndexaClient("tok", transport=httpx.MockTransport(handler)))
    result = await call(srv, "indexa_get_instrument_transactions", account_number="ABC12345")
    assert result["items"][0]["instrument"] == {"name": "Fund", "isin_code": "X"}
