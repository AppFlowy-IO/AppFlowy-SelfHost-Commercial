# Docker Compose

With Docker and the Docker Compose plugin installed, first copy the environment template from the repository root:

```bash
cp deploy.env .env
```

Edit `.env` to set your domain, HTTPS/WebSocket schemes, credentials, and optional email or AI settings. Replace the example passwords and JWT secret before exposing the deployment publicly. Compose [loads the root `.env` automatically](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/), and Git ignores this file.

Compose uses the public `appflowyinc/appflowy_cloud` and `appflowyinc/appflowy_worker` images. Both provide AMD64 and ARM64 builds, and Docker selects the image architecture for your host automatically.

Nginx configuration and certificates remain in [`docker/nginx`](../docker/nginx). For HTTPS, replace the bundled development certificate and key in `docker/nginx/ssl/` with your deployment's certificates.

Start the services from the repository root:

```bash
docker compose up -d
```

With the default localhost settings, open [AppFlowy Web](http://localhost) or the [Admin console](http://localhost/console). The template creates the admin account `admin@example.com` with password `password`.

If upgrading an installation previously started from `docker/`, move its existing `.env` to the repository root and retain its Compose project name. For the old default, add `COMPOSE_PROJECT_NAME=docker` to `.env`; if you used a custom project name, keep that value. This reuses the existing named data volumes and the default network. Containers whose definition changed are recreated in place: `nginx` and `appflowy_cloud` leave the old `cloud_proxy` network, and `minio`, `appflowy_cloud`, and `appflowy_worker` move to new image references. Unchanged service definitions are reused. The old `<project>_cloud_proxy` network is left behind and can be removed with `docker network rm` after the upgrade.

## Storage and Redis

PostgreSQL, MinIO, and Search use the named volumes `postgres_data`, `minio_data`, and `keyword_index_data`. Retain the Compose project name when recreating containers so they select the same volumes. `docker compose down -v` removes deployment data volumes; it is not an upgrade command.

Redis uses the image's default command. The root Compose file does not configure AOF, an explicit named Redis data volume, or a Redis health check. It does not guarantee that Redis-backed queues or pending work survive container replacement. Retaining PostgreSQL and MinIO data does not establish Redis queue durability.

For a local Swarm installation, follow the [Docker Swarm guide](docker-swarm.md). It uses a separate stack and direct Docker commands; the [deployment CI guide](deployment-ci.md) describes the automated checks and their limits.

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
