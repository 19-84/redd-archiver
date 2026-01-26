[Home](../README.md) | [Docs](../README.md#documentation) | [API](API.md) | [FAQ](FAQ.md)

---

# Search Guide

> **TL;DR:** PostgreSQL full-text search with GIN indexing. Requires Docker deployment. Sub-second results, Tor-compatible, Google-style operators.

## Overview

Redd-Archiver uses PostgreSQL full-text search for lightning-fast, database-powered search capabilities:

**Key Features**:
- **GIN Indexing**: Instant lookup for large datasets
- **Relevance Ranking**: Intelligent result ordering with `ts_rank()`
- **Highlighted Excerpts**: Context with `ts_headline()`
- **Advanced Filters**: By subreddit, author, date, score
- **Concurrent Queries**: Multiple simultaneous searches
- **Constant Memory**: Efficient for any dataset size

**Why PostgreSQL FTS?**
- Native PostgreSQL indexing (no separate search engine)
- Large-scale tested (hundreds of GB)
- Tor-compatible (server-side processing)
- Sub-second response times with GIN indexes

---

## Search Architecture

### Database-Powered Search

```
User Query
    ↓
Search Server (Flask)
    ↓
PostgreSQL FTS Engine
    ↓  ← GIN Index Lookup
    ↓  ← Relevance Ranking (ts_rank)
    ↓  ← Result Highlighting (ts_headline)
Results (JSON/HTML)
```

**Advantages**:
- **Constant Memory**: Streaming results from database
- **Concurrent**: Connection pooling handles multiple users
- **Real-time**: No separate indexing step required
- **Scalable**: Efficient for datasets of any size

---

## Command-Line Interface

### Basic Search

```bash
# Search for a term
python postgres_search.py "machine learning"

# Search in specific subreddit
python postgres_search.py "privacy" --subreddit technology

# Limit results
python postgres_search.py "python" --limit 50
```

### Advanced Search

```bash
# Search with score filter
python postgres_search.py "data science" --min-score 100 --limit 20

# Search by author
python postgres_search.py "tutorial" --author specific_user

# Search with date range
python postgres_search.py "announcement" --after 2024-01-01 --before 2024-12-31

# Combine filters
python postgres_search.py "machine learning" \
  --subreddit MachineLearning \
  --min-score 50 \
  --limit 100
```

### Output Formats

```bash
# JSON output (default)
python postgres_search.py "query" --format json

# Pretty table output
python postgres_search.py "query" --format table

# Export to CSV
python postgres_search.py "query" --format csv > results.csv
```

---

## Web API Setup

### Using Docker Compose (Recommended)

```bash
# Start search server
docker compose up -d search-server

# Verify it's running
curl http://localhost:5000/health
# Expected: {"status":"healthy"}

# Access web interface
open http://localhost:5000
```

### Manual Setup

```bash
# Set database connection
export DATABASE_URL="postgresql://user:pass@localhost:5432/reddarchiver"

# Start search server
python search_server.py

# Server starts on port 5000
# Access at http://localhost:5000
```

### Web API Endpoints

**Health Check**:
```bash
GET /health
# Returns: {"status":"healthy"}
```

**Search**:
```bash
GET /search?q=query&subreddit=optional&limit=50

# Examples:
curl "http://localhost:5000/search?q=python&limit=10"
curl "http://localhost:5000/search?q=machine+learning&subreddit=MachineLearning"
curl "http://localhost:5000/search?q=privacy&min_score=100"
```

**Features**:
- RESTful JSON API
- Real-time search with PostgreSQL FTS
- Rate limiting (100 requests/minute)
- CSRF protection
- Result highlighting with `ts_headline()`

---

## Search Operators

### Google-Style Search Syntax

Redd-Archiver supports Google-style search operators:

| Operator | Syntax | Example | Description |
|----------|--------|---------|-------------|
| **Exact Phrase** | `"phrase"` | `"machine learning"` | Match exact phrase |
| **Boolean OR** | `word1 OR word2` | `python OR javascript` | Match either term |
| **Exclude** | `-term` | `python -beginner` | Exclude term |
| **Subreddit Filter** | `sub:name` | `sub:technology` | Search in specific subreddit |
| **Author Filter** | `author:name` | `author:username` | Search by author |
| **Score Filter** | `score:N` | `score:100` | Minimum score |
| **Type Filter** | `type:post\|comment` | `type:post` | Result type |
| **Sort** | `sort:score\|date` | `sort:score` | Sort order |

### Examples

**Find high-scoring posts about machine learning**:
```
machine learning score:100 type:post
```

**Search excluding certain terms**:
```
python -javascript -ruby
```

**Search specific subreddit**:
```
"data science" sub:MachineLearning
```

**Combine multiple filters**:
```
python tutorial score:50 type:post author:specific_user
```

**Boolean search**:
```
(python OR javascript) tutorial -beginner
```

---

## Search Performance

### Response Times

Typical search performance with GIN indexes:

| Archive Size | Query Type | Response Time |
|--------------|------------|---------------|
| <100K posts | Simple | <100ms |
| 100K-1M posts | Simple | <200ms |
| >1M posts | Simple | <500ms |
| Any size | Complex multi-term | <1 second |

**Factors Affecting Speed**:
- Query complexity (number of terms)
- Result set size
- Index quality (run `VACUUM ANALYZE` periodically)
- Hardware (CPU, RAM, SSD vs HDD)

### Optimization Tips

**1. Regular Index Maintenance**:
```sql
-- Update statistics
VACUUM ANALYZE posts;
VACUUM ANALYZE comments;

-- Rebuild indexes if necessary
REINDEX TABLE posts;
REINDEX TABLE comments;
```

**2. Tune PostgreSQL Settings**:
```sql
-- Increase work_mem for complex queries
SET work_mem = '256MB';

-- Adjust effective_cache_size (75% of RAM)
SET effective_cache_size = '6GB';
```

**3. Use Field Selection** (API):
```bash
# Only fetch needed fields (faster)
curl "http://localhost:5000/search?q=python&fields=id,title,score"
```

**4. Limit Result Size**:
```bash
# Smaller limits = faster responses
curl "http://localhost:5000/search?q=python&limit=25"
```

---

## Search Features

### Relevance Ranking

PostgreSQL `ts_rank()` calculates relevance scores:
- Term frequency in document
- Term position (title weighted higher)
- Document length normalization

Results automatically sorted by relevance.

### Result Highlighting

`ts_headline()` shows matching content in context:

```json
{
  "title": "Introduction to **Machine Learning**",
  "excerpt": "This post covers **machine learning** basics including..."
}
```

Matching terms are highlighted (default: `**bold**` in JSON, `<mark>` in HTML).

### Concurrent Queries

Connection pooling supports multiple simultaneous searches:
- Default: 8 connections
- Configure via `REDDARCHIVER_MAX_DB_CONNECTIONS`
- Each query gets its own connection from pool

---

## Integration with REST API

Search is fully integrated with the REST API:

**Search Endpoint**:
```bash
GET /api/v1/search?q=query&subreddit=optional&limit=50
```

**Search with Export**:
```bash
# Export results to CSV
GET /api/v1/search?q=python&format=csv

# Export to NDJSON
GET /api/v1/search?q=python&format=ndjson
```

**Search Explain** (debugging):
```bash
GET /api/v1/search/explain?q=python+tutorial
# Returns: Parsed query structure and operators used
```

See [API.md](API.md) for complete API documentation.

---

## Troubleshooting

### Slow Search Queries

**Problem**: Search takes >2 seconds

**Solutions**:
1. **Check indexes exist**:
```sql
SELECT indexname FROM pg_indexes WHERE tablename = 'posts';
-- Should show: posts_search_vector_idx (GIN)
```

2. **Update statistics**:
```sql
VACUUM ANALYZE posts;
VACUUM ANALYZE comments;
```

3. **Check query complexity**:
```bash
# Use explain to debug
GET /api/v1/search/explain?q=your_complex_query
```

### No Search Results

**Problem**: Search returns no results but content exists

**Solutions**:
1. **Check FTS vectors generated**:
```sql
SELECT COUNT(*) FROM posts WHERE search_vector IS NOT NULL;
```

2. **Test direct FTS query**:
```sql
SELECT title FROM posts 
WHERE search_vector @@ to_tsquery('english', 'python')
LIMIT 5;
```

3. **Rebuild search vectors**:
```sql
UPDATE posts SET search_vector = 
  setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
  setweight(to_tsvector('english', coalesce(selftext, '')), 'B');
```

### Search Server Won't Start

**Problem**: `Address already in use` error

**Solution**:
```bash
# Check what's using port 5000
sudo lsof -i :5000

# Kill process or use different port
export FLASK_RUN_PORT=5001
python search_server.py
```

---

## See Also

- [API.md](API.md) - REST API search endpoints
- [PERFORMANCE.md](PERFORMANCE.md) - Performance tuning
- [QUICKSTART.md](../QUICKSTART.md) - Deploy search server
- [FAQ](FAQ.md) - Common search questions

---

**Last Updated**: 2026-01-26
