# Docker Compose

[Documentation](README.md)

For CPU, RAM, and storage guidance, see [Hardware requirements and sizing](HARDWARE_SIZING.md).
The [single-server profiles](HARDWARE_SIZING.md#single-server-sizing) provide example hardware sizes
for the default all-in-one Compose installation.

With Docker and Docker Compose **2.30 or newer** installed, first copy the environment template from the repository root:

```bash
cp deploy.env .env
```

Check the installed plugin with `docker compose version --short`. The configuration uses optional,
raw environment files for persistent restore selections, which require Compose 2.30 or newer.
Older plugins can reject the base file even while Backup is disabled. The CI tooling checks this
minimum before rendering any deployment.

Edit `.env` to set your domain, HTTPS/WebSocket schemes, credentials, and optional email or AI settings. Replace the example passwords and JWT secret before exposing the deployment publicly. Compose [loads the root `.env` automatically](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/), and Git ignores this file.

Compose uses the public `appflowyinc/appflowy_cloud` and `appflowyinc/appflowy_worker` images. Both provide AMD64 and ARM64 builds, and Docker selects the image architecture for your host automatically.

Nginx configuration and certificates remain in [`docker/nginx`](../docker/nginx). For HTTPS, replace the bundled development certificate and key in `docker/nginx/ssl/` with your deployment's certificates.

Start the services from the repository root:

```bash
docker compose up -d
```

With the default localhost settings, open [AppFlowy Web](http://localhost) or the [Admin console](http://localhost/console). The template creates the admin account `admin@example.com` with password `password`.

If upgrading an installation previously started from `docker/`, move its existing `.env` to the repository root and retain its Compose project name. For the old default, add `COMPOSE_PROJECT_NAME=docker` to `.env`; if you used a custom project name, keep that value. This reuses the existing named data volumes and the default network. Containers whose definition changed are recreated in place: `nginx` and `appflowy_cloud` leave the old `cloud_proxy` network, and `minio`, `appflowy_cloud`, and `appflowy_worker` move to new image references. Unchanged service definitions are reused. The old `<project>_cloud_proxy` network is left behind and can be removed with `docker network rm` after the upgrade.

## Redis

The bundled Redis service uses Redis's default `maxmemory=0`: no configured memory cap.
AppFlowy permits background task publication in this mode, so indexing and other queue-backed
features do not require an extra Redis memory setting. Host or container memory limits still apply.

If you explicitly configure a positive `maxmemory`, AppFlowy applies its percentage-based memory
admission check (80% by default). Use `noeviction` to retain queue and collaboration keys, and
allow `INFO memory` so the publisher can observe the configured limit. An unavailable memory
sample or actual Redis write refusal still defers publication. Changes to the sampled limit or
usage can take up to five minutes to become visible.

The same behavior applies to external Redis. AppFlowy honors the server's configuration and does
not change it at runtime.

## Backup

Backup is optional. Use Docker Compose **2.30 or newer**, set this value in the root `.env`,
and start the deployment:

```dotenv
APPFLOWY_BACKUP_PROFILE=backup
```

```bash
docker compose up -d
```

Open **Tools → Backup** in the Admin console. Cloud discovers the ready service automatically;
there is no additional Admin setting or `APPFLOWY_BACKUP_ENABLED` flag.
See the [Backup guide](BACKUP.md) for creating backups, exports, schedules, and restores.

The environment template selects [docker-compose.backup.yml](../docker-compose.backup.yml)
automatically. Keep its derived `COMPOSE_PROFILES`, `COMPOSE_PATH_SEPARATOR`, and `COMPOSE_FILE`
settings from [deploy.env](../deploy.env). When upgrading an older `.env`, copy those three
settings from the template without replacing your existing credentials or project name.
Using `--profile backup` alone does not select the supporting file.

### What startup prepares

The supplied configuration reuses the installation's database, Redis, and object-storage
connections. Backup creates a separate private artifact bucket, prepares its persistent work
and restore directories, and discovers the current Compose project. Its short startup step
configures Docker socket access, then runs the supervisor, worker, and recovery coordinator as
the image's `postgres` user. If the host socket is writable only by root, a supervised internal
bridge provides access; the host socket's ownership and permissions are unchanged. There is no manual
Docker group ID, `runner.env`, pgBackRest configuration, or stanza initialization step for new
online backups. The live PostgreSQL image and archive settings are unchanged.

With Backup enabled, Search starts as UID/GID `999`, matching Backup's `postgres` user.
Before Search starts, its entrypoint migrates the shared cache's ownership while retaining
file permissions. This lets Backup capture private LMDB data and use its reader lockfile.

The Backup coordinator has Docker administration access so it can pause and restart application
services during restore. The supplied writer list in
[docker-compose.backup.yml](../docker-compose.backup.yml) covers Cloud, GoTrue, Worker, Search,
AI, and [MCP](#ai-apps-mcp); restore stops them and switches each to the restored bucket and Redis
database. If you add connectors or other services that write to this installation, extend the
Backup service's `APPFLOWY_BACKUP_COMPOSE_WRITERS` environment setting through a Compose override
before using restore. Every listed service needs a container, and a running application writer
that is missing from the list stops restore.

Use the Backup image published with your Cloud release. The
[release-image workflow](RELEASE_IMAGES.md) proposes its exact version and digest when
Backup is published. Once pinned, that Compose image reference determines the version;
use an explicit Compose override for qualification builds. Its PostgreSQL tools must support
your database version and extensions;
the bundled deployment uses PostgreSQL 16 with pgvector.

Qualify Cloud, Worker, Search, GoTrue, Admin, and Backup together. A successfully pulled `latest`
tag does not establish compatibility. For an unreleased build, select its exact image through an
override and retain the image digest with the deployment's recovery records. The
[Backup CI lane](deployment-ci.md#backup-acceptance) records the tested digests and fails if the
running images differ.

### Storage and retention

By default, Backup reuses your S3/MinIO endpoint and credentials and creates a private bucket
named `<APPFLOWY_S3_BUCKET>-backups`. For example, `appflowy` uses `appflowy-backups`. The
application attachment bucket and the backup bucket must be different.

For the bundled MinIO deployment, the existing credentials can create the bucket automatically.
For external S3, allow bucket creation or pre-create a private bucket with the required read,
write, list, multipart-upload, and cleanup permissions. Readiness also needs `s3:ListBucket`
for its `HeadBucket` check, `s3:GetBucketAcl`, and `s3:GetBucketPolicy` so it can verify that
the bucket is private. Grant `s3:CreateBucket` only when startup should create a missing bucket.
An existing bucket must remain private; startup does not rewrite its access policy. Cloud uses
the same artifact settings for authenticated downloads.

No additional environment settings are needed for the standard deployment. To use a different
private bucket name, optionally set `APPFLOWY_BACKUP_BUCKET` in the existing root `.env`.
Portable exports expire after 24 hours by default. Recovery backups default to 30 days;
scheduled-backup retention can be selected in the Admin console.

For advanced deployments, custom artifact-storage settings must be passed to **both** Cloud and
Backup through a Compose override. Runner-only settings, such as retention or the writer list,
belong on the Backup service. Append your override file to `COMPOSE_FILE` in `.env` so every
later `docker compose up -d` includes it; the supplied explicit file list does not automatically
load `docker-compose.override.yml`. See the service's
[environment reference](https://github.com/AppFlowy-IO/AppFlowy-Cloud-Premium/blob/main/services/appflowy-backup/deploy/runner.env.example)
for the supported advanced settings. Keep credentials private.

Recovery backups, portable exports, and restore staging consume disk and object storage. Keep
adequate free space and retain the private artifact bucket and Docker data volumes. Search-index
and embedding data are excluded from new backups by default; administrators can include them in
the creation dialog. Page and database content are captured independently of those options.

### Persistent restore state

Backup generates private deployment state in its `backup_work` volume and selected resource
files under `backup-ops/runtime/`. Compose reads these files automatically on later starts so
a normal `docker compose up -d` continues using the restored object bucket, Redis database, and
search directory. The directory is created automatically and ignored by Git. Preserve it when
moving or upgrading the deployment; do not edit its generated files by hand.

Keep the original Compose files, `.env`, and appended overrides as the deployment inputs.
A flattened `docker compose config` export resolves the current environment files and can freeze
old storage selections; do not replace the installed source files with that export after restore.
The selected object bucket and Redis database must agree across Cloud, Worker, Search, and any
additional writers. Search uses a fresh active index directory and rebuilds restored workspaces;
an included LMDB archive remains a diagnostic cache rather than being served as current data.

Keep the existing Compose project name when upgrading. If an older deployment used
`snapshot_runner`, stop and remove that old service with its previous configuration before
starting `appflowy_backup`. Preserve any older pgBackRest repositories and configuration needed
to restore legacy recovery chains; new backups no longer require them.

### Upgrade with existing backups

For the v0.19.2 storage rollout, follow the [release migration requirements](../README.md#release-notes):

1. Retain a usable recovery point, the deployment configuration and secrets, the private artifact
   bucket, `backup_work`, and `backup-ops/runtime/`. Keep the current Compose project name.
2. Drain application traffic and stop all application writers, including optional MCP or custom
   integrations. Pause Backup work for the rollout so capture cannot overlap the migration.
3. Run the updated Cloud migration runner, or the matching `appflowy-migrate` for a custom job.
   Preserve the existing migration history and checksums; do not edit migration records to bypass
   a restore or startup failure.
4. After migrations finish, start the matching GoTrue, Cloud, Worker, Search, Admin, and Backup
   builds, check readiness, and then resume application traffic.
5. Verify an existing recovery point or ZIP against the upgraded build in an isolated installation
   before relying on it for rollback. A rollback build must understand the updated storage protocol
   and migration history. Redacted exports also require Backup's schema policy to match the migrated
   Cloud schema.

Restore preparation uses the migration runner before switching the live database. During the
verification stage, Cloud's `/api/ready` probe can succeed while application requests remain fenced;
the supplied backup override uses this probe so the coordinator can finish the switch before
restarting other writers. Wait for the restore job and normal application readiness before opening
clients. Preserve the private restore journal if a coordinator restart interrupts this process.

### Pause Backup

```bash
docker compose stop appflowy_backup
```

Keep the enabled profile and storage settings while pausing the service. The application remains
available; new Backup operations are unavailable until its service is ready again. Existing
history and completed downloads remain visible. Clearing `APPFLOWY_BACKUP_PROFILE` alone does
not stop an already running container.

## Storage and Redis

PostgreSQL, MinIO, and Search use the named volumes `postgres_data`, `minio_data`, and `keyword_index_data`. Retain the Compose project name when recreating containers so they select the same volumes. `docker compose down -v` removes deployment data volumes; it is not an upgrade command.

Redis uses the image's default command and the [memory behavior](#redis) above. The root Compose file does not configure AOF, an explicit named Redis data volume, or a Redis health check. It does not guarantee that Redis-backed queues or pending work survive container replacement. Retaining PostgreSQL and MinIO data does not establish Redis queue durability.

For a local Swarm installation, follow the [Docker Swarm guide](docker-swarm.md). It uses a separate stack and direct Docker commands; the [deployment CI guide](deployment-ci.md) describes the automated checks and their limits.

## Interactive business API documentation

Self-host Cloud images containing Swagger support serve the interactive API reference automatically
at `https://your-domain/api/docs` (or `http://localhost/api/docs` locally). No enable flag or separate
Swagger container is required. The existing Nginx `/api` location forwards the page and its assets.

See the [OpenAPI guide](OPENAPI.md) for authentication, testing requests, downloading the document,
and updating Swagger with your Cloud image. Remove `APPFLOWY_ENABLE_SWAGGER` from older `.env` or
Compose overrides; it is no longer used and setting it to `false` does not disable the page.

## OAuth providers

The [`gotrue` service](../docker-compose.yml) forwards Google, GitHub, and Discord OAuth settings from the root `.env`. The settings are listed in [`deploy.env`](../deploy.env).

For provider setup instructions, see the [authentication guide](AUTHENTICATION.md).

Set `FQDN` and `SCHEME` for your public deployment URL before configuring a provider. Register an OAuth application with that provider and set its callback URL to `${API_EXTERNAL_URL}/callback`, which resolves to `https://your-domain/gotrue/callback` for an HTTPS deployment.

Update the matching provider settings in `.env`. For example, for Google:

```dotenv
GOTRUE_EXTERNAL_GOOGLE_ENABLED=true
GOTRUE_EXTERNAL_GOOGLE_CLIENT_ID=your-client-id
GOTRUE_EXTERNAL_GOOGLE_SECRET=your-client-secret
GOTRUE_EXTERNAL_GOOGLE_REDIRECT_URI=${API_EXTERNAL_URL}/callback
```

For GitHub or Discord, use the corresponding `GOTRUE_EXTERNAL_GITHUB_*` or `GOTRUE_EXTERNAL_DISCORD_*` settings. Leave providers you do not use disabled.

Apply the updated environment from the repository root:

```bash
docker compose up -d gotrue
```

## SAML

For Okta, follow the [SAML setup guide](OKTA_SAML.md). The SAML settings forwarded to GoTrue are `GOTRUE_SAML_ENABLED` and `GOTRUE_SAML_PRIVATE_KEY`; configure them in the root `.env`.

## Enterprise identity

SCIM provisioning, custom OIDC / OAuth providers, and LDAP sign-in are configured in the Admin console rather than through `.env`. See [SCIM Provisioning](SCIM.md), [OIDC / OAuth](OIDC.md), and [LDAP](LDAP.md). The bundled [`docker/nginx/nginx.conf`](../docker/nginx/nginx.conf) already routes `/scim` to AppFlowy Cloud and sets `X-Forwarded-For` for `/api`; if you use a customized Nginx configuration, the SCIM and LDAP guides show the exact directives to add.

## AI apps (MCP)

The `appflowy_mcp` service lets AI apps such as Claude, ChatGPT, Cursor, Claude Code, and Codex
read and edit AppFlowy content through the [Model Context Protocol](https://modelcontextprotocol.io).
The bundled Nginx serves it on your AppFlowy domain, and the service publishes no port of its own.

Users add **`https://your-domain/mcp`** to their AI app as a remote MCP server or custom connector.
AppFlowy shows the same URL under **Settings → AI apps**, where users connect AI apps and manage
their connections. When a user connects, the AI app opens an AppFlowy consent page; the user signs
in, chooses a workspace, and grants the app access to that workspace only.

### Turning AI apps on

AI apps are off until an administrator turns them on: open the Admin console, go to
**AI apps (MCP)**, and switch on **Enable AI app access**. The same page sets who may use AI apps
and the rate limits, and lists every change. Changes reach every AppFlowy service within seconds, without
a restart. The page needs a Team plan license or higher.

`APPFLOWY_MCP_ENABLED` in `.env` is unset by default, so the Admin switch decides. Set it to
`false` to keep AI apps off whatever Admin stores (the page then shows **Managed by deployment**),
or to `true` to turn them on until an administrator changes it there. Recreate `appflowy_cloud`
and `appflowy_mcp` after changing it.

Upgrading from a version without this switch turns AI apps off until an administrator turns them
on. Existing connections are kept and resume once AI apps are on again, unless an app's 30-day
sign-in expired meanwhile.

### Public URL and HTTPS

`APPFLOWY_MCP_BASE_URL` in `.env` defaults to `${APPFLOWY_BASE_URL}`. Set the origin only, without
`/mcp`. AppFlowy Cloud advertises it to AppFlowy Web and Desktop, and the Admin console's MCP Tool
Console uses it. It is also the OAuth issuer: changing it, for example from `http` to `https` or to
a new domain, makes every connected AI app reconnect. Recreate the affected services after a change:

```bash
docker compose up -d appflowy_mcp appflowy_cloud admin_frontend
```

When upgrading an installation whose `.env` predates this setting, copy the **AI apps (MCP)**
block from [deploy.env](../deploy.env) into `.env`, or at least add
`APPFLOWY_MCP_BASE_URL=${APPFLOWY_BASE_URL}` after `APPFLOWY_BASE_URL`. Without it, MCP still
answers on your domain, but AppFlowy Cloud does not advertise the URL to AppFlowy Web and Desktop,
and the Admin MCP Tool Console is unavailable.

Hosted AI apps such as claude.ai and ChatGPT connect from the internet. They need a public HTTPS
origin: set `SCHEME=https` and `WS_SCHEME=wss`, and install a certificate those apps trust in
`docker/nginx/ssl/`. AI apps running on the same machine as the server, such as Claude Code or
Cursor, also work with `http://localhost`.

### Who can connect

- **Workspace approval:** by default, a workspace owner must approve an AI app before members can
  connect it to that workspace. Members can request access, and owners can approve or dismiss
  requests, revoke approvals, or allow any AI app in their workspace.
- **Email allowlist:** by default every account can use AI apps. To restrict them, choose
  **Only these domains and people** in Admin → AI apps (MCP). `.env` can set the starting lists
  instead, as a comma-separated domain list (`APPFLOWY_MCP_ALLOWED_EMAIL_DOMAINS=example.com`)
  and/or exact addresses (`APPFLOWY_MCP_ALLOWED_EMAILS`); lists saved in Admin take precedence.
- **Server-wide client lists:** `MCP_ALLOWED_CLIENT_IDS` blocks every AI app except the listed
  OAuth client IDs, and `MCP_ALLOWED_REDIRECT_HOSTS` limits which callback hosts (host or
  host:port) may register. Leave both empty to let workspace owners decide.

Recreate `appflowy_mcp` after changing these `.env` settings (and `appflowy_cloud` too for the
email lists); changes made in Admin apply without a restart. Users can always revoke their own
connections from Settings → AI apps.

### Routes, limits, and custom proxies

The bundled [`docker/nginx/nginx.conf`](../docker/nginx/nginx.conf) sends exactly these paths to
`appflowy_mcp:8002`; everything else keeps its existing service:

| Path | Match |
| --- | --- |
| `/mcp` | exact (Streamable HTTP; `GET` holds a server-sent event stream open) |
| `/api/mcp` and everything under it | prefix, ahead of the `/api` location for AppFlowy Cloud |
| `/.well-known/oauth-authorization-server` | exact |
| `/.well-known/oauth-protected-resource` and its sub-paths | prefix |
| `/.well-known/mcp.json` | exact |

`/oauth/*` stays on AppFlowy Web, which serves the consent page. MCP's health, metrics, and root
`/sse` endpoints are not published. If you use your own reverse proxy, route the same paths and,
for `/mcp` and `/api/mcp`, use HTTP/1.1 without proxy buffering or caching, with read and send
timeouts of at least an hour and a body limit of at least 4 MiB. Pass `Host` and
`X-Forwarded-Proto`, and set both `X-Real-IP` and `X-Forwarded-For` to `$remote_addr`, replacing
any value the client sent.

MCP answers CORS requests itself. By default it mirrors the request origin; AppFlowy Web and the
Admin console on this domain need nothing more. To limit which other browser origins may call MCP
directly, list them (scheme, host and optional port, comma-separated) in
`APPFLOWY_CORS_ALLOWED_ORIGINS` and recreate `appflowy_mcp`.

Unauthenticated OAuth and client-registration requests are limited per client address to 60 a
minute, the server default, until Admin → AI apps (MCP) sets another limit; that page also sets
each user's tool-call and search limits per workspace. To start from a different limit, set
`APPFLOWY_MCP_OAUTH_IP_RATE_LIMIT_PER_MINUTE` in `.env` and recreate both `appflowy_cloud` and
`appflowy_mcp`, which must agree.
MCP records the client address in its audit log. MCP takes that address from `X-Forwarded-For` or
`X-Real-IP` only when the request comes from `APPFLOWY_MCP_TRUSTED_PROXY_CIDRS`, which defaults to
Docker's private address pools (`172.16.0.0/12,10.0.0.0/8,192.168.0.0/16`); a blank value restores
that default. Even then it believes only the right-most `X-Forwarded-For` address, the one that
proxy set, and never the entries a client wrote to its left. A proxy may therefore append the
address it received the request from or replace the header with it, as the bundled Nginx does;
either way no client, even one on a private LAN or VPN, chooses its own address. What matters is
that nothing else inside those ranges reaches MCP directly: only Nginx and other Compose
containers can. If a CDN, tunnel, or load balancer sits in front of Nginx, set `set_real_ip_from`
to only its address ranges and `real_ip_header` as the [LDAP guide](LDAP.md#nginx-client-address)
describes, so that `$remote_addr` is the end user. On Docker Swarm, the routing mesh hides client
addresses from Nginx; see [client addresses](docker-swarm.md#client-addresses).

MCP keeps its own PostgreSQL pool of up to `APPFLOWY_MCP_DATABASE_MAX_CONNECTIONS` (8)
connections; include it in your [connection budget](HARDWARE_SIZING.md#connection-budget). It starts
after Cloud and uses the same database, Redis, object storage, and Search settings. Upgrade Cloud,
Worker, Search, and MCP together.

## Search admission

This Compose deployment includes Search and defaults `APPFLOWY_SEARCH_SERVICE_URL` to
`http://appflowy_search:4002`. When deliberately deploying without Search, explicitly clear the
value in `.env`:

```dotenv
APPFLOWY_SEARCH_SERVICE_URL=
```

Recreate Cloud to apply the updated environment:

```bash
docker compose up -d appflowy_cloud
```

An absent variable keeps the bundled service default; an explicitly empty or whitespace-only
value means Search is unconfigured. Cloud records admission for the installation, and Worker,
MCP, and Search observe it through notifications and a five-second recovery poll. There is no
Admin enable/disable switch. AI and individual indexing capabilities retain narrower controls.

Cloud checks configured Search every 10 seconds. A new installation waits for two consecutive
healthy checks before accepting indexing work. An enabled installation continues queuing during
brief failures; after 60 seconds of observed unhealthiness, admission pauses. Two consecutive
healthy checks resume admission and start reconciliation of content changed while paused.
Existing queued work is retained when admission pauses; its durability still depends on Redis
storage and queue retention. The Admin Search overview shows checking, degraded, paused, and
recovering states, the last failure, and the next check. An existing enabled installation keeps
admission during its first health checks when upgrading to this policy.

Unconfigured Search stops new indexing tasks and pauses consumers after propagation. Restoring
the service URL and recreating Cloud starts health checks; indexing resumes after two successes.
Use the same Search configuration on every Cloud replica.

### Server compatibility and rollout

The minimum server capability is **URL-derived admission with automatic Search health checks**.
A numbered published server release containing that capability has not yet been qualified for
this deployment change. These configuration files alone do not add it to an older image. Before
relying on an empty URL or automatic outage pause/recovery, deploy a matching server release and
verify the admission states in Admin. Upgrade Cloud, Worker, Search, and MCP together, with Cloud
migrations completing first; mixed Cloud versions can overwrite the shared admission decision.

Compose and Swarm supply a fixed `APPFLOWY_SEARCH_ENABLED=true` inside Cloud for bootstrap
compatibility with older images that otherwise disable Search on fresh installations. It is not
read from `.env` and is not an operator toggle. New Cloud ignores that retired variable and
`APPFLOWY_INDEXER_ENABLED`; its Search URL and observed health control admission. This fixed
compatibility value keeps the ordinary bundled Search deployment working during a staged release;
it does not make older images support unconfigured Search or automatic health admission.
