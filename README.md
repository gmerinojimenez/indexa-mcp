# indexa-mcp

A **local, read-only** [MCP](https://modelcontextprotocol.io) server to query your
[Indexa Capital](https://indexacapital.com) accounts from Claude or any other MCP client.

- Only sends `GET` requests to a closed list of endpoints. It cannot move money, make
  contributions or modify anything.
- Runs on your machine over **stdio** (it opens no network port).
- Never returns personal data (ID document, address, holders, contract).
- Unofficial project, not affiliated with Indexa Capital. Not financial advice.

## Tools

| Tool | Endpoint | Returns |
|---|---|---|
| `indexa_list_accounts` | `GET /users/me` | Your accounts (number, type, risk, status). Start here |
| `indexa_get_account` | `GET /accounts/{n}` | Account profile (type, risk, dates) |
| `indexa_get_portfolio` | `.../portfolio` | Total value, cash, positions, target vs. real weights |
| `indexa_get_performance` | `.../performance` | Returns, P&L, volatility, Sharpe, monthly history, benchmark |
| `indexa_get_fees` | `.../fees` | Fee breakdown |
| `indexa_get_cash_transactions` | `.../cash-transactions` | Contributions, withdrawals, fees (filterable, paginated) |
| `indexa_get_instrument_transactions` | `.../instrument-transactions` | Fund buys/sells (filterable, paginated) |
| `indexa_get_pending_transactions` | `.../pending-transactions` | Pending orders and requests |
| `indexa_get_fiscal_results` | `.../fiscal-results` | Realized/unrealized gains and losses per lot (paginated) |

List tools accept `date_from`, `date_to` (`YYYY-MM-DD`), `limit` (1-200, default 20) and
`offset`. All tools are advertised with `readOnlyHint: true`.

## Requirements

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- An Indexa API token: private area → **User settings → Applications**

## Install and configure

### Claude Code

```bash
claude mcp add indexa -e INDEXA_API_TOKEN="$INDEXA_API_TOKEN" -- \
  uvx --from git+https://github.com/gmerinojimenez/indexa-mcp indexa-mcp
```

### Claude Desktop

`~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "indexa": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/gmerinojimenez/indexa-mcp", "indexa-mcp"],
      "env": { "INDEXA_API_TOKEN": "your-token" }
    }
  }
}
```

### From a local clone

```bash
git clone https://github.com/gmerinojimenez/indexa-mcp && cd indexa-mcp
uv sync
claude mcp add indexa -e INDEXA_API_TOKEN="$INDEXA_API_TOKEN" -- \
  uv run --directory "$PWD" indexa-mcp
```

### Without keeping the token in plain text (macOS)

Store it in the Keychain:

```bash
security add-generic-password -s indexa-mcp -a "$USER" -w   # prompts for the token
```

and start the server through a wrapper that reads it on the fly:

```json
{
  "mcpServers": {
    "indexa": {
      "command": "sh",
      "args": ["-c", "INDEXA_API_TOKEN=$(security find-generic-password -s indexa-mcp -w) exec uvx --from git+https://github.com/gmerinojimenez/indexa-mcp indexa-mcp"]
    }
  }
}
```

## Example questions

- "How much do I have in Indexa and how is the portfolio split?"
- "What is my annualized return and how am I doing against the benchmark?"
- "List my contributions in 2025."
- "How much have I paid in fees?"
- "Do I have any pending orders?"

## Environment variables

| Variable | Description |
|---|---|
| `INDEXA_API_TOKEN` | **Required.** Indexa API token |
| `INDEXA_MCP_LOG_LEVEL` | Optional. Log level on stderr (default `WARNING`) |

## Security

Summary (details in [SECURITY.md](SECURITY.md)):

- Closed list of `GET` endpoints; the base URL is a constant that cannot be changed through
  the environment; redirects are never followed.
- The token only travels in the `X-AUTH-TOKEN` header and is never logged or shown in errors.
- Personal data is filtered with an allow-list; response sizes are capped.
- **Important:** the Indexa token itself is *not* read-only; the guarantee comes from this
  server's code. Whatever you query is sent to the AI client you use. If the token leaks,
  revoke it in Indexa.

## Development

```bash
uv sync
uv run pytest            # tests with mocked HTTP, they never touch the real API
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pip-audit --skip-editable
```

To try it with the official inspector:

```bash
npx @modelcontextprotocol/inspector uv run indexa-mcp
```

## License

MIT
