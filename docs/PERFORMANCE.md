[Home](../README.md) | [Docs](../README.md#documentation) | [Architecture](../ARCHITECTURE.md) | [FAQ](FAQ.md)

---

# Performance Guide

> **TL;DR:** Constant 4GB RAM usage regardless of dataset size. Tested with hundreds of GB. PostgreSQL handles large datasets efficiently.

## PostgreSQL Backend Performance

### Memory Usage

| RAM | Configuration | Performance |
|-----|---------------|-------------|
| 4GB | `--no-user-pages --memory-limit 2.0` | Process large datasets, no user pages |
| 8GB | Default settings | Optimal for most archives |
| 16GB+ | Parallel user pages enabled | Fastest performance |

**Key Advantage**: Memory usage is constant - 4GB RAM works for 10GB or 1TB dataset.

---

## Database Storage

| Input (.zst) | PostgreSQL DB | HTML Output | Example |
|--------------|---------------|-------------|---------|
| 93.6MB | ~150MB | 1.4GB | r/technology |
| 100MB | ~160MB | ~1.5GB | Small archives |
| 500MB | ~800MB | ~7.5GB | Research projects |
| 2GB | ~3.2GB | ~30GB | Large collections |
| 100GB | ~160GB | ~1.5TB | Enterprise-scale |

**Storage ratio**: Database is ~1.6x compressed input, HTML is ~15x input size.

---

## Processing Speed

**Import Phase** (to PostgreSQL):
- Streaming ingestion with constant memory
- 15,000+ posts/second with COPY protocol
- Efficient for any dataset size

**Export Phase** (HTML generation):
- Database-backed rendering
- Keyset pagination (O(1) regardless of offset)
- Parallel user page generation (if 16GB+ RAM)

**Search Indexing**:
- Instant with PostgreSQL GIN indexes
- No separate indexing step required

---

## Dynamic Serving Performance

Measured on real data (26K-post community, `REDDARCHIVER_SERVE_MODE=dynamic`):

| Route | Latency (p50) |
|---|---|
| Subreddit index (any page/sort) | 1–23ms |
| Cross-subreddit `/all/` | ~24ms |
| Filtered listing (`?min_score=&from=`) | ~1ms |
| Post page (300+ comments) | ~22ms |
| User page | ~12ms |
| API endpoints / FTS search | 1–6ms |

What makes it fast:
- **Exact-match queries + canonical-name resolution**: user-facing input
  (URLs, API params, search operators) is case-normalized once at the
  boundary, so every query hits composite B-tree indexes directly.
- **Listing cache**: pagination counts, score-range samples, and subreddit
  stats are cached in-process (`REDDARCHIVER_LISTING_CACHE_TTL`, default 300s).
- **HTTP caching**: all GET responses carry `Cache-Control: public, max-age`
  plus ETags — repeat visits revalidate with 304s
  (`REDDARCHIVER_HTTP_CACHE_MAX_AGE`, default 300s, `0` disables).
- **Trimmed payloads**: listing queries strip `selftext` server-side (index
  rows never render it).

---

## Static Output Performance

Lighthouse (simulated slow 4G): **94–100 performance, 100 accessibility,
100 best-practices, ~0 CLS, 0ms blocking time** (the output contains no
JavaScript). Typical page weight is 3–32KB gzipped plus ~13KB gzipped CSS.

For high-traffic static deployments, export with `--precompress` to write
`.gz` siblings next to every page — the bundled nginx configs have
`gzip_static on`, serving precompressed responses with zero per-request
compression CPU.

---

## Search Performance

**PostgreSQL FTS Performance**:
- **GIN Indexes**: Optimized for text search
- **Concurrent Queries**: Multiple simultaneous searches via connection pooling
- **Memory Efficient**: Constant usage with streaming results

**Query Speed** (approximate):
- Simple queries: <100ms
- Complex multi-term: <500ms
- Large result sets: <1 second

See [SEARCH.md](SEARCH.md) for search-specific performance details.

---

## Architecture Benefits

**Why PostgreSQL v1.0 is Fast**:
- **Constant Memory**: 4GB RAM regardless of dataset size
- **Streaming Processing**: No need to load entire dataset
- **Indexed Search**: GIN indexes for instant lookups
- **Resume Capability**: Database-backed progress tracking
- **Concurrent Operations**: Multi-connection pool for parallelism

---

## Performance Tuning

### Environment Variables

```bash
# Connection Pool (default: auto-detect)
REDDARCHIVER_MAX_DB_CONNECTIONS=8

# Parallel Workers (default: auto-detect)
REDDARCHIVER_MAX_PARALLEL_WORKERS=4

# User Page Batch Size (default: 2000)
REDDARCHIVER_USER_BATCH_SIZE=2000

# Memory Limit in GB (default: auto-detect)
REDDARCHIVER_MEMORY_LIMIT=8.0
```

### CLI Flags

```bash
--debug-memory-limit 8.0      # Override memory limit
--debug-max-connections 8     # Override DB connection pool
--debug-max-workers 4         # Override parallel workers
```

### PostgreSQL Tuning

The Docker deployment ships a tuned `postgres.conf` (memory sizing, WAL/
checkpoint spreading for bulk COPY imports, `random_page_cost = 1.1` so the
planner favors index scans on SSD-class storage). For bigger dedicated hosts,
scale the memory settings proportionally:

```ini
# postgres.conf — scale up for a dedicated 16GB+ host
shared_buffers = 4GB              # ~25% of RAM
effective_cache_size = 12GB       # ~75% of RAM
work_mem = 64MB
maintenance_work_mem = 1GB
max_wal_size = 8GB                # bulk imports generate WAL quickly
```

The import path additionally sets `synchronous_commit = off` and
`maintenance_work_mem = 4GB` per session during bulk loading, and the
user-statistics aggregation raises its own `work_mem` — no manual steps
needed.

---

## See Also

- [SCALING.md](SCALING.md) - Horizontal scaling for very large archives
- [ARCHITECTURE.md](../ARCHITECTURE.md) - Technical architecture details
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Performance issues
- [FAQ - Performance](FAQ.md#performance) - Common performance questions

---

**Last Updated**: 2026-06-12
