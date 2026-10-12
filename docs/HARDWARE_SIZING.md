# Hardware requirements and sizing

[Documentation](README.md)

This guide provides initial hardware sizing for AppFlowy Self-Hosted Commercial with 100, 500,
or 1,000 peak online users. It covers CPU, memory, storage, and network capacity for single-server
and multi-server installations. For installation instructions, see [Docker Compose](docker-compose.md)
or [Kubernetes/Helm](../helm/appflowy-cloud/README.md).

## Sizing assumptions

User counts refer to **people online during the busiest period**, with a mix of editing, reading,
searching, and pauses. Registered accounts, connected devices, and continuously active editors
represent different loads. Record editing rates and the number of people sharing a document when
assessing capacity.

The profiles assume one instance of each application service and external AI model providers.
Large imports, exports, reindexing, backups, and history restores require additional measured
capacity when they overlap with normal traffic. Budget separately for local AI inference,
monitoring, optional services, and Kubernetes overhead where applicable.

Unless identified as a production reference, the figures below are **planning estimates**. They
are starting configurations for workload validation, not benchmarked capacities or minimum system
requirements. Content size, activity rates, background work, and the AppFlowy release affect the
resources required.

## Single-server sizing

All application services, PostgreSQL, Redis, and MinIO share one machine, as in the default Docker
Compose installation. The figures below cover the **whole machine**, including local object storage.

| Peak online users | CPU | RAM | Storage |
| --- | --- | --- | --- |
| 100 | 4 vCPU | 16 GiB | SSD; capacity based on data and retention. |
| 500 | 8 vCPU | 32 GiB | SSD; capacity based on data and retention. |
| 1,000 | 16 vCPU | 64 GiB | SSD; capacity based on data and retention. |

All three profiles are estimates. PostgreSQL, object storage, and application jobs compete for the
same CPU, memory, and disk I/O. Leave capacity for the operating system, filesystem cache, and
traffic bursts. Validate the complete workload before selecting the final machine size.

## Multi-server sizing

Application services share one host; PostgreSQL and Redis each use a separate host. Object storage
runs separately on AWS S3 or another compatible service.

| Peak online users | Application server | PostgreSQL server | Redis server | Evidence |
| --- | --- | --- | --- | --- |
| 100 | 4 vCPU / 8 GiB RAM | 2 vCPU / 4 GiB RAM | 1 vCPU / 2 GiB RAM | Planning estimate. |
| 500 | 4 vCPU / 16 GiB RAM | 2 vCPU / 8 GiB RAM | 2 vCPU / 8 GiB RAM | Planning estimate. |
| 1,000 | 8 vCPU / 32 GiB RAM | 4 vCPU / 16 GiB RAM | 2 vCPU / 16 GiB RAM | Operator-reported production reference. |

Object-storage hardware is additional to these figures when it is self-managed. The smaller
profiles retain resources for baseline service overhead; capacity does not scale proportionally
with user counts.

### Production reference

An operator reports approximately **1,000 users editing online** with the following AWS machines:

| Component | Instance | CPU | RAM |
| --- | --- | --- | --- |
| Application services | [t2.2xlarge](https://aws.amazon.com/ec2/instance-types/t2/) | 8 vCPU | 32 GiB |
| PostgreSQL | [t3.xlarge](https://aws.amazon.com/ec2/instance-types/t3/) | 4 vCPU | 16 GiB |
| Redis | [r6g.large](https://aws.amazon.com/ec2/instance-types/r6g/) | 2 vCPU | 16 GiB |
| Object storage | AWS S3 | Managed service | Managed service |

The compute footprint is **14 provisioned vCPU and 64 GiB RAM across three machines, plus S3**.
The application-server figures exclude PostgreSQL, Redis, and object storage. Combining these
resources into one machine does not establish an equivalent capacity because storage performance,
processor characteristics, and resource contention differ.

This reference records production experience. The report does not include a reproducible benchmark
with defined edit rates, dataset, duration, and latency results. Validate a comparable workload on
the intended Commercial release; the reported user count is not a tested maximum.

## Storage requirements

Use SSD-backed storage for PostgreSQL and Search. Specify **capacity, IOPS, and throughput** for each
volume. In a single-server installation, account for the combined I/O demand of all local services.

| Component | Storage allowance |
| --- | --- |
| PostgreSQL | Database files, indexes, history, WAL, and maintenance or restore working space. |
| MinIO or external object storage | Attachments, collaboration data, published content, retained versions, and growth. |
| Search | Persistent indexes and rebuild or maintenance space. |
| Redis | Space for the selected persistence policy, in addition to its RAM allocation. |
| Application host | Operating system, container images, logs, import extraction, and export staging. |
| Backups | Retained archives and capture/restore working space, with an independent backup destination. |

As an initial planning allowance, retain **30% free space after forecast growth and maintenance
needs**. For example, 150 GiB of data and working space requires `150 / 0.70 = 214.3 GiB` of capacity;
a 250 GiB volume meets that example budget. Apply this calculation per volume and revise it using
measured growth.

Disk capacity cannot be determined from user count alone. Large attachments, retained history, and
imports can dominate storage growth. Compressed import size also understates extraction space.
Measure physical storage use, including indexes and backups.

## CPU, memory, and network considerations

| Resource | Sizing considerations |
| --- | --- |
| CPU | Account for sustained editing/search demand and background job peaks. Equal vCPU counts can perform differently across processor generations and instance families. |
| RAM | Include every service's working set, caches, OS overhead, and concurrent jobs. Leave Redis memory headroom for process overhead and persistence operations. |
| Disk I/O | Measure PostgreSQL and Search latency during peak traffic and maintenance. A larger disk alone does not establish sufficient IOPS or throughput. |
| Network | Size bandwidth for concurrent uploads, downloads, backups, and object-storage traffic. For separate hosts, measure latency between application, PostgreSQL, Redis, and object storage. |
| Local AI inference | Size CPU/GPU memory and concurrency for the selected models separately; the tables assume external model providers. |

The production reference uses burstable T2 and T3 instances for the application and PostgreSQL
hosts. Their sustained CPU capacity depends on
[AWS CPU credits](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-credits-baseline-concepts.html).
Check credit consumption over representative busy periods. Standard mode can constrain performance
after credits are exhausted; Unlimited mode can incur surplus-credit charges. For sustained CPU
loads, consider hardware with predictable sustained performance.

## Validate and expand capacity

Validate a sizing profile with representative content, editing rates, and background work before
rolling it out to the full target group. Measure a busy period and a longer steady workload to
identify memory growth, queue buildup, CPU credit depletion, and storage pressure. Record client
latency, errors, and resource headroom alongside the online-user count.

| Observed constraint | Hardware to assess |
| --- | --- |
| Sustained CPU saturation with increasing latency | CPU capacity on the busy application or data-service host. |
| Low available memory, swapping, or out-of-memory failures | RAM on the affected host, accounting for service working sets and job overlap. |
| High database or index I/O latency | Storage IOPS, throughput, and competing activity. |
| Growing imports or indexing queues | CPU, RAM, and storage capacity of Worker/Search and their dependencies. |
| Slow uploads, downloads, or object-store requests | Network bandwidth and latency, plus object-storage throughput. |
| Insufficient space for forecast growth or maintenance | Disk or object-storage capacity and retention needs. |

With one server, resize the machine or separate the resource-constrained service. With multiple
servers, expand the affected host first. Confirm that the bottleneck is hardware: service limits,
slow queries, and network faults can also cause poor performance, and additional hardware alone
may not resolve them.
