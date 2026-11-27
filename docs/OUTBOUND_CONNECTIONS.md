# Outbound connections from AppFlowy Cloud

[Documentation](README.md)

Without a license, a fresh `appflowy_cloud` container contacts only the other services of your deployment, at startup and while idle. A connection to a host outside your network starts only when someone uses a feature that needs one or an administrator sets up a provider, and installing a commercial license adds regular check-ins with the license issuer. By contrast, the bundled MinIO checks `dl.min.io` for updates every time it starts, until you [turn that off](#example-turn-off-minios-update-check).

This guide covers Cloud and the other containers of the Compose deployment: what starts each connection, where it goes and how to keep it off. It describes self-hosted release 0.22.1, whose server images are tagged `0.22.1`. To check your Cloud image, run `docker compose images appflowy_cloud` in your Compose directory. Images `0.22.0` and earlier make more of these connections by default; see [releases before 0.22.1](#releases-before-0221).

Connections to public web hosts use HTTPS on TCP port 443 unless a configured URL names another port. Mail and LDAP use the ports you configure.

## How the switches work

The switches for PDF images, the email domain list, mail and the billing relay are in **Admin → Environment**, named after their environment variables. AI has **Enable AI Features** on Admin’s AI page, and desktop updates have their own **Desktop updates** page.

- **Order.** A value saved in Admin decides. Without one, Cloud uses the environment variable of the same name, read when the container starts, and then the default given below. AI uses `AI_ENABLED`, and desktop updates have no variable. **Reset** deletes the saved value.
- **Environment variables.** `docker-compose.yml` passes `AI_ENABLED` to Cloud, but not the four `APPFLOWY_*` switches or most other Cloud variables in this guide. To set one, add it under `appflowy_cloud` in an override file, like the [MinIO example](#example-turn-off-minios-update-check). An Admin setting needs no such change.
- **Timing.** The Cloud replica that saves a value applies it at once. Other Cloud replicas, the Worker and Search follow within 60 seconds. Requests already running finish with the value they read.
- **Failures.** While the saved settings cannot be read, for example during a database outage, each feature stays off for that attempt. Cloud keeps the AI setting it last confirmed.
- **Invalid values.** The on/off variables accept `true`, `false`, `1` and `0`, and the list source accepts an `http` or `https` URL. Any other value stops Cloud at startup with an error that names the variable. An invalid `AI_ENABLED` keeps AI off and logs an error instead.

## Features that contact other hosts

| Feature | What starts a connection? | Where does it go? | Default in 0.22.1, and how to keep it off |
| --- | --- | --- | --- |
| Desktop updates | A desktop app checks for an update; the request needs no sign-in. Cloud reuses a successful answer for 15 minutes. | `api.github.com`. If the release has an update manifest, also `github.com` and its download host, such as `release-assets.githubusercontent.com`. The app downloads installers itself. | **Off.** **Admin → Desktop updates → Enable auto update** turns lookups on. While it is off, Cloud contacts no GitHub host and still tells older desktops when they must upgrade. |
| Images in PDF exports | An export that includes images refers to an image by URL. Images uploaded to the exported workspace are read from storage instead. | The image’s host, and up to 3 redirects. Private addresses are refused, and no proxy is used. | **Off.** `APPFLOWY_PDF_EXPORT_REMOTE_IMAGES_ENABLED`. While it is off, these images print as placeholders, including uploads from other workspaces and other URLs on your own host. The view export’s `include_images=false` skips all images. |
| Disposable email domain list | An administrator imports the list. Startup and sign-ups never download it. | The configured source. Redirects are refused. | **No source,** so an import reports an error. To allow imports, set `APPFLOWY_DISPOSABLE_DOMAINS_URL` to your mirror or the [upstream list](https://raw.githubusercontent.com/disposable-email-domains/disposable-email-domains/main/disposable_email_blocklist.conf). |
| Email from Cloud and the Worker | Workspace and guest invitations, guest approvals, access requests, and workspace export and import results. Mention emails too, once `APPFLOWY_NOTIFICATION_ENABLE_EMAIL=true` is set for Cloud. Before some invitations, guest approvals and exports, Cloud checks that it can reach the relay. Admin’s mail and overall health checks test it too. | The relay in `APPFLOWY_MAILER_SMTP_HOST` and `APPFLOWY_MAILER_SMTP_PORT`. | **Nothing is sent** until the SMTP settings are complete, and the example password of `deploy.env` counts as unset. To keep your settings but stop mail, turn off `APPFLOWY_MAILER_ENABLED` in Admin, which applies to Cloud and the Worker. |
| AI models | Cloud calls a model for search summaries, embeddings, presentation media, meeting transcription and Admin’s model tests. Chat and writing tools go through the `ai` container, and indexing through `appflowy_search`. | Only providers configured in Admin’s AI pages or `.env`, such as `api.openai.com`, `api.anthropic.com`, `generativelanguage.googleapis.com` and `dashscope.aliyuncs.com`. Azure OpenAI, DeepSeek, custom and local providers use the URL you configure. | **On, with no provider configured.** Turning off **Enable AI Features** on Admin’s AI page stops Cloud, Search and the AI service from calling providers, including Admin’s tests. `AI_ENABLED=false` in `.env` reaches only Cloud, so Search keeps calling a configured embedding model. [AI models](MODEL_CONFIG.md) |
| AI Meeting with AssemblyAI | With AI on and a key in Admin or `ASSEMBLYAI_API_KEY`, Cloud uploads recordings, fetches transcripts and gets a token for live audio. The app opens the live audio stream itself. **Test connection** can use a key and endpoints you haven’t saved yet. | `api.assemblyai.com` and `streaming.assemblyai.com`, as set in `ASSEMBLYAI_API_BASE` and `ASSEMBLYAI_STREAMING_API_BASE`, or the endpoints saved in Admin’s meeting settings. | **No key is shipped.** Turning off AI stops these requests and the test. [AI Meeting](AI_MEETING_CONFIG.md) |
| LDAP sign-in | Someone signs in through an enabled directory. An administrator’s **Test connection** contacts the directory **even while it is disabled**. | Your LDAP server, usually TCP 389 for LDAP or StartTLS, or 636 for LDAPS. | **No directory is configured.** Disabling a directory stops sign-in through it, and saving one contacts nothing. [LDAP setup](LDAP.md) |
| Connected apps | A member links an account or uses a connected app. Cloud refreshes a token only when a request needs it. Disconnecting deletes only the local connection. | Google Drive and Calendar use `oauth2.googleapis.com` and `www.googleapis.com`. Slack uses `slack.com`, Notion uses `api.notion.com`, and GitHub uses `github.com` and `api.github.com`. | **No provider is enabled.** Only providers enabled in Admin receive requests. [Connections](CONNECTION.md) |
| Apple account deletion | Someone deletes their own Apple-linked account, and their app sends its Apple token. | `appleid.apple.com` | **Off.** Cloud needs both `APPFLOWY_APPLE_OAUTH_CLIENT_ID` and `APPFLOWY_APPLE_OAUTH_CLIENT_SECRET`, which Docker Compose doesn’t pass to it. The account is deleted locally either way. |

Self-hosted Cloud never sends mobile push notifications through Firebase, even with a service account key.

## When does Cloud contact AppFlowy about a license?

**Billing pages in Admin.** Admin’s license and upgrade pages reach AppFlowy Billing at `beta.appflowy.cloud` through Cloud’s `/api/commercial/billing/` routes. Cloud relays these requests when you verify a commercial account, look up plans, manage a subscription, redeem an invitation or manage registered devices. The routes need no AppFlowy session, so while the relay is on, anyone who can reach your server can make it contact AppFlowy Billing. The relay is on by default. If you don’t use these pages, turn off `APPFLOWY_COMMERCIAL_BILLING_ENABLED` in **Admin → Environment**; the routes then answer that the feature is unavailable.

**Installing or checking a license.** Cloud contacts the issuer named in the signed license, normally `beta.appflowy.cloud`:

- When an administrator installs a license, Cloud binds the installation. It sends the license ID, the machine’s hostname, the host of `APPFLOWY_BASE_URL`, a machine fingerprint and installation identifiers. The address it reports is `0.0.0.0`, unless `APPFLOWY_IP_SERVICES` in Cloud’s environment lists IP lookup services, comma-separated, for Cloud to ask in order. `APPFLOWY_DISABLE_IP_DETECTION=true` keeps that lookup off whatever the list says.
- When the license’s next check is due, and when an administrator refreshes it, Cloud verifies the license with its ID, the hostname, the fingerprint and the installation ID. A check that is already due runs at startup, and failed checks are retried with growing delays.

**Usage reports.** Within 30 minutes of a valid license being installed, Cloud enrolls the installation with the issuer, using the signed license and proof of the installation’s identity. An enrolled installation reports right after enrolling and then every 24 hours, even when nobody signs in. Reporting continues after the license expires or is removed. Each report holds the installation ID, configured host, machine hostname, server version, collection time and status, the counts of regular users, guests and system administrators when available, and a copy of the installed license.

Without a license or an earlier enrollment, Cloud makes no license checks or usage reports. Neither has a switch.

## Services on your deployment network

| Service | Default Compose destination | When Cloud uses it |
| --- | --- | --- |
| PostgreSQL | `postgres:5432` (TCP) | At startup and during normal use, to read and save data and listen for changes. |
| Redis | `redis:6379` (TCP) | At startup and during normal use, for caches, queues and live collaboration. |
| MinIO | `http://minio:9000` | At every start, Cloud creates its bucket if it is missing and reads the bucket’s settings. Cloud doesn’t start while MinIO is unreachable. It stores files, snapshots and installation state there. |
| GoTrue | `http://gotrue:9999` | One check at startup, then sign-in and account administration. |
| Search | `http://appflowy_search:4002` | A health check right after startup and every 10 seconds, even when nobody searches, and search and indexing requests. An empty `APPFLOWY_SEARCH_SERVICE_URL` turns the checks off. |
| AI service | `http://ai:5001` | AI requests, a check when someone creates a Chat page, presentations and license changes. Cloud never polls it. |
| Server log collector | `http://appflowy_log_collector:8088` | With the server logs profile enabled, when an administrator lists, previews or exports logs. [Server logs](docker-compose.md#server-logs) |

If you host PostgreSQL or Redis elsewhere, Cloud connects to the host in `APPFLOWY_DATABASE_URL` or `APPFLOWY_REDIS_URI`. [Deployment settings](../deploy.env)

- **Files and backups.** You can use regional AWS S3 or another S3-compatible store in place of MinIO. Backup keeps its archives in a private bucket in the same storage. [Backup](BACKUP.md)
- **Search vectors.** Cloud and Search store them in PostgreSQL by default. With `VECTOR_STORAGE_TYPE=s3_vectors`, they use the regional AWS endpoint, such as `s3vectors.us-east-1.api.aws`. Without `APPFLOWY_S3_VECTOR_ACCESS_KEY` and `APPFLOWY_S3_VECTOR_SECRET_KEY`, the AWS SDK looks for credentials itself and can contact AWS STS or the instance metadata service at `169.254.169.254`. [AWS S3 Vectors endpoints](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-regions-quotas.html)
- **Outbound proxies.** Cloud’s web requests use `HTTP_PROXY` and `HTTPS_PROXY` when they are set in its environment, except image downloads for PDF exports. Add the services above to `NO_PROXY` so that requests to them stay on your network.

## Other containers

Each container opens its own connections, and Docker contacts its registry, normally Docker Hub, when it pulls an image.

| Container | What starts a connection? | Where does it go? | How to keep it off |
| --- | --- | --- | --- |
| `minio` | Every start: MinIO checks for a newer release. | `dl.min.io` | Set `MINIO_UPDATE=off`, as in the [example below](#example-turn-off-minios-update-check). |
| `gotrue` | Sign-in email, such as magic links and password recovery, sign-in through an OAuth or SAML provider you enable, and the metadata URL of a SAML provider an administrator adds. | The relay in `GOTRUE_SMTP_HOST`, and your sign-in providers. | Leave `GOTRUE_SMTP_HOST` empty to send no email. The 0.22.1 image also sends none while `.env` still holds the example SMTP block of `deploy.env`: `smtp.gmail.com` with the example user and password. OAuth and SAML providers stay off until you enable them. |
| `ai` | AI requests that Cloud forwards, such as chat and writing tools, and web search once it is turned on. | Your configured AI providers, including the image URLs they return. Web search uses Brave Search, Tavily or DuckDuckGo and fetches the pages it finds. | Turn off **Enable AI Features** in Admin. Web search is off until it is turned on in Admin’s AI tools settings. |
| `appflowy_search` | Indexing and search create embeddings. | Your configured embedding provider. | Turn off **Enable AI Features** in Admin. |
| `appflowy_worker` | Workspace export and import results sent by email. | The `APPFLOWY_MAILER_SMTP_*` relay. | As for [email from Cloud](#features-that-contact-other-hosts). |
| `appflowy_mcp` | An AI app that identifies itself with a metadata URL connects, or a connection list shows one. The first sign-in steps of an AI app need no AppFlowy account. | The app’s metadata URL. | Turn off MCP on Admin’s MCP page. MCP also stays off without a One, Team or Enterprise license. [Turning MCP off or on](docker-compose.md#turning-mcp-off-or-on) |
| `admin_frontend` | An administrator tests a SAML metadata URL. | That URL and up to 3 redirects. | The test runs only when an administrator starts it. |
| `appflowy_backup` | With the backup profile enabled, scheduled and manual backups upload archives. | Your object storage, in a private backup bucket. | The backup profile is off by default. [Backup](BACKUP.md) |

### Example: turn off MinIO’s update check

The bundled MinIO asks `dl.min.io` for a newer release every time it starts. To turn that off, save this as `compose.offline.yml` alongside `docker-compose.yml`.

```yaml
services:
  minio:
    environment:
      MINIO_UPDATE: "off"
```

Append `:compose.offline.yml` to the existing `COMPOSE_FILE` value in `.env`, then run `docker compose up -d minio` to apply it. To set one of Cloud’s variables the same way, add an `appflowy_cloud` entry with its own `environment` to this file and run `docker compose up -d appflowy_cloud`.

## Reading a firewall entry

Start with the container that opened the connection. Your firewall may also record the DNS lookup, or a connection to your proxy instead of the destination.

- **GitHub from `appflowy_cloud`.** Automatic updates are on in **Admin → Desktop updates**, or a member uses a connected GitHub account. If the connection came from a user’s computer, the desktop app may be checking its own update feed or downloading an installer. Desktop `0.14.0` is one version that reads its feed directly from GitHub. [Desktop 0.14.0 update feed](https://github.com/AppFlowy-IO/AppFlowy/blob/5cf3a365dec0d59f64bad1ee4bb1050471a39b93/frontend/appflowy_flutter/lib/startup/tasks/auto_update_task.dart#L20-L21)
- **`beta.appflowy.cloud` from a server without a license.** Someone opened Admin’s license or upgrade pages, or another client called `/api/commercial/billing/`. See [billing pages in Admin](#when-does-cloud-contact-appflowy-about-a-license).
- **`dl.min.io` when the deployment starts.** This is MinIO’s update check; see the [example](#example-turn-off-minios-update-check).
- **GitHub, Pixabay or Medium from a user’s computer after an email.** AppFlowy’s emails load their images from `raw.githubusercontent.com`, and access request emails can show default icons from `cdn.pixabay.com` and `miro.medium.com`. The recipient’s mail app fetches them, not your server.
- **A mail relay or AI provider while everyone is idle.** Check whether an administrator opened Admin’s health page. While mail and AI are on, it tests the mail relay and sends the words `health check` to the configured embedding model. Docker’s scheduled health check only reads `/api/health` at `127.0.0.1:8000`, which contacts nothing.

## Releases before 0.22.1

Images `0.22.0` and earlier make these connections by default:

- **Desktop updates.** Cloud looks up a release on `api.github.com` whenever a desktop asks, even with automatic updates turned off.
- **PDF exports** download every image URL in the exported content, uploads included, and don’t check whether an address is private.
- **The disposable email domain list** is imported from `raw.githubusercontent.com` unless `APPFLOWY_DISPOSABLE_DOMAINS_URL` names another source, and redirects are followed.
- **Email.** With the example SMTP block of `deploy.env`, Cloud connects to `smtp.gmail.com:465` with the example credentials, for example for an access request or an invitation to an existing account. The Worker does the same for import results.
- **AI.** Admin’s overall health check sends the words `health check` to a configured embedding model, and the vision and AssemblyAI tests contact their providers, even with AI turned off.
- **Apple.** Cloud asks Apple to revoke a supplied token even without Apple credentials.
- **Billing.** The billing relay has no switch.
- **License binding** asks `checkip.amazonaws.com`, `api.ipify.org`, `ipv4.icanhazip.com` and `ifconfig.me` in turn for the server’s public address. In Cloud’s environment, `APPFLOWY_IP_SERVICES` replaces that list, and `APPFLOWY_DISABLE_IP_DETECTION=true` turns the lookup off.
- **Web search.** The AI service offers web search through DuckDuckGo, and web fetch, unless `WEB_SEARCH_ENABLED=false` is set for it.
- **GoTrue mail.** With the example SMTP block of `deploy.env`, a magic-link or recovery request makes GoTrue contact `smtp.gmail.com`.
- **MCP.** Connection lists can fetch AI apps’ metadata documents while MCP is off.

Older images differ further:

- **Before 0.22.0**, an enrolled installation sends a usage report at startup and every 30 minutes.
- **Up to 0.21.8**, Cloud’s commercial account token exchange sent the requesting account’s email and the installation’s GoTrue JWT signing secret to `beta.appflowy.cloud`. The 0.21.9 image omits it. [Cloud 0.21.9 image build](https://github.com/AppFlowy-IO/AppFlowy-Docker-CI/actions/runs/44224795649)

After you upgrade to 0.22.1, desktop update lookups, image downloads in PDF exports, disposable list imports, the license IP lookup and web search stay off unless a saved Admin value or an environment variable turns them on.
