# Troubleshooting Guide

This guide covers common issues and solutions for Redd-Archiver.

## Table of Contents

- [Installation Issues](#installation-issues)
- [Database Connection Problems](#database-connection-problems)
- [Performance Issues](#performance-issues)
- [Memory Issues](#memory-issues)
- [Import/Processing Errors](#importprocessing-errors)
- [HTML Generation Problems](#html-generation-problems)
- [Docker Issues](#docker-issues)
- [Search Server Issues](#search-server-issues)

## Installation Issues

### Python Version Compatibility

**Problem**: `SyntaxError` or incompatibility warnings

**Solution**:
```bash
# Check Python version (requires 3.7+)
python --version

# If too old, use pyenv or install newer Python
pyenv install 3.12
pyenv local 3.12
```

### Missing Dependencies

**Problem**: `ModuleNotFoundError` when running

**Solution**:
```bash
# Install all dependencies
pip install -r requirements.txt

# Or using uv
uv sync

# Verify psycopg installation
python -c "import psycopg; print(psycopg.__version__)"
```

### PostgreSQL Not Installed

**Problem**: `psql: command not found`

**Solution**:
```bash
# Ubuntu/Debian
sudo apt update && sudo apt install postgresql postgresql-contrib

# macOS
brew install postgresql@16
brew services start postgresql@16

# Or use Docker (recommended)
docker-compose up -d postgres
```

## Database Connection Problems

### Cannot Connect to PostgreSQL

**Problem**: `could not connect to server` or `connection refused`

**Solution 1**: Check PostgreSQL is running
```bash
# Check status
sudo systemctl status postgresql

# Start if stopped
sudo systemctl start postgresql

# Or with Docker
docker-compose ps
docker-compose up -d postgres
```

**Solution 2**: Verify DATABASE_URL
```bash
# Check environment variable
echo $DATABASE_URL

# Should look like:
# postgresql://user:password@localhost:5432/reddarchiver

# Test connection
psql $DATABASE_URL -c "SELECT version();"
```

**Solution 3**: Check PostgreSQL authentication
```bash
# Edit pg_hba.conf (location varies by OS)
sudo nano /etc/postgresql/16/main/pg_hba.conf

# Add this line for local development:
# local   all   all   trust
```

### Authentication Failed

**Problem**: `password authentication failed for user`

**Solution**:
```bash
# Reset PostgreSQL password
sudo -u postgres psql
postgres=# ALTER USER reddarchiver WITH PASSWORD 'new_password';
postgres=# \q

# Update DATABASE_URL
export DATABASE_URL="postgresql://reddarchiver:new_password@localhost:5432/reddarchiver"
```

### Database Does Not Exist

**Problem**: `database "reddarchiver" does not exist`

**Solution**:
```bash
# Create database
sudo -u postgres createdb reddarchiver

# Or from psql
sudo -u postgres psql
postgres=# CREATE DATABASE reddarchiver;
postgres=# \q
```

## Performance Issues

### Slow Import Speed

**Problem**: Import taking much longer than expected

**Diagnosis**:
```bash
# Check system resources
htop  # CPU and memory usage
iostat -x 5  # Disk I/O

# Check PostgreSQL activity
psql $DATABASE_URL -c "SELECT * FROM pg_stat_activity;"
```

**Solutions**:

1. **Increase connection pool**:
```bash
export REDDARCHIVER_MAX_DB_CONNECTIONS=16
```

2. **Tune PostgreSQL** (edit postgresql.conf):
```ini
shared_buffers = 4GB              # 25% of RAM
work_mem = 256MB                  # Per operation
maintenance_work_mem = 1GB        # For indexing
effective_cache_size = 12GB       # 75% of RAM
```

3. **Use Unix socket** (15-30% faster):
```bash
# Instead of TCP
DATABASE_URL="postgresql:///reddarchiver?host=/var/run/postgresql"
```

4. **Disable swap** (if enough RAM):
```bash
sudo swapoff -a
```

### Slow Search Queries

**Problem**: Search takes >1 second to return results

**Solutions**:

1. **Verify GIN indexes exist**:
```sql
SELECT tablename, indexname FROM pg_indexes
WHERE tablename IN ('posts', 'comments')
AND indexname LIKE '%search%';
```

2. **Rebuild indexes**:
```bash
psql $DATABASE_URL -f sql/indexes.sql
```

3. **Update statistics**:
```sql
ANALYZE posts;
ANALYZE comments;
```

4. **Check query plan**:
```sql
EXPLAIN ANALYZE
SELECT * FROM posts
WHERE search_vector @@ to_tsquery('test');
```

## Memory Issues

### Out of Memory During Processing

**Problem**: `MemoryError` or system becomes unresponsive

**Solutions**:

1. **Reduce batch size**:
```bash
export REDDARCHIVER_USER_BATCH_SIZE=1000  # Default: 2000
```

2. **Reduce parallel workers**:
```bash
export REDDARCHIVER_MAX_PARALLEL_WORKERS=2  # Default: auto-detect
```

3. **Use import-only mode** (process in stages):
```bash
# Stage 1: Import to database only
python reddarc.py /data --output archive/ --import-only

# Stage 2: Export HTML later
python reddarc.py /data --output archive/ --export-from-database
```

4. **Increase system memory or swap**:
```bash
# Add swap space (temporary solution)
sudo fallocate -l 8G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

### PostgreSQL Memory Issues

**Problem**: PostgreSQL crashes or becomes slow

**Solution**: Tune postgresql.conf
```ini
# Reduce if limited RAM
shared_buffers = 2GB              # Was 4GB
work_mem = 128MB                  # Was 256MB
```

## Import/Processing Errors

### Invalid .zst File

**Problem**: `zstandard.ZstdError` or decompression fails

**Solutions**:
```bash
# Verify file integrity
zstd -t file.zst

# Re-download if corrupted
# Check file size matches expected size
ls -lh file.zst
```

### JSON Parsing Errors

**Problem**: `JSONDecodeError` during import

**Solutions**:
```bash
# Enable error logging
python reddarc.py /data --log-level DEBUG --log-file errors.log

# Check for malformed lines
grep "JSONDecodeError" errors.log

# These errors are usually non-fatal and can be ignored if rare
```

### Resume Not Working

**Problem**: Processing restarts from beginning instead of resuming

**Solution**:
```bash
# Check processing metadata
psql $DATABASE_URL -c "SELECT * FROM processing_metadata;"

# Force rebuild if needed
python reddarc.py /data --force-rebuild
```

### Comment Thread Reconstruction Slow

**Problem**: Thread building takes hours

**Solution**:
```bash
# Verify keyset pagination indexes exist
psql $DATABASE_URL -c "
SELECT indexname FROM pg_indexes
WHERE tablename='comments'
AND indexname LIKE '%post_id%';
"

# If missing, rebuild indexes
psql $DATABASE_URL -f sql/indexes.sql
```

## HTML Generation Problems

### Missing User Pages

**Problem**: User pages not generated or incomplete

**Solutions**:

1. **Ensure parallel processing enabled**:
```bash
python reddarc.py /data --force-parallel-users
```

2. **Check for errors**:
```bash
grep "user page" .archive-error.log
```

3. **Try sequential processing** (if parallel fails):
```bash
export ARCHIVE_USER_PAGE_WORKERS=1
```

### Broken Links in Generated HTML

**Problem**: Links return 404 or point to wrong pages

**Solutions**:
- Regenerate with `--force-rebuild`
- Check that all files completed (no partial runs)
- Verify output directory permissions

### Missing Static Assets

**Problem**: CSS/JS not loading, styling broken

**Solution**:
```bash
# Verify static directory exists
ls -la output/r/static/

# Should contain:
# - css/
# - js/
# - fonts/

# Regenerate if missing
python reddarc.py /data --output archive/ --force-rebuild
```

## Docker Issues

### Container Fails to Start

**Problem**: `docker-compose up` fails

**Solutions**:

1. **Check logs**:
```bash
docker-compose logs postgres
docker-compose logs reddarchiver-builder
```

2. **Verify .env file exists**:
```bash
ls -la .env
# Should exist and have correct permissions

cp .env.example .env
# Edit .env with your settings
```

3. **Check port conflicts**:
```bash
# PostgreSQL port 5432
sudo lsof -i :5432

# Kill conflicting process or change port in .env
```

### Volume Permission Issues

**Problem**: `Permission denied` when writing to volumes

**Solution**:
```bash
# Fix volume permissions
sudo chown -R $USER:$USER output/ data/ logs/

# Or in docker-compose.yml, set user:
user: "${UID}:${GID}"
```

### Out of Disk Space

**Problem**: Docker fills up disk

**Solutions**:
```bash
# Check Docker disk usage
docker system df

# Clean up old containers and images
docker system prune -a

# Remove unused volumes
docker volume prune
```

## Search Server Issues

### Search API Not Responding

**Problem**: `curl http://localhost:5000/health` fails

**Solutions**:

1. **Check if running**:
```bash
docker-compose ps search-server
# Should show "Up"

docker-compose up -d search-server
```

2. **Check logs**:
```bash
docker-compose logs search-server
```

3. **Verify DATABASE_URL**:
```bash
docker-compose exec search-server env | grep DATABASE_URL
```

### CSRF Errors

**Problem**: `400 Bad Request` or CSRF validation failed

**Solution**: Ensure FLASK_SECRET_KEY is set
```bash
# Generate new secret key
python3 -c "import secrets; print(secrets.token_hex(32))"

# Add to .env
FLASK_SECRET_KEY=<generated_key>

# Restart container
docker-compose restart search-server
```

## Getting More Help

If you're still experiencing issues:

1. **Check logs**:
```bash
# Application log
cat output/.archive-error.log

# PostgreSQL log (location varies)
tail -f /var/log/postgresql/postgresql-16-main.log
```

2. **Enable debug logging**:
```bash
python reddarc.py /data --log-level DEBUG --log-file debug.log
```

3. **System information**:
```bash
# Gather system info for bug reports
python --version
psql --version
docker --version
uname -a
free -h
df -h
```

4. **Check [GitHub Issues](https://github.com/19-84/redd-archiver/issues)**
   - Search existing issues
   - Open new issue with details above

5. **Database diagnostics**:
```sql
-- Check table sizes
SELECT
    tablename,
    pg_size_pretty(pg_total_relation_size(tablename::regclass)) AS size
FROM pg_tables
WHERE schemaname = 'public';

-- Check index sizes
SELECT
    indexname,
    pg_size_pretty(pg_relation_size(indexname::regclass)) AS size
FROM pg_indexes
WHERE schemaname = 'public';
```

---

**Last Updated**: 2025-12-27
**Version**: 1.0.0
