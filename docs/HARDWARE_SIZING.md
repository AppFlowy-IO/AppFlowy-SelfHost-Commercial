# Deployment topology and hardware sizing

[Documentation](README.md)

Choose where AppFlowy's services will run, then size the machines for your busiest period. This
guide covers 100, 500, and 1,000 online users, starting with the default Docker Compose deployment.

- [Choose a deployment topology](#choose-a-deployment-topology)
- [Understand the user counts](#understand-the-user-counts)
- [Single-server deployment: all services on one machine](#single-server-deployment-all-services-on-one-machine)
- [Multi-server deployment: separate application and data services](#multi-server-deployment-separate-application-and-data-services)
- [Plan storage and memory](#plan-storage-and-memory)
- [Validate capacity and expand](#validate-capacity-and-expand)

## Choose a deployment topology

**Deployment topology** describes where services run. **Hardware sizing** and **capacity planning**
describe the CPU, memory, storage, and workload those services need.

| Topology | Where services run | When to choose it |
| --- | --- | --- |
| Single-server, or all-in-one | Application services, PostgreSQL, Redis, and MinIO share one machine. | A straightforward installation with one host to operate. This is the default Compose layout. |
| Multi-server, or separated services | Application services share one host; PostgreSQL and Redis have separate hosts; object storage runs separately. | Independent resizing or isolation of database, cache, and storage workloads. |

Docker Compose, Docker Swarm, and Kubernetes/Helm are deployment tools. A topology describes
placement regardless of the tool. A multi-server layout also needs a separate availability design:
a single PostgreSQL server, Redis server, or application host remains a point of failure.

## Understand the user counts

The tables use **peak online users** as a planning target: people with AppFlowy open during the
busiest period, with a mix of editing, reading, searching, and pauses. Record active editors and
action rates separately. Continuous editing by every connected client is a different workload.

For example, an organization with 1,000 accounts and 100 people online at its busiest time can
start qualification with a 100-user profile. Measure this activity; do not assume a fixed percentage
of registered users will be online. Training sessions can produce much higher simultaneous activity.

For each deployment, record:

- Registered accounts, peak online people, and connected browser/desktop/mobile sessions.
- Concurrent editors, edits per second, and the largest group sharing a page or database.
- Typical and largest documents, database row counts, attachments, and workspace distribution.
- Search traffic, import/export sizes, backups, and other jobs overlapping with peak use.

The profiles assume one instance of each application service and external AI model providers.
Local model inference needs a separate CPU/GPU budget. Add resources for monitoring and optional
services, and validate large imports, exports, reindexing, backups, and restores before allowing
them to overlap with peak traffic. License seats are separate from hardware capacity.

## Single-server deployment: all services on one machine

The supplied [Docker Compose file](../docker-compose.yml) runs the application services,
PostgreSQL, Redis, and MinIO in separate containers on the same Docker host. All containers share
that machine's CPU, RAM, storage performance, and network connection.

### Initial machine profiles

| Target peak online users | Machine CPU | Machine RAM | Storage |
| --- | --- | --- | --- |
| 100 | 4 vCPU | 16 GiB | SSD, sized for data and retention. |
| 500 | 8 vCPU | 32 GiB | SSD, sized for data and retention. |
| 1,000 | 16 vCPU | 64 GiB | SSD, sized for data and retention. |

**All three rows are proposed pilot sizes. They have not been benchmarked and are not established
minimums or supported capacity limits.** They include an allowance for PostgreSQL, Redis, and local
object storage alongside the application. The production reference later in this guide uses
separate machines and S3, so it does not validate these single-server estimates.

Choose a resizable Linux machine and validate with every intended service running. If CPU, memory,
or storage becomes constrained, increase the relevant resource or move the constrained service to
another machine. Use [storage planning](#plan-storage-and-memory) to select disk capacity and IOPS.

### Prepare and start a new installation

1. Install Docker Engine and Docker Compose **2.30 or newer**, and use the deployment files and
   compatible service images for your chosen AppFlowy release. Verify architecture support for
   the images you will run. Check Compose with `docker compose version --short`.
2. From the repository root, create the environment file for a **new** installation:

   ```bash
   cp deploy.env .env
   ```

   Keep the existing `.env`, project name, and deployment files when maintaining an installation;
   follow the [Compose upgrade instructions](docker-compose.md) instead of replacing them.
3. Configure the domain, HTTPS/WebSocket schemes, credentials, admin account, and TLS certificates
   using the [Compose guide](docker-compose.md). Replace the example passwords and JWT secret.
   Configure email and external AI providers when needed.
4. Ensure Docker's data location has enough space for the database, MinIO, Search, and container
   images. If using dedicated disks, configure their mounts before creating the data volumes.
5. Validate the configuration without displaying resolved secrets, then start the services:

   ```bash
   docker compose config --quiet
   docker compose up -d
   ```

These commands target the Docker host selected by your Docker context. Run them against the
machine you sized for this installation.

### What happens after Docker Compose starts

Compose uses the published images referenced by the deployment file; this startup does not compile
AppFlowy. It obtains missing images, creates the project's default network and data volumes, and
starts the containers in the background. Existing named volumes are reused for the same project.
See Docker's [Compose startup](https://docs.docker.com/reference/cli/docker/compose/up/) and
[networking](https://docs.docker.com/compose/how-tos/networking/) documentation.

The base configuration starts these **11 service containers**:

| Compose service | Purpose |
| --- | --- |
| `nginx` | Receives HTTP/HTTPS traffic and routes web, API, authentication, and WebSocket requests. |
| `appflowy_web` | Serves the AppFlowy web application. |
| `admin_frontend` | Serves the Admin console. |
| `gotrue` | Provides authentication. |
| `appflowy_cloud` | Handles application APIs and realtime collaboration. |
| `appflowy_worker` | Processes background work, including imports and exports. |
| `appflowy_search` | Provides search and maintains the persistent keyword index. |
| `ai` | Runs the AI service and connects to configured model providers. |
| `postgres` | Stores relational data using PostgreSQL with pgvector. |
| `redis` | Supports caching, streams, queues, and service coordination. |
| `minio` | Provides local S3-compatible object storage. |

The optional `appflowy_backup` service is enabled separately; see the [Backup guide](BACKUP.md).
Running the AI container does not install a local language model.

Compose honors the health dependencies declared in the file: for example, GoTrue waits for
PostgreSQL and Cloud waits for GoTrue. Initial database and service startup takes time. A returned
shell prompt or a running container alone does not establish that the installation is ready for
users; complete the checks below.

Nginx publishes host ports **80 and 443** by default, configurable through `NGINX_PORT` and
`NGINX_TLS_PORT`. PostgreSQL and Redis have no published host ports in the base file. Containers
communicate by service name on the Compose network. Compose does not provision extra machines or
automatically resize the host when demand grows.

### Verify the installation

From the same deployment directory and with the same Compose project settings, check status and
resource use:

```bash
docker compose ps --all
docker compose stats --no-stream
```

Services with health checks should become healthy; other services should remain running without
repeated exits. If a service fails, inspect its recent logs. For example:

```bash
docker compose logs --since 10m --tail 100 postgres gotrue appflowy_cloud appflowy_search
```

Open the configured AppFlowy URL and its `/console` Admin path. For a local test with the default
settings, these are `http://localhost` and `http://localhost/console`. Sign in with the configured
admin account, then verify a normal user's workflow: create a page, edit it from two sessions,
upload and download an attachment, and search for the page after indexing finishes.

On the Linux host, check available memory and the filesystems holding Docker data:

```bash
free -h
df -h
```

[Compose stats](https://docs.docker.com/reference/cli/docker/compose/stats/) shows container usage;
check host resources as well. An idle installation may use little CPU while still needing memory
for its services. Invite a pilot group and repeat these checks during editing and background jobs.

### Persistent data and shared resources

The base file creates named volumes for PostgreSQL (`postgres_data`), MinIO (`minio_data`), and
Search (`keyword_index_data`). Docker normally prefixes their names with the Compose project name.
These volumes retain data across container replacement when the same volumes are reused. Keep the
project name stable. `docker compose down -v` removes deployment data volumes and is not an upgrade
command. A copy on the same host does not protect against host or disk loss; configure independent
backups and test a restore.

Redis persistence needs explicit attention: the base Compose file does not configure AOF or an
explicit named Redis data volume. It does not guarantee that queues and pending work survive
container replacement. See [Storage and Redis](docker-compose.md#storage-and-redis).

The default services have no per-service CPU or memory budgets in the base Compose file. They
compete for the host's resources. Reserve capacity for PostgreSQL, Redis, MinIO, the OS, and
filesystem cache when allocating resources to application containers. If you add container limits,
validate them under load; adding host RAM does not increase an existing container limit.

### Connection capacity

Check the reverse proxy before a large rollout. The bundled
[Nginx configuration](../docker/nginx/nginx.conf) sets `worker_connections` to 1,024. That setting
limits connections per worker, including upstream connections; it is not a user count. WebSocket
clients keep connections open while online, alongside ordinary HTTP traffic.

Review `worker_processes`, `worker_connections`, and the container/host open-file limits for the
target workload. Adjust and test them together before relying on the larger machine profiles.
More CPU or RAM alone does not raise a configured connection limit. See
[Nginx connection limits](https://nginx.org/en/docs/ngx_core_module.html#worker_connections).

## Multi-server deployment: separate application and data services

This layout uses one application host, a separate PostgreSQL host, a separate Redis host, and
external object storage. It allows each component to be sized and expanded independently.

### Initial machine profiles

| Target peak online users | Application server | PostgreSQL server | Redis server | Basis |
| --- | --- | --- | --- | --- |
| 100 | 4 vCPU / 8 GiB RAM | 2 vCPU / 4 GiB RAM | 1 vCPU / 2 GiB RAM | Planning estimate; validate with your workload. |
| 500 | 4 vCPU / 16 GiB RAM | 2 vCPU / 8 GiB RAM | 2 vCPU / 8 GiB RAM | Planning estimate; validate with your workload. |
| 1,000 | 8 vCPU / 32 GiB RAM | 4 vCPU / 16 GiB RAM | 2 vCPU / 16 GiB RAM | Operator-reported production reference below. |

Object storage is additional to these machines. For self-managed MinIO or another object-storage
service, budget its hardware separately. The 100- and 500-user rows are unbenchmarked pilot
estimates that retain resources for baseline service overhead. They are not derived by dividing
user counts into the larger machines' specifications.

### Production reference for 1,000 users

An operator reports approximately **1,000 users editing online** with:

- Application services on [EC2 t2.2xlarge](https://aws.amazon.com/ec2/instance-types/t2/):
  8 vCPU and 32 GiB RAM.
- PostgreSQL on [EC2 t3.xlarge](https://aws.amazon.com/ec2/instance-types/t3/):
  4 vCPU and 16 GiB RAM.
- Redis on [EC2 r6g.large](https://aws.amazon.com/ec2/instance-types/r6g/):
  2 vCPU and 16 GiB RAM.
- AWS S3 for object storage.

This is **14 provisioned vCPU and 64 GiB RAM across three machines, plus S3**. The 8 vCPU / 32 GiB
application host excludes PostgreSQL, Redis, and object storage. Adding the machine specifications
together does not establish an equivalent single-server capacity: processor families, storage,
CPU credits, and contention differ.

The user count records production experience; the report does not include a reproducible benchmark
specifying edit rates, dataset, duration, and latency/error results. Use it as a reference for a
similar workload and validate the Commercial release you plan to deploy. It is not a tested maximum
or a guarantee for every 1,000-user workload.

Equal vCPU counts can deliver different performance across instance families. The T2 application
host and T3 PostgreSQL host use
[CPU credits](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-credits-baseline-concepts.html).
Record Standard or Unlimited mode and monitor `CPUUtilization` and `CPUCreditBalance` on both.
[Standard mode](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-performance-instances-standard-mode.html)
limits sustained CPU after credits are depleted;
[Unlimited mode](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-performance-instances-unlimited-mode-concepts.html)
can incur surplus-credit charges. For sustained demand, consider predictable sustained CPU capacity
and validate the chosen hardware.

### Configure the service placement

1. Provision compatible PostgreSQL with pgvector, Redis, and object storage. Configure persistent
   storage and backups for each. Keep the services on a low-latency private network where applicable.
2. Configure the application services to use the same installation's dependency endpoints and
   credentials. In Compose, review `POSTGRES_HOST`, `REDIS_HOST`, `APPFLOWY_DATABASE_URL`,
   `GOTRUE_DATABASE_URL`, `APPFLOWY_REDIS_URI`, and the S3 settings in your environment file. Preserve
   GoTrue's authentication-schema settings when changing its database address.
3. Adapt the deployment files to the chosen layout. Changing an endpoint does not disable a bundled
   container. When excluding local PostgreSQL, Redis, or MinIO, also reconcile dependency health
   checks, proxy routes, and any backup/restore configuration that refers to them. Validate the
   resulting Compose configuration before starting it.
4. For Kubernetes, use the [Helm guide](../helm/appflowy-cloud/README.md) to configure external
   dependencies and disable the corresponding bundled services. Account for cluster overhead.
5. Start the application deployment and verify sign-in, editing, attachments, and search through
   the configured public URL. Measure application-to-dependency latency as part of the pilot.

The supplied root Compose file implements the single-server layout. The steps above require a
configuration adapted to external dependencies. Separate Compose projects on different machines
do not share the default service-name network; use reachable private DNS names or addresses.

After startup, application containers run on their application host and send database, Redis, and
object-storage requests over the network. The external services remain on their own hosts; Compose
on the application machine does not manage their lifecycle or backups. Monitor all hosts together.
Separating services permits independent resizing but does not automatically provide failover.

## Plan storage and memory

Use SSD-backed storage for PostgreSQL and the Search index. Record capacity, IOPS, and throughput.
For a single-server deployment, include all local services' data and I/O on the same machine; for
a multi-server deployment, calculate the budget for each host and volume.

| Location | Include in the budget |
| --- | --- |
| PostgreSQL | Database files, indexes, history, WAL, and maintenance/restore space. |
| MinIO or external object storage | Attachments, collaboration data, published content, retained versions, and growth. |
| Search | Persistent keyword indexes and rebuild/maintenance space. |
| Redis | In-memory data, streams/queues, and disk space for the configured persistence policy. |
| Application host | OS, container images, rotated logs, import extraction, and export staging. |
| Backups | Retained archives, capture/restore scratch space, and an independent backup destination. |

As an initial planning allowance, retain **30% free disk space after forecast growth and required
maintenance space**. For example, 150 GiB of data and temporary work needs `150 / 0.70 = 214.3 GiB`;
a 250 GiB volume meets that example budget. Apply this per volume and revise it using measured
growth. It is a planning allowance, not an AppFlowy storage requirement.

Compressed imports can expand substantially. Workspace storage figures also omit some physical
copies, indexes, and backups. Measure physical usage and test restore space; see the
[Backup guide](BACKUP.md).

Budget RAM for every process, filesystem cache, and overlapping jobs. Leave room on the Redis host
beyond its configured data limit for overhead and persistence operations. Container limits and
Kubernetes requests do not establish user capacity. Search's mapped index capacity differs from
resident RAM; see [Search configuration](SEARCH_CONFIG.md).

Large imports, exports, reindexing, history restores, and backups can exceed ordinary editing demand.
Measure their overlap and allocate more resources or schedule them outside peak hours. Size local
AI inference separately; see [AI model configuration](MODEL_CONFIG.md).

## Validate capacity and expand

Before rolling out either topology to the full organization:

1. Record the release, image digests, machine types, limits, storage, enabled features, and topology.
   Use compatible Commercial images and sufficient license seats.
2. Prepare an isolated pilot with representative pages, databases, attachments, permissions, and
   history, including large workspaces.
3. Define the peak user target and activity: edits, reads, searches, idle sessions, shared documents,
   and background jobs. Generate load from a separate machine.
4. Increase gradually: for example, 25, 50, and 100 users, then 250 and 500, then 750 and 1,000 as
   appropriate. Let each step stabilize and stop if latency, correctness, or resource pressure
   becomes unacceptable.
5. Measure a representative busy period and a longer soak. Include reconnects, cold starts, and
   intended job overlap. Watch memory, queue growth, CPU credits, and disk I/O.
6. Verify that edits reach collaborators and remain saved after reconnecting, search catches up,
   and queues drain. Successful HTTP responses alone do not establish correct synchronization.

Agree on acceptance targets before testing. Record p95/p99 client editing, page-opening and search
latency, failures/retries, resource headroom, workload rates, and duration. Repeat after substantial
changes to versions, content, features, or hardware.

| Signal | What to investigate or expand |
| --- | --- |
| Sustained CPU pressure or throttling | Identify the busy service, its limit, and competing jobs. Add sustained CPU or reduce overlap. Check CPU credits independently. |
| Falling available memory, swapping, or out-of-memory restarts | Check working sets, caches, container limits, and job overlap. Increase memory where pressure occurs. |
| PostgreSQL query latency, pool waits, or I/O pressure | Check slow queries, connection budgets, memory, disk latency, and IOPS. Expand the constrained database resource. |
| Redis latency, memory growth, evictions, or queues | Check data growth, commands, persistence overhead, and network latency. Size its host and data limit together. |
| Imports or indexing fall behind | Track queue age and duration. Check the owning service and its database/storage dependencies. |
| Editing slows or clients reconnect repeatedly | Correlate client latency with application, dependency, and network metrics; verify sync correctness. |
| Disk space falls | Review retention, scratch space, and growth; expand before maintenance space is exhausted. |

On one machine, expand the host or move the constrained service out. Across multiple machines,
expand the affected host first. Extra application replicas add database connections and dependency
load; keep aggregate pool limits within PostgreSQL's connection budget, with administrative headroom.

The supplied Helm chart runs Search as a single writer with a persistent index. Increase its
resources as needed; do not run multiple Search replicas against the same index directory. See the
[Helm guide](../helm/appflowy-cloud/README.md).
