# Configure AppFlowy Search

`appflowy_search` provides keyword and semantic search. It is included in the supplied [Docker Compose configuration](../docker-compose.yml).

## Setup

For a new installation, follow the [Docker Compose guide](docker-compose.md). For an existing installation:

1. Set `APPFLOWY_SEARCH_VERSION` in your existing `.env` to the version recommended for your AppFlowy release.
2. Keep Search connected to the same PostgreSQL, Redis, and object storage as Cloud. The supplied Compose file passes these settings to Search.
3. Keep Search on the internal network. Change `APPFLOWY_SEARCH_SERVICE_URL` only if Cloud must connect to a different Search address.

Use compatible Cloud, Worker, and Search releases. When upgrading, allow Cloud to finish its database migrations before starting the updated Worker and Search services.

## Configure the index path

Set `APPFLOWY_KEYWORD_INDEX_DIR` in `.env` to the directory **inside the Search container**. For example:

```dotenv
APPFLOWY_KEYWORD_INDEX_DIR=/data/appflowy-search
```

In `docker-compose.yml`, replace the existing index mount under `appflowy_search.volumes` so it uses the same path:

```yaml
volumes:
  - keyword_index_data:${APPFLOWY_KEYWORD_INDEX_DIR:?Set APPFLOWY_KEYWORD_INDEX_DIR in .env}
```

Keep the existing named volume and Compose project name to retain its data. The directory must be writable by Search. Changing the container path while reusing that volume does not require rebuilding its contents.

If you also move to a different volume or host directory, stop Search and copy its index data before switching. An empty index directory requires rebuilding, which can increase load and temporarily leave results incomplete. Do not remove deployment volumes during a normal upgrade.

## Configure LMDB storage

LMDB stores a separate keyword index for each workspace. Change these settings only when you need to adjust index capacity or the number of open indexes:

| Setting | Purpose |
| --- | --- |
| `APPFLOWY_KEYWORD_INDEX_MAP_SIZE_BYTES` | Initial map capacity per workspace. Lowering it does not shrink existing indexes. |
| `APPFLOWY_KEYWORD_INDEX_MAX_MAP_SIZE_BYTES` | Maximum map capacity per workspace as its index grows. |
| `APPFLOWY_KEYWORD_MAX_LOADED_WORKSPACES` | Maximum number of workspace indexes kept open. Closing an index preserves its files. |
| `APPFLOWY_KEYWORD_MAX_TOTAL_MMAP_BYTES` | Combined map-size budget for open workspace indexes. This is not a strict RAM limit. |

Set the values you want in `.env`. Byte settings require integer byte counts; the workspace setting requires a positive integer count.

The supplied Compose file already forwards `APPFLOWY_KEYWORD_INDEX_MAP_SIZE_BYTES`. For the other settings, add the corresponding entry to the existing `appflowy_search.environment` list. For example, to configure the per-workspace maximum:

```yaml
environment:
  - APPFLOWY_KEYWORD_INDEX_MAX_MAP_SIZE_BYTES=${APPFLOWY_KEYWORD_INDEX_MAX_MAP_SIZE_BYTES:?Set a byte limit in .env}
```

Keep the existing environment entries. Add each other setting using the same pattern, and set its value before applying the configuration.

Keep the per-workspace maximum at least as large as the initial map size. Allow enough aggregate budget for the indexes you expect to keep open, including their growth. Map capacity is not the same as RAM usage; monitor memory and free disk space when changing these limits.

## Enable semantic search

Keyword search does not require an AI provider.

For semantic search, configure and enable an embedding provider and model in **Admin → Settings → AI Settings**, with the applicable AI license. Follow [Configure AI models](MODEL_CONFIG.md) for setup and model changes.

Changing the embedding model requires regenerating existing embeddings. Turning off AI features does not stop keyword indexing.

## Apply changes

From the deployment directory, with compatible Cloud and its dependencies already running:

```bash
docker compose config --quiet
docker compose pull appflowy_search
docker compose up -d --no-deps appflowy_search
```

Use the same Compose files and project name as your existing deployment. If you changed Cloud's Search address, recreate Cloud as well.

Adding a variable to `.env` only takes effect when Compose passes it to the service. Use `up -d` to apply configuration changes; restarting an existing container alone does not update its environment.

## Check Search

```bash
docker compose ps appflowy_search
docker compose logs --since 10m --tail 100 appflowy_search
```

Search for a known page using an account that can access it. After editing the page, confirm that the updated content becomes searchable. A healthy container does not guarantee that indexing has finished.

If results are missing or Search remains slow, check available disk space, the index volume, and recent service errors. Share the service versions, affected workspace, UTC failure time, and relevant log entries with support. Remove credentials and document content before sharing logs.

Page-access errors require a separate permission investigation; rebuilding search indexes does not repair row permissions.
