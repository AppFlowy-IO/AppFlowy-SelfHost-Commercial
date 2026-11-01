# Release image updates

Self-hosters should use the deployment files from one AppFlowy self-hosted release.
The AppFlowy team selects the component images; operators do not need to give Web,
Cloud, GoTrue, and the other services the same version number.

## Automatic update PRs

[Update release image pins](../.github/workflows/update-release-images.yml) receives
`selfhost-images-published` repository dispatches from these publishers:

| Publisher | When it notifies | Compose services it can update |
| --- | --- | --- |
| [AppFlowy-Docker-CI](https://github.com/AppFlowy-IO/AppFlowy-Docker-CI/actions/workflows/self_host_cloud_docker.yml) | After every selected image's version manifest is successfully published | Cloud and Worker together, plus selected Search, GoTrue, AI, and Backup images |
| [AppFlowy-Web](https://github.com/AppFlowy-IO/AppFlowy-Web/releases) | After Web's version manifest is published, and when a GitHub release is published | Web |

**Tags ending in `_test` never dispatch an update.** The receiving workflow and its
update script also reject these tags before accessing the registry or modifying files.
The normal test-image publishing workflows remain available.

For a real version tag, the receiver:

1. Reads the default branch's deployment files, without loading an operator's `.env`.
2. Resolves each notified image's immutable multi-platform index digest. Both
   `linux/amd64` and `linux/arm64` must be available before an update can be proposed.
3. Changes the selected Compose images to `repository:version@sha256:digest`, updates
   the matching Helm tag/digest, and regenerates the Swarm files.
4. Opens or refreshes `automation/image-updates/<source>-<tag>[-<services>]` as a PR. The version
   remains readable, while the digest prevents tag replacement from changing a deployment.

Repeated publication/release notifications for the same image selection reuse the same PR.
Cloud branches also identify the selected services, so a GoTrue-only publication cannot
replace an open Cloud/Worker/Search update for the same version. Notifications older than
the selected services' current versions are ignored. Reusing an already pinned version
with different image contents fails; publish a new version instead.

The PR does not merge itself, publish a self-hosted release, or deploy an installation.
Review the deployment results, supported client versions, and migration requirements
before merging. Optional features and upgrades still need their release-specific checks.
The [deployment CI coverage](deployment-ci.md) describes the runtime checks and limitations;
the image-index check does not substitute for ARM64 runtime qualification.

The automation advances only the services identified by the publisher. It does not
guess versions for other services or certify an initial compatibility baseline. Before
advertising a complete supported release bundle, pin and qualify its remaining images too.
Once a service has a literal image pin, legacy `*_VERSION` values in `.env` no longer
override that reference. Use an explicit Compose override for development qualification.

## Deployment checks

On image-update PRs, both deployment workflows use the images configured in the proposed
Compose files. They omit the standard `0.20.0` server/Backup and `0.19.30` Web baseline
overrides, so a green result cannot be produced by substituting different component images.
Other branches use that fixed qualification baseline.

If a Web GitHub release is published before its Docker build completes, its first update
attempt can fail because the image is not available yet. The successful Web manifest job
sends the notification again. An unavailable image never falls back to `latest`.

## Installation of the automation

The receiver must be on this repository's default branch before enabling the publisher
changes. GitHub only delivers `repository_dispatch` workflows from the default branch.
Merge the accompanying changes in AppFlowy-Docker-CI and AppFlowy-Web afterward.

All three workflows use the existing organization secret `PUBLIC_REPO_TOKEN`. Its token
must have access to AppFlowy-SelfHost-Commercial with Contents write (dispatch and branches)
and Pull requests write. A classic token for these public repositories can use `public_repo`;
a fine-grained token or GitHub App can grant the repository permissions above.
Using an App/PAT token for PR creation allows normal deployment checks to start automatically.
The workflows never print the token or require a local credential to be copied into GitHub.

For a missing notification, use **Actions → Update release image pins → Run workflow**.
Choose `cloud` or `web` and enter the published tag. Cloud defaults to Cloud, Worker and
Search; override the service list to match the images actually published, for example
`appflowy_backup` for a Backup-only release. Manual `_test` requests are also ignored.
