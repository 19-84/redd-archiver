[Home](../README.md) | [Docs](../README.md#documentation) | [Quickstart](../QUICKSTART.md) | [FAQ](FAQ.md)

---

# Installation Guide

> **TL;DR:** Docker is recommended for fast setup. Local PostgreSQL requires manual database creation. See [QUICKSTART.md](../QUICKSTART.md) for quick deployment.

## Quick Install (Docker - Recommended)

For fast deployment, see [QUICKSTART.md](../QUICKSTART.md) which covers Docker setup in 2-15 minutes.

This guide provides detailed installation instructions for both Docker and local PostgreSQL setups.

---

## Prerequisites

### System Requirements

**Minimum**:
- **Python 3.7 or higher**
- **PostgreSQL 12+** (required for v1.0+)
- 4GB+ RAM (PostgreSQL uses constant memory)
- Disk space: ~1.5-2x your input .zst file size for PostgreSQL database

**Recommended**:
- 8GB+ RAM
- SSD storage (3-5x faster than HDD)
- 4+ CPU cores

### Python Dependencies

Redd-Archiver uses modern, performance-focused dependencies:

**Core**:
- `psycopg[binary,pool]==3.2.3` - PostgreSQL adapter with connection pooling
- `zstandard==0.23.0` - Fast .zst decompression
- `psutil==6.1.1` - System resource monitoring

**HTML Generation**:
- `jinja2>=3.1.6` - Modern template engine with inheritance
- `rcssmin>=1.1.2` - CSS minification for smaller file sizes

**Performance**:
- `orjson>=3.11.4` - Fast JSON parsing

---

## Docker Installation (Recommended)

### Step 1: Clone Repository

```bash
git clone https://github.com/19-84/redd-archiver.git
cd redd-archiver
```

### Step 2: Create Required Directories

```bash
mkdir -p data output/.postgres-data logs tor-public
```

### Step 3: Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit configuration
nano .env  # or vim, code, etc.
```

**Required changes in `.env`**:
```bash
# Change the password in BOTH places:
POSTGRES_PASSWORD=YOUR_SECURE_PASSWORD
DATABASE_URL=postgresql://reddarchiver:YOUR_SECURE_PASSWORD@/reddarchiver?host=/var/run/postgresql
```

**Important**: The password must match in both `POSTGRES_PASSWORD` and `DATABASE_URL`!

### Step 4: Start Services

```bash
# Start PostgreSQL and other services
docker compose up -d

# Wait for services to become healthy
sleep 30

# Verify services are running
docker compose ps
# All services should show "healthy"
```

### Step 5: Verify Installation

```bash
# Test nginx
curl http://localhost/health
# Expected: OK

# Test search server
curl http://localhost:5000/health
# Expected: {"status":"healthy"}

# Test database connection
docker compose exec postgres psql -U reddarchiver -d reddarchiver -c "SELECT version();"
```

### Step 6: Run Archive Generator

```bash
# Configure database connection (already set in .env, but can override)
export DATABASE_URL="postgresql://reddarchiver:your_password@localhost:5432/reddarchiver"

# Generate your first archive
python reddarc.py /path/to/data/ --output my-archive/
```

---

## Local PostgreSQL Installation

For systems where you prefer to install PostgreSQL directly instead of using Docker.

### Ubuntu/Debian

#### Install PostgreSQL

```bash
# Update package list
sudo apt update

# Install PostgreSQL
sudo apt install postgresql postgresql-contrib python3-pip

# Verify installation
psql --version
```

#### Create Database

```bash
# Switch to postgres user
sudo -u postgres psql

# In PostgreSQL shell:
CREATE USER "redd-archiver" WITH PASSWORD 'your_secure_password';
CREATE DATABASE "redd-archiver" OWNER "redd-archiver";
GRANT ALL PRIVILEGES ON DATABASE "redd-archiver" TO "redd-archiver";
\q

# Or as one-liners:
sudo -u postgres createuser redd-archiver
sudo -u postgres createdb -O redd-archiver redd-archiver
sudo -u postgres psql -c "ALTER USER \"redd-archiver\" WITH PASSWORD 'your_secure_password';"
```

#### Install Python Dependencies

```bash
# Clone repository
git clone https://github.com/19-84/redd-archiver.git
cd redd-archiver

# Install dependencies
pip3 install -r requirements.txt

# Or using uv (recommended)
pip3 install uv
uv sync
```

#### Configure Connection

```bash
# Set DATABASE_URL environment variable
export DATABASE_URL="postgresql://redd-archiver:your_secure_password@localhost:5432/redd-archiver"

# Add to ~/.bashrc or ~/.zshrc for persistence:
echo 'export DATABASE_URL="postgresql://redd-archiver:your_secure_password@localhost:5432/redd-archiver"' >> ~/.bashrc
source ~/.bashrc
```

#### Run Archive Generator

```bash
python reddarc.py /path/to/data/ --output my-archive/
```

---

### macOS

#### Install PostgreSQL

```bash
# Using Homebrew
brew install postgresql@16

# Start PostgreSQL service
brew services start postgresql@16

# Verify installation
psql --version
```

#### Create Database

```bash
# Create user
createuser redd-archiver

# Create database
createdb -O redd-archiver redd-archiver

# Set password
psql -c "ALTER USER \"redd-archiver\" WITH PASSWORD 'your_secure_password';"
```

#### Install Python Dependencies

```bash
# Clone repository
git clone https://github.com/19-84/redd-archiver.git
cd redd-archiver

# Install dependencies
pip3 install -r requirements.txt

# Or using uv (recommended)
brew install uv
uv sync
```

#### Configure Connection

```bash
# Set DATABASE_URL
export DATABASE_URL="postgresql://redd-archiver:your_secure_password@localhost:5432/redd-archiver"

# Add to shell profile for persistence:
echo 'export DATABASE_URL="postgresql://redd-archiver:your_secure_password@localhost:5432/redd-archiver"' >> ~/.zshrc
source ~/.zshrc
```

#### Run Archive Generator

```bash
python reddarc.py /path/to/data/ --output my-archive/
```

---

### Windows (WSL2)

#### Install WSL2

If not already installed:
```powershell
# In PowerShell (as Administrator)
wsl --install
# Restart computer
```

#### Follow Ubuntu Instructions

Once WSL2 is running, follow the [Ubuntu/Debian instructions](#ubuntudebian) above.

---

## Troubleshooting Installation

### PostgreSQL Connection Issues

**Problem**: `could not connect to server` or `connection refused`

**Solutions**:

1. **Check PostgreSQL is running**:
```bash
# Ubuntu/Debian
sudo systemctl status postgresql

# macOS
brew services list | grep postgresql

# Start if stopped
sudo systemctl start postgresql  # Ubuntu
brew services start postgresql@16  # macOS
```

2. **Verify DATABASE_URL is correct**:
```bash
echo $DATABASE_URL
# Should show: postgresql://redd-archiver:password@localhost:5432/redd-archiver
```

3. **Check PostgreSQL is listening**:
```bash
# Check if PostgreSQL is listening on port 5432
sudo netstat -plnt | grep 5432

# Or using ss
sudo ss -tlnp | grep 5432
```

4. **Test connection manually**:
```bash
psql -U redd-archiver -d redd-archiver -h localhost
```

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md#database-connection-problems) for more database issues.

---

### Python Version Issues

**Problem**: `SyntaxError` or incompatibility warnings

**Solution**: Ensure Python 3.7+
```bash
python --version
# or
python3 --version
```

If too old, install newer Python:
```bash
# Ubuntu/Debian
sudo apt install python3.10

# macOS
brew install python@3.10

# Or use pyenv
curl https://pyenv.run | bash
pyenv install 3.12
pyenv local 3.12
```

---

### Dependency Installation Fails

**Problem**: `ERROR: Could not find a version that satisfies the requirement`

**Solutions**:

1. **Update pip**:
```bash
pip3 install --upgrade pip
```

2. **Use uv (faster, more reliable)**:
```bash
pip3 install uv
uv sync
```

3. **Install system dependencies first** (Ubuntu/Debian):
```bash
sudo apt install python3-dev libpq-dev
```

---

### Permission Errors

**Problem**: `PermissionError: [Errno 13] Permission denied`

**Solutions**:

1. **Check output directory permissions**:
```bash
ls -la output/
chmod 755 output/
```

2. **Don't run as root**:
```bash
# Bad
sudo python reddarc.py ...

# Good
python reddarc.py ...
```

3. **PostgreSQL data directory** (Docker):
```bash
sudo chown -R 999:999 output/.postgres-data
```

---

## Upgrading

### Check Current Version

```bash
python reddarc.py --version
```

### Review Changes

Before upgrading, review [CHANGELOG.md](../CHANGELOG.md) for:
- Breaking changes
- New features
- Migration steps

### Upgrade Process

#### Docker Installation

```bash
cd redd-archiver

# Pull latest code
git pull origin main

# Rebuild containers
docker compose down
docker compose up -d --build

# Verify
docker compose ps
```

#### Local Installation

```bash
cd redd-archiver

# Pull latest code
git pull origin main

# Update dependencies
pip install -r requirements.txt --upgrade

# Or with uv
uv sync

# Check database schema (if migrations exist)
# Run any migration scripts in sql/migrations/
```

### Database Migrations

If upgrading requires database schema changes:

```bash
# Check for migrations
ls sql/migrations/

# Apply migrations (example)
psql -U redd-archiver -d redd-archiver -f sql/migrations/003_add_total_activity_column.sql
```

---

## See Also

- [QUICKSTART.md](../QUICKSTART.md) - Fast deployment guide (2-15 minutes)
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common installation issues
- [FAQ](FAQ.md) - Quick answers to installation questions
- [Docker README](../docker/README.md) - Complete Docker reference

---

**Last Updated**: 2026-01-26
