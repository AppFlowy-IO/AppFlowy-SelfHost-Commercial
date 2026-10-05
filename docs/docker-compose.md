# Docker Compose

With Docker and the Docker Compose plugin installed, first copy the environment template from the repository root:

```bash
cp deploy.env .env
```

Edit `.env` to set your domain, HTTPS/WebSocket schemes, credentials, and optional email or AI settings. Replace the example passwords and JWT secret before exposing the deployment publicly. Compose [loads the root `.env` automatically](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/), and Git ignores this file.

Compose uses the public `appflowyinc/appflowy_cloud` and `appflowyinc/appflowy_worker` images. Both provide AMD64 and ARM64 builds, and Docker selects the image architecture for your host automatically.

Nginx configuration and certificates remain in [`docker/nginx`](../docker/nginx). For HTTPS, replace the bundled development certificate and key in `docker/nginx/ssl/` with your deployment's certificates.

For an existing installation, complete the [Redis persistence migration](#redis-persistence) before recreating Redis. For a new installation, start the services from the repository root:

```bash
docker compose up -d
```

With the default localhost settings, open [AppFlowy Web](http://localhost) or the [Admin console](http://localhost/console). The template creates the admin account `admin@example.com` with password `password`.

If upgrading an installation previously started from `docker/`, move its existing `.env` to the repository root and retain its Compose project name. For the old default, add `COMPOSE_PROJECT_NAME=docker` to `.env`; if you used a custom project name, keep that value. This reuses the existing named data volumes and the default network. Containers whose definition changed are recreated in place: `nginx` and `appflowy_cloud` leave the old `cloud_proxy` network, and `minio`, `appflowy_cloud`, and `appflowy_worker` move to new image references. Unchanged service definitions are reused; Redis requires the persistence migration below. The old `<project>_cloud_proxy` network is left behind and can be removed with `docker network rm` after the upgrade.

## Backup

The self-hoster prepares and runs the Backup deployment. Once its service reports ready,
AppFlowy Admin users need no additional configuration: open **Tools → Backup** and use the
available operations. Cloud discovers the service automatically; there is no Admin enable
setting or `APPFLOWY_BACKUP_ENABLED` flag.

The current deployment still requires one-time operator setup. Selecting Backup starts the
prepared configuration; it does not create storage buckets, supply credentials or initialize
pgBackRest. With Backup disabled, this additional setup is unnecessary.

| Requirement | What the self-hoster configures | What Compose supplies |
| --- | --- | --- |
| PostgreSQL backup repository and WAL archiving | Private pgBackRest repository settings and one-time stanza initialization | Compatible PostgreSQL tooling, archiving options and shared socket |
| Private backup archive storage | Bucket, endpoint, credentials and access permissions in `backup-ops/runner.env` | The same storage settings for Backup uploads and Cloud's authenticated downloads |
| Persistent work files and coordinator access | Existing Compose project name, Docker socket group ID and any custom writer services | Persistent volumes, coordinator connections and shutdown settings |

Server backup is disabled in the default deployment. The root `.env` controls it through
`APPFLOWY_BACKUP_PROFILE`:

```dotenv
APPFLOWY_BACKUP_PROFILE=
```

After completing the setup below, enable Backup by changing that value to:

```dotenv
APPFLOWY_BACKUP_PROFILE=backup
```

Then use the same `docker compose up -d` command. The main Compose file declares `appflowy_backup`
with the `backup` profile. The environment template automatically selects the
[supporting configuration](../docker-compose.backup.yml) when the value is nonempty; no YAML
edits, filenames or extra command flags are needed. Leave `COMPOSE_PROFILES`, `COMPOSE_FILE` and
`COMPOSE_PATH_SEPARATOR` at their derived template values. This deployment supports an empty
`APPFLOWY_BACKUP_PROFILE` value or `backup`. The template maps this deployment setting to
Docker's [COMPOSE_PROFILES setting](https://docs.docker.com/compose/how-tos/environment-variables/envvars/#compose_profiles);
it is not a Cloud feature flag.
Use the `.env` switch when enabling Backup; `--profile backup` alone does not select its
supporting configuration.

The supporting file supplies Backup's environment, mounts, dependencies and shutdown settings,
along with PostgreSQL tooling and WAL archiving. With the default empty value, it is not loaded
and no private Backup files are required.

When upgrading an existing deployment that named this service `snapshot_runner`, stop and remove
its old container using the previous deployment configuration before starting `appflowy_backup`.
Retain the existing Compose project name, private configuration and data volumes.

Admin's **Tools → Backup** page reads Cloud's authenticated runner status every 30 seconds.
New operations become available when the service reports ready and supports them. A stopped or
unready runner keeps existing history and downloads visible while new operations remain
unavailable. Readiness failures identify deployment issues for the self-hoster to resolve;
Admin users do not configure PostgreSQL, storage credentials or coordinator connections.

The Backup service uses `appflowyinc/appflowy_backup:latest` by default. Before enabling it,
confirm that the registry contains a Backup image built from the same server release as Cloud,
Worker, and Search. If your release process publishes immutable tags, set the `image` value for
`appflowy_backup` in the supporting Compose file to that tag instead of relying on `latest`.
The Backup image must use the same PostgreSQL major and compatible extensions as the existing
`postgres_data` volume; the Compose override does not migrate a PostgreSQL data directory.

Prepare the private files below and apply both Compose files during a deployment window.
The override recreates PostgreSQL with the Backup image while retaining `postgres_data`.
The image's PostgreSQL major must match
the existing data directory; the supplied configuration uses PostgreSQL 16 with pgvector.
Keep any custom extension libraries compatible. Back up your current deployment configuration
and retain the existing Compose project name and data volumes.

1. Prepare new private operator files from the supplied examples:

   ```bash
   umask 077
   mkdir -p backup-ops/pgbackrest/conf.d backup-ops/certificates
   cp docker/backup/runner.env.example backup-ops/runner.env
   cp docker/backup/pgbackrest.conf.example backup-ops/pgbackrest/pgbackrest.conf
   chmod 600 backup-ops/runner.env backup-ops/pgbackrest/pgbackrest.conf
   ```

   These copy commands are for initial setup. Preserve existing `backup-ops` configuration on
   later upgrades; the directory is ignored by Git. Review file ownership so the image's
   `postgres` user can read the private pgBackRest configuration and certificates. Keep the
   `conf.d` directory even when it is empty.

2. Edit `backup-ops/pgbackrest/pgbackrest.conf` for a dedicated private PostgreSQL repository.
   Edit `backup-ops/runner.env` for a private artifact bucket, credentials and staging limits.
   Replace every `replace-me` value. Source database, Redis and application object settings
   already come from the root deployment environment; the example does not duplicate their
   credentials. The artifact settings are shared by Cloud and Backup for authenticated downloads
   and multipart uploads. Prepare the repositories and grant their required read, write,
   listing, multipart and cleanup permissions. Use a separate artifact bucket from public
   attachments, retain TLS verification, and place custom CA certificates in
   `backup-ops/certificates` when needed. Disable external pgBackRest expiration jobs for this
   dedicated repository so retained recovery dependencies cannot disappear.

3. Set the exact existing `COMPOSE_PROJECT_NAME` and `APPFLOWY_BACKUP_DOCKER_GID` in the root
   `.env`. On a Linux Docker host, `stat -c '%g' /var/run/docker.sock` reports the socket group
   ID. Review the writer inventory in the override if MCP, connectors or other writer services
   are deployed. The coordinator has Docker administration access and must account for every
   writer in this installation. The override configures persistent work/journal volumes and the
   shutdown grace period; no additional process settings are needed.

4. Set `APPFLOWY_BACKUP_PROFILE=backup` in the root `.env`. Validate without printing the resolved
   configuration, then initialize the dedicated stanza
   against the configured PostgreSQL service:

   ```bash
   docker compose config --quiet
   docker compose up -d postgres
   docker compose exec --user postgres postgres \
     pgbackrest --config=/etc/pgbackrest/pgbackrest.conf --stanza=appflowy stanza-create
   ```

   Initialize the stanza only for a new repository. If your PostgreSQL user or port differs,
   update the stanza settings to match. Check the resulting database health before continuing.

5. Start the configured deployment, confirm readiness, and open **Tools → Backup**:

   ```bash
   docker compose up -d
   ```

   This enables backup capture and portable exports when readiness checks pass. Readiness
   failures appear in Admin with their blockers; starting the service needs no Cloud enable flag
   or restart. Keep `APPFLOWY_BACKUP_PROFILE=backup` for subsequent deployment changes.
   If you change Cloud's artifact credentials or endpoint, recreate Cloud to apply that
   environment change.

To stop a previously enabled Backup service, use the same configuration:

```bash
docker compose stop appflowy_backup
```

Stop the service while the enabled configuration is still selected. Clearing `APPFLOWY_BACKUP_PROFILE`
alone does not stop a container that is already running. Keep the enabled configuration when
pausing Backup so PostgreSQL's WAL archiving setup remains intact.

This setup does not enable **Restore server** or **Restore from ZIP**. Those operations require
a separately prepared restore coordinator, private deployment configuration, readiness fence
and persistent activation journals. Portable exports can be independently verified and restored
with the matching Backup CLI into new targets. New backups capture online while users continue
editing; restoring an installation requires its own coordinated deployment procedure.

## Redis persistence

The bundled Redis service enables AOF with `appendfsync everysec`, uses `maxmemory-policy noeviction`, and stores `/data` in the Compose-managed `redis_data` volume. Pending work survives container recreation when this volume is retained. One-second fsync still permits recent writes to be lost in a crash; keep durable backups and provision memory/disk capacity for your workload. This change does not set a memory limit or enable hosted storage quotas in self-host builds.

When upgrading the previous Redis service, its existing anonymous `/data` volume is **not** automatically copied into `redis_data`. Before running `docker compose up` with this change:

1. Pause Redis writers and back up the existing dataset. Keep the existing container and volume until migration is verified.
2. Enable AOF on the running Redis with `redis-cli CONFIG SET appendonly yes`. Use `INFO persistence` to confirm `aof_rewrite_in_progress=0`, `aof_rewrite_scheduled=0`, and `aof_last_bgrewrite_status=ok` before stopping it. See [Redis's AOF migration procedure](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/#how-i-can-switch-to-aof-if-im-currently-using-dumprdb-snapshots).
3. Stop Redis and copy its complete `/data` contents, including the AOF directory and manifest, into the new project's `redis_data` volume while retaining file ownership. Start Redis with the new configuration and verify the dataset before resuming writers.

Retain the Compose project name so subsequent recreations select the same volume. `docker compose down -v` removes deployment data volumes; it is not an upgrade command. External Redis deployments need equivalent persistence settings on their own servers.

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
