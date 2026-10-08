# AppFlowy OpenAPI and Swagger UI

Open `https://your-domain/api/docs` to browse AppFlowy's business APIs and send requests to your own
installation through Swagger UI. With the default local Docker Compose setup, open
[http://localhost/api/docs](http://localhost/api/docs).

## Before you begin

- Run a self-host AppFlowy Cloud image containing the Swagger integration. Older images do not
  include the page. Custom Cloud builds must enable the `self-host-af` Cargo feature.
- Start your deployment using the [Docker Compose guide](docker-compose.md). Use your deployment's
  domain, scheme, and published port in place of the examples in this guide.
- Sign in to AppFlowy with a user who can access the workspace you want to test.

Swagger UI and the OpenAPI document are bundled inside the `appflowy_cloud` image. They are enabled
automatically for self-host builds; no separate Swagger image, account, or environment flag is
needed. All UI assets are served by your installation.

`APPFLOWY_ENABLE_SWAGGER` is no longer used. Remove it from older `.env` files or Compose overrides;
setting it to `false` does not disable Swagger.

## Open the API reference

| Resource | URL |
| --- | --- |
| Interactive Swagger UI | `https://your-domain/api/docs` |
| OpenAPI JSON document | `https://your-domain/api/docs/openapi.json` |

The bundled [Nginx configuration](../docker/nginx/nginx.conf) already forwards `/api` to Cloud,
including `/api/docs` and its subpaths. If you use a custom reverse proxy, preserve these paths and
forward them to the same Cloud service as your other API requests.

Expand an API group or use the filter to find an operation. Leave the **Servers** selection on
**This AppFlowy installation** so requests use the same domain as the documentation page.

The reference covers business operations such as workspaces, pages, databases, files, sharing,
publishing, search, and AI. Server administration, SCIM provisioning, and license/billing management
are excluded. Available features still depend on your installation's configuration and license.

## Authorize requests

Browsing the reference does not require an API token. To execute authenticated operations, use a
GoTrue **user access token** issued by this installation:

1. Sign in to AppFlowy Web. In your browser's developer tools, open **Network**, then open or reload
   a workspace.
2. Select an authenticated request to your installation's `/api/` routes. Under request headers,
   copy the token from `Authorization: Bearer <token>` without the `Bearer ` prefix.
3. In Swagger UI, click **Authorize**, paste the token into **bearerAuth**, click **Authorize**,
   then close the dialog.

For an account with email/password sign-in, you can also obtain `access_token` from GoTrue:

```bash
curl --request POST 'https://your-domain/gotrue/token?grant_type=password' \
  --header 'Content-Type: application/json' \
  --data '{"email":"your-email","password":"your-password"}'
```

Use the `access_token` field from the response. For SSO or other sign-in methods, use your signed-in
browser session as described above. The JWT signing secret, an admin service key, and an MCP token
are not user access tokens. Keep your token private; it grants your account's permissions.

Swagger retains authorization in the current tab's memory. Refreshing the page clears it. If the
token expires, obtain a new one and authorize again.

## Test your first API

1. Expand **Workspaces → List workspace** (`GET /api/workspace`).
2. Click **Try it out**, then **Execute**.
3. Inspect **Server response**. For responses using AppFlowy's JSON envelope, `code: 0` means
   success; HTTP `200` alone does not guarantee business success.
4. Copy a returned workspace ID into another operation's `workspace_id` parameter. Replace example
   page, database, and object IDs with real IDs from that workspace.

Requests run with your user's normal permissions. Use a test workspace for write operations:
creating, updating, or deleting through Swagger changes the actual installation. An account created
directly through GoTrue must first initialize its AppFlowy profile; opening AppFlowy Web completes
the normal sign-in flow before you test workspace APIs.

Some operations require additional setup, such as an AI provider, an existing page, or a binary
file in the documented format. WebSocket and legacy GET-with-body operations are listed with
**Try it out** disabled because the browser cannot execute those transports.

## Download and update the document

Download your installation's OpenAPI document for use in another API client or code generator:

```bash
curl --fail --output appflowy-openapi.json 'https://your-domain/api/docs/openapi.json'
```

The document belongs to the running Cloud release. When upgrading, select the intended
`APPFLOWY_CLOUD_VERSION` in the root `.env`, follow that release's upgrade instructions and companion
service requirements, then pull and recreate Cloud. From the repository root, the Cloud steps are:

```bash
docker compose pull appflowy_cloud
docker compose up -d appflowy_cloud
```

Refresh `/api/docs` afterward to load the updated reference. No separate Swagger deployment is
needed. New APIs appear when the installed Cloud release includes them in its bundled document;
refreshing the page alone does not upgrade Cloud.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| `/api/docs` returns `404` | Confirm the running image includes Swagger support and is a self-host build. Verify that your proxy forwards `/api/docs` and its subpaths to Cloud. |
| The page is blank or cannot load the definition | Open `/api/docs/openapi.json` directly; it should return JSON. Check that the proxy also forwards the UI JavaScript and CSS under `/api/docs/`. |
| A request returns `401` | Authorize with a current user access token from this installation. Refreshing Swagger clears the token. |
| A request returns `403` or a nonzero application `code` | Read the response message and check workspace membership, permissions, feature configuration, and required input IDs. |
| A request reports a network or CORS error | Use **This AppFlowy installation**. A custom server must be reachable by your browser and permit the Swagger page's origin; an HTTPS page needs an HTTPS API. |
| Documentation still looks old after an upgrade | Confirm Cloud was recreated with the intended image, refresh the page, and check whether an external proxy or CDN is serving cached assets or JSON. |
