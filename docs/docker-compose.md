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

## Installation identity and license reporting state

Cloud mounts the private named volume `appflowy_cloud_state` at `/var/lib/appflowy/license`.
The deployment sets `APPFLOWY_INSTALLATION_IDENTITY_PATH` to
`/var/lib/appflowy/license/installation.json` and `APPFLOWY_LICENSE_REPORT_STATE_PATH` to
`/var/lib/appflowy/license/report.json`. A compatible Cloud image uses these files for its
installation identity and reporting credential. Retain this volume across container recreation,
image upgrades, and PostgreSQL restores. A container restart alone does not establish that state
will survive recreation. Avoid `docker compose down --volumes` when retaining the installation.

Only Cloud mounts this volume. Keep its contents private: the installation file contains the UUID's
private preimage and the reporting file contains a credential.
Replicas serving one PostgreSQL database must share one installation identity and state directory;
do not create a separate licensed device identity for each replica. The default local Docker volume
stays on its Docker host and does not provide shared storage across hosts.

These paths require a Cloud image that supports persistent installation identity. An older image
ignores the new identity path. Before upgrading a deployment that already has a reporting credential
at a custom or container-local path, stop Cloud and privately preserve that file at the new report
path, retaining its ownership and restrictive permissions. Retain both files outside PostgreSQL
backup restoration; restoring application data must not roll back the installation's identity.

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
services during restore. The default writer list covers Cloud, GoTrue, Worker, Search, and AI.
If you add MCP, connectors, or other services that write to this installation, include their
Compose service names in the Backup service's `APPFLOWY_BACKUP_COMPOSE_WRITERS` environment
setting through a Compose override before using restore.

Backup uses `appflowyinc/appflowy_backup:${APPFLOWY_BACKUP_VERSION:-latest}`. Use the Backup image
published with your Cloud release and set `APPFLOWY_BACKUP_VERSION` to that release's
tag when available. Its PostgreSQL tools must support your database version and extensions;
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
