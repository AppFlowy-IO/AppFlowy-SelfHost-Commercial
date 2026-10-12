# Hardware requirements and sizing

[Documentation](README.md)

Use this guide to plan CPU, memory, and storage for AppFlowy Self-Hosted Commercial. The tables
provide example hardware profiles for single-server and multi-server deployments. **The example
user counts do not define a maximum deployment size.**

For installation instructions, see [Docker Compose](docker-compose.md) or
[Kubernetes/Helm](../helm/appflowy-cloud/README.md).

## Sizing assumptions

**Peak online users** means people using AppFlowy simultaneously during the busiest period, with
a mix of editing, reading, searching, and normal pauses. Size for this concurrent activity rather
than the total number of registered accounts.

The figures are **planning estimates**. Actual capacity depends on activity, content size, and
background processing. Validate the selected profile with a representative workload before
production use.

The profiles assume one instance of each application service and externally hosted AI models.
Reserve capacity for the operating system and filesystem cache. Allow additional resources for
large imports, exports, index rebuilds, backups, monitoring, and orchestration. Size additional
replicas and local AI inference separately.

## Single-server sizing

All application services, PostgreSQL, Redis, and MinIO run on one host, as in the default Docker
Compose installation. CPU and memory figures apply to the **entire host**, including MinIO.

| Peak online users | CPU | RAM |
| --- | --- | --- |
| 100 | 4 vCPU | 16 GiB |
| 500 | 8 vCPU | 32 GiB |
| 1,000 | 16 vCPU | 64 GiB |

All services share CPU, memory, and disk I/O. Allow for application traffic and storage operations
running at the same time.

## Multi-server sizing

Application services share one host; PostgreSQL and Redis each use a dedicated host. S3-compatible
object storage runs separately from these three hosts.

| Peak online users | Application server | PostgreSQL server | Redis server |
| --- | --- | --- | --- |
| 100 | 4 vCPU / 8 GiB RAM | 2 vCPU / 4 GiB RAM | 1 vCPU / 2 GiB RAM |
| 500 | 4 vCPU / 16 GiB RAM | 2 vCPU / 8 GiB RAM | 2 vCPU / 8 GiB RAM |
| 1,000 | 8 vCPU / 32 GiB RAM | 4 vCPU / 16 GiB RAM | 2 vCPU / 16 GiB RAM |

Figures are **per host**. Each host needs spare capacity for peak demand. Budget hardware for
self-managed object storage separately. This layout allows each host to be resized independently.

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

## Larger deployments and capacity growth

For deployments above 1,000 peak online users, use workload-specific sizing. The multi-server
layout allows application, database, cache, and storage resources to be assessed independently.
Do not extrapolate capacity in direct proportion to user count or vCPU count.

Load-test the target concurrency with representative content and background jobs. Measure response
times, editing synchronization latency, and errors alongside resource use. Add capacity to the
component that limits performance, then repeat the test.

| Constraint | Resource to assess |
| --- | --- |
| Sustained high CPU utilization | CPU capacity on the affected host. |
| Low available memory, swapping, or out-of-memory failures | RAM and peak memory use. |
| High database or index I/O latency | Storage IOPS and throughput. |
| Slow uploads, downloads, or object-storage transfers | Network bandwidth and latency. |
| Insufficient space for growth or maintenance | Disk or object-storage capacity. |

Choose CPUs with sufficient sustained performance; equal vCPU counts can perform differently
across processor and instance families. For separate hosts, provide low-latency connections between
the application, PostgreSQL, and Redis, and sufficient bandwidth for object-storage transfers.
