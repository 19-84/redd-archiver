---
name: Performance Issue
about: Report slow performance, memory issues, or optimization opportunities
title: '[PERFORMANCE] '
labels: performance
assignees: ''
---

## Performance Issue Description

A clear and concise description of the performance problem.

## Environment

**Redd-Archiver Version**: (e.g., v1.0.0)

**Operating System**: (e.g., Ubuntu 22.04)

**Hardware**:
- CPU: (e.g., Intel i7-9700K, 8 cores)
- RAM: (e.g., 16GB)
- Storage: (e.g., NVMe SSD, 500GB)
- Disk I/O Speed: (if known)

**PostgreSQL Configuration**:
```bash
# Key settings from postgresql.conf
shared_buffers=4GB
work_mem=256MB
maintenance_work_mem=1GB
max_connections=100
```

**Python Version**: (output of `python --version`)

**Deployment Method**:
- [ ] Docker Compose
- [ ] Local PostgreSQL
- [ ] Remote PostgreSQL
- [ ] Other (please specify)

## Dataset Information

**Input Size**: (e.g., 500MB .zst file)

**Data Characteristics**:
- Total Posts:
- Total Comments:
- Total Users:
- Subreddit Count:
- Date Range: (e.g., 2020-2023)

## Performance Metrics

**Current Performance**:
- Processing Time: (e.g., 4 hours)
- Memory Usage: (e.g., peak 12GB RAM)
- Disk Usage: (e.g., 2.5GB database)
- CPU Usage: (e.g., average 80%)

**Expected Performance** (if known from similar datasets):
- Processing Time: (e.g., expected 2 hours)
- Memory Usage: (e.g., expected 8GB RAM)

## Bottleneck Identification

Which phase is slow?
- [ ] .zst decompression
- [ ] PostgreSQL import
- [ ] Comment threading
- [ ] User page generation
- [ ] HTML rendering
- [ ] Search indexing
- [ ] Other (please specify)

## Timing Breakdown

If available, provide timing information for different phases:
```
[2024-01-15 10:00:00] Starting import...
[2024-01-15 10:30:00] Posts imported (30 minutes)
[2024-01-15 12:00:00] Comments imported (90 minutes)
[2024-01-15 13:00:00] User pages generated (60 minutes)
```

## Resource Utilization

**During Slow Phase**:
- CPU Usage: (e.g., 25% - underutilized)
- Memory Usage: (e.g., 90% - near limit)
- Disk I/O: (e.g., 200 MB/s read, 50 MB/s write)
- Network: (if remote PostgreSQL)
- PostgreSQL Connection Count: (e.g., 8/8 active)

**Monitoring Tools Used** (if any):
- [ ] `top`/`htop`
- [ ] `iostat`
- [ ] PostgreSQL `pg_stat_activity`
- [ ] Redd-Archiver built-in metrics
- [ ] Other (please specify)

## Configuration

**Environment Variables**:
```bash
DATABASE_URL=postgresql://...
REDDARCHIVER_MAX_DB_CONNECTIONS=8
REDDARCHIVER_MAX_PARALLEL_WORKERS=4
REDDARCHIVER_USER_BATCH_SIZE=2000
# Add any other relevant configuration
```

**Command Used**:
```bash
python reddarc.py /data --output archive/ --min-score 10
```

## Logs/Metrics

Paste relevant performance-related log output:
```
[Paste performance metrics, timing logs, or profiling data here]
```

## PostgreSQL Query Performance

If you've identified slow queries, include them here:
```sql
-- Example slow query
EXPLAIN ANALYZE
SELECT * FROM posts WHERE subreddit = 'technology' ORDER BY created_utc DESC;
```

## Attempts to Resolve

Have you tried any performance tuning? What were the results?
- [ ] Increased `REDDARCHIVER_MAX_DB_CONNECTIONS`
- [ ] Adjusted PostgreSQL configuration
- [ ] Added more RAM
- [ ] Moved to SSD storage
- [ ] Other (please describe)

**Results**: (e.g., "Increasing connections from 8 to 16 reduced time by 20%")

## Expected Improvements

What level of performance improvement are you looking for?
- Target processing time:
- Target memory usage:
- Target throughput:

## Additional Context

Add any other context about the performance issue:
- Comparison with previous versions
- Performance on different datasets
- Profiling results (if available)
- System monitoring graphs/screenshots

## Checklist

- [ ] I have searched existing issues to avoid duplicates
- [ ] I have provided complete environment and hardware information
- [ ] I have included dataset size and characteristics
- [ ] I have identified which phase is slow
- [ ] I have provided timing metrics
- [ ] I have described resource utilization during the slow phase
- [ ] I have included relevant configuration and logs
