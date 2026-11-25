# Outbound connections from AppFlowy Cloud

[Documentation](README.md)

With the bundled services, a fresh Free Tier `appflowy_cloud` container can start and stay idle on your own network. Enrolling a commercial license adds regular check-ins with the license issuer.

These details come from the source for `appflowyinc/appflowy_cloud:0.21.8`, the image pinned in Docker Compose on November 25, 2026. To check your version, run `docker compose images appflowy_cloud` in your Compose directory. [Compose image pin](https://github.com/AppFlowy-IO/AppFlowy-SelfHost-Commercial/blob/f58f4ffafab79f11bf895b0bfeb4ec9548223baa/docker-compose.yml#L195) · [Image update](https://github.com/AppFlowy-IO/AppFlowy-SelfHost-Commercial/pull/97)

## Connections triggered by features

Cloud skips Firebase push, LDAP sign-in and connected-app requests when the corresponding provider is unconfigured. Once configured, a provider can receive a queued notification or an administrator’s test even when nobody has the feature open. Built-in features have their own destinations. A desktop update check can reach GitHub even if you’ve never connected a GitHub account. Public HTTPS connections normally use TCP port 443.

### Features that use a provider

| Feature | What triggers a request? | Where does it go? |
| --- | --- | --- |
| Mobile push | Cloud needs both a Firebase service account key file and a queued notification. It gets an access token, then sends the notification and device token. | The service account’s token endpoint (usually `oauth2.googleapis.com`), then `fcm.googleapis.com`. |
| LDAP sign-in | A sign-in uses an enabled directory. An administrator can also test a saved directory **even when sign-in is disabled**. | Your LDAP server, usually TCP 389 for LDAP or StartTLS, or 636 for LDAPS. [LDAP setup](LDAP.md) |
| Connected apps | Only enabled providers receive token and API requests when someone links or uses an account. Cloud refreshes tokens on demand. Disconnecting removes the local connection. | Google Drive and Calendar use `oauth2.googleapis.com` and `www.googleapis.com`. Slack uses `slack.com`, Notion uses `api.notion.com`, and GitHub uses `github.com` and `api.github.com`. [Connections](CONNECTION.md) |
| AI models | Cloud calls an active model for search summaries, presentation media or meeting transcription. Admin’s overall health check can send the words `health check` to a configured embedding model **even with user-facing AI off**. | `api.openai.com`, `api.anthropic.com`, `dashscope.aliyuncs.com` or `generativelanguage.googleapis.com`. Azure OpenAI, DeepSeek and custom providers use a configured URL. A local model keeps those calls on your network. [AI models](MODEL_CONFIG.md) |
| AI Meeting with AssemblyAI | Meeting transcription needs AI enabled and a key in Admin or the environment. Cloud uploads recordings, retrieves transcripts or gets a token for live audio. **Test connection** checks both endpoints, even with a key you haven’t saved yet. | `api.assemblyai.com` and `streaming.assemblyai.com`, or your configured endpoints. The client opens the live audio stream. [AI Meeting](AI_MEETING_CONFIG.md) |

### Built-in actions

| Action | What triggers a request? | Where does it go? |
| --- | --- | --- |
| Desktop update check | Cloud looks up a release only when a client asks. **Turning off automatic updates still allows this lookup.** Cloud caches a successful result for 15 minutes. | `api.github.com` for release details. If a manifest is available, `github.com` and its download host, such as `release-assets.githubusercontent.com`. The client downloads the installer. |
| Disposable email list sync | An administrator requests a sync to download the list used to screen sign-ups. Ordinary sign-ups use the local list. | `raw.githubusercontent.com` or the mirror set in `APPFLOWY_DISPOSABLE_DOMAINS_URL`. |
| Email | Invitations, workspace access requests and notifications can send mail. An access request can try the sample relay even if you never set up notification emails. Admin’s mail and overall health checks also test the relay when its settings pass validation. | Your SMTP relay and port. The Compose example supplies `smtp.gmail.com:465` with TLS. |
| Apple account deletion | When someone deletes an Apple-linked account and supplies an Apple access or refresh token, Cloud asks Apple to revoke it. | `appleid.apple.com`. |
| PDF export | Exports include images by default. Cloud downloads a remote image when it appears in the content being exported. On the view export, `include_images=false` skips these downloads. | The image URLs in the content and any redirects. These can use different hosts and ports. |

## When does Cloud contact AppFlowy about a license?

**Billing in Admin.** Cloud contacts `beta.appflowy.cloud` over HTTPS when you verify a commercial account, look up plans, manage a subscription, redeem an invitation or manage registered devices.

**Commercial account token exchange in `0.21.8`.** When an administrator uses this action, Cloud sends the account email and the installation’s **GoTrue JWT signing secret** (the key used to sign login tokens) to `beta.appflowy.cloud` over HTTPS. The published `0.21.9` Cloud image omits this exchange. [Cloud 0.21.9 image build](https://github.com/AppFlowy-IO/AppFlowy-Docker-CI/actions/runs/44224795649)

**Applying or verifying a license.** Cloud contacts the issuer named in the signed license, normally `beta.appflowy.cloud`, when you apply or refresh the license and when its next verification is due. To bind the installation, Cloud sends its public IP address, configured host, machine hostname, license ID and installation identifiers.

During binding, Cloud looks up its public IP over HTTPS. It tries `checkip.amazonaws.com`, `api.ipify.org`, `ipv4.icanhazip.com` and `ifconfig.me/ip` in order and stops at the first valid answer. To choose your own lookup services, set `APPFLOWY_IP_SERVICES` to a comma-separated list of URLs in the Cloud container environment. `APPFLOWY_DISABLE_IP_DETECTION=true` skips just the IP lookup.

**Usage reporting after enrollment.** Cloud uses a signed license and proof of installation identity to register with the issuer. In `0.21.8`, an enrolled installation sends a report to that issuer **at startup and every 30 minutes**, even when nobody is signed in. Reporting can continue after the license expires or is removed. A fresh installation without a license or prior enrollment skips these reports.

Each report includes the installation fingerprint, configured host, machine hostname, server version, collection time and status. It includes counts of regular users, guests and system administrators when available, along with a copy of the installed license when present.

## Services on your deployment network

| Service | Default Compose destination | When Cloud uses it |
| --- | --- | --- |
| PostgreSQL | `postgres:5432` (TCP) | At startup and during normal use to read and save data and listen for changes. |
| Redis | `redis:6379` (TCP) | At startup and during normal use for caches, queues and live collaboration. |
| MinIO | `http://minio:9000` | Checks the bucket at startup and creates it if configured. Stores files, snapshots and installation state. |
| GoTrue | `http://gotrue:9999` | Checks the sign-in service at startup, then handles sign-in and account administration. |
| Search | `http://appflowy_search:4002` | Checks the configured service regularly, even when nobody searches. Also sends search and index management requests. An empty `APPFLOWY_SEARCH_SERVICE_URL` skips the automatic probes. |
| AI service | `http://ai:5001` | Handles chat, presentations, service checks and AI license changes. |
| Server log collector | `http://appflowy_log_collector:8088` | With the server logs profile enabled, an administrator can list, preview or export logs. [Server logs](docker-compose.md#server-logs) |

If you host PostgreSQL or Redis elsewhere, Cloud connects to the host in `APPFLOWY_DATABASE_URL` or `APPFLOWY_REDIS_URI`. [Deployment settings](../deploy.env)

- **Files and backups.** You can use regional AWS S3 or another S3-compatible store in place of MinIO. Backup archive uploads use the same endpoint by default. Set `APPFLOWY_BACKUP_S3_ENDPOINT` if you keep archives elsewhere. [Backup](BACKUP.md)
- **Search vectors.** Cloud stores these in PostgreSQL by default. With `VECTOR_STORAGE_TYPE=s3_vectors`, vector operations use the regional AWS endpoint, such as `s3vectors.us-east-1.api.aws`. If you use an AWS role, its credential service can also receive requests. [AWS S3 Vectors endpoints](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-regions-quotas.html)

When tracing a connection, check which process opened it. Worker, Search, AI, GoTrue and MCP make their own requests, and Docker pulls images. Docker’s default health check reads a local `OK` from `127.0.0.1:8000` on the `/api/health` path. Admin runs the broader mail and embedding checks. Firewall logs may also show DNS requests to your resolver or traffic through your configured proxy.
