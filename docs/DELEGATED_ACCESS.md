# Delegated row access for a dashboard

[Documentation](README.md)

A backend application whose users sign in with Microsoft Entra ID can read and edit AppFlowy database rows as each signed-in user. AppFlowy applies that user's own workspace and database permissions, records the user as the editor, and can name the backend in the audit log. The backend holds no AppFlowy password or long-lived AppFlowy credential.

The backend sends the user's Entra access token to GoTrue and receives an AppFlowy token that lasts at most five minutes and works on two operations only:

| Operation | Scope |
| --- | --- |
| `GET /api/workspace/{workspace_id}/database/{database_id}/row/detail?ids={row_id}` | `data.read` |
| `PATCH /api/workspace/{workspace_id}/database/{database_id}/row/{row_id}` | `data.write` |

Every other AppFlowy API rejects this token. Delegated access is off until you complete the steps below.

## Before you begin

- Run a GoTrue image and an AppFlowy Cloud image that both include delegated access. With an older GoTrue the exchange fails with `unsupported_grant_type`; with an older Cloud the row API answers 401.
- Serve AppFlowy over HTTPS. Cloud refuses to start with a delegated-access issuer that is not an HTTPS URL. It accepts a loopback HTTP address for a local trial.
- Add the tenant's OIDC provider in the Admin console, as described in [OIDC](OIDC.md), with the tenant-specific issuer `https://login.microsoftonline.com/<tenant-id>/v2.0`. Note its identifier, which looks like `custom:entra`.
- Each user must have signed in to AppFlowy through that provider at least once. That sign-in links the AppFlowy account to the user's Entra object ID. An account that only shares an email address, or that was only provisioned by SCIM, cannot be used.
- Keep the GoTrue and AppFlowy Cloud hosts on synchronized clocks. Cloud refuses a token that GoTrue's clock dates more than five seconds ahead of its own.

This flow has been tested with tokens in Entra's documented format from a test issuer. Confirm it in your tenant before you depend on it.

## Step 1: Register the API and the dashboard in Entra

1. Register an application for the AppFlowy row API. Expose two delegated scopes named `data.read` and `data.write`, and set its access token version to 2 (`requestedAccessTokenVersion: 2` in the manifest). Its application ID is the **audience** used below.
2. In the dashboard's own Entra application, add those scopes as delegated API permissions and grant consent. Its application ID is the **Entra client ID** used below.
3. In the dashboard backend, acquire an access token for the row API on behalf of the signed-in user, for example with Microsoft's [On-Behalf-Of flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-on-behalf-of-flow). A token for Microsoft Graph has the wrong audience and is rejected.

## Step 2: Create the signing key

GoTrue signs delegated tokens with its own ES256 key, separate from the login secret. Create one on a trusted machine with Python and the `cryptography` package:

```python
import base64, json, secrets
from cryptography.hazmat.primitives.asymmetric import ec

numbers = ec.generate_private_key(ec.SECP256R1()).private_numbers()
b64 = lambda value: base64.urlsafe_b64encode(value.to_bytes(32, "big")).rstrip(b"=").decode()
print(json.dumps([{
    "kty": "EC", "crv": "P-256", "alg": "ES256", "kid": "exchange-" + secrets.token_hex(4),
    "key_ops": ["sign"], "x": b64(numbers.public_numbers.x), "y": b64(numbers.public_numbers.y),
    "d": b64(numbers.private_value),
}]))
```

The output is a private key. Store it like `GOTRUE_JWT_SECRET`.

## Step 3: Enable the exchange in GoTrue

Add the settings to the root `.env` and restart GoTrue. There is no separate switch: these settings turn the exchange on, and GoTrue refuses to start when only some of them are set. Its log then says `GoTrue could not load its configuration` and names the setting. Leave the client list out for now: with none configured, GoTrue refuses every exchange and lets an administrator register the first backend.

```dotenv
GOTRUE_TOKEN_EXCHANGE_TENANT_ID=<lowercase Entra tenant UUID>
GOTRUE_TOKEN_EXCHANGE_PROVIDER=custom:entra
GOTRUE_TOKEN_EXCHANGE_SIGNING_KEYS='<output of step 2>'
```

```bash
docker compose up -d gotrue
```

Docker Swarm reads the same settings from the environment you deploy the stack with. With the Helm chart, set the same values under `gotrue.config.tokenExchange` (`tenantId`, `provider`, `signingKeys`). The chart stores the key in the GoTrue secret.

## Step 4: Register the backend

Sign in as the GoTrue administrator and register the backend as a confidential client. GoTrue requires a redirect URI at registration; use an HTTPS address the dashboard owns.

```bash
ADMIN_TOKEN=$(curl --silent --request POST 'https://your-domain/gotrue/token?grant_type=password' \
  --header 'Content-Type: application/json' \
  --data '{"email":"<GOTRUE_ADMIN_EMAIL>","password":"<GOTRUE_ADMIN_PASSWORD>"}' | jq -r .access_token)

curl --silent --request POST 'https://your-domain/gotrue/admin/oauth/clients' \
  --header "Authorization: Bearer $ADMIN_TOKEN" --header 'Content-Type: application/json' \
  --data '{"client_name":"Dashboard","redirect_uris":["https://dashboard.example.com/callback"],"token_endpoint_auth_method":"client_secret_basic"}'
```

The response contains `client_id` and `client_secret`. The secret is shown once. Give both to the dashboard backend.

Leave `GOTRUE_OAUTH_SERVER_ENABLED` unset. Delegated access does not use GoTrue's OAuth authorization endpoints, and enabling them lets a registered client request ordinary login tokens.

## Step 5: Allow the backend and turn on the row API

Name the registered client in GoTrue's policy and tell AppFlowy Cloud which tokens to accept:

```dotenv
GOTRUE_TOKEN_EXCHANGE_CLIENTS='{"<client_id from step 4>":{"entra_client_id":"<dashboard Entra application ID>","audience":"<row API Entra application ID>","scopes":["data.read","data.write"]}}'
APPFLOWY_TOKEN_EXCHANGE_ISSUER=${API_EXTERNAL_URL}
APPFLOWY_TOKEN_EXCHANGE_AUDIENCE=<row API Entra application ID>
```

```bash
docker compose up -d gotrue appflowy_cloud
```

Cloud starts with both of its settings empty or both set. The issuer must equal `API_EXTERNAL_URL` exactly.

With the Helm chart, set `gotrue.config.tokenExchange.clients` to the same mapping and `appflowy-cloud.config.tokenExchangeAudience` to the audience. The chart supplies the issuer.

## Step 6: Call the API from the backend

Exchange the user's Entra token with HTTP Basic authentication, using the client ID and secret from step 4:

```bash
curl --silent --user "$CLIENT_ID:$CLIENT_SECRET" 'https://your-domain/gotrue/token' \
  --data-urlencode 'grant_type=urn:ietf:params:oauth:grant-type:token-exchange' \
  --data-urlencode 'subject_token_type=urn:ietf:params:oauth:token-type:access_token' \
  --data-urlencode "subject_token=$ENTRA_ACCESS_TOKEN" \
  --data-urlencode 'scope=data.read data.write'
```

Send the returned `access_token` as `Authorization: Bearer <token>` to the two operations above. Their request and response bodies are those of the ordinary row API in the [OpenAPI reference](OPENAPI.md).

- Keep the token on the server and reuse it for that user until `expires_in`. Then exchange a current Entra token again. There is no refresh token.
- Check the `code` field of a 200 response as well as the HTTP status. A user without permission on the database gets HTTP 200 with code `1012`.
- By default GoTrue allows each backend 150 exchanges per five minutes, and 8 exchanges in progress at once across all backends. One token per active user uses one exchange every five minutes. Raise `GOTRUE_TOKEN_EXCHANGE_RATE_LIMIT` and `GOTRUE_TOKEN_EXCHANGE_MAX_CONCURRENT` for a larger audience.

## What a refusal means

| Response | Cause |
| --- | --- |
| GoTrue does not start; its log says `GoTrue could not load its configuration` | A setting is missing or malformed. The log names a delegated access setting, for example `token exchange requires GOTRUE_TOKEN_EXCHANGE_SIGNING_KEYS`. For any other setting the reason is not logged, because it can quote the setting's value: run `docker compose run --rm gotrue ./auth migrate` to read it. |
| Exchange: `invalid_client` | Wrong client ID or secret, or the client is missing from `GOTRUE_TOKEN_EXCHANGE_CLIENTS`. |
| Exchange: `invalid_grant` | The Entra token is expired, is for another tenant, audience or dashboard, or its user has no AppFlowy account linked through the OIDC provider. |
| Exchange: `invalid_scope` | The requested scope is not allowed for the client or absent from the Entra token. |
| Row API: 401 with `WWW-Authenticate: Bearer error="invalid_token"` | The header's `error_description` names the cause when GoTrue issued the token: wrong issuer or audience setting in Cloud, an expired token, clocks out of step, or a session that was revoked or whose user is deactivated. Request a new token; if the user is deactivated, the exchange answers `invalid_grant`. |
| Row API: 403 with `error="insufficient_scope"` | The token lacks `data.read` for the read or `data.write` for the edit. |
| Row API: 503 with `Retry-After` | Cloud cannot read GoTrue's signing keys and holds none it still trusts. |
| Row API: 200 with code `1012` | The user's own AppFlowy permissions do not allow the operation. |

AppFlowy Cloud logs the cause of each refused token that GoTrue issued as an `INFO` line, `Refused a delegated access token`. When it cannot read GoTrue's signing keys it logs an `ERROR` line, `Unable to refresh delegated signing keys`.

## Operate it

- **Remove a user's access.** Deactivate the user in the Admin console or remove their access to the workspace. Cloud checks the user and the session on every request.
- **Remove a backend.** Delete its entry from `GOTRUE_TOKEN_EXCHANGE_CLIENTS` and restart GoTrue. Tokens already issued expire within five minutes. With the list empty, GoTrue issues no tokens at all.
- **Turn it off.** Remove the `GOTRUE_TOKEN_EXCHANGE_*` tenant, provider, client and signing-key settings and both `APPFLOWY_TOKEN_EXCHANGE_*` settings, then restart GoTrue and AppFlowy Cloud.
- **Rotate the signing key.** Add the new private key to `GOTRUE_TOKEN_EXCHANGE_SIGNING_KEYS` with `"key_ops":["sign"]`, keep the old key's public part (`kty`, `crv`, `alg`, `kid`, `x`, `y`) with `"key_ops":["verify"]`, and restart GoTrue. Remove the old key after five minutes. Cloud fetches a key it has not seen within a few seconds.
- **GoTrue restarts.** Cloud keeps accepting tokens signed by the keys it last read for up to five minutes while GoTrue is unreachable.
- **Audit.** With [audit logging](AUDIT.md) enabled, each delegated read and edit is recorded as `database.rows.read` or `database.row.updated` with the user, the backend's client ID, the exchange session, the rows read or the fields edited, and the backend's address. A refused scope or permission is recorded as `security.delegated_access.denied`. Each delegated read writes one audit record, so have the backend reuse what it has read where it can.
