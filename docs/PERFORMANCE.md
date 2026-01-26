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

For large archives, tune PostgreSQL settings:
```sql
-- Increase shared buffers (25% of RAM)
shared_buffers = 2GB

-- Increase work memory
work_mem = 256MB

-- Increase maintenance work memory
maintenance_work_mem = 1GB
```

---

## See Also

- [SCALING.md](SCALING.md) - Horizontal scaling for very large archives
- [ARCHITECTURE.md](../ARCHITECTURE.md) - Technical architecture details
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Performance issues
- [FAQ - Performance](FAQ.md#performance) - Common performance questions

---

**Last Updated**: 2026-01-26
