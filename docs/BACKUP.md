# Server Backup

AppFlowy Backup is an optional service for protecting a self-hosted AppFlowy server. It coordinates PostgreSQL recovery points, application objects, and portable diagnostic exports. The Admin console sends backup requests to this service; it does not run inside the browser and it does not change the way users edit documents.

Backup is disabled in the default deployment. When it is enabled and healthy, administrators can use **Tools → Backup** without another application setting.

## What it does

- Creates full, differential, or incremental recovery backups.
- Keeps the database and application object storage at a consistent recovery point.
- Stores backup artifacts in the private object-storage location configured for the deployment.
- Produces a portable export for troubleshooting or moving data to another installation.
- Shows progress, warnings, expiry, size, and download actions in the Admin console.

A backup is only useful if its PostgreSQL repository and artifact storage are retained. Treat both as production data and protect them with the same access controls as the live installation.

## Before you begin

- Run matching releases of AppFlowy Cloud, Worker, Search, MCP, PostgreSQL, and the Backup image. Pin the Backup image to the same release instead of using `latest` in production.
- Allocate private object storage for backup artifacts. The bucket must be reachable by both AppFlowy Cloud and Backup.
- Allocate a PostgreSQL backup repository for pgBackRest and enough local disk for temporary capture work.
- Make sure the host can pass the Docker socket to the Backup container. Backup coordinates the other Compose services during recovery and validation.
- Keep the existing Compose project name. Backup uses it to find the running Cloud, Worker, Search, MCP, and database containers.

The detailed storage, pgBackRest, certificate, and Docker-socket setup is in [Docker Compose backup setup](docker-compose.md#backup). For the stock localhost deployment, the administrator sign-in is `admin@example.com` with password `password`; change this before exposing the server.

## Enable Backup

1. From the self-host deployment directory, create the private operator files:

   ```bash
   mkdir -p backup-ops/pgbackrest/conf.d backup-ops/certificates
   cp docker/backup/runner.env.example backup-ops/runner.env
   cp docker/backup/pgbackrest.conf.example backup-ops/pgbackrest/pgbackrest.conf
   chmod 600 backup-ops/runner.env backup-ops/pgbackrest/pgbackrest.conf
   ```

2. Edit `backup-ops/runner.env` with the private artifact bucket, endpoint, credentials, and retention settings. Edit `backup-ops/pgbackrest/pgbackrest.conf` with the PostgreSQL repository settings. Do not commit either file.

3. Set the Docker socket group ID and enable the profile in the root `.env`:

   ```dotenv
   APPFLOWY_BACKUP_DOCKER_GID=123
   APPFLOWY_BACKUP_PROFILE=backup
   ```

   On Linux, get the group ID with `stat -c '%g' /var/run/docker.sock`. On macOS, use the group ID reported by Docker Desktop for the mounted socket.

4. Check the merged Compose file without printing secrets, then start the deployment:

   ```bash
   docker compose --env-file .env config --quiet
   docker compose --env-file .env up -d
   ```

5. Wait for the `appflowy_backup` container to report ready. If the service is not ready, the Backup controls remain unavailable and the Admin page explains that the deployment needs attention.

To disable the service later, stop it while the backup profile is still selected, then follow the shutdown instructions in the [Compose guide](docker-compose.md#backup). Do not simply remove the profile while PostgreSQL archiving is still configured.

## Create a recovery backup

1. Sign in to the Admin console with an administrator account.
2. Open **Tools → Backup**. The page shows the runner state, scheduled jobs, and previous backup or export jobs.

   ![Admin Tools → Backup page](../asset/backup-admin-overview.png)

3. Select **Create recovery backup**.
4. Give the backup a name and choose a backup type:

   | Type | Use it when |
   | --- | --- |
   | **Full** | You need an independent recovery point or are starting a new chain. |
   | **Differential** | You want changes since the latest full backup. |
   | **Incremental** | You want the smallest backup and can retain its parent chain. |

5. Submit the job. You can close the dialog or leave the page; progress is saved on the server. The job changes from **Queued** to **Running**, then **Completed** or **Completed with warnings**.
6. Open **View report** on a completed job to inspect warnings and affected objects. Download is available only after the artifact has been finalized.

## Export a portable report

Use the row’s **More** menu to create an export for support or diagnostics. An export is a portable copy of the selected recovery point; it is different from a recovery backup and should be treated as a diagnostic artifact.

When the export finishes, download the single report ZIP. It contains the readable PDF summary, the full Markdown diagnostics, and structured JSON. Keep the ZIP private when it contains account or email mapping data.

![Completed backup report and ZIP download](../asset/backup-report-download.png)

## Restore safely

A server restore replaces the current installation with the selected recovery point. Before starting one:

1. Test the backup on a separate self-host deployment first.
2. Close connected AppFlowy clients and stop automated jobs that write to the server.
3. Confirm that the backup includes the PostgreSQL repository, object storage, and any optional search data needed by your deployment.
4. Open the completed recovery backup in **Tools → Backup**, choose **Restore server**, and follow the confirmation prompt.
5. Wait for the job to finish. The server can disconnect during the final switch; sign in again with an account from the restored backup and verify workspaces, pages, databases, files, and permissions.

A restore may replace the administrator session. The Admin console keeps the last recorded progress so you can return after signing in again.

![Restore progress after the server session is replaced](../asset/backup-restore-session.png)

## Read job status

- **Queued**: accepted and waiting for the Backup runner.
- **Running**: capture, validation, upload, or restore is in progress.
- **Completed**: the requested operation finished successfully.
- **Completed with warnings**: the operation finished, but the report lists items that need review.
- **Failed**: no usable artifact was published. Open the report and check the Backup container logs before retrying.
- **Cancelled**: the operation stopped before publishing a usable result.

Do not use a running or failed job as a restore source. If the page says the runner is unavailable, repair the deployment first; creating jobs while the runner is offline cannot produce a valid backup.

## Common problems

| Symptom | What to check |
| --- | --- |
| Backup controls are disabled | `appflowy_backup` is not running or has not passed readiness checks. Check `docker compose ps` and the container logs. |
| PostgreSQL archiving or stanza errors | Verify the pgBackRest repository, stanza name, credentials, and that the Backup image uses the same PostgreSQL major version as the database. |
| Artifact upload or download fails | Check bucket endpoint, region, credentials, certificate files, and network access from both Cloud and Backup. |
| Job stays queued | Confirm the Backup container can access the Docker socket and that `APPFLOWY_BACKUP_COMPOSE_PROJECT` matches the existing Compose project. |
| Restore cannot start | Use a completed recovery backup, keep the source artifact available, and ensure the target has enough temporary disk. |
| Download is missing | Downloads appear only after the backup or export artifact is finalized. Refresh the page after the job reaches a terminal state. |

For operator-level diagnostics, see the full [Docker Compose backup setup](docker-compose.md#backup) and the Backup report generated by the Admin console.
