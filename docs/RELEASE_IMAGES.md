# Release image updates

Self-hosters should use the deployment files from one AppFlowy self-hosted release.
The AppFlowy team selects the component images; operators do not need to give Web,
Cloud, GoTrue, and the other services the same version number.

## Automatic update PRs

[Update release image pins](../.github/workflows/update-release-images.yml) receives
`selfhost-images-published` repository dispatches from these publishers:

| Publisher | When it notifies | Compose services it can update |
| --- | --- | --- |
| [AppFlowy-Docker-CI](https://github.com/AppFlowy-IO/AppFlowy-Docker-CI/actions/workflows/self_host_cloud_docker.yml) | After every selected image's version manifest is successfully published | Cloud and Worker together, plus selected Search, MCP, GoTrue, AI, Backup, and log collector images |
| [AppFlowy-Web](https://github.com/AppFlowy-IO/AppFlowy-Web/releases) | After Web's version manifest is published, and when a GitHub release is published | Web |
| [Admin frontend Docker CI](https://github.com/AppFlowy-IO/AppFlowy-Docker-CI/actions/workflows/admin_frontend_docker.yml) | After public version manifests are published with both AMD64 and ARM64 enabled | Admin frontend |

Admin notifications use the separate `admin` source and update only the public
`appflowyinc/admin_frontend` image. Set `push_public` and `build_arm64` to `true` in
the Admin build; premium-only and AMD64-only builds do not request deployment updates.
The `tag_latest` option does not affect version-pin updates.

**Tags ending in `_test` never dispatch an update.** The receiving workflow and its
update script also reject these tags before accessing the registry or modifying files.
The normal test-image publishing workflows remain available.

For a real version tag, the receiver:

1. Reads the default branch's deployment files, without loading an operator's `.env`.
2. Resolves each notified image's immutable multi-platform index digest. Both
   `linux/amd64` and `linux/arm64` must be available before an update can be proposed.
3. Changes the selected Compose images to `repository:version@sha256:digest`, updates
   the matching Helm tag/digest, and regenerates the Swarm files.
   Existing version overrides such as `GOTRUE_VERSION` and `APPFLOWY_MCP_VERSION` keep the new pin
   as their default. The optional log collector exists only in Compose: its pin becomes the default inside
   `${APPFLOWY_SERVER_LOGS_IMAGE:-…}`, so an installation's own image still wins, and no Helm
   or Swarm file changes for it.
4. Opens or refreshes `automation/image-updates/<source>-<tag>[-<services>]` as a PR. The version
   remains readable, while the digest prevents tag replacement from changing a deployment.
5. Enables squash auto-merge for that PR's exact head commit. GitHub waits for the required
   **Deployment tests** and **Backup tests** checks before merging it. A PR that changes the
   `appflowy_mcp` image is left for a reviewer instead; see [MCP copies](#mcp-copies).
6. After the merge, the [self-hosted upgrade check](deployment-ci.md#self-hosted-upgrade-check)
   upgrades the team's server to the new pins and checks every service.

Repeated publication/release notifications for the same image selection reuse the same PR.
Cloud branches also identify the selected services, so a GoTrue-only publication cannot
replace an open Cloud/Worker/Search update for the same version. Notifications older than
the selected services' current versions are ignored. Reusing an already pinned version
with different image contents fails; publish a new version instead.

Only PRs opened or refreshed by the image-update workflow opt into auto-merge. Other PRs
remain manual unless a maintainer enables auto-merge individually. A merge does not publish
a self-hosted release or deploy self-hosters' installations. Supported client versions, migration
requirements, optional features, and upgrades still need their release-specific checks.
The [deployment CI coverage](deployment-ci.md) describes the runtime checks and limitations;
the image-index check does not substitute for ARM64 runtime qualification.

The automation advances only the services identified by the publisher. It does not
guess versions for other services or certify an initial compatibility baseline. Before
advertising a complete supported release bundle, pin and qualify its remaining images too.
Once a service has a literal image pin, legacy `*_VERSION` values in `.env` no longer
override that reference. Use an explicit Compose override for development qualification.

## Deployment checks

Web-image-only updates run source validation, Swarm parity, Helm lint/rendering tests,
unit tests, and image resolution, without starting deployments or running integration tests.
The detector compares the actual Compose, Swarm, and Helm configuration and requires all
three Web pins to agree. Documentation can accompany a Web image update. A change to any
other service, deployment setting, or code still requires full integration. This applies to
the PR and its post-merge push, regardless of the branch name.

Both integration workflows use the images configured in the proposed Compose files on all
branches. A manual Backup run may override its Backup image to qualify a matching build.
Incompatible Cloud, MCP or Backup images must be corrected at publication.

Cloud releases can retain the existing Backup pin when its code and migration catalog
are unchanged. Backup does not need rebuilding for every server image update.
When Cloud adds migrations, publish Backup from the same Cloud commit and include its
`appflowy_backup` pin in the deployment update. Backup embeds the migration catalog and
rejects restoring a database with newer migrations. Updating Cloud alone can therefore pass
the core deployment checks while failing Backup restore acceptance. Re-running the same
image pair cannot resolve that incompatibility.

If a Web GitHub release is published before its Docker build completes, its first update
attempt can fail because the image is not available yet. The successful Web manifest job
sends the notification again. An unavailable image never falls back to `latest`.

## MCP copies

MCP's routes and settings, and the guides that describe them, follow AppFlowy-Cloud-Premium files
and must match the `appflowy_mcp` image that serves them. CI does not compare the two repositories.
These are the copies, with the server source when it is not the same path
(`MCP_COPIES` in [ci/update_release_images.py](../ci/update_release_images.py) lists the same):

- `docker/nginx/nginx.conf`: the MCP locations (server: `nginx/nginx.conf`).
- `helm/appflowy-cloud/templates/ingress-mcp.yaml`: the whole file.
- `helm/appflowy-cloud/templates/_helpers.tpl`: the `appflowy.mcp.*` helpers.
- `helm/appflowy-cloud/templates/appflowy-mcp/deployment.yaml`: the whole file.
- `helm/appflowy-cloud/templates/appflowy-mcp/service.yaml`: the whole file.
- `helm/appflowy-cloud/templates/observability/servicemonitor-appflowy-mcp.yaml`: the whole file.
- `helm/appflowy-cloud/values.yaml`: `appflowy-mcp` and `ingress.mcp`.
- `docker-compose.yml`: the `appflowy_mcp` environment.
- `deploy.env`: the MCP section.
- `docs/docker-compose.md`: the MCP route table and settings (server: the MCP locations in
  `nginx/nginx.conf` and `deploy.env`'s MCP section).
- `helm/appflowy-cloud/README.md`: the MCP Ingress path table and `appflowy-mcp` rows (server:
  `ingress-mcp.yaml` and `values.yaml`'s `appflowy-mcp`).

When an update PR changes the `appflowy_mcp` image, its description lists these files: compare
them with the server commit that the publisher run built, not the server tag with the same number.
Such a PR does not enable auto-merge. Port the server's changes in a separate PR against the
default branch and merge it before the image-update PR. Do not push the port to the image-update
branch: whenever the publisher notifies the same images again, the workflow rebuilds that branch
from the default branch and force-pushes it, which drops every commit added by hand. Once the port
has merged, update the image-update PR from the default branch so its checks run with the ported
files, then merge it.

The commercial MCP `0.21.8` image was built from
[server commit `39502be`](https://github.com/AppFlowy-IO/AppFlowy-Cloud-Premium/commit/39502be94d3f31f12266d6a62e49ee917c901c63).
Use the previous pinned image's build commit as the baseline for each update.

### Deliberate differences from the server

`service.yaml`, the ServiceMonitor and the bodies of the Nginx MCP locations match the server.
Everything else differs only as follows:

- **Published image.** `docker-compose.yml` runs the published `appflowyinc/appflowy_mcp` image and
  has no `build` section; the server's Compose file names `appflowyinc/appflowy_mcp_premium` and
  builds it from its source tree.
- **GoTrue audience.** The commercial defaults retain GoTrue's existing empty audience.
  MCP receives the two-quote setting for that exact claim. The pinned MCP build supports this setting.
- **Backup selection.** MCP takes its bucket and Redis database from Backup's restore selection,
  like the other writers: Compose through the `appflowy_mcp` `env_file` entries (which the Swarm
  generator turns into environment entries), the chart through `appflowy.backup.bucketSelection`
  and `appflowy.backup.redisSelection`. The server sets the bucket and Redis address directly.
- **Waiting for Cloud.** MCP starts once Cloud is ready: Compose waits for `appflowy_cloud` to be
  `service_healthy`, and the chart runs the `appflowy.waitForCloud` init container. The server
  starts MCP once Cloud has started and lets it restart until Cloud's migrations exist.
- **Bundled Search.** This chart deploys Search, so MCP's `APPFLOWY_SEARCH_SERVICE_URL` names the
  bundled Search Service while `appflowy-search.enabled` (empty otherwise), with Cloud's
  `searchRequestTimeoutSecs`. The server's chart has no Search, only
  `appflowy-mcp.config.searchServiceUrl`.
- **No encoded-collab cache or S3 timeouts.** No service here gets the server's Redis cache
  ceiling, encoded-collab memory and disk cache settings (nor the chart's cache volume), or S3
  timeout settings, so MCP does not either. The chart reads `global.s3.presignedUrlEndpoint`
  directly; it has no `appflowy.s3.presignedUrlEndpoint` helper.
- **Trusted proxies and browser origins.** Compose and Swarm give Nginx and MCP a dedicated
  proxy subnet with a network-scoped alias. The chart trusts the socket peer until the operator
  supplies the ingress controller's source CIDRs. Browser CORS defaults to the public Web origin.
- **One MCP origin.** `appflowy-mcp.config.publicBaseUrl` is the chart's only source of the MCP
  origin (`appflowy.mcp.baseUrl`); with `appflowy-mcp.enabled=false` it names an MCP service
  deployed elsewhere. The server's `appflowy.mcp.advertisedUrl` helper and
  `admin-frontend.config.mcpBaseUrl` are not copied. Compose and Swarm use the API origin when an
  older environment file omits
  `APPFLOWY_MCP_BASE_URL`. An explicit empty value suppresses discovery.
- **One audit fallback.** The chart gives Cloud and MCP the same
  `appflowy-cloud.config.auditEnable`; the server's chart has a separate
  `appflowy-mcp.config.auditEnable`.
- **Swarm Backup.** Its overlay keeps MCP at zero replicas and suppresses discovery because
  the supported Swarm adapter cannot drain MCP or update its restore selections.
- **No inline password form.** No file here sets `MCP_OAUTH_INLINE_FORM`; MCP keeps that
  development-only form off while it is unset, as the server's `false` does.
- **Guides and comments.** The server has no Compose guide and no MCP rows in its chart README, so
  `docs/docker-compose.md`, `helm/appflowy-cloud/README.md` and `deploy.env`'s MCP section describe
  these deployments in their own words. Comments name this repository's tests where the server's
  name `script/ci/check_mcp_edge.py` or its Rust tests, and the Ingress comment says "MCP" where
  the server's says "AI apps (MCP)".

## Installation of the automation

The receiver must be on this repository's default branch before enabling the publisher
changes. GitHub only delivers `repository_dispatch` workflows from the default branch.
Merge the accompanying changes in AppFlowy-Docker-CI and AppFlowy-Web afterward.

The publisher and receiver workflows use the existing organization secret `PUBLIC_REPO_TOKEN`.
Its token must have access to AppFlowy-SelfHost-Commercial with Contents write (dispatch and branches)
and Pull requests write. A classic token for these public repositories can use `public_repo`;
a fine-grained token or GitHub App can grant the repository permissions above.
Using an App/PAT token for PR creation allows normal deployment checks to start automatically.
The workflows never print the token or require a local credential to be copied into GitHub.

Repository settings must allow auto-merge. The `main` branch must require **Deployment tests**
and **Backup tests** from GitHub Actions, including for administrators. Both are always-running
aggregate checks: documentation and Web image updates get explicit, validated skips; failed
change detection or a missing, failed, or cancelled required test cannot satisfy the gates.
Configure these requirements before enabling auto-merge in the publisher workflow, so a PR
cannot merge while its first CI run is still being scheduled.

For a missing notification, use **Actions → Update release image pins → Run workflow**.
Choose `cloud`, `web`, or `admin` and enter the published tag. Admin defaults to
`admin_frontend`. Cloud defaults to Cloud, Worker, Search and MCP. Override the service
list to match the images actually published, for example
`appflowy_backup` for a Backup-only release. Manual `_test` requests are also ignored.
