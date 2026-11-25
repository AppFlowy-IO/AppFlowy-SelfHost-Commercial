# Outbound connections from AppFlowy Cloud

[Documentation](README.md)

On a fresh installation using the self-hosted Free Tier, Cloud can start and remain idle using only the bundled services on the deployment network. Commercial license enrollment adds background traffic to the license issuer. Other destinations depend on the services you configure and the features people use.

This guide covers connections initiated by `appflowy_cloud`. It was checked against the source for **`appflowyinc/appflowy_cloud:0.21.8`**, the image pinned in Docker Compose on November 25, 2026. Worker, Search, AI, GoTrue and MCP also make connections of their own. Docker pulls images, and clients download desktop installers. [Audited Compose file](https://github.com/AppFlowy-IO/AppFlowy-SelfHost-Commercial/blob/f58f4ffafab79f11bf895b0bfeb4ec9548223baa/docker-compose.yml#L195) · [Image update](https://github.com/AppFlowy-IO/AppFlowy-SelfHost-Commercial/pull/97)

## Services on the deployment network

| Service | Default Compose destination | When and why Cloud connects |
| --- | --- | --- |
| PostgreSQL | `postgres:5432` (TCP) | At startup and during normal use to read and write application data and listen for database events. |
| Redis | `redis:6379` (TCP) | At startup and during normal use for caches, queues and realtime collaboration. |
| Object storage | `http://minio:9000` | At startup to check the bucket and create it if configured. During use to read and write files, snapshots and installation state. |
| GoTrue | `http://gotrue:9999` | At startup to check authentication service health, then for sign-in and account administration. |
| Search | `http://appflowy_search:4002` | Periodic health checks and requests to search or administer an index. |
| AI | `http://ai:5001` | Chat and presentation requests, service checks and changes to the AI license. |
| Server log collector | `http://appflowy_log_collector:8088` | With the server logs profile enabled, Cloud asks the collector which logs are available and retrieves them for Admin previews and exports. [Server logs](docker-compose.md#server-logs) |

If you move PostgreSQL or Redis off the deployment network, the destination follows `APPFLOWY_DATABASE_URL` or `APPFLOWY_REDIS_URI`. [Deployment settings](../deploy.env)

- **Files and backups.** Cloud can use regional AWS S3 or your S3-compatible endpoint in place of MinIO. Backup archive uploads use the installation’s object store by default and can use a separate `APPFLOWY_BACKUP_S3_ENDPOINT`. [Backup](BACKUP.md)
- **Search vectors.** The default vector store uses PostgreSQL. With `VECTOR_STORAGE_TYPE=s3_vectors`, vector operations contact the regional Amazon S3 Vectors endpoint, for example `s3vectors.us-east-1.api.aws`. AWS role credentials may also require a call to the configured credential service. [AWS S3 Vectors endpoints](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-regions-quotas.html)

## Commercial accounts and licenses

| Trigger | HTTPS destination | Purpose and data |
| --- | --- | --- |
| Someone uses a commercial account or billing action in Admin | `beta.appflowy.cloud` | Cloud forwards the requested operation, such as account verification, plan lookup, subscription management, invitation redemption or device management. |
| An administrator binds a license to the installation | `checkip.amazonaws.com`, `api.ipify.org`, `ipv4.icanhazip.com`, then `ifconfig.me/ip` | Cloud asks for its public IP address and stops at the first valid response. The binding request sends that address to the license issuer along with the configured host, machine hostname, license ID and installation identifiers. |
| A license is applied, refreshed, or reaches its signed verification deadline | The issuer in the signed license, normally `beta.appflowy.cloud` | Cloud binds or verifies the installation with its issuer. For older licenses without an issuer, verification uses `APPFLOWY_SELF_HOST_BASE_URL` if set and otherwise uses `https://beta.appflowy.cloud`. |
| An installation enrolls for license usage reporting | The issuer in the signed license | Cloud presents the signed license and proof of installation identity to obtain a reporting credential. |
| An enrolled Cloud starts, then every **30 minutes** in `0.21.8` | The issuer saved at enrollment | Cloud reports the installation fingerprint, configured host, machine hostname, server version, collection time and status, available counts of regular users, guests and system administrators, and the installed license when available. Reporting can continue after the license expires or is removed. |

To use your own public IP lookup service, pass `APPFLOWY_IP_SERVICES` as a comma-separated list of URLs in the **Cloud container environment**. Setting `APPFLOWY_DISABLE_IP_DETECTION=true` skips only the public IP lookups during binding.

**Commercial account token exchange.** In `0.21.8`, when an administrator uses this exchange, Cloud sends the account email and the installation’s **GoTrue JWT signing secret** to `beta.appflowy.cloud` over HTTPS. The published `0.21.9` Cloud image omits the exchange. [Cloud 0.21.9 image build](https://github.com/AppFlowy-IO/AppFlowy-Docker-CI/actions/runs/44224795649)

## Connections triggered by features

Public HTTPS destinations below normally use TCP port 443. Internal relays, provider overrides and URLs found in documents can use other hosts or ports.

| Feature | Destination | When and why Cloud connects |
| --- | --- | --- |
| Desktop update check | `api.github.com`, then `github.com` and its release asset CDN (such as `release-assets.githubusercontent.com`) | A client asks for update information. Cloud reads GitHub release metadata and, when available, the update manifest. Successful lookups are cached for 15 minutes. A client request can trigger a lookup even when automatic updates are disabled. |
| Disposable email domain list | `raw.githubusercontent.com` or `APPFLOWY_DISPOSABLE_DOMAINS_URL` | An administrator requests a sync. Cloud downloads the list used to screen sign-ups. |
| Email | Configured SMTP relay and port, for example `smtp.gmail.com:465` with TLS | When sending invitations or notifications, or when an administrator tests mail delivery. |
| Mobile push | Service account’s OAuth token endpoint (usually `oauth2.googleapis.com`) and `fcm.googleapis.com` | With Firebase credentials configured, Cloud obtains an access token and sends the notification and device token when a push is due. |
| LDAP sign-in | Configured directory, usually TCP 389 for LDAP or StartTLS, or 636 for LDAPS | Cloud binds and searches the directory during sign-in or an administrator’s connection test. [LDAP](LDAP.md) |
| Apple account deletion | `appleid.apple.com` | When deleting an Apple-linked account with an Apple token, Cloud asks Apple to revoke the token. |
| Connected apps | Google Drive and Calendar use `oauth2.googleapis.com` and `www.googleapis.com`. Slack uses `slack.com`, Notion uses `api.notion.com`, and GitHub uses `github.com` and `api.github.com`. | When someone connects or uses an enabled integration, Cloud exchanges or refreshes credentials and calls the provider API on that person’s behalf. Disconnecting can also revoke a token. [Connections](CONNECTION.md) |
| AI models | `api.openai.com`, `api.anthropic.com`, `dashscope.aliyuncs.com`, `generativelanguage.googleapis.com`, or the configured endpoint for Azure OpenAI, DeepSeek or another compatible provider | Cloud can call a model directly for search summaries, embedding health checks, presentation media analysis or meeting transcription. The selected provider receives the text or media needed for the request and can run on your own network. [AI models](MODEL_CONFIG.md) |
| AI Meeting with AssemblyAI | `api.assemblyai.com` and `streaming.assemblyai.com`, or the transcription and streaming endpoints configured in Admin | Cloud submits recorded audio for transcription, retrieves results and requests tokens for live transcription. **Test connection** checks both endpoints. The client opens the live audio stream. [AI Meeting](AI_MEETING_CONFIG.md) |
| PDF export with images | HTTP or HTTPS image URLs in the exported document and any redirect destinations | Cloud fetches the images to embed them in the PDF. The document determines the hosts and ports. |

To check which image your deployment uses, run `docker compose images appflowy_cloud` in its Compose directory. When reading firewall logs, account for DNS requests to the deployment’s resolver and any configured network proxy. Container logs can also show Docker’s health check calling Cloud on `127.0.0.1:8000`.
