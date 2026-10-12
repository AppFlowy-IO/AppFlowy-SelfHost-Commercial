# Hardware requirements and sizing

[Documentation](README.md)

Use these starting profiles to size AppFlowy Self-Hosted Commercial for 100, 500, or 1,000 peak
online users. For installation instructions, see [Docker Compose](docker-compose.md) or
[Kubernetes/Helm](../helm/appflowy-cloud/README.md).

## Sizing assumptions

User counts mean people online during the busiest period, with a mix of editing, reading,
searching, and pauses. The figures are **planning estimates**; validate them with your expected
activity and content before production use.

The profiles assume one instance of each application service and external AI model providers.
Allow additional resources for large imports, exports, reindexing, backups, monitoring, and
Kubernetes overhead where applicable. Size local AI inference separately.

## Single-server sizing

All application services, PostgreSQL, Redis, and MinIO share one machine, as in the default Docker
Compose installation. These figures cover the **whole machine**, including local object storage.

| Peak online users | CPU | RAM |
| --- | --- | --- |
| 100 | 4 vCPU | 16 GiB |
| 500 | 8 vCPU | 32 GiB |
| 1,000 | 16 vCPU | 64 GiB |

Leave capacity for the operating system, filesystem cache, and traffic bursts. All services share
the same CPU, memory, and disk I/O.

## Multi-server sizing

Application services share one host; PostgreSQL and Redis each use a separate host. Object storage
runs separately on S3-compatible storage.

| Peak online users | Application server | PostgreSQL server | Redis server |
| --- | --- | --- | --- |
| 100 | 4 vCPU / 8 GiB RAM | 2 vCPU / 4 GiB RAM | 1 vCPU / 2 GiB RAM |
| 500 | 4 vCPU / 16 GiB RAM | 2 vCPU / 8 GiB RAM | 2 vCPU / 8 GiB RAM |
| 1,000 | 8 vCPU / 32 GiB RAM | 4 vCPU / 16 GiB RAM | 2 vCPU / 16 GiB RAM |

Budget object-storage hardware separately when it is self-managed. Each host needs its own
resource headroom; the application-server figures exclude PostgreSQL, Redis, and object storage.

## Storage requirements

Use SSD-backed storage for PostgreSQL and Search. Size disk capacity from your data, retention,
and growth, and check that IOPS and throughput meet peak demand.

| Component | Include in the storage budget |
| --- | --- |
| PostgreSQL | Data, indexes, history, WAL, and maintenance or restore space. |
| Object storage | Attachments, collaboration data, published content, and retained versions. |
| Search | Persistent indexes and rebuild space. |
| Redis | Space for the chosen persistence policy, in addition to RAM. |
| Application host | OS, container images, logs, import extraction, and export staging. |
| Backups | Retained archives and restore space, with an independent backup destination. |

As an initial allowance, keep **30% free disk space after forecast growth and maintenance needs**.
Measure physical storage use: user count and compressed import size alone do not determine it.

## When to add capacity

Measure a representative busy period, including background jobs. Track user-visible latency and
errors alongside resource use, then expand the constrained resource.

| Constraint | Resource to assess |
| --- | --- |
| Sustained CPU saturation | CPU capacity on the affected host. |
| Low available memory, swapping, or out-of-memory failures | RAM and peak working-set size. |
| High database or index I/O latency | Storage IOPS and throughput. |
| Slow uploads, downloads, or object-storage transfers | Network bandwidth and latency. |
| Insufficient space for growth or maintenance | Disk or object-storage capacity. |

Choose CPUs with enough sustained performance for the workload; equal vCPU counts can perform
differently across instance families. For separate hosts, keep application-to-database and Redis
latency low. Resize the affected host or separate a resource-intensive service as demand grows.
