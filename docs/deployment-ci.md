# Deployment CI

[Deployment integration](../.github/workflows/deployment-test.yml) runs on pull requests, pushes to `main`, `master`, and `release/public/**`, and manually from GitHub Actions.

Use **Deployment tests** as the required pull-request status check. It succeeds only when image preparation and every runtime job succeeds; a skipped, cancelled, or failed deployment cannot produce a passing aggregate check. Adding the workflow does not configure repository branch protection automatically.

Backup is disabled in the default installation and all three standard CI deployments. The separate,
manually triggered [Backup integration](../.github/workflows/backup-test.yml) workflow enables it
with `APPFLOWY_BACKUP_PROFILE=backup`.

## What a passing run verifies

Each job starts a fresh installation on its own disposable GitHub-hosted Linux runner:

| Job | Deployment under test |
| --- | --- |
| Compose | The root `docker-compose.yml`, with isolated test configuration. |
| Swarm | `docker-swarm/docker-stack.yml` on a single-node Swarm, with staged startup. |
| Helm | `helm/appflowy-cloud` in a real kind Kubernetes cluster, through the chart's Ingress resources and an ingress controller. |

Swarm's local public origin is `http://127.0.0.1`, avoiding Docker versions whose published ingress ports hang on IPv6 `localhost`. Requests still pass through Swarm's published ingress port and Nginx. Compose and Helm use `http://localhost`.

The workflow resolves the AppFlowy application's image tags once and passes the same immutable Linux AMD64 image digests to the runtime jobs. It does not resolve or pull the Backup image. Image identity checks compare the actual running images against the lock. Before applying those pins, CI also checks the Helm chart's source image references so an incorrect repository or tag cannot be hidden by CI overrides. Helm retains its chart's Redis image and uses a pinned ingress controller in place of Compose/Swarm's standalone Nginx; these exceptions are recorded separately. The Swarm parity check also fails if its generated files have drifted from the root Compose sources.

All runtime jobs must verify:

- Service readiness and the public API, authentication, Web, and Admin routes.
- Administrator authentication, ordinary-user provisioning, login, and workspace access.
- Document creation/readback, database creation, and row creation/edit/readback.
- Attachment upload/download with byte equality, completed Worker HTML import, and keyword search.
- Two browser clients exchanging document edits, reconnecting after Cloud replacement, and retaining content after reload and in a fresh browser context.
- Replacement of storage/application services, followed by readback of the same documents, rows, attachments, imports, and search results. New imports and search indexing must also work after recovery.
- Five checks in the final **Register through AppFlowy Web and sign in from a fresh browser** step: sign-up through Web's form, workspace access, document creation and editing, password sign-in to the same account in a fresh browser context, and readback of that same document's saved title and content. This journey uses neither an API-created user nor injected login tokens.

The default license allows one occupied seat. After every recovery and image check passes, the final step removes only this disposable CI run's verified ordinary-user fixture through the supported Admin API. It checks the recorded creation UUID, generated email, sole workspace ownership, and single membership before deletion, then requires occupied seats to drop from one to zero with the license limit unchanged. The new browser user therefore exercises normal registration within the existing license. Cleanup is restricted to GitHub-hosted CI; it does not delete accounts in the retained local test deployment.

Tests fail on timeouts and failed assertions. Registry download failures also fail the run; the workflow does not silently skip a deployment or a required application check.

## Backup acceptance

Run **Backup integration** from GitHub Actions to qualify Backup explicitly. Its `backup_image`
input selects a matching release tag or digest; the core images still come from the versioned
`deploy.env`. Those Cloud, Worker, Search, GoTrue, Admin, and Backup builds must be compatible.
The workflow sets `APPFLOWY_BACKUP_PROFILE=backup`, resolves immutable core and Backup image
digests, and installs the root Compose deployment with `docker-compose.backup.yml`. The runtime
harness writes that profile into the isolated installation's `.env` so ordinary Compose
redeployment keeps Backup enabled. An unavailable image or missing Backup capability fails this
workflow; it is separate from the standard **Deployment tests** check.

The dedicated workflow runs the core application and browser journeys plus the production Backup
process, public Admin API, and restore coordinator. Its additional checks are implemented in
[ci/backup_smoke.py](../ci/backup_smoke.py):

- Discover a ready runner with online backup, schedules, export, and ZIP restore capabilities.
- Dispatch a real one-shot schedule, verify its one-hour retention and expiry metadata, and remove
  the schedule without removing the generated recovery point.
- Check the recovery manifest's online capture interval and omitted derived-data options.
- Export a portable full ZIP, download it as an administrator, reject anonymous and ordinary-user
  downloads, and import it using the server's advertised multipart size.
- Change a database row after capture, restore the imported ZIP, and verify the captured account's
  workspace access, document marker, original row value, attachment bytes, and document/row keyword
  search. Ordinary users must still be denied administrator Backup access.
- Independently read the PostgreSQL database OID and Docker lifecycle events to verify the database
  switch and that every prior writer stopped before the first writer restarted. Check that resource
  writers were replaced, GoTrue restarted, verification-only mode ended, and persisted storage selections
  agree. A short cutover missed by HTTP polling must still have complete daemon event evidence.
- Run ordinary Compose deployment again and require the restored selections and application
  fixture to survive. The runtime harness checks the selected storage across the application
  services rather than relying only on a completed job status.
- Capture a second recovery point including the local Search cache and embeddings, restore it
  through the retained recovery path, and check that Search rebuilds correctly.
- Export and import identity-redacted, synthetic-content, and empty-content profiles against the
  migrated schema. Delete generated export artifacts, wait for catalog deletion, and require their
  downloads to become unavailable.

The lane retains actual Compose source and environment-file references under its private runtime
directory. It adds only explicit CI overrides, so Backup's generated bucket, Redis database, and
Search-directory selections remain effective after recreation. A flattened resolved Compose file
cannot provide that persistence contract. All profiles use fresh disposable data; existing local
deployment state is never a test input.

`backup-results.json` records completed checks and explicit limits. A successful result checks
document marker bytes, not a decoded CRDT-text equivalence proof; it does not prove a concurrent
HTTP/WebSocket edit fell inside the capture interval. Embedding inclusion is checked without
calling an AI provider. The schedule's expiry timestamp and manual artifact deletion are tested,
but the run does not wait one hour to prove automatic expiration. Redacted ZIPs are validated by
the real import worker; their transformed accounts are not activated and independently audited.
Coordinator interruption, rollback at every cutover phase, cross-version upgrades, and historical
customer archives require the server's separate Backup qualification suite.

The optional [Swarm](docker-swarm.md#backup-and-restore) and
[Helm](../helm/appflowy-cloud/README.md#backup-and-restore) adapters have separate deployment
constraints. Their configuration/adapter tests do not substitute for a complete restore run with
the matching adapter image. This workflow's Swarm and Helm jobs test the core application without
Backup; the Compose Backup lane does not certify Swarm or Kubernetes restore.

### Qualify a locally built Backup image

The local runner uses a new Compose project with its own credentials, named data volumes,
network, and loopback HTTP/TLS ports. It can coexist with an existing local AppFlowy installation
or Swarm. It never joins, resets, or reuses those deployments. Docker Compose 2.30+, Python,
and the packages in `docker-swarm/requirements.txt` are required. All core images selected by the
versioned Compose source and the matching Backup image must already exist in the local Docker
engine; this path records native image IDs and never pulls missing images implicitly.

From the repository root, select the completed local build and a new run identifier:

```bash
umask 077
qualification_id="backup-$(date +%Y%m%d-%H%M%S)"
backup_image="appflowyinc/appflowy_backup:your-build-tag"
qualification_runtime="ci/.local/${qualification_id}"
qualification_images="ci/.local/${qualification_id}-images.json"
qualification_artifacts="ci-artifacts/${qualification_id}"

python3 ci/images.py --local --backup --backup-image "$backup_image" --output "$qualification_images"
python3 ci/local_backup.py up --runtime "$qualification_runtime" --images "$qualification_images" --artifacts "$qualification_artifacts"
python3 ci/local_backup.py backup-test --runtime "$qualification_runtime" --images "$qualification_images" --artifacts "$qualification_artifacts"
```

`backup-test` creates the small ordinary application fixture, runs the Backup acceptance workflow
above, and writes `backup-acceptance.json` only after it passes. It does not run the browser
collaboration or registration journeys. Use the full CI workflow for those checks. A missing or
incompatible image is a failed prerequisite, not a passing restore result.

Collect diagnostics after a success or failure, then remove only that run's resources:

```bash
python3 ci/local_backup.py diagnostics --runtime "$qualification_runtime" --images "$qualification_images" --artifacts "$qualification_artifacts"
python3 ci/local_backup.py cleanup --runtime "$qualification_runtime" --images "$qualification_images" --artifacts "$qualification_artifacts"
```

The runtime must be a private child of `ci/.local/`; keep sanitized artifacts outside it.
The runner records a private ownership token and the local Docker endpoint, labels its containers,
networks and volumes, and refuses resources whose ownership differs. A remote Docker context
cannot be hidden by also setting a local `DOCKER_HOST`. It rejects operator application variables
from the Compose process environment. A new `up` requires a new runtime directory, so rerunning it
cannot overwrite credentials or the selected resources of a retained restore. Keep the runtime
directory until cleanup completes, and share only the sanitized artifact directory.
Cleanup and diagnostics use the private copy of the image lock and original source manifest saved
inside that runtime. They therefore remain available after the repository checkout or the original
image-lock file changes. They still require valid ownership and unchanged installed `.env`, Compose
sources, and CI overrides; generated restore selections remain dynamic. Tests and new deployments
always require the current checkout's fingerprint.

## Configuration and evidence

CI starts with `deploy.env`, generates temporary credentials, disables external AI/semantic indexing and SMTP, and applies settings sized for a test runner. Keyword search remains enabled; the Backup fixture keeps application indexing enabled while disabling the background embedding worker. Helm's checked-in test settings are in [ci/helm-values.yaml](../ci/helm-values.yaml).

Docker Compose **2.30 or newer** is checked before rendering. The renderer and image resolver copy
an explicit list of versioned source files to an isolated directory, excluding the operator's
`.env`, `backup-ops/`, and restored selection files. The image lock includes a source fingerprint
covering both Compose files, source environment files, Nginx inputs, and generated Swarm source;
changing any recorded deployment input requires a new lock. Rendered secrets remain private.

Compose and Swarm do not explicitly configure Redis AOF or a named Redis data volume. Helm retains its existing chart-specific Redis configuration. CI checks application recovery after service replacement, but does not require a Redis marker to survive or claim that Redis-backed queues and pending work are durable.

The standard workflow uploads an image lock and separate sanitized evidence for Compose, Swarm,
and Helm. The Backup workflow uploads its own image lock and Compose Backup evidence. Review the
application checks, browser results, recovery results, running-image evidence,
and diagnostic logs in those artifacts. `core-acceptance.json` records the completed functional and
recovery checks; `backup-results.json` records the additional Backup checks;
`backup-restore-<job>.json` records database identity, writer lifecycle, and hashed storage selections;
`fixture-cleanup.json` records the verified fixture removal. The final registration journey
produces `registration-results.json` and `registration.log`; available results and logs are
collected even if it fails. Final `acceptance.json` is written only after registration passes.
Resolved environment files, generated account credentials, exported backup ZIPs, and Kubernetes
secrets stay in the runner's temporary directory and are not uploaded.

Completed test evidence is saved before collecting optional service diagnostics. Each diagnostic command has a 30-second timeout; failures produce warnings and sanitized details in `diagnostic-failures.json` while collection continues. Single-node Swarm logs come directly from this stack's local task containers, including retained containers from service replacement. A diagnostic failure does not change the result of an application assertion or bypass a failed test step.

Python and Playwright are CI/test dependencies installed by the workflow. They are **not installation requirements** for AppFlowy: the [Swarm setup guide](docker-swarm.md) uses Docker commands directly.

## Scope of the result

A green check means that the tested commit and recorded images passed these core workflows on fresh Linux AMD64 installations. It does not certify every AppFlowy feature or every deployment environment.

External AI providers, semantic search, SMTP delivery, OAuth/SAML/LDAP/SCIM, HTTPS certificates, ARM64, upgrades from existing databases, interrupted imports, Redis queue durability, Swarm/Helm backup restoration, multi-node Swarm, and high availability require additional tests. The default kind network plugin does not enforce NetworkPolicy, so this job does not certify network isolation. A fresh-install Backup restore does not replace the release-specific migration steps in the [deployment instructions](../README.md).

The full Compose and Swarm configurations still contain optional AI; the runtime acceptance profile leaves it disabled. Helm renders its normal templates with a separate CI values overlay. Keep these test overrides explicit when extending coverage so CI cannot hide a broken deployment setting.
