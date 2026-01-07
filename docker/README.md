# Redd-Archiver Docker Deployment Guide

**Complete guide for running Redd-Archiver with PostgreSQL 18 using Docker Compose**

> **Quick Start**: New users should start with [QUICKSTART.md](../QUICKSTART.md) at the repository root for copy-paste-friendly deployment instructions. This document provides comprehensive reference documentation.

## Docker vs Offline Browsing

**Why Docker Deployment?**
- ✅ **Full-text search** - PostgreSQL FTS with GIN indexing
- ✅ **Server-side processing** - Tor-compatible architecture
- ✅ **Advanced features** - Search by keywords, author, date, score

**Offline Browsing Alternative**:
- Generated HTML files work without any server
- Browse via sorted index pages (by score, comments, date)
- Pagination and full comment threads
- No search functionality
- See [Deployment Options](../README.md#-deployment-options) for comparison

### Single Instance Scale

Redd-Archiver has been tested with archives up to **hundreds of gigabytes per instance**. For very large archive collections (multiple terabytes), consider horizontal scaling with multiple topic-based instances. See [Scaling for Very Large Archives](../README.md#-scaling-for-very-large-archives) for multi-instance deployment strategies.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Prerequisites](#prerequisites)
3. [Initial Setup](#initial-setup)
4. [Usage Examples](#usage-examples)
5. [Unix Socket vs TCP Performance](#unix-socket-vs-tcp-performance)
6. [Configuration](#configuration)
7. [Troubleshooting](#troubleshooting)
8. [Development Workflow](#development-workflow)
9. [Production Deployment](#production-deployment)
10. [Monitoring & Maintenance](#monitoring--maintenance)

---

## Quick Start

**Get running in 3 minutes:**

```bash
# 1. Clone and navigate to project
cd redd-archiver

# 2. Create environment file
cp .env.example .env
# Edit .env and set POSTGRES_PASSWORD

# 3. Start services
docker-compose up -d

# 4. Verify health
docker-compose ps
docker-compose logs -f

# 5. Process your first archive (example)
docker-compose exec redd-archiver-builder python reddarc.py /data \
  --subreddit example \
  --comments-file /data/example_comments.zst \
  --submissions-file /data/example_submissions.zst \
  --output /output/example-archive
```

**Expected result**: Archive generated in `./output/example-archive/` in ~5-10 minutes

---

## Prerequisites

### System Requirements

**Minimum**:
- Docker Engine 24.0+
- Docker Compose v2.0+
- 8GB RAM
- 10GB free disk space
- Linux/macOS/Windows with WSL2

**Recommended**:
- 16GB RAM (for large archives)
- SSD storage
- 4+ CPU cores

### Docker Installation

**Linux**:
```bash
# Install Docker
curl -fsSL https://get.docker.com | sh

# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker

# Install Docker Compose (if not included)
sudo apt-get install docker-compose-plugin
```

**macOS**:
```bash
# Install Docker Desktop
brew install --cask docker
```

**Windows**:
1. Install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
2. Enable WSL2 integration
3. Allocate at least 8GB RAM in Docker Desktop settings

### Verify Installation

```bash
docker --version          # Should be 24.0+
docker-compose version    # Should be v2.0+
docker run hello-world    # Test Docker works
```

---

## Initial Setup

### 1. Environment Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit configuration
nano .env  # or vim, code, etc.
```

**Critical settings**:
```bash
# Security: Change the default password!
POSTGRES_PASSWORD=your-secure-password-here

# Paths (adjust to your data location)
DATA_PATH=/path/to/your/reddit-data
OUTPUT_PATH=./output
LOG_PATH=./logs
```

### 2. Create Required Directories

```bash
# Create directories with proper permissions
mkdir -p data output logs

# Place your .zst files in data/
# ls data/
#   Example_comments.zst
#   Example_submissions.zst
```

### 3. Build Images

```bash
# Build the redd-archiver-builder image
docker-compose build

# Expected build time: 2-5 minutes (first time)
# Subsequent builds: 10-30 seconds (cached layers)
```

### 4. Start Services

```bash
# Start all services in detached mode
docker-compose up -d

# Watch startup logs
docker-compose logs -f

# Wait for healthy status
docker-compose ps
# Both containers should show "healthy" status within 30 seconds
```

---

## Usage Examples

### Basic Archive Generation

```bash
# Single subreddit processing
docker-compose exec redd-archiver-builder python reddarc.py /data \
  --subreddit technology \
  --comments-file /data/technology_comments.zst \
  --submissions-file /data/technology_submissions.zst \
  --output /output/technology-archive
```

### With Filtering Options

```bash
# Filter posts by score and comment count
docker-compose exec redd-archiver-builder python reddarc.py /data \
  --subreddit news \
  --comments-file /data/news_comments.zst \
  --submissions-file /data/news_submissions.zst \
  --output /output/news-archive \
  --min-score 100 \
  --min-comments 50
```

### Memory-Constrained Processing

```bash
# Limit memory usage for systems with limited RAM
docker-compose exec redd-archiver-builder python reddarc.py /data \
  --subreddit all \
  --comments-file /data/all_comments.zst \
  --submissions-file /data/all_submissions.zst \
  --output /output/all-archive \
  --memory-limit 4.0 \
  --no-user-pages
```

### Resume Interrupted Processing

```bash
# Automatically resume from last checkpoint
docker-compose exec redd-archiver-builder python reddarc.py /data \
  --output /output/existing-archive \
  --resume
```

### Interactive Shell Access

```bash
# Open shell in builder container
docker-compose exec redd-archiver-builder bash

# Now you can run commands directly:
python reddarc.py --help
ls /data
ls /output
```

---

## Unix Socket vs TCP Performance

### What Are Unix Sockets?

Unix sockets are an efficient inter-process communication (IPC) method for processes on the same host. Instead of using TCP/IP networking, Unix sockets use direct file system communication.

### Performance Benefits

Unix sockets provide performance advantages for local database connections:
- Lower connection establishment overhead
- Reduced latency for queries and bulk operations
- More efficient connection pool operations
- Better performance for COPY protocol operations

### Real-World Impact: Example Benchmark

- **Benchmark**: ~5-10 minutes for typical archives
- **PostgreSQL (TCP)**: 8-10 minutes
- **PostgreSQL (Unix socket)**: **7-9 minutes** ⚡

**Additional savings**: 3-4.5 minutes over TCP approach

### How It Works in Docker

```yaml
# docker-compose.yml configuration
volumes:
  postgres_socket:    # Shared volume for socket file
    driver: local

services:
  postgres:
    volumes:
      - postgres_socket:/var/run/postgresql  # PostgreSQL creates socket here

  redd-archiver-builder:
    volumes:
      - postgres_socket:/var/run/postgresql:ro  # Builder reads socket (read-only)
```

### Connection Strings

**Unix Socket (Primary)**:
```bash
# Format: postgresql://user:pass@/database?host=/socket/path
DATABASE_URL=postgresql://reddarchiver:changeme@/reddarchiver?host=/var/run/postgresql
```

**TCP Socket (Fallback)**:
```bash
# Format: postgresql://user:pass@hostname:port/database
DATABASE_URL_TCP=postgresql://reddarchiver:changeme@postgres:5432/reddarchiver
```

### When to Use Each

#### Use Unix Socket (Recommended):
✅ Development on local machine
✅ Docker Compose deployment (single host)
✅ Maximum performance needed
✅ High-volume bulk operations

#### Use TCP Socket:
🔄 PostgreSQL on separate server (production)
🔄 Kubernetes deployment (pods on different nodes)
🔄 External tools (pgAdmin, monitoring)
🔄 Cross-network access needed

### Verifying Socket Connection

```bash
# Check socket file exists
docker-compose exec postgres ls -la /var/run/postgresql/
# Should show: .s.PGSQL.5432 (socket file)

# Test connection from builder
docker-compose exec redd-archiver-builder python3 -c "
import psycopg
conn = psycopg.connect('postgresql://reddarchiver:changeme@/reddarchiver?host=/var/run/postgresql')
print('✅ Unix socket connection successful!')
conn.close()
"

# Benchmark comparison
echo "TCP benchmark:"
time docker-compose exec redd-archiver-builder python3 -c "
import psycopg
[psycopg.connect('postgresql://reddarchiver:changeme@postgres:5432/reddarchiver').close() for _ in range(100)]
"

echo "Unix socket benchmark:"
time docker-compose exec redd-archiver-builder python3 -c "
import psycopg
[psycopg.connect('postgresql://reddarchiver:changeme@/reddarchiver?host=/var/run/postgresql').close() for _ in range(100)]
"
```

---

## Configuration

### Environment Variables

See `.env.example` for complete list. Key variables:

**Database**:
- `POSTGRES_PASSWORD`: Database password (CHANGE THIS!)
- `POSTGRES_DB`: Database name (default: reddarchiver)
- `POSTGRES_USER`: Database user (default: reddarchiver)

**Performance**:
- `MEMORY_LIMIT`: Memory limit for processing (default: 8.0 GB)
- `POSTGRES_SHM_SIZE`: Shared memory for PostgreSQL (default: 256mb)

**Paths**:
- `DATA_PATH`: Input data directory (default: ./data)
- `OUTPUT_PATH`: Output archive directory (default: ./output)
- `LOG_PATH`: Log directory (default: ./logs)

### PostgreSQL Tuning

Edit `postgres.conf` for performance tuning:

```conf
# Memory settings (adjust for your system)
shared_buffers = 4GB              # 25% of system RAM
effective_cache_size = 12GB       # 75% of system RAM
work_mem = 256MB                  # Per-operation memory

# Parallelism (adjust for CPU cores)
max_parallel_workers = 8          # Total parallel workers
max_parallel_workers_per_gather = 4  # Workers per query
```

**After changes**:
```bash
docker-compose restart postgres
docker-compose logs -f postgres  # Verify no errors
```

### Resource Limits

Uncomment resource limits in `docker-compose.yml`:

```yaml
services:
  postgres:
    deploy:
      resources:
        limits:
          memory: 4g
          cpus: '4'

  redd-archiver-builder:
    deploy:
      resources:
        limits:
          memory: 2g
          cpus: '2'
```

---

## Troubleshooting

### Container Won't Start

**Symptom**: `docker-compose up -d` fails or containers exit immediately

**Solutions**:
```bash
# Check logs for errors
docker-compose logs postgres
docker-compose logs redd-archiver-builder

# Common issues:
# 1. Port 5432 already in use
sudo lsof -i :5432  # Find process using port
docker-compose down  # Stop containers
# Kill conflicting process or change POSTGRES_PORT in .env

# 2. Permission denied on volumes
sudo chown -R $USER:$USER data output logs

# 3. Invalid postgres.conf syntax
docker-compose exec postgres postgres --version  # Test config
```

### Connection Refused

**Symptom**: Builder can't connect to PostgreSQL

**Solutions**:
```bash
# Verify PostgreSQL is healthy
docker-compose ps postgres  # Should show "healthy"

# Test connectivity
docker-compose exec redd-archiver-builder pg_isready -h postgres -p 5432

# Check Unix socket exists
docker-compose exec postgres ls -la /var/run/postgresql/
# Should show: .s.PGSQL.5432

# Test Unix socket connection
docker-compose exec redd-archiver-builder \
  psql -h /var/run/postgresql -U reddarchiver -d reddarchiver -c "SELECT 1"

# Force TCP fallback (troubleshooting)
docker-compose exec -e DATABASE_URL=$DATABASE_URL_TCP redd-archiver-builder \
  python reddarc.py --help
```

### Unix Socket Not Working

**Symptom**: Falls back to TCP despite Unix socket configuration

**Solutions**:
```bash
# 1. Verify socket volume is mounted
docker volume ls | grep postgres-socket
docker-compose exec postgres ls -la /var/run/postgresql/

# 2. Check socket permissions
docker-compose exec postgres ls -l /var/run/postgresql/.s.PGSQL.5432
# Should be: srwxrwxrwx (777 permissions)

# 3. Verify postgres.conf settings
docker-compose exec postgres cat /etc/postgresql/postgresql.conf | grep unix_socket

# 4. Restart with clean volumes
docker-compose down -v
docker-compose up -d
```

### Out of Memory

**Symptom**: Container killed by OOM (Out of Memory)

**Solutions**:
```bash
# 1. Reduce PostgreSQL memory settings
# Edit postgres.conf:
shared_buffers = 2GB  # Reduce from 4GB
work_mem = 128MB      # Reduce from 256MB

# 2. Limit container memory
# Uncomment resource limits in docker-compose.yml

# 3. Use memory-constrained processing
docker-compose exec redd-archiver-builder python reddarc.py /data \
  --memory-limit 2.0 \
  --no-user-pages \
  ...

# 4. Increase Docker Desktop memory (macOS/Windows)
# Docker Desktop -> Settings -> Resources -> Memory -> 8GB+
```

### Slow Performance

**Symptom**: Processing slower than expected baseline (12 minutes)

**Diagnostic**:
```bash
# 1. Check system resources
docker stats

# 2. Monitor PostgreSQL queries
docker-compose exec postgres psql -U reddarchiver -d reddarchiver -c "
SELECT pid, state, query_start, query
FROM pg_stat_activity
WHERE state = 'active';
"

# 3. Check disk I/O
docker-compose exec postgres iostat -x 5

# 4. Verify Unix socket is in use
docker-compose logs redd-archiver-builder | grep "Unix socket"
```

**Solutions**:
- Ensure using Unix socket (not TCP fallback)
- Allocate more CPU cores in docker-compose.yml
- Use SSD storage for Docker volumes
- Increase `max_parallel_workers` in postgres.conf

### Volume Permission Issues

**Symptom**: Permission denied accessing /data, /output, or /logs

**Solutions**:
```bash
# Fix ownership
sudo chown -R $USER:$USER data output logs

# Or run containers with your UID/GID
# Add to docker-compose.yml:
services:
  redd-archiver-builder:
    user: "${UID}:${GID}"

# Set in .env:
UID=1000  # Your user ID: echo $UID
GID=1000  # Your group ID: echo $GID
```

---

## Development Workflow

### Hot Reload Setup

```bash
# Mount current directory for code changes
docker-compose exec redd-archiver-builder bash

# Edit code on host system
# Changes immediately available in container
```

### Running Tests

```bash
# Unit tests
docker-compose exec redd-archiver-builder pytest tests/

# Integration tests (requires PostgreSQL)
docker-compose exec redd-archiver-builder pytest tests/integration/

# Performance benchmarks
docker-compose exec redd-archiver-builder pytest benchmarks/
```

### Database Access

```bash
# PostgreSQL shell
docker-compose exec postgres psql -U reddarchiver -d reddarchiver

# Useful queries:
\dt                    # List tables
\d+ posts              # Describe posts table
\di                    # List indexes
SELECT COUNT(*) FROM posts;
SELECT COUNT(*) FROM comments;

# Database size
SELECT pg_size_pretty(pg_database_size('reddarchiver'));
```

### Cleanup

```bash
# Stop containers
docker-compose down

# Remove volumes (DELETES ALL DATA!)
docker-compose down -v

# Remove images
docker-compose down --rmi all

# Complete reset
docker-compose down -v --rmi all --remove-orphans
docker volume prune -f
```

---

## Production Deployment

### Security Checklist

- [ ] Change `POSTGRES_PASSWORD` to strong password
- [ ] Use Docker secrets instead of environment variables
- [ ] Restrict PostgreSQL port exposure (remove `ports:` in docker-compose.yml)
- [ ] Use read-only volume mounts where possible
- [ ] Run containers as non-root user
- [ ] Enable Docker Content Trust (DCT)
- [ ] Regular security updates for base images

### Production Configuration

**docker-compose.prod.yml**:
```yaml
version: '3.8'

services:
  postgres:
    restart: always
    deploy:
      resources:
        limits:
          memory: 8g
          cpus: '8'
        reservations:
          memory: 4g
          cpus: '4'
    # Don't expose port publicly
    ports: []
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    secrets:
      - db_password

  redd-archiver-builder:
    restart: "no"  # Manual restart for processing
    deploy:
      resources:
        limits:
          memory: 4g
          cpus: '4'

secrets:
  db_password:
    file: ./secrets/db_password.txt
```

**Usage**:
```bash
# Start with production config
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Backup Strategy

```bash
# Automated daily backups
docker-compose exec postgres pg_dump -U reddarchiver reddarchiver | \
  gzip > backups/reddarchiver-$(date +%Y%m%d).sql.gz

# Restore from backup
gunzip -c backups/reddarchiver-20250115.sql.gz | \
  docker-compose exec -T postgres psql -U reddarchiver reddarchiver
```

### Monitoring

Add Prometheus + Grafana monitoring:

**docker-compose.monitoring.yml**:
```yaml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana:latest
    volumes:
      - grafana_data:/var/lib/grafana
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD}

volumes:
  prometheus_data:
  grafana_data:
```

---

## Monitoring & Maintenance

### Health Checks

```bash
# Container health status
docker-compose ps

# Detailed health check
docker-compose exec postgres ./docker/healthcheck/postgres-healthcheck.sh
docker-compose exec redd-archiver-builder python /healthcheck.py

# Resource usage
docker stats
```

### Performance Metrics

```bash
# PostgreSQL statistics
docker-compose exec postgres psql -U reddarchiver -d reddarchiver -c "
SELECT schemaname, tablename,
       pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"

# Connection pool status
docker-compose exec postgres psql -U reddarchiver -d reddarchiver -c "
SELECT state, COUNT(*)
FROM pg_stat_activity
GROUP BY state;
"

# Slow queries
docker-compose exec postgres psql -U reddarchiver -d reddarchiver -c "
SELECT pid, now() - query_start AS duration, query
FROM pg_stat_activity
WHERE state = 'active'
AND now() - query_start > interval '5 seconds'
ORDER BY duration DESC;
"
```

### Maintenance Tasks

```bash
# Vacuum database (reclaim space)
docker-compose exec postgres psql -U reddarchiver -d reddarchiver -c "VACUUM VERBOSE;"

# Analyze statistics (improve query planning)
docker-compose exec postgres psql -U reddarchiver -d reddarchiver -c "ANALYZE VERBOSE;"

# Reindex (rebuild indexes)
docker-compose exec postgres psql -U reddarchiver -d reddarchiver -c "REINDEX DATABASE reddarchiver;"

# Check for bloat
docker-compose exec postgres psql -U reddarchiver -d reddarchiver -c "
SELECT schemaname, tablename,
       pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_relation_size(schemaname||'.'||tablename) DESC;
"
```

---

## Production HTTPS Deployment

### Overview

Redd-Archiver supports production HTTPS deployment with automatic SSL certificate management via Let's Encrypt. This section covers setting up HTTPS with automated certificate renewal for public-facing archives.

**What you get**:
- Automatic SSL/TLS certificates from Let's Encrypt
- Zero-downtime certificate renewal every 90 days
- HTTP to HTTPS redirect
- Modern TLS configuration (TLS 1.2+)
- HSTS security headers

### Deployment Scenarios

| Scenario | Protocol | Use Case | Certbot Required |
|----------|----------|----------|------------------|
| **Local/Offline** | HTTP | Home networks, VPN access, localhost | ❌ No |
| **Public HTTPS** | HTTPS | Public archives, production sites | ✅ Yes |
| **Tor Hidden Service** | HTTP | Tor-only access (.onion) | ❌ No (future) |
| **Static Hosting** | HTTPS | GitHub/Codeberg Pages | ❌ No (future) |

This guide covers **Public HTTPS** deployment.

### Prerequisites

Before starting HTTPS setup:

1. **Domain Name**: You need a domain or subdomain (e.g., `archive.example.com`)
2. **DNS Configuration**: A record pointing your domain to your server's public IP
3. **Firewall**: Ports 80 and 443 open for inbound traffic
4. **Server Access**: SSH access with Docker installed

#### DNS Configuration

Your domain MUST point to your server before requesting certificates:

```bash
# Check your server's public IP
curl ifconfig.me

# Check DNS resolution
dig +short your-domain.com

# These should match!
```

Configure an A record at your DNS provider:

| Type | Name                 | Value        | TTL  |
|------|----------------------|--------------|------|
| A    | archive.example.com  | 203.0.113.42 | 3600 |

Wait 5-60 minutes for DNS propagation before proceeding.

### Quick Start (5 Minutes)

**Automated setup with init script (recommended)**:

```bash
# 1. Configure environment
cp .env.example .env
nano .env

# Set these values:
DOMAIN=archive.yoursite.com
EMAIL=you@yoursite.com
CERTBOT_TEST_CERT=true  # Start with staging (test mode)

# 2. Run initialization script
chmod +x docker/scripts/init-letsencrypt.sh
./docker/scripts/init-letsencrypt.sh

# 3. Verify HTTPS works
curl https://archive.yoursite.com/health

# 4. Switch to production (optional, after testing)
# Edit .env: CERTBOT_TEST_CERT=false
# Remove staging certs: sudo docker run --rm -v reddarchiver-certbot-certs:/etc/letsencrypt alpine rm -rf /etc/letsencrypt
# Re-run: ./docker/scripts/init-letsencrypt.sh
```

**Expected output**: HTTPS accessible in ~5 minutes, certificates renew automatically.

### Manual Setup (Step-by-Step)

For users who want full control over the process:

#### Step 1: Configure Environment

```bash
# Add to .env
DOMAIN=archive.yoursite.com  # Your actual domain
EMAIL=you@yoursite.com       # For Let's Encrypt notifications
CERTBOT_TEST_CERT=true       # Use staging initially
HTTP_PORT=80
HTTPS_PORT=443
```

#### Step 2: Start Services (HTTP Mode)

```bash
# Start containers in HTTP mode
docker compose up -d

# Verify HTTP works
curl http://archive.yoursite.com/health
# Should return: OK
```

#### Step 3: Request Certificate

```bash
# Request staging certificate (for testing)
docker compose run --rm certbot certonly \
  --webroot \
  --webroot-path=/var/www/certbot \
  --email you@yoursite.com \
  --agree-tos \
  --staging \
  -d archive.yoursite.com

# Verify certificate was created
docker compose exec certbot certbot certificates
# Should show: (STAGING) Let's Encrypt Authority X3
```

#### Step 4: Update Nginx Configuration

```bash
# Create HTTPS config with your domain
sed "s/DOMAIN_PLACEHOLDER/$DOMAIN/g" docker/nginx/nginx.conf.https > docker/nginx/nginx.conf.https.active
```

#### Step 5: Switch to HTTPS

```bash
# Stop services
docker compose down

# Start with production profile (activates certbot + HTTPS)
docker compose --profile production up -d

# Wait for services to start
sleep 10
```

#### Step 6: Test HTTPS

```bash
# Test HTTPS (use -k for staging certs)
curl -k https://archive.yoursite.com/health
# Should return: OK

# Test HTTP redirect
curl -I http://archive.yoursite.com/
# Should return: HTTP/1.1 301 Moved Permanently
# Location: https://archive.yoursite.com/
```

#### Step 7: Switch to Production Certificates (Optional)

```bash
# Update .env
CERTBOT_TEST_CERT=false

# Remove staging certificates
sudo docker run --rm -v reddarchiver-certbot-certs:/etc/letsencrypt alpine rm -rf /etc/letsencrypt

# Request production certificate
docker compose run --rm certbot certonly \
  --webroot \
  --webroot-path=/var/www/certbot \
  --email you@yoursite.com \
  --agree-tos \
  -d archive.yoursite.com

# Restart services
docker compose down
docker compose --profile production up -d

# Test without -k flag (production certs are trusted)
curl https://archive.yoursite.com/health
```

### Certificate Renewal

Certificates automatically renew every 90 days.

#### How It Works

1. Certbot container runs renewal check every 12 hours
2. If certificate expires in <30 days, renewal is triggered
3. New certificate is obtained from Let's Encrypt
4. Nginx is automatically reloaded with new certificate (zero downtime)

#### Monitoring Renewal

```bash
# View renewal logs
docker compose logs certbot

# Check certificate expiration
docker compose exec certbot certbot certificates

# Test renewal (dry-run, doesn't actually renew)
docker compose exec certbot certbot renew --dry-run
```

### Troubleshooting

#### DNS Not Resolving

**Symptom**: `init-letsencrypt.sh` reports DNS mismatch

**Solution**:
1. Verify A record at DNS provider
2. Check propagation: `dig +short your-domain.com`
3. Wait for DNS propagation (up to 48 hours, usually 5-60 minutes)

#### Port 80 Not Accessible

**Symptom**: Certificate request fails with "connection refused"

**Solution**:
```bash
# Check firewall
sudo ufw status
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Check nginx is listening
docker compose exec nginx netstat -tlnp | grep :80
```

#### Rate Limit Exceeded

**Symptom**: Let's Encrypt returns rate limit error

**Solution**:
1. Use staging mode: `CERTBOT_TEST_CERT=true` in .env
2. Wait 1 week (Let's Encrypt rate limit resets)
3. Ensure DNS is correct before requesting production cert

**Let's Encrypt Rate Limits**:
- 50 certificates per registered domain per week
- 5 duplicate certificates per week
- Staging environment has no rate limits (for testing)

#### Nginx Won't Start After HTTPS

**Symptom**: Nginx container exits with certificate error

**Solution**:
```bash
# Check certificate files exist
ls -la $(sudo docker run --rm -v reddarchiver-certbot-certs:/etc/letsencrypt alpine ls /etc/letsencrypt/live/)

# Verify nginx config syntax
docker compose run --rm nginx nginx -t

# Check logs
docker compose logs nginx

# Verify domain placeholder was replaced
grep DOMAIN_PLACEHOLDER docker/nginx/nginx.conf.https.active
# Should return nothing (no matches)
```

### Security Considerations

#### TLS Configuration

Current configuration uses:
- **Protocols**: TLS 1.2 and TLS 1.3 only (no SSL, TLS 1.0, TLS 1.1)
- **Ciphers**: Strong cipher suites (HIGH:!aNULL:!MD5)
- **HSTS**: Enabled with 1-year max-age
- **OCSP Stapling**: Enabled for privacy and performance
- **HTTP/2**: Enabled

#### Docker Socket Access

**Risk**: Certbot container requires Docker socket access to reload nginx

**Mitigation**:
- Read-only socket access (`:ro` mount)
- Official certbot/certbot image (trusted source)
- Helper script only executes nginx reload (minimal privilege)
- Socket used only by deploy hook after successful renewal

**Alternative** (if socket access is unacceptable):
Use manual nginx reload via host cron job:

```bash
# Add to host crontab
0 3 * * * docker exec reddarchiver-nginx nginx -s reload
```

#### SSL Labs Testing

After production deployment, test your SSL configuration:

1. Visit: https://www.ssllabs.com/ssltest/
2. Enter your domain
3. Wait for scan to complete
4. Should achieve **A or A+ rating**

Expected ratings:
- Certificate: 100%
- Protocol Support: 95%
- Key Exchange: 90%
- Cipher Strength: 90%

### Advanced Topics

#### Multiple Domains

Add additional domains to single certificate:

```bash
docker compose run --rm certbot certonly \
  --webroot \
  --webroot-path=/var/www/certbot \
  --email you@yoursite.com \
  --agree-tos \
  -d archive.yoursite.com \
  -d www.archive.yoursite.com \
  -d old-archive.yoursite.com
```

#### Wildcard Certificates

Requires DNS-01 challenge (not HTTP-01):

```bash
# Requires DNS provider API credentials
docker compose run --rm certbot certonly \
  --dns-cloudflare \
  --dns-cloudflare-credentials /path/to/cloudflare.ini \
  --email you@yoursite.com \
  --agree-tos \
  -d '*.yoursite.com'
```

**Note**: Wildcard certs require `certbot/dns-<provider>` image instead of `certbot/certbot`.

#### Switching Between HTTP and HTTPS

```bash
# Disable HTTPS (switch to local development)
docker compose down
docker compose up -d  # Uses HTTP config (nginx.conf.http)

# Enable HTTPS (production)
docker compose down
docker compose --profile production up -d  # Uses HTTPS config + certbot
```

---

## Tor Hidden Service Deployment

### Overview

Redd-Archiver supports Tor hidden service deployment, making your archive accessible via .onion address. Tor provides practical benefits for homelab users and privacy-focused deployments.

**Why use Tor?**

**For Homelab Users** (practical benefits):
- ✅ No port forwarding or NAT configuration needed
- ✅ No domain name purchase required
- ✅ No DNS configuration or dynamic IP management
- ✅ No exposing your home server to the internet
- ✅ Works behind CGNAT (carrier-grade NAT)
- ✅ Share archives with friends without security risks

**For Privacy-Focused Deployments**:
- ✅ User anonymity (IP addresses hidden)
- ✅ Censorship resistance
- ✅ Server location privacy
- ✅ End-to-end encryption
- ✅ No certificate authorities involved

**Tor makes hosting accessible**: Share your archive with others without dealing with networking complexity or security exposure.

### Why Redd-Archiver Works Well on Tor

**Optimized for Tor Networks**:
- Server-side PostgreSQL search with GIN indexing
- Zero JavaScript requirement (works on Tor Browser "Safest" mode)
- All assets served locally (no CDN delays or blocked resources)
- Full functionality without external dependencies

**Performance**: Optimized for low-latency networks including Tor. Theme switching is instant via CSS.

### Deployment Modes

| Mode | Clearnet Access | Tor Access | Best For |
|------|----------------|------------|----------|
| **Dual-Mode** | ✅ HTTPS | ✅ .onion | Public archives + privacy option |
| **Tor-Only** | ❌ Blocked | ✅ .onion | Homelab sharing, maximum privacy |

### Prerequisites

**For Dual-Mode**:
- HTTPS already configured (see "Production HTTPS Deployment" above)
- Tor Browser for testing

**For Tor-Only** (easiest deployment):
- Tor Browser for access
- **That's it!** No domain, DNS, firewall, or port forwarding needed

### Quick Start - Dual Mode (2 Minutes)

Add Tor to existing HTTPS deployment:

```bash
# 1. Ensure HTTPS is already running
docker compose --profile production ps
# Should show: nginx, certbot running

# 2. Start Tor (no downtime for existing services)
docker compose --profile production --profile tor up -d

# 3. Wait for Tor to generate keys (30-60 seconds)
sleep 30

# 4. Get your .onion address
docker compose logs tor | grep "Your .onion address"

# 5. Access via Tor Browser
# Download Tor Browser: https://www.torproject.org/download/
# Visit: http://[your-address].onion
```

**Expected output**: Archive accessible on both HTTPS and .onion

### Quick Start - Tor Only (2 Minutes)

**Perfect for homelab users** - no networking configuration needed:

```bash
# 1. Start Tor-only mode (no prerequisites needed!)
docker compose -f docker-compose.yml -f docker-compose.tor-only.yml --profile tor up -d

# 2. Wait for Tor to generate keys
sleep 30

# 3. Get your .onion address
docker compose logs tor | grep "Your .onion address"

# 4. Share .onion address with friends/colleagues
# They download Tor Browser: https://www.torproject.org/download/
# They visit: http://[your-address].onion

# That's it! No port forwarding, no DNS, no domain name needed.
```

**Expected output**: Archive accessible via .onion to anyone with Tor Browser

**Why this is great for homelabs**:
- Share subreddit archives without exposing home IP
- No router configuration or port forwarding needed
- No domain name purchase ($10-15/year saved)
- No dealing with dynamic IP addresses
- Works behind restrictive NAT/CGNAT
- Distribute banned/controversial subreddit archives securely

### Hidden Service Keys Management

Tor generates cryptographic keys in `./tor-hidden-service/`:

```
tor-hidden-service/
├── hostname              # Your .onion address (public, shareable)
├── hs_ed25519_public_key # Public key (part of cryptographic identity)
└── hs_ed25519_secret_key # Private key (SECRET - never share!)
```

#### Backup Your Keys

**CRITICAL**: Backup this directory to preserve your .onion address:

```bash
# Create backup
tar -czf tor-keys-backup-$(date +%Y%m%d).tar.gz tor-hidden-service/

# Store securely (encrypted storage, offline backup, etc.)
# If you lose these keys, your .onion address changes forever
```

#### Restore from Backup

```bash
# Extract backup
tar -xzf tor-keys-backup-20250101.tar.gz

# Restart Tor
docker compose restart tor

# Verify .onion address restored
docker compose logs tor | grep "Your .onion address"
```

### Understanding .onion Addresses

**.onion v3 addresses** (current standard):
- Format: `http://abcdefgh...xyz.onion` (56 characters + .onion)
- Cryptographically derived from ED25519 public key
- Cannot be chosen or customized (generated from key)
- Permanent (tied to private key)

Example: `http://thehiddenwiki7fhdx5h4gn...xyz.onion`

**Why so long?**
- v3 addresses provide stronger cryptography (ED25519)
- Resistant to collision attacks
- More secure than legacy v2 (16 char) addresses

### Troubleshooting

#### Tor Container Won't Start

**Symptom**: Tor container exits immediately

**Solution**:
```bash
# Check logs
docker compose logs tor

# Common issues:
# 1. torrc syntax error
docker compose run --rm tor tor --verify-config

# 2. Permission denied on hidden service directory
chmod 700 tor-hidden-service/
docker compose restart tor

# 3. Port conflict (unlikely, internal only)
docker compose ps
```

#### .onion Address Not Generated

**Symptom**: hostname file doesn't exist after 60 seconds

**Solution**:
```bash
# Check Tor logs for errors
docker compose logs tor

# Verify hidden service directory is writable
ls -la tor-hidden-service/

# Manually trigger key generation
docker compose exec tor cat /var/lib/tor/hidden_service/hostname

# If still failing, remove directory and regenerate
docker compose down
rm -rf tor-hidden-service/
docker compose --profile tor up -d
```

#### Can't Access .onion from Tor Browser

**Symptom**: "Unable to connect" in Tor Browser

**Solution**:
```bash
# 1. Verify Tor container is healthy
docker compose ps tor
# Should show: healthy

# 2. Verify hostname exists
docker compose exec tor cat /var/lib/tor/hidden_service/hostname

# 3. Check nginx is accessible from Tor container
docker compose exec tor wget -O- http://nginx/health
# Should return: OK

# 4. Verify Tor network connectivity
# In Tor Browser, visit: https://check.torproject.org/
# Should show: "Congratulations. This browser is configured to use Tor."

# 5. Check Tor logs for circuit build failures
docker compose logs tor | grep -i "circuit"
```

#### Clearnet Still Accessible in Tor-Only Mode

**Symptom**: Can access archive via http://localhost in Tor-only mode

**Solution**:
```bash
# Verify using docker-compose.tor-only.yml
docker compose config | grep -A5 "nginx:" | grep "ports:"
# Should show: ports: [] (empty array)

# Restart with correct command
docker compose down
docker compose -f docker-compose.yml -f docker-compose.tor-only.yml --profile tor up -d

# Verify ports not exposed
docker compose ps nginx
# Ports column should be empty
```

### Security Considerations

#### Key Management Best Practices

1. **Backup Regularly**: Copy `./tor-hidden-service/` to secure location
2. **Secure Permissions**: `chmod 700 tor-hidden-service/`
3. **Never Version Control**: Add to .gitignore (already configured)
4. **Encrypt Backups**: Use encryption for off-site backups
5. **Test Restores**: Verify backups work before you need them

#### Operational Security

**For Dual-Mode** (HTTPS + Tor):
- Same content on both channels can enable correlation
- Users may be tracked if they access both
- Consider different content/styling for .onion vs clearnet
- Document this trade-off for your users

**For Tor-Only** (maximum privacy):
- No correlation with clearnet identity
- Users guaranteed anonymous access
- No DNS leaks (no domain name used)
- No certificate authority involvement

#### Resource Considerations

Tor hidden services can handle moderate traffic:
- Small archives: <100 concurrent users
- Large archives: May need OnionBalance for load distribution
- Monitor: `docker stats reddarchiver-tor`

### Advanced Topics

#### Multiple Tor Addresses (OnionBalance)

For high-traffic archives, distribute load across multiple .onion addresses:

```yaml
# Future implementation - out of scope
services:
  onionbalance:
    image: onionbalance/onionbalance:latest
    # Configuration for load balancing
```

**Use case**: Archives with >1000 concurrent Tor users

#### Client Authorization

Restrict .onion access to specific users:

```bash
# Generate client key
docker compose exec tor onionservice-auth

# Add to authorized_clients/
# Future implementation - see docs/TOR_DEPLOYMENT.md
```

**Use case**: Private archives, limited distribution

### Switching Between Modes

```bash
# HTTP → Tor-Only
docker compose down
docker compose -f docker-compose.yml -f docker-compose.tor-only.yml --profile tor up -d

# Tor-Only → Dual-Mode
docker compose down
docker compose --profile production --profile tor up -d

# Dual-Mode → HTTPS only (remove Tor)
docker compose down
docker compose --profile production up -d
```

### Static Hosting (GitHub Pages / Codeberg Pages)

For small archives that don't need search functionality:

**What you get**:
- Zero-cost hosting
- No server management
- Automatic HTTPS
- Browse-only navigation

**Limitations**:
- No search server (browse via navigation)
- Repository size limits (~500MB max recommended)
- Manual updates required

**See [docs/STATIC_DEPLOYMENT.md](../docs/STATIC_DEPLOYMENT.md) for complete guide.**

**Quick example**:
```bash
# Generate archive locally
python reddarc.py /data --output archive/

# Push to GitHub/Codeberg
cd archive/
git init && git add . && git commit -m "Initial archive"
git remote add origin https://github.com/username/repo.git
git push -u origin main

# Enable Pages in repository settings
```

---

## Additional Resources

- [PostgreSQL 18 Documentation](https://www.postgresql.org/docs/18/)
- [psycopg3 Documentation](https://www.psycopg.org/psycopg3/docs/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Let's Encrypt Documentation](https://letsencrypt.org/docs/)
- [Certbot Documentation](https://eff-certbot.readthedocs.io/)
- [Redd-Archiver Project Documentation](../README.md)
- [PostgreSQL Migration Plan](../POSTGRES_MIGRATION_PLAN.md)

---

## Support

**Issues**: Report bugs at https://github.com/19-84/redd-archiver/issues

**Performance Problems**: Include:
- System specs (RAM, CPU, storage type)
- Docker version and platform (Linux/macOS/Windows)
- Archive size (number of posts/comments)
- Relevant logs from `docker-compose logs`

---

**Last Updated**: 2025-12-27
**Docker Compose Version**: 3.8
**PostgreSQL Version**: 18-alpine
**Python Version**: 3.12
