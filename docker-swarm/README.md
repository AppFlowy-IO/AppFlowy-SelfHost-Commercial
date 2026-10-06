# AppFlowy on Docker Swarm

Follow the [step-by-step Docker Swarm setup guide](../docs/docker-swarm.md) for a fresh local installation. Deployment uses **Docker commands and your shell**. Python, package installation, and setup scripts are not required.

The [root docker-compose.yml](../docker-compose.yml) is the source of truth. This folder contains its generated Swarm counterpart, an initial-startup override, and optional development tests. The setup and recorded tests cover one Swarm node; they do not establish multi-node or high-availability support.

## Deployment files

- [docker-stack.yml](docker-stack.yml) preserves all 11 root services, including AI, with the same application images, environment variables, commands, health checks, ports, and volumes.
- [docker-stack.bootstrap.yml](docker-stack.bootstrap.yml) initially scales application services to zero so infrastructure and migrations can start in order. It does not change application settings.
- `.local/swarm.env` is the operator's private configuration for the direct Docker guide. It is copied from [deploy.env](../deploy.env), edited, and explicitly loaded into the shell before deployment.

The guide uses stack `appflowy-swarm` and ports `18081`/`18444`. It leaves AI at zero replicas with AI features disabled. To use AI, configure the provider credentials and enable the service as described in the guide. All 11 services remain in the configuration.

The Swarm counterpart makes these explicit compatibility changes:

- Adds legacy Compose `version: '3.8'` and a default overlay network.
- Removes `depends_on`; Swarm does not implement Compose startup ordering.
- Converts `restart` to `deploy.restart_policy`, retaining Swarm's default of one replica and using stop-first updates. Omitting an explicit base replica count lets the bootstrap override set zero replicas on older Docker CLIs.
- Constrains PostgreSQL, MinIO, and Search to `node.labels.appflowy.data == true` so local volumes remain on the designated data node.
- Converts Nginx's configuration and certificate mounts to Swarm configs, and its TLS private key mount to a Swarm secret. Source paths are relative to this folder.

Redis matches the root Compose configuration: the image's default command, with no explicit AOF settings, named Redis data volume, or health check. The base stack does not guarantee that Redis-backed queues or pending work survive replacement. See [storage and Redis](../docs/docker-compose.md#storage-and-redis).

## Startup and storage

`docker stack deploy` submits a deployment; it does not establish application readiness or automatically load `.env`. The guide explicitly loads a trusted shell-compatible environment file, deploys the original YAML files once, and waits for each stage: PostgreSQL/Redis/MinIO, GoTrue, Cloud and its migrations, then Worker/Search/Web/Admin/Nginx. AI is optional. Passing an already interpolated Compose rendering through another interpolation step can change literal dollar signs, including those in Search's health check.

The bootstrap override is for initial startup or a planned restart: applying it to a running stack scales application services down. For release upgrades, follow the migration and rollout requirements in the [root deployment instructions](../README.md). A generic Swarm rolling update does not implement that sequence, and the local tests have not validated release upgrades.

Label one designated data node `appflowy.data=true`. Docker's local volumes do not move when services move to another node. Single-replica services have downtime during replacement. Multiple Cloud replicas, shared storage, stateful failover, cross-node networking, and backup restoration require separate validation.

## Optional: maintain source parity

These are development checks, not deployment prerequisites. Install Python 3.10 or later and PyYAML in an isolated environment only when using the generator or automated harness:

```bash
python3 -m venv docker-swarm/.venv
source docker-swarm/.venv/bin/activate
python3 -m pip install -r docker-swarm/requirements.txt
python3 docker-swarm/generate.py --check
```

After editing the root Compose file, regenerate and review its counterpart:

```bash
python3 docker-swarm/generate.py
python3 docker-swarm/generate.py --check
```

[generate.py](generate.py) reads raw YAML without loading `.env` or resolving variables. Its parity check fails when the committed counterpart is stale. See [deployment CI](../docs/deployment-ci.md) for Compose, Swarm, and Helm checks.

## Optional: isolated automated tests

The [local.py](local.py) test harness also requires the Docker Compose plugin. It is separate from the direct Docker installation above and uses a different stack namespace, ports, credentials, and volumes. [prepare.py](prepare.py) derives its configuration from the committed Swarm file and [deploy.env](../deploy.env); it never reads your root `.env` or `.local/swarm.env`.

The test profile runs 10 services with AI omitted and semantic embedding workers disabled. Keyword search remains enabled. It generates test credentials, uses local-only SMTP settings, applies smaller resource settings, adds startup health checks, and pins native-platform images to registry digests. Redis retains the base stack's configuration; this profile does not add Redis persistence. Runtime files and evidence live in the ignored `.local/` directory. Keep it private and retain credentials when retaining the test volumes.

With the optional Python environment active:

```bash
python3 -m unittest discover -s docker-swarm/tests -p 'test_*.py'
python3 docker-swarm/local.py up
python3 docker-swarm/local.py status
python3 docker-swarm/local.py test
python3 docker-swarm/local.py verify
```

`up` pulls images, initializes Swarm if needed, and starts the test stack in stages. `up --no-pull` reuses cached image digests. Rerunning it stops the test application and restarts it in order with retained volumes. The harness requires a local Docker endpoint and single-node manager; ownership checks prevent it from changing unrelated services.

The test URL defaults to **<http://localhost:18080>**, with development TLS on `18443`. The ordinary user's login is in `.local/ordinary-user.json`; administrative credentials are in `.local/credentials.json`. The default stack is `af-swarm-local`, or the previously recorded stack name. Existing metadata retains the original `af-swarm-local-20261006` experiment's settings.

Optional overrides are `SWARM_TEST_DIR`, `SWARM_STACK_NAME` (must start with `af-swarm-`), `SWARM_HTTP_PORT`, and `SWARM_TLS_PORT`. Use the same values in every terminal for a test run.

To replace selected test services and verify retained fixtures:

```bash
python3 docker-swarm/local.py replace postgres redis minio appflowy_search
python3 docker-swarm/local.py verify
```

### Two-browser realtime and reconnect test

This optional test needs Node.js and the locked browser dependencies:

```bash
npm ci --prefix ci
ci/node_modules/.bin/playwright install chromium
```

Run `local.py test` first to create the ordinary user and workspace, then start:

```bash
node docker-swarm/tests/ui_smoke.mjs
```

The test launches separate browser contexts, creates a document, and checks edits in both directions. When it prints `ready_for_cloud_replacement`, run this in a second terminal:

```bash
python3 docker-swarm/local.py replace appflowy_cloud
```

Cloud replacement signals the waiting browser test after recovery. It checks reconnection, another edit, both client reloads, and a fresh third context without cached document data. Results and screenshots are saved under `.local/`.

To reuse an existing AppFlowy Web checkout's installed Playwright, set `APPFLOWY_WEB_DIR` to that directory. `SWARM_BROWSER_CHANNEL=chrome` uses an installed Google Chrome instead of the default Chromium. These browser dependencies are unrelated to deployment requirements.

### Stop the automated test stack

```bash
python3 docker-swarm/local.py down
```

Volumes are retained. `python3 docker-swarm/local.py down --leave-swarm` additionally leaves a Swarm created by the harness only when its ownership checks pass and no services or other nodes remain. This command does not manage the separate `appflowy-swarm` stack from the direct Docker guide.

## Recorded local evidence

On 2026-10-06, the current Swarm files passed a fresh local Linux ARM64 run with 10 services active and AI disabled. Redis retained the root Compose defaults without added AOF settings, a named volume, or a health check. All running application image IDs matched the recorded native image lock.

The run passed authentication, document operations, database row creation/edit/readback, attachment byte equality, Worker HTML import, and keyword search. Two browser clients exchanged edits, reconnected after Cloud replacement, and retained matching content after reload and in a fresh browser context. After PostgreSQL, MinIO, Redis, Search, and Worker replacement, existing application data remained readable and fresh imports and search indexing passed. Temporary service interruptions are expected during replacement.

Sanitized results are stored locally in the ignored `ci/.local/swarm-final-evidence/` directory. The temporary verification stack and its volumes were removed. The separately retained `af-swarm-local-20261006` experiment used an older Redis override; it is not the configuration validated by this final run.

These checks do not establish Redis queue durability, multiple-node operation, HA, AI features, HTTPS application workflows, release upgrades, backup restoration, or interrupted-import recovery. See the [deployment CI guide](../docs/deployment-ci.md) for automated coverage and limits.
