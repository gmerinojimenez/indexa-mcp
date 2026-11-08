# Security policy

## Design guarantees

- **Read-only.** The HTTP client only issues `GET` requests to a closed list of
  endpoints (`Endpoint` in `src/indexa_mcp/client.py`). No tool accepts a URL, a path or an
  HTTP verb. Account numbers are validated against `^[A-Z0-9]{4,16}$` before being
  placed in a path.
- **Fixed destination.** The base URL (`https://api.indexacapital.com`) is a constant and
  cannot be changed by environment variables. Redirects are never followed, so the
  token cannot be replayed to another host.
- **Token handling.** The token is read once from `INDEXA_API_TOKEN`, sent only in the
  `X-AUTH-TOKEN` header, and never logged or included in errors or tool output.
- **Local only.** stdio transport: no network port is opened.
- **Personal data minimised.** `indexa_list_accounts` and `indexa_get_account` use an
  allow-list, so ID document, email, address, holders and contract data are never
  returned to the model.
- **Bounded output.** Responses are capped at 5 MiB, lists are paginated (max 200 per
  page) and large time series are omitted.

## Limits you should know about

- The Indexa API token itself is **not** read-only: it can do whatever the API allows.
  The read-only guarantee comes from this server's code, not from the credential. Keep
  the token secret and revoke it in the Indexa web app if it leaks.
- Everything the tools return (balances, positions, transactions) is sent to the AI
  client you connect, and therefore to its provider.
- Free-text fields (e.g. transaction comments) are external data; a compromised source
  could try to inject instructions. The server instructions tell the model to treat them
  as data.

## Reporting a vulnerability

Please open a private security advisory on GitHub (Security > Report a vulnerability)
rather than a public issue.
