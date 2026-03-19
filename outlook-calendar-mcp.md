# Outlook Calendar MCP — Development Notes
*2026-03-19*

## What We Confirmed

- Microsoft Graph API is live and accessible at `https://graph.microsoft.com`
- Ohio University Azure AD tenant is active — OU credentials authenticate successfully
- [Graph Explorer](https://developer.microsoft.com/en-us/graph/graph-explorer) completes the full OAuth flow with OU credentials
- Access token **and** refresh token are obtainable directly from the Graph Explorer UI
- Calendar read/write endpoints respond correctly with a valid token

---

## Goal

Build an MCP (Model Context Protocol) server that connects Claude (Cowork) to Outlook Calendar via the Microsoft Graph API, enabling natural language calendar management — e.g. "add office hours Tuesday 2–4pm recurring weekly."

---

## Key Endpoints

```
GET    https://graph.microsoft.com/v1.0/me/calendars
GET    https://graph.microsoft.com/v1.0/me/calendarView?startDateTime=...&endDateTime=...
POST   https://graph.microsoft.com/v1.0/me/events
PATCH  https://graph.microsoft.com/v1.0/me/events/{id}
DELETE https://graph.microsoft.com/v1.0/me/events/{id}
```

---

## Authentication

**Short-term (no IT involvement needed):**
- Copy access token + refresh token from Graph Explorer's "Access token" tab
- Store in a local credentials file (gitignored)
- Access tokens expire in ~60–90 minutes; refresh token can be exchanged for new access tokens automatically
- Graph Explorer requests `offline_access` scope by default, so refresh tokens are available

**Long-term:**
- Proper Azure AD app registration with `client_id` / `client_secret` and OAuth redirect URI
- May need OU IT involvement, or use a personal Azure subscription that authenticates via OU account

---

## What the MCP Needs

1. OAuth token handler — reads `outlook_credentials.json`, auto-renews via refresh token
2. Tool definitions: `create_event`, `list_events`, `update_event`, `delete_event`
3. Runs as a local MCP server that Cowork connects to (Python, using `mcp` SDK or `fastmcp`)
4. Credentials file (gitignored): `outlook_credentials.json`

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "expires_at": "2026-03-19T15:00:00"
}
```

---

## Next Steps

1. Grab `access_token` and `refresh_token` from Graph Explorer
2. Build a simple Python MCP server (`fastmcp` or `mcp` SDK)
3. Test a `POST /me/events` with a hardcoded event to confirm write access
4. Wire up to Cowork as a local MCP connection
5. Add natural language parsing so Claude can interpret scheduling requests
6. Eventually: proper app registration in Azure AD for a sustainable auth flow

---

## References

- [Graph Explorer](https://developer.microsoft.com/en-us/graph/graph-explorer)
- [Graph API Calendar docs](https://learn.microsoft.com/en-us/graph/api/resources/calendar)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [OAuth 2.0 token refresh flow](https://learn.microsoft.com/en-us/azure/active-directory/develop/v2-oauth2-auth-code-flow)
- [fastmcp](https://github.com/jlowin/fastmcp)
