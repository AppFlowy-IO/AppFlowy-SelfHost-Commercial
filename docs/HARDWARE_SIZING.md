# Hardware requirements and sizing

[Documentation](README.md)

This guide helps you choose CPU, memory, storage, and database settings for AppFlowy Self-Hosted
Commercial. It gives example hardware profiles for single-server and multi-server deployments, the
PostgreSQL settings each profile needs, and the warning signs that tell you a deployment has
outgrown its profile. **The example user counts are planning points, not a maximum deployment
size.**

For installation instructions, see [Docker Compose](docker-compose.md) or
[Kubernetes/Helm](../helm/appflowy-cloud/README.md).

## Sizing assumptions

**Peak online users** means the number of people using AppFlowy at the same time during your
busiest period, with a normal mix of editing, reading, searching, and pauses. Size for this
concurrent activity, not for the total number of registered accounts.

All figures are **planning estimates**. Real capacity depends on how active your users are, how
large your content is, and how much background processing runs (indexing, imports, backups).
Validate the profile you choose with a representative workload before production use, then keep
an eye on the [capacity signals](#capacity-signals) after go-live.

The profiles assume one instance of each application service and externally hosted AI models.
Leave room for the operating system and the filesystem cache. Add resources for large imports and
exports, index rebuilds, backups, monitoring, and orchestration. Size additional replicas and
local AI inference separately.

## Choosing hosts

### Use fixed-performance CPUs

Do not run the application or PostgreSQL hosts on burstable or shared-core instance types (for
example AWS T-series, Azure B-series, or Google Cloud shared-core E2) unless you enable the
provider's unlimited-credit mode. These instances only deliver their full vCPU count while they
have CPU credits. Once the credits run out, which happens as soon as the average load stays above
a baseline of 10–40 % of the vCPUs, the host reports high CPU "steal" time, every database and
Redis round trip slows down, and no application setting can compensate. Prefer current-generation
general-purpose or compute-optimized families; equal vCPU counts perform differently across
processor generations.

### Keep the hosts close

Place the application, PostgreSQL, and Redis hosts in the same datacenter or availability zone,
with a round-trip time below 1 ms. Each collaboration update makes several database and Redis
round trips, so distance between hosts shows up as latency for every user. On public clouds,
cross-zone placement also adds per-gigabyte transfer charges in both directions.

### Monitor every host

Collect host metrics (CPU including steal time, memory, disk IOPS and throughput, network) on
every host, including the database hosts. The [capacity signals](#capacity-signals) below depend
on them, and a database host without metrics cannot tell you when it is running out of memory.

## Single-server sizing

All application services, PostgreSQL, Redis, and MinIO run on one host, as in the default Docker
Compose installation. CPU and memory figures apply to the **entire host**, including MinIO.

| Peak online users | CPU | RAM |
| --- | --- | --- |
| 100 | 4 vCPU | 16 GiB |
| 500 | 8 vCPU | 32 GiB |
| 1,000 | 16 vCPU | 64 GiB |

All services share CPU, memory, and disk I/O, so plan for application traffic and storage
operations at the same time. Give PostgreSQL an explicit share of the RAM with the
[memory settings](#memory-settings) below; it does not take that share by itself.

## Multi-server sizing

Application services share one host; PostgreSQL and Redis each use a dedicated host.
S3-compatible object storage runs separately from these three hosts.

| Peak online users | Application server | PostgreSQL server | Redis server |
| --- | --- | --- | --- |
| 100 | 4 vCPU / 8 GiB RAM | 2 vCPU / 4 GiB RAM | 1 vCPU / 2 GiB RAM |
| 500 | 4 vCPU / 16 GiB RAM | 4 vCPU / 16 GiB RAM | 2 vCPU / 8 GiB RAM |
| 1,000 | 8 vCPU / 32 GiB RAM | 8 vCPU / 32 GiB RAM | 2 vCPU / 16 GiB RAM |

Figures are **per host**, and each host needs spare capacity for peak demand. PostgreSQL is
usually the first host to reach its limit, so give its RAM the extra check in
[IOPS and throughput](#iops-and-throughput): the more of the database that fits in memory, the
less disk I/O you need. Budget self-managed object storage separately. This layout lets you resize
each host independently.

## Kubernetes resource requests and limits

The Helm chart's default `resources` values are sized for evaluation clusters. Set them explicitly
for production. The table gives values for the 1,000-user profile. At 500 users, halve the
requests and keep the limits. At 100 users, the chart defaults are enough, except that
`appflowy-cloud` needs limits of at least 1 CPU and 2 GiB.

| Service | CPU request / limit | Memory request / limit |
| --- | --- | --- |
| appflowy-cloud | 1.5 / 5 | 2.5 GiB / 6 GiB |
| appflowy-worker | 0.5 / 2.5 | 1.5 GiB / 6 GiB |
| appflowy-search | 0.5 / 2 | 2 GiB / 4 GiB |
| gotrue | 0.1 / 0.5 | 128 MiB / 512 MiB |
| appflowy-ai | 0.1 / 1 | 256 MiB / 1 GiB |
| appflowy-web, admin-frontend (each) | 0.05 / 0.2 | 128 MiB / 256 MiB |
| nginx or ingress controller | 0.1 / 1 | 256 MiB / 768 MiB |
| postgresql (bundled chart) | match the PostgreSQL server row | match the PostgreSQL server row |
| redis (bundled chart) | 0.5 / 1 | 8 GiB / 12 GiB |
| minio (bundled chart) | 0.5 / 2 | 1 GiB / 4 GiB |

Three rules keep these values healthy:

- **Set CPU limits to about twice the request.** A limit close to the request throttles the
  service during bursts even when the node has idle CPU. Throttling shows up as a rising
  `nr_throttled` count in the container's `cpu.stat` and as slower requests.
- **Leave room for rolling updates.** Kubernetes runs the old and the new pod of a service at the
  same time, so the node needs free CPU and memory equal to the largest pod's request, and
  PostgreSQL needs room for a second `appflowy-cloud` connection pool (see the
  [connection budget](#connection-budget)). `appflowy-search` runs one replica with a `Recreate`
  strategy and needs no extra room.
- **Keep memory limits above real usage.** A container that exceeds its memory limit is killed
  (exit code 137) and restarts, which disconnects every user on it.

## PostgreSQL configuration

### Connection budget

Each service keeps its own pool of PostgreSQL connections. When the pools together exceed
PostgreSQL's `max_connections`, new connections fail with "too many clients already" and the
application logs pool-acquire timeouts. Size `max_connections` from the pools, not the other way
round.

| Service | Setting | Default |
| --- | --- | --- |
| appflowy_cloud | `APPFLOWY_DATABASE_MAX_CONNECTIONS` | 40 in `deploy.env` |
| appflowy_cloud audit log | `APPFLOWY_AUDIT_DB_MAX_CONNECTIONS` | 4 |
| appflowy_worker | `APPFLOWY_WORKER_DATABASE_MAX_CONNECTIONS` | 16 |
| appflowy_search | `APPFLOWY_SEARCH_DATABASE_MAX_CONNECTIONS` and `APPFLOWY_SEARCH_EMBEDDING_DB_MAX_CONNECTIONS` | 20 and 10 |
| gotrue | `GOTRUE_DB_MAX_POOL_SIZE` | unlimited when unset; set it to 10 |
| AI, backup, and administrative sessions | — | reserve 20 |

Add the pools, add the `appflowy_cloud` pool once more if you use rolling updates, and round up:

| Peak online users | `APPFLOWY_DATABASE_MAX_CONNECTIONS` | PostgreSQL `max_connections` |
| --- | --- | --- |
| 100 | 40 | 200 |
| 500 | 100 | 350 |
| 1,000 | 200 | 500 |

PostgreSQL's default `max_connections` of 100 is fully allocated by the default pools, so raise it
even for the smallest profile. Budget about 10 MiB of RAM per connection, plus `work_mem` for each
active sort or hash. `appflowy_cloud` divides its pool into internal lanes for general queries,
collaboration, permissions, and websocket sessions; values below 40 leave each lane only a few
connections, so do not go lower. The services connect as the database superuser by default, which
means `superuser_reserved_connections` does not protect your administrative access; the reserve of
20 above does.

### Memory settings

PostgreSQL starts with conservative defaults (`shared_buffers` is 128 MB) and will not use the RAM
you give the host unless you tell it to. Set these values for the RAM available to PostgreSQL: the
whole host in the multi-server layout, or its share of the host in the single-server layout.

| RAM for PostgreSQL | `shared_buffers` | `effective_cache_size` | `work_mem` | `maintenance_work_mem` |
| --- | --- | --- | --- | --- |
| 4 GiB | 1 GB | 3 GB | 16 MB | 256 MB |
| 8 GiB | 2 GB | 6 GB | 32 MB | 512 MB |
| 16 GiB | 4 GB | 12 GB | 64 MB | 1 GB |
| 32 GiB | 8 GB | 24 GB | 64 MB | 2 GB |

On SSD storage also set `random_page_cost = 1.1`.

How to apply the settings:

- **Docker Compose:** extend the `command` of the `postgres` service in `docker-compose.yml`,
  keeping the existing port flag, for example
  `command: ["postgres", "-c", "port=5432", "-c", "max_connections=200", "-c", "shared_buffers=1GB", "-c", "effective_cache_size=3GB"]`,
  or mount your own `postgresql.conf`.
- **Helm (bundled PostgreSQL):** set `postgresql.primary.extendedConfiguration`.
- **Managed PostgreSQL** (Amazon RDS, Cloud SQL, Azure Database): use the service's parameter
  group. Managed defaults for `max_connections` depend on the instance size, so check them against
  the budget above.

## Storage requirements

Use SSD-backed storage for PostgreSQL and Search. Size disk capacity for data volume, retention,
and forecast growth. Check that storage IOPS and throughput meet peak demand.

| Component | Include in the storage budget |
| --- | --- |
| PostgreSQL | Data, indexes, history, write-ahead logs (WAL), and maintenance or restore space. |
| Object storage | Attachments, collaboration data, published content, and retained versions. |
| Search | Persistent indexes and rebuild space. |
| Redis | Space for the chosen persistence policy, in addition to RAM. |
| Application host | Operating system, container images, logs, and temporary import/export files. |
| Backups | Retained archives and restore space, with an independent backup destination. |

Keep free space for growth and temporary maintenance needs. Estimate capacity from measured
storage use; user count and compressed import size alone are insufficient.

### IOPS and throughput

Cloud block volumes cap IOPS and throughput separately from capacity. An AWS gp3 volume, for
example, delivers 3,000 IOPS and 125 MiB/s at any size unless you pay for more, and small Azure
and Google Cloud disks deliver far less. Check the cap, not only the size.

| Peak online users | PostgreSQL volume | Search volume |
| --- | --- | --- |
| 100 | 3,000 IOPS, 125 MiB/s | 3,000 IOPS |
| 500 | 3,000–6,000 IOPS, 250 MiB/s | 3,000 IOPS |
| 1,000 | 6,000 IOPS or more, 250 MiB/s | 3,000 IOPS |

PostgreSQL disk traffic is mostly reads, and reads only reach the disk when the working set does
not fit in memory. As a planning rule, keep the PostgreSQL host's RAM at 15–25 % of the database
size. Below that, expect several thousand random read IOPS all day, and either add RAM or raise
the volume's IOPS cap.

## Capacity signals

These are the signs that a deployment has outgrown its profile, and what to do about each.

| Signal | What it means | What to do |
| --- | --- | --- |
| CPU steal time above 5 %, or a cloud CPU credit balance at zero | A burstable instance is being throttled | Move to a fixed-performance instance type, or enable unlimited mode |
| PostgreSQL backends above 80 % of `max_connections`, "too many clients already" errors, or pool-acquire timeouts in the `appflowy_cloud` logs | The connection budget is exhausted | Raise `max_connections` per the budget; on Kubernetes, check for rolling-update overlap |
| The PostgreSQL volume runs at its IOPS or throughput cap, with sustained random reads | The working set is larger than RAM, or the volume cap is too low | Add RAM to the PostgreSQL host first, then raise the cap |
| PostgreSQL CPU above 60 % for hours at a time | The database host is undersized | Move to the next profile |
| Container CPU throttling (`nr_throttled` rising in `cpu.stat`) with slower requests | The CPU limit is below demand | Raise the limit to about twice the request |
| Containers killed with exit code 137 | The memory limit is below demand | Raise the memory limit |
| Redis `used_memory` close to the host RAM or to `maxmemory`, or evictions | Redis is undersized | Add RAM to the Redis host |

## Reference measurements

AppFlowy's hosted beta environment runs this stack on Kubernetes at roughly the 1,000-user
profile. These measurements from October 2026 show what the profile carries in practice and are
the basis for the figures above.

| Component | Hardware | Observed load |
| --- | --- | --- |
| Peak online users | — | 1,100–1,180 on weekdays, 700–780 at weekends |
| Application host | 8 vCPU / 32 GiB, fixed-performance | All pods together: 3.9 cores and 8.6 GiB at the 95th percentile; 1-minute peaks of 6.6 cores during rolling updates |
| PostgreSQL host | 4 vCPU / 16 GiB | 55–75 % CPU with peaks above 80 %; 3,300 commits/s; 170 GiB of data; 2,000–2,900 random read IOPS all day because the working set exceeds RAM |
| Redis host | 2 vCPU / 16 GiB | 0.7 cores, 5.6 GiB used, 245 client connections |
| Object storage | S3 | 1.2 TiB of attachments and collaboration data, plus 3.3 TiB of retained backups |

The PostgreSQL host is the component closest to its limit, which is why the 1,000-user profile
specifies 8 vCPU / 32 GiB for PostgreSQL rather than the 4 vCPU / 16 GiB this environment runs.

## Larger deployments

For deployments above 1,000 peak online users, [contact AppFlowy](https://appflowy.com/contact)
for hardware sizing and capacity planning guidance. Include your expected peak concurrency,
data volume, and growth plans.
