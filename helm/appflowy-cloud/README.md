# AppFlowy Cloud Helm Chart

This chart bundles the AppFlowy Cloud services (API, auth, web, admin, worker, search and AI) with PostgreSQL, Redis and MinIO. Configure credentials and TLS before a public deployment. The repository's deployment CI installs the chart in a disposable kind cluster using [ci/helm-values.yaml](../../ci/helm-values.yaml), then exercises the same application tests as Compose and Swarm.

## What is deployed

- AppFlowy Cloud API (main backend)
- AppFlowy Web 
- Admin console
- GoTrue (auth server)
- AppFlowy Worker (background jobs)
- AppFlowy Search with a persistent keyword index
- AppFlowy AI 
- PostgreSQL (pgvector), Redis, and MinIO
- Optional kube-prometheus-stack (Prometheus Operator + Grafana) and ServiceMonitors when you enable monitoring

## Prerequisites

1. Kubernetes 1.25+ cluster (minikube is the easiest for local work).
2. Helm 3.10+.
3. A storage class that supports PVCs (minikube provides `standard`).
4. An Ingress controller (the nginx ingress addon is enabled in the local flow).
5. cert-manager (optional) if you want automatic TLS.
6. Prometheus Operator / kube-prometheus-stack (optional) if you want ServiceMonitors + Grafana.

## Required values in `values.yaml` (production)

Before deploying to a real cluster, set these in `helm/appflowy-cloud/values.yaml` (or provide them via a separate
override file or existing Kubernetes Secrets):

| Key | When it is required | Why it matters |
| --- | --- | --- |
| `global.domain` | Always | Public hostname used for ingress routing and redirect URLs. |
| `global.jwt.secret` (or `global.jwt.existingSecret`) | Always | Shared JWT signing secret for GoTrue + AppFlowy Cloud. |
| `gotrue.config.adminPassword` | Always | Default admin login password for the console. |
| `postgresql.auth.postgresPassword` | When `postgresql.enabled=true` | Sets the Bitnami Postgres password used by the app. |
| `global.postgresql.host` + `global.postgresql.password` (or `existingSecret`) | When using an external Postgres | Tells AppFlowy where to connect. Also set `postgresql.enabled=false`. |
| `minio.auth.rootPassword` | When `minio.enabled=true` | Sets MinIO credentials used by the app. |
| `global.s3.endpoint` + `global.s3.accessKey` + `global.s3.secretKey` (or `existingSecret`) | When using external S3 | Points AppFlowy at your external object store. Also set `global.s3.useMinio=false` and `minio.enabled=false`. |
| `ingress.tls.secretName` or `ingress.certManager.*` | When `ingress.tls.enabled=true` | TLS termination requires either a cert-manager Issuer or an existing TLS Secret. |

Optional but common:

- `global.scheme` / `global.wsScheme`: set to `http`/`ws` if you run without TLS. If you also set `ingress.tls.enabled=false`, set `ingress.scim.enabled=false` as well, or the chart refuses to render (see [Enterprise identity routes](#enterprise-identity-routes-scim-ldap-oidc-saml)).
- `global.s3.presignedUrlEndpoint`: set when clients must reach MinIO through an external ingress.
- `gotrue.config.smtp.*` / `gotrue.config.oauth.*`: set only if you enable SMTP or OAuth providers.
- `appflowy-ai.secrets.*`: set only if you enable AI providers.
- `appflowy-ai.enabled=false`: runs the core services without a paid AI provider. For keyword search without semantic embedding workers, also set `appflowy-search.config.backgroundIndexerEnabled=false`.
- `appflowy-search.enabled`: controls deployment of Search and supplies Cloud's initial/reset `APPFLOWY_SEARCH_ENABLED` default. A stored **Admin → Environment → Search** override takes precedence, including after restarts; changing the chart default does not replace that override.
- `*.image.digest`: pins an application or infrastructure image to an immutable registry digest; when set, it takes precedence over `image.tag`.
- `ingress.scim.enabled`: defaults to `true` and adds the `/scim` route for SCIM provisioning; set it to `false` when SCIM is unused or must use a separate edge (see below).

Internal PostgreSQL, Redis and MinIO host overrides are empty by default so the chart derives the release's Service names. Leave them empty when using bundled infrastructure. Init containers wait for PostgreSQL, GoTrue and Cloud migrations before background workers start. Search uses one replica, a PVC and `Recreate` updates so two processes never write its keyword index concurrently. Redis persists its AOF on its PVC.

The PostgreSQL subchart runs the same upstream pgvector image family as Compose, with explicit probe settings and the image's UID 999. Redis retains its existing Bitnami chart image and configuration. If upgrading an existing installation with a custom PostgreSQL image or data directory ownership, verify those settings against the existing volume before applying the new defaults. Web and Admin need to write startup configuration into their published images; their per-component security settings account for this instead of disabling health checks.

## Backup and restore

`appflowy-backup.enabled` defaults to `false`. Enabling it requires a Backup image built with the
Kubernetes adapter and compatible Cloud, Worker, Search and Admin images from the same tested
release. An older Compose-only Backup image cannot run this configuration. The adapter and chart
have deterministic unit/render coverage; a complete restore in a live cluster remains a release
acceptance requirement before production use.

The current Kubernetes adapter supports online backup, schedules, export and ZIP restoration for
one replica of each chart-managed writer, bundled persistent PostgreSQL, and persistent Search.
Cloud, Worker, Search, GoTrue and enabled AI are included in the writer inventory. Cloud and GoTrue
autoscalers must be disabled. Workloads managed by Argo CD, Flux or KEDA are rejected: running a
second controller during database cutover can restart a writer. Do not run Helm upgrades, rollouts,
manual scaling or another deployment reconciler while a restore is pending. Legacy physical
backup maintenance leases are not supported by this adapter.

Backup and Search share the same writable `ReadWriteOnce` keyword-index PVC and fixed node.
This allows LMDB read transactions to maintain their lockfile during online capture. Do not replace
that local filesystem with NFS or a generic shared network filesystem. Kubernetes
[`ReadWriteOnce` permits multiple pods on one node](https://kubernetes.io/docs/concepts/storage/persistent-volumes/#access-modes);
it does not prove that the writer has stopped. The coordinator scales every registered writer to
zero, waits for terminating pods to exit, checks the inventory again and rejects replacement
workload identities before changing the database.

Add these settings to your existing release values, selecting your built image and node:

```yaml
appflowy-backup:
  enabled: true
  image:
    tag: "<tested-backup-version>" # Or set digest: sha256:...
  nodeName: "<kubernetes.io/hostname label of the Search storage node>"
  # Kubernetes API endpoint/Service CIDR as seen by your NetworkPolicy provider.
  apiServerCIDR: "10.96.0.1/32"
  persistence:
    size: 50Gi
  artifacts:
    bucket: "appflowy-backups"
```

The API egress rule allows TCP 443 and 6443 to that CIDR. Check whether your cluster's network
plugin evaluates policy before or after Service address translation and use the actual API
destination it enforces. The Backup ServiceAccount can read pod/autoscaler inventory, update only
the named application Deployments, read the named PostgreSQL StatefulSet and manage its runtime
ConfigMap within the release namespace. It has no Secret-reading, pod-exec or cluster-wide rights.
PostgreSQL tools run inside Backup using credentials already mounted through Secret references.

Backup and Search run as UID/GID 999. On an existing installation, stop Search and migrate the
existing index PVC's ownership to that identity before enabling Backup, then allow Search to
restart. The storage initializer refuses existing files owned by another UID; it does not change
ownership recursively while a live Search process may be writing. Newly provisioned storage is
initialized automatically. Size the Backup work PVC for extracted archives and the prepared
database as well as the durable journals; this is separate from the artifact bucket.

The coordinator writes an independent `<fullname>-backup-runtime` ConfigMap containing only the
selected source bucket, Redis database number, Search directory and Cloud verification flag.
Helm does not render, replace or delete it. Application environment entries reference this map,
so normal pod replacement and subsequent Helm upgrades keep the restored resources. Backup's
artifact bucket and prefix remain fixed and are shared with Cloud, keeping downloads and imports
connected to the same archive repository. Keep Backup enabled after a restore; pause schedules in
Admin instead of disabling the chart feature, which would remove these runtime references.

Restore intent, admitted workload UIDs, the previous selection and each API mutation are written
to the Backup PVC before cutover. API updates use resource-version comparison; an uncertain or
conflicting response retains the journal and blocks another mutation. On restart, the coordinator
acquires its exclusive process lock and recovers that journal before accepting new work. Database
OID checks distinguish an interrupted switch from a completed commit. Cloud starts alone with
application writes fenced for migration validation, must pass `/api/ready`, then stops before
commit. GoTrue and Cloud become ready before the remaining writers resume. Search receives a new
generation and rebuild plan; captured LMDB files never become an unchecked serving index.

Retain the Backup PVC, runtime ConfigMap, Search PVC and restore journals while recovering an
interrupted operation. The Backup PVC has Helm's `keep` policy. If a workload UID changed, an API
mutation conflicted or the original Backup pod is still running, inspect the retained state and
workload inventory before retrying; deleting a journal is not a recovery procedure.

Read-only chart checks:

```bash
helm lint helm/appflowy-cloud -f ci/helm-values.yaml
python3 -m unittest discover -s helm/appflowy-cloud/tests -v
```

Release acceptance must additionally restore accounts, permissions, documents, database rows and
attachment bytes in a disposable cluster; recreate all pods and perform a Helm upgrade afterward;
interrupt the coordinator before and after database commit; and verify rollback/forward recovery,
a second restore, and Search rebuild with and without captured indexes.

## Enterprise identity routes (SCIM, LDAP, OIDC, SAML)

SCIM provisioning is served by Cloud at `/scim/v2` and authenticated with a per-connection bearer
token issued in the Admin console. `ingress.scim.enabled` (default `true`) adds a `/scim` `Prefix`
path to the primary TLS Ingress, routed to the Cloud Service port without rewriting. While it is
enabled, the chart fails to render at all if `ingress.enabled`, `ingress.tls.enabled`, or
`appflowy-cloud.enabled` is false, because a bearer credential must never travel over plaintext or
be redirected; a deployment without TLS must therefore also set `ingress.scim.enabled=false`. Two
Ingress-Nginx defaults still fall short of the SCIM edge requirements: plaintext requests receive a
`308` redirect (`ssl-redirect`) instead of a refusal, and access logs record the request URI with
its query string. Give the IdP only the HTTPS URL, and configure the controller's log format to
omit query strings. The path inherits the primary Ingress annotations; if those apply browser or
external authentication, set `ingress.scim.enabled=false` and publish `/scim` through a dedicated
HTTPS route that keeps the path intact, never redirects plaintext requests, is exempt from
browser-login or external-auth middleware, forwards `Authorization` untouched, allows at least
256 KiB request bodies, does not cache or retry `POST`/`PATCH`, and omits query strings from access
logs (SCIM filters carry email addresses). No SCIM token or SCIM-specific environment variable
belongs in the Deployment; Cloud stores only the token hash. See [docs/SCIM.md](../../docs/SCIM.md).

LDAP sign-in uses the ordinary `/api` route. Failed attempts are rate-limited per client address,
taken from `X-Forwarded-For` only when the header holds exactly one address, and independently per
login value. Ingress-Nginx's defaults satisfy the address requirement: it sets the header to the
connecting client. Keep the controller's `compute-full-forwarded-for` at its default `false`; a
comma-separated chain is ignored, every user then shares the controller pod's bucket, and ten
failures anywhere lock everyone out for five minutes. When a CDN or load balancer sits in front of
the controller, enable `use-forwarded-headers` together with `proxy-real-ip-cidr` restricted to
that edge, and make sure the edge itself sends exactly one address in `X-Forwarded-For`.
`APPFLOWY_LDAP_SECRET_KEY` is optional and the chart does not expose it (add it to the Cloud
Deployment yourself); without it the LDAP bind passwords are encrypted under the JWT secret, so
rotating `global.jwt.secret` requires re-entering them. See [docs/LDAP.md](../../docs/LDAP.md).

OIDC, OAuth, and SAML sign-in continue through the existing GoTrue routes (`/gotrue/authorize`,
`/gotrue/callback`, `/gotrue/sso/saml/acs`). Custom OIDC providers require a publicly resolvable
HTTPS issuer that stays reachable from the GoTrue pod: each sign-in exchanges the code at the IdP's
token endpoint, and the discovery document is fetched again whenever GoTrue's one-hour cache expires
or the pod restarts. See [docs/OIDC.md](../../docs/OIDC.md).

## Local minikube quick start

1. **Prepare your tooling and values**
   - Run `./script/check_local_env.sh` to make sure `kubectl`, `helm`, `minikube`, and Docker are reachable, and that `.env.nginx`/`values-test.yaml` exist.
   - `helm/appflowy-cloud/values-test.yaml` is gitignored so you can keep secrets there. Use `.env.nginx` as a reference for values such as `FQDN`, `SCHEME`, and the MinIO credentials. For local minikube, override `global.domain`, `global.scheme`, `global.wsScheme`, `global.jwt.secret`, and the `global.s3` block.
   - `global.s3.presignedUrlEndpoint` (or `APPFLOWY_S3_PRESIGNED_URL_ENDPOINT` in env-based setups) rewrites presigned URLs so clients can reach MinIO through your public ingress instead of the private `minio` service address. Set it to your public host (e.g., `https://<domain>/minio-api`) when you proxy uploads/downloads through nginx.

2. **Add Helm repos**
   ```bash
   helm repo add bitnami https://charts.bitnami.com/bitnami
   helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
   helm repo update
   helm dependency update helm/appflowy-cloud
   ```

3. **Start minikube and the ingress tunnel**
   ```bash
   minikube start -p appflowy --driver=docker --cpus=4 --memory=6144
   minikube addons enable ingress -p appflowy
   minikube tunnel -p appflowy
   ```
   This starts minikube with the Docker driver, enables the nginx ingress addon, and launches `minikube tunnel`. Keep the tunnel terminal open so `localhost` routes to the ingress controller.

4. **Deploy AppFlowy**
   ```bash
   helm upgrade --install appflowy-test helm/appflowy-cloud \
     -n default \
     -f helm/appflowy-cloud/values-test.yaml \
     --create-namespace \
     --dependency-update
   ```
   The command installs the chart into the default namespace with the `appflowy-test` release by default. `values-test.yaml` is layered on top of `values.yaml`, so change only what you need (domain, secrets, resource limits, etc.).

5. **Verify ingress**
   - Run `kubectl get ingress -n default` to confirm ingress, then open `http://localhost/` (or `http://localhost/app`), `http://localhost/console`, and `http://localhost/api`.
   - Use `kubectl get pods -n default` and `kubectl get ingress -n default` for quick status checks.

6. **Tear down**
   - `helm uninstall appflowy-test -n default` uninstalls the release.
   - To reset (uninstall, clear PVCs, and redeploy with monitoring enabled):
     ```bash
     helm uninstall appflowy-test -n default || true
     kubectl delete pvc -n default -l app.kubernetes.io/instance=appflowy-test --ignore-not-found
     helm upgrade --install appflowy-test helm/appflowy-cloud \
       -n default \
       -f helm/appflowy-cloud/values-test.yaml \
       -f helm/appflowy-cloud/values/features/monitoring.yaml \
       --create-namespace \
       --dependency-update
     ```

## Monitoring and metrics (optional)

Metrics are off by default so your cluster stays lightweight.

| Overlay | Effect | Requirements |
| --- | --- | --- |
| `values/features/metrics.yaml` | Turns on `/metrics` plus ServiceMonitors for AppFlowy Cloud, the worker, and AI services. | A Prometheus Operator already installed (ServiceMonitor CRD must exist). |
| `values/features/monitoring.yaml` | Enables `kube-prometheus-stack`, its ServiceMonitor CRDs, and the same AppFlowy ServiceMonitors with the stack. | Nothing else—this overlay installs Prometheus, Alertmanager, and Grafana for you. |

Enable metrics-only ServiceMonitors:

```bash
helm upgrade --install appflowy-test helm/appflowy-cloud \
  -n default \
  -f helm/appflowy-cloud/values-test.yaml \
  -f helm/appflowy-cloud/values/features/metrics.yaml \
  --create-namespace \
  --dependency-update
```

Enable the monitoring stack plus ServiceMonitors:

```bash
helm upgrade --install appflowy-test helm/appflowy-cloud \
  -n default \
  -f helm/appflowy-cloud/values-test.yaml \
  -f helm/appflowy-cloud/values/features/monitoring.yaml \
  --create-namespace \
  --dependency-update
```

ServiceMonitors require the `ServiceMonitor` CRD:

```bash
kubectl get crd servicemonitors.monitoring.coreos.com
```

If it is missing, install the Prometheus Operator (either via this chart or your own manifests) first. Once enabled, AppFlowy exposes metrics at `/metrics` on the standard service ports and the chart attaches the Prometheus job labels automatically.

## Accessing Grafana

When you deploy with monitoring enabled (using `values/features/monitoring.yaml`), Grafana is available as a ClusterIP service. Use port-forwarding to access it locally:

1. **Start port-forward:**
   ```bash
   kubectl port-forward -n default svc/appflowy-test-grafana 8083:80
   ```

2. **Open in browser:**
   ```
   http://localhost:8083
   ```

3. **Get login credentials:**
   | Field | Value |
   | --- | --- |
   | Username | `admin` |
   | Password | Run the command below to retrieve it |

   ```bash
   kubectl get secret appflowy-test-grafana -n default -o jsonpath="{.data.admin-password}" | base64 -d && echo
   ```

   The default password is `prom-operator` when using kube-prometheus-stack defaults.

4. **Pre-configured dashboards:**
   Grafana comes with several pre-installed dashboards from kube-prometheus-stack. Navigate to **Dashboards > Browse** to explore Kubernetes cluster metrics, node metrics, and more.

## Helm value overrides and ordering

Helm merges override files in the order you pass them. For example:

```bash
helm upgrade appflowy appflowy-cloud \
  -f helm/appflowy-cloud/values.yaml \
  -f helm/appflowy-cloud/values-test.yaml \
  -f helm/appflowy-cloud/values/features/monitoring.yaml
```

1. `values.yaml` defines chart defaults.
2. `values-test.yaml` (custom, local overrides, gitignored) tweaks resources, credentials, ingress settings, and `global` values.
3. Any feature overlays (metrics or monitoring) come last. That is why `values/features/monitoring.yaml` can set `kube-prometheus-stack.enabled: true` even though the base file leaves it disabled.
4. `--set` always wins if you append it after files.

## S3/MinIO configuration notes

The Helm chart defaults to MinIO so AppFlowy can store uploads. Update the `global.s3` block or the equivalent `.env`/`.env.nginx` settings when you point to Dell PowerScale or another S3-compatible backend. Key properties:

- `useMinio`: set to `false` if you rely on an external bucket.
- `endpoint`/`region`/`bucket`/`accessKey`/`secretKey`: match the target S3 storage.
- `presignedUrlEndpoint`: when AppFlowy generates presigned URLs, it signs them for the endpoint it talks to (usually internal hostnames). Set this to the public URL that clients can reach (often the nginx ingress you expose at `https://<domain>`). When present, AppFlowy rewrites the generated URL to swap out the internal host for the public one, keeping the original signature intact.

For a PowerScale-specific example, see [`doc/DELL_POWERSCALE_S3.md`](../../doc/DELL_POWERSCALE_S3.md).

## Useful kubectl/helm/minikube commands

| Command | Description |
| --- | --- |
| `./script/check_local_env.sh` | Validates `kubectl`, `helm`, `minikube`, Docker, and required env files. |
| `minikube start -p appflowy --driver=docker --cpus=4 --memory=6144`<br>`minikube addons enable ingress -p appflowy`<br>`minikube tunnel -p appflowy` | Boots minikube (Docker driver), enables ingress, and runs `minikube tunnel`. |
| `minikube tunnel -p appflowy` | Starts only the tunnel if you already have minikube running. |
| `helm upgrade --install appflowy-test helm/appflowy-cloud -n default -f helm/appflowy-cloud/values-test.yaml --create-namespace --dependency-update` | Deploys `appflowy-test` into the default namespace (values-test overrides in effect). |
| `helm upgrade --install appflowy-test helm/appflowy-cloud -n default -f helm/appflowy-cloud/values-test.yaml -f helm/appflowy-cloud/values/features/metrics.yaml --create-namespace --dependency-update` | Same as above but applies `values/features/metrics.yaml` (enables ServiceMonitors). |
| `helm upgrade --install appflowy-test helm/appflowy-cloud -n default -f helm/appflowy-cloud/values-test.yaml -f helm/appflowy-cloud/values/features/monitoring.yaml --create-namespace --dependency-update` | Applies the monitoring overlay; installs kube-prometheus-stack + ServiceMonitors. |
| `kubectl get pods -n default`<br>`kubectl get ingress -n default` | Shows pods and ingress objects for quick health checks. |
| `kubectl logs -n default -f deployment/appflowy-test-appflowy-cloud-<component>` | Streams logs from `appflowy-cloud-<component>` deployments (`cloud`, `worker`, `gotrue`, `web`, `admin`, `ai`). |
| `kubectl get ingress -n default` | Lists ingress rules for local testing (`http://localhost/`, `http://localhost/console`, `http://localhost/api`). |
| `kubectl port-forward -n default svc/appflowy-test-appflowy-cloud-web 8080:80`<br>`kubectl port-forward -n default svc/appflowy-test-appflowy-cloud-admin 8081:3000`<br>`kubectl port-forward -n default svc/appflowy-test-appflowy-cloud-cloud 8082:8000` | Port-forwards core services for local access (Web:8080, Admin:8081, API:8082); run each command in its own terminal. |
| `kubectl port-forward -n default svc/appflowy-test-appflowy-cloud-web 8080:80`<br>`kubectl port-forward -n default svc/appflowy-test-appflowy-cloud-admin 8081:3000`<br>`kubectl port-forward -n default svc/appflowy-test-appflowy-cloud-cloud 8082:8000`<br>`kubectl port-forward -n default svc/appflowy-test-grafana 8083:80` | Port-forwards all services including Grafana (Web:8080, Admin:8081, API:8082, Grafana:8083); run each command in its own terminal. |
| `kubectl port-forward -n default svc/appflowy-test-grafana 8083:80` | Port-forwards Grafana only to localhost:8083. |
| `helm uninstall appflowy-test -n default` | Uninstalls the Helm release (safe when nothing is deployed). |
| `helm uninstall appflowy-test -n default`<br>`kubectl delete pvc -n default -l app.kubernetes.io/instance=appflowy-test --ignore-not-found`<br>`helm upgrade --install appflowy-test helm/appflowy-cloud -n default -f helm/appflowy-cloud/values-test.yaml -f helm/appflowy-cloud/values/features/monitoring.yaml --create-namespace --dependency-update` | Uninstalls, deletes PVCs, and redeploys with the monitoring overlay (mnemonics for fresh starts). |

> The chart installs into the `default` namespace with the `appflowy-test` release by default. Adjust the release name and `--namespace` values in the commands above if you need another target.

## Troubleshooting

- **`http://localhost/` does not resolve**: make sure `minikube tunnel -p appflowy` is running (it keeps the tunnel alive in that shell) and that the nginx ingress addon is enabled.
- **GoTrue → Postgres connection failures**: ensure `postgresql.primary.containerSecurityContext.readOnlyRootFilesystem` is `false` (the defaults set this), and wait a few seconds for Postgres to finish initializing before GoTrue retries.
- **`helm dependency build` / `Chart.lock` errors**: always run `helm dependency update` inside `helm/appflowy-cloud` so your local `charts/` folder matches `Chart.lock`.
- **Prometheus or Grafana pods crash shortly after install**: they rely on persistent volumes and metrics; try uninstalling, deleting PVCs, and reinstalling with the monitoring overlay if something is stuck.
- **APIs require `APPFLOWY_S3_PRESIGNED_URL_ENDPOINT`**: clients must reach the same host that the signed URL uses. Set `global.s3.presignedUrlEndpoint` (or `APPFLOWY_S3_PRESIGNED_URL_ENDPOINT` in your env file) to the externally routable hostname or ingress path so uploads/downloads succeed.

## Helm test hook: test-connection

The chart includes a Helm test hook at `helm/appflowy-cloud/templates/tests/test-connection.yaml`. Running `helm test <release>` launches a short-lived pod that verifies connectivity to key dependencies in the **target cluster** (PostgreSQL, Redis, GoTrue, AppFlowy Cloud, Web, AI, MinIO). This is different from CI template checks because it validates live DNS, network policy, and secrets in your actual environment. Keep it enabled so you can quickly confirm that a deployment is functional after install or upgrade.

## External clusters and production deployments

When targeting a shared cluster:

1. Create the namespace (e.g., `kubectl create namespace appflowy`).
2. Provision secrets for Postgres, Redis, JWT, and S3 instead of embedding them in `values-test.yaml`.
3. Run Helm directly (and make sure you override `global.domain`/schemes plus provide production secrets):
   ```bash
   helm upgrade --install appflowy ./helm/appflowy-cloud \
     -f ./helm/appflowy-cloud/values.yaml \
     --set global.domain=appflowy.example.com \
     --namespace appflowy
   ```
4. Use overlays (`values/features/metrics.yaml` or `values/features/monitoring.yaml`) to add observability as needed.

Keep this README, `values-test.yaml`, and `.env.nginx` in sync when you introduce other platforms (OpenShift, EKS, k3s). The structure is intentionally modular so you can add new overlay files for platform-specific tweaks later (simply drop another file in `values/features/` and reference it in your Helm command).
