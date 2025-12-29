# AppFlowy on EC2 with Cloudflare HTTPS (Helm)

This beginner-friendly guide shows the simplest way to host AppFlowy on a single EC2 instance using the Helm chart and Cloudflare HTTPS. It also includes an advanced section if you want cert-manager or external databases.

Note: The example values, passwords, and resource sizes in this document are for demonstration only. Replace them with strong secrets and production-appropriate sizing before going live.

Example resource requests/limits from `helm/appflowy-cloud/values.yaml` (requests → limits):
- PostgreSQL (primary): 256Mi / 100m → 1Gi / 500m
- Redis (master): 128Mi / 50m → 256Mi / 200m
- MinIO: 256Mi / 100m → 512Mi / 500m
- GoTrue: 128Mi / 100m → 512Mi / 500m
- AppFlowy Cloud: 256Mi / 200m → 1Gi / 1000m
- AppFlowy Worker: 256Mi / 100m → 512Mi / 500m
- AppFlowy Web: 128Mi / 50m → 256Mi / 200m
- Admin Frontend: 64Mi / 50m → 128Mi / 200m
- AppFlowy AI: 256Mi / 100m → 1Gi / 1000m

References used while preparing this guide:
- Cloudflare SSL/TLS encryption modes: https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/
- Cloudflare Origin CA certificates (trusted only by Cloudflare): https://developers.cloudflare.com/ssl/origin-configuration/origin-ca/
- cert-manager DNS-01 with Cloudflare: https://cert-manager.io/docs/configuration/acme/dns01/cloudflare/

## Simple setup (recommended for beginners)

This uses:
- k3s on one EC2 instance
- nginx ingress
- Cloudflare Origin CA certificate
- bundled PostgreSQL + MinIO from the Helm chart

### 1) Prepare EC2

- Launch an Ubuntu 22.04 EC2 instance.
- Security group inbound rules:
  - 22 from your IP
  - 80 and 443 from the internet (or Cloudflare IP ranges)
- SSH in:
  ```bash
  ssh -i /path/to/key.pem ubuntu@<EC2_PUBLIC_IP>
  ```
- Install tools:
  ```bash
  sudo apt update
  sudo apt install -y curl git
  ```

### 2) Install Kubernetes (k3s)

```bash
curl -sfL https://get.k3s.io | sh -s - --disable traefik
sudo chmod 644 /etc/rancher/k3s/k3s.yaml
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
```

Verify:

```bash
kubectl get nodes
```

### 3) Install Helm

```bash
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

### 4) Get the chart and dependencies

```bash
git clone <your-repo-url> AppFlowy-Cloud-Premium
cd AppFlowy-Cloud-Premium

helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm dependency update helm/appflowy-cloud
```

### 5) Install nginx ingress

```bash
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update
helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
  -n ingress-nginx --create-namespace
```

Quick check (should return an nginx 404 if reachable):

```
http://<EC2_PUBLIC_IP>
```

### 6) Configure Cloudflare DNS + SSL

1. Cloudflare DNS: create an **A record**
   - Name: `app`
   - IPv4: `<EC2_PUBLIC_IP>`
   - Proxy status: **Proxied** (orange cloud)
2. Cloudflare SSL/TLS mode: **Full (strict)**
3. Optional: enable **Always Use HTTPS**

### 7) Create a Cloudflare Origin CA certificate

1. Cloudflare dashboard: **SSL/TLS > Origin Server > Create Certificate**
2. Hostname: `app.yourdomain.com`
3. Key type: RSA
4. Validity: 15 years (fine for origin certs)
5. Download the certificate and private key

Create a Kubernetes TLS secret:

```bash
kubectl create namespace appflowy
kubectl create secret tls appflowy-origin-tls \
  --cert=origin-cert.pem \
  --key=origin-key.pem \
  -n appflowy
```

Important: keep the Cloudflare proxy **enabled**. Browsers do not trust Origin CA certificates directly.

### 8) Create a simple Helm values file

Create `helm/appflowy-cloud/values-ec2-cloudflare.yaml`:

```yaml
global:
  domain: "app.yourdomain.com"
  scheme: "https"
  wsScheme: "wss"
  s3:
    presignedUrlEndpoint: "https://app.yourdomain.com/minio-api"
    accessKey: "minioadmin"
    secretKey: "<S3_SECRET_KEY>"
  jwt:
    secret: "<JWT_SECRET>"

ingress:
  enabled: true
  className: "nginx"
  tls:
    enabled: true
    secretName: "appflowy-origin-tls"
  certManager:
    enabled: false

postgresql:
  enabled: true
  auth:
    postgresPassword: "<POSTGRES_PASSWORD>"

minio:
  enabled: true
  auth:
    rootUser: "minioadmin"
    rootPassword: "<S3_SECRET_KEY>"

gotrue:
  config:
    adminEmail: "admin@example.com"
    adminPassword: "<ADMIN_PASSWORD>"
```

Notes:
- Use strong values for `<JWT_SECRET>`, `<POSTGRES_PASSWORD>`, and `<S3_SECRET_KEY>`.
- `minio.rootPassword` and `global.s3.secretKey` should match.

### 9) Deploy AppFlowy

```bash
helm upgrade --install appflowy ./helm/appflowy-cloud \
  -n appflowy --create-namespace \
  -f ./helm/appflowy-cloud/values.yaml \
  -f ./helm/appflowy-cloud/values-ec2-cloudflare.yaml
```

Wait for pods and ingress:

```bash
kubectl get pods -n appflowy
kubectl get ingress -n appflowy
```

### 10) Verify

- Web UI: `https://app.yourdomain.com/app`
- Admin UI: `https://app.yourdomain.com/console`
- Login redirects should use `https://app.yourdomain.com/gotrue/...`

## Advanced setup (optional)

Use this section if you want publicly trusted TLS (Let’s Encrypt) or external databases.

### A) cert-manager with Cloudflare DNS-01

1. Install cert-manager:
   ```bash
   helm repo add jetstack https://charts.jetstack.io
   helm repo update
   helm upgrade --install cert-manager jetstack/cert-manager \
     -n cert-manager --create-namespace \
     --set installCRDs=true
   ```
2. Create a Cloudflare API token with **Zone:DNS:Edit** and **Zone:Read**.
3. Store the token:
   ```bash
   kubectl create secret generic cloudflare-api-token-secret \
     --from-literal=api-token="<CLOUDFLARE_API_TOKEN>" \
     -n cert-manager
   ```
4. Create a ClusterIssuer:
   ```yaml
   apiVersion: cert-manager.io/v1
   kind: ClusterIssuer
   metadata:
     name: cloudflare-issuer
   spec:
     acme:
       email: you@yourdomain.com
       server: https://acme-v02.api.letsencrypt.org/directory
       privateKeySecretRef:
         name: cloudflare-issuer-account-key
       solvers:
         - dns01:
             cloudflare:
               apiTokenSecretRef:
                 name: cloudflare-api-token-secret
                 key: api-token
   ```
5. Update your values:
   ```yaml
   ingress:
     certManager:
       enabled: true
       issuerKind: "ClusterIssuer"
       issuerName: "cloudflare-issuer"
     tls:
       enabled: true
       secretName: "appflowy-tls"
   ```

### B) Use external Postgres/Redis/S3

- Set `postgresql.enabled: false`, `redis.enabled: false`, `minio.enabled: false`.
- Provide `global.postgresql.*`, `global.redis.*`, and `global.s3.*`.
- Create secrets and reference them via `global.*.existingSecret` fields (see `values.yaml`).

### C) Hardening tips

- Restrict EC2 inbound 80/443 to Cloudflare IP ranges: https://www.cloudflare.com/ips/
- Keep Cloudflare proxy enabled when using Origin CA.
- Enable Cloudflare WAF rules if the instance is public.
- Set `ingress.annotations` for rate limiting if needed.

## Troubleshooting

- **Login redirects to http://<service-name>:9999**: `global.domain`/`scheme`/`wsScheme` are not set to your public hostname.
- **Cloudflare 525/526 errors**: origin cert is missing/invalid; use Origin CA or cert-manager with Full (strict).
- **Cloudflare 522 timeout**: ingress not reachable; check security group, nginx service, and EC2 public IP.
- **Uploads fail**: set `global.s3.presignedUrlEndpoint` to the public Cloudflare URL.
- **Ingress IP is empty**: give it a minute; on single-node setups nginx may still bind to the node IP.
