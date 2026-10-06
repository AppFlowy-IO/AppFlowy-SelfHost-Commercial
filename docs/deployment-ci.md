# Deployment CI

[Deployment integration](../.github/workflows/deployment-test.yml) runs on pull requests, pushes to `main`, `master`, and `release/public/**`, and manually from GitHub Actions.

Use **Deployment tests** as the required pull-request status check. It succeeds only when image preparation and all three runtime jobs succeed; a skipped, cancelled, or failed deployment cannot produce a passing aggregate check. Adding the workflow does not configure repository branch protection automatically.

## What a passing run verifies

Each job starts a fresh installation on its own disposable GitHub-hosted Linux runner:

| Job | Deployment under test |
| --- | --- |
| Compose | The root `docker-compose.yml`, with isolated test configuration. |
| Swarm | `docker-swarm/docker-stack.yml` on a single-node Swarm, with staged startup. |
| Helm | `helm/appflowy-cloud` in a real kind Kubernetes cluster, through the chart's Ingress resources and an ingress controller. |

The workflow resolves the AppFlowy application's image tags once and passes the same immutable Linux AMD64 image digests to all three jobs. It checks the actual running images against the image lock. Before applying those pins, it also checks the Helm chart's source image references so an incorrect repository or tag cannot be hidden by CI overrides. Helm retains its chart's Redis image and uses a pinned ingress controller in place of Compose/Swarm's standalone Nginx; these exceptions are recorded separately. The Swarm parity check also fails if its generated file has drifted from the root Compose file.

All three runtime jobs must verify:

- Service readiness and the public API, authentication, Web, and Admin routes.
- Administrator authentication, ordinary-user provisioning, login, and workspace access.
- Document creation/readback, database creation, and row creation/edit/readback.
- Attachment upload/download with byte equality, completed Worker HTML import, and keyword search.
- Two browser clients exchanging document edits, reconnecting after Cloud replacement, and retaining content after reload and in a fresh browser context.
- Replacement of storage/application services, followed by readback of the same documents, rows, attachments, imports, and search results. New imports and search indexing must also work after recovery.

Tests fail on timeouts and failed assertions. Registry download failures also fail the run; the workflow does not silently skip a deployment or a required application check.

## Configuration and evidence

CI starts with `deploy.env`, generates temporary credentials, disables external AI/semantic indexing and SMTP, and applies settings sized for a test runner. It preserves each source deployment's storage configuration. Keyword search remains enabled. Helm's checked-in test settings are in [ci/helm-values.yaml](../ci/helm-values.yaml).

Compose and Swarm do not explicitly configure Redis AOF or a named Redis data volume. Helm retains its existing chart-specific Redis configuration. CI checks application recovery after service replacement, but does not require a Redis marker to survive or claim that Redis-backed queues and pending work are durable.

Each run uploads an image lock and separate sanitized evidence for Compose, Swarm, and Helm. Review the application checks, browser results, recovery results, running-image evidence, and diagnostic logs in those artifacts. Resolved environment files, rendered credentials, and Kubernetes secrets stay in the runner's temporary directory and are not uploaded.

Python and Playwright are CI/test dependencies installed by the workflow. They are **not installation requirements** for AppFlowy: the [Swarm setup guide](docker-swarm.md) uses Docker commands directly.

## Scope of the result

A green check means that the tested commit and recorded images passed these core workflows on fresh Linux AMD64 installations. It does not certify every AppFlowy feature or every deployment environment.

External AI providers, semantic search, SMTP delivery, OAuth/SAML/LDAP/SCIM, HTTPS certificates, ARM64, upgrades from existing databases, interrupted imports, Redis queue durability, backup restoration, multi-node Swarm, and high availability require additional tests. The default kind network plugin does not enforce NetworkPolicy, so this job does not certify network isolation. A fresh-install test does not replace the release-specific migration steps in the [deployment instructions](../README.md).

The full Compose and Swarm configurations still contain optional AI; the runtime acceptance profile leaves it disabled. Helm renders its normal templates with a separate CI values overlay. Keep these test overrides explicit when extending coverage so CI cannot hide a broken deployment setting.
