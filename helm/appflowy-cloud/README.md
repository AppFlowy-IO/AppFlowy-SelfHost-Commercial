# AppFlowy Cloud Helm Chart

This chart bundles the AppFlowy Cloud services (API, auth, web, admin, worker and AI) with the infrastructure they need, so you can deploy to Kubernetes with a single command. The defaults are production-oriented (HTTPS + TLS). For local minikube use, apply `values-test.yaml`.

## What is deployed

- AppFlowy Cloud API (main backend)
- AppFlowy Web 
- Admin console
- GoTrue (auth server)
- AppFlowy Worker (background jobs)
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

- `global.scheme` / `global.wsScheme`: set to `http`/`ws` if you run without TLS.
- `global.s3.presignedUrlEndpoint`: set when clients must reach MinIO through an external ingress.
- `gotrue.config.smtp.*` / `gotrue.config.oauth.*`: set only if you enable SMTP or OAuth providers.
- `appflowy-ai.secrets.*`: set only if you enable AI providers.

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
