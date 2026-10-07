# Docker Compose

With Docker and Docker Compose **2.30 or newer** installed, first copy the environment template from the repository root:

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

The Backup coordinator has Docker administration access so it can pause and restart application
services during restore. The default writer list covers Cloud, GoTrue, Worker, Search, and AI.
If you add MCP, connectors, or other services that write to this installation, include their
Compose service names in the Backup service's `APPFLOWY_BACKUP_COMPOSE_WRITERS` environment
setting through a Compose override before using restore.

Backup uses `appflowyinc/appflowy_backup:${APPFLOWY_BACKUP_VERSION:-latest}`. Use the Backup image
published with your Cloud release and set `APPFLOWY_BACKUP_VERSION` to that release's immutable
tag when available. Its PostgreSQL tools must support your database version and extensions;
the bundled deployment uses PostgreSQL 16 with pgvector.

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

Keep the existing Compose project name when upgrading. If an older deployment used
`snapshot_runner`, stop and remove that old service with its previous configuration before
starting `appflowy_backup`. Preserve any older pgBackRest repositories and configuration needed
to restore legacy recovery chains; new backups no longer require them.

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
