# Docker Swarm setup

Run a fresh AppFlowy installation on a local, single-node Docker Swarm using Docker commands directly. You need a running Docker Desktop or Docker Engine and a shell; no Python, extra packages, or setup script is required. Run these commands from the repository root.

The [Swarm stack](../docker-swarm/docker-stack.yml) preserves all 11 services from the root [docker-compose.yml](../docker-compose.yml). This walkthrough starts 10 services, leaving optional AI at zero replicas.

## 1. Prepare your configuration

```bash
mkdir -p docker-swarm/.local
cp deploy.env docker-swarm/.local/swarm.env
chmod 600 docker-swarm/.local/swarm.env
```

Edit `docker-swarm/.local/swarm.env`. Change these existing settings:

```bash
FQDN=127.0.0.1:18081
NGINX_PORT=18081
NGINX_TLS_PORT=18444
```

Use `127.0.0.1` for this local setup. On some Docker versions, `localhost` resolves to IPv6 `::1`, where Swarm's published ingress port accepts a connection but does not forward it. Explicit IPv4 avoids this [Docker ingress issue](https://github.com/moby/moby/issues/53091).

Set your own `POSTGRES_PASSWORD`, `GOTRUE_ADMIN_EMAIL`, `GOTRUE_ADMIN_PASSWORD`, `GOTRUE_JWT_SECRET`, `AWS_ACCESS_KEY`, and `AWS_SECRET`. Use a URL-safe PostgreSQL password, or URL-encode it in the database URLs. For this local run, keep the template defaults `GOTRUE_DISABLE_SIGNUP=false` and `GOTRUE_MAILER_AUTOCONFIRM=true` so you can register through the Web app without email confirmation. Append:

```bash
AI_ENABLED=false
APPFLOWY_INDEXER_DATABASE_ENABLED=false
```

This file will be loaded by the shell. Keep it as trusted shell assignments, quote literal secrets with single quotes (for example, `GOTRUE_ADMIN_PASSWORD='your-password'`), and retain the template's `${...}` references so dependent URLs expand. Never commit this file; `.local/` is ignored by Git. Keep it when reusing the stack's data.

Load it in the current terminal:

```bash
set -a
. ./docker-swarm/.local/swarm.env
set +a
```

Repeat this loading step in a new terminal before deploying. `docker stack deploy` does not automatically read `.env` files. Deploy the original stack files directly so their variables are interpolated once.

## 2. Enable Swarm and label the data node

Check that Docker points to your local engine:

```bash
docker context show
docker info --format '{{.Swarm.LocalNodeState}}'
```

If Swarm is `inactive`, initialize it:

```bash
docker swarm init
```

If Docker asks for an address, use `docker swarm init --advertise-addr <manager-ip>`; Docker Desktop can use `eth0` as the address. If Swarm is already active, reuse it only if it is your local single-node manager.

```bash
docker node ls
docker node update --label-add appflowy.data=true "$(docker info --format '{{.Swarm.NodeID}}')"
```

PostgreSQL, MinIO, and Search store data on this labeled node. Label only one node for this setup; local volumes do not follow services to another node.

## 3. Start infrastructure, then the application

Use the separate stack name `appflowy-swarm`. The bootstrap override starts PostgreSQL, Redis, and MinIO, with the other services at zero replicas:

```bash
docker stack deploy \
  -c docker-swarm/docker-stack.yml \
  -c docker-swarm/docker-stack.bootstrap.yml \
  appflowy-swarm
docker stack services appflowy-swarm
docker ps --filter label=com.docker.stack.namespace=appflowy-swarm \
  --format 'table {{.Names}}\t{{.Status}}'
```

Repeat the `docker ps` command until PostgreSQL and MinIO show **healthy**, and Redis shows **Up**. Redis has no configured health check in the base stack. Then start GoTrue:

```bash
docker service scale appflowy-swarm_gotrue=1
```

Repeat the `docker ps` check until GoTrue is **healthy**, then start Cloud:

```bash
docker service scale appflowy-swarm_appflowy_cloud=1
```

Wait until Cloud is **healthy**, so startup and database migrations finish before Worker and Search start. Then run:

```bash
docker service scale \
  appflowy-swarm_appflowy_worker=1 \
  appflowy-swarm_appflowy_search=1 \
  appflowy-swarm_appflowy_web=1 \
  appflowy-swarm_admin_frontend=1 \
  appflowy-swarm_nginx=1
docker stack services appflowy-swarm
```

Wait for 10 services to show `1/1`, with AI at `0/0`, and for Search to show **healthy** in `docker ps`. A successful deploy command or `1/1` alone does not establish application readiness. Swarm does not implement Compose's `depends_on` ordering.

For failures, inspect the affected service:

```bash
docker service ps --no-trunc appflowy-swarm_appflowy_cloud
docker service logs --tail 100 appflowy-swarm_appflowy_cloud
```

## 4. Open and test AppFlowy

Make sure your license has at least one available user seat, then test registration through the public Web app:

1. Open **<http://127.0.0.1:18081>** and choose **Create account**.
2. Enter a new user's email address, password, and password confirmation, then submit the form. Confirm that the new user enters a workspace.
3. Create a document, give it a title, add text, and upload a small attachment.
4. Sign out, or open a fresh private browser window. Choose **Sign in with password** and use the new account's email and password. Confirm that the same workspace, document title, text, and attachment are available.

The system administrator account is for the Admin console at **<http://127.0.0.1:18081/console>**. Use `GOTRUE_ADMIN_EMAIL` and `GOTRUE_ADMIN_PASSWORD` there to manage the installation.

Replace Cloud, then wait for it to become healthy and refresh the page to check that your document and attachment remain available:

```bash
docker service update --force appflowy-swarm_appflowy_cloud
```

One replica means brief downtime during replacement. PostgreSQL, MinIO, and Search use named volumes. Redis matches the root Compose configuration, with no explicit AOF settings or named Redis data volume; pending Redis-backed work is not guaranteed to survive replacement. Port `18444` uses the repository's development TLS certificate; this walkthrough uses HTTP.

## 5. Stop or start again

```bash
docker stack rm appflowy-swarm
```

This removes the stack and retains named volumes. To start again, load the same environment file and repeat step 3, waiting for readiness at each stage. The bootstrap override scales application services down, so use it for initial startup or a planned restart.

To enable AI later, configure its provider credentials, set `AI_ENABLED=true`, and follow the staged deployment with `docker service scale appflowy-swarm_ai=1` in the final stage. Reapplying only the base stack starts every service at once, so it is not the staged migration procedure.

See [docker-swarm/README.md](../docker-swarm/README.md) for optional automated tests and parity maintenance, and [deployment CI](deployment-ci.md) for automated Compose, Swarm, and Helm checks. This single-node guide does not establish multi-node operation, high availability, or safe release upgrades.
