# ABOUTME: Alpine-based Dockerfile for Redd-Archiver archive builder with PostgreSQL support
# ABOUTME: Uses uv for fast dependency installation and minimal image size

# ============================================================================
# Alpine-based build for minimal image size and fast deployment
# ============================================================================
FROM python:3.12-alpine

# Set working directory
WORKDIR /app

# Install system dependencies
# - build-base: Essential build tools (gcc, make, etc.)
# - postgresql-dev: PostgreSQL development headers for psycopg
# - postgresql-libs: PostgreSQL runtime libraries
# - postgresql-client: psql command-line tool
# - musl-dev: C library for Alpine (required for Python extensions)
# - ca-certificates: SSL/TLS certificate bundle
# - linux-headers: Kernel headers (required for psutil compilation)
# - p7zip: 7z compression utility (required for Ruqqus .7z archives)
RUN apk add --no-cache \
    build-base \
    postgresql-dev \
    postgresql-libs \
    postgresql-client \
    musl-dev \
    ca-certificates \
    linux-headers \
    p7zip

# Install uv (Python package manager - 10-100x faster than pip)
# Using official installation script from astral.sh
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy requirements file first for better caching
COPY requirements.txt .

# Create virtual environment and install dependencies using uv
# uv is 10-100x faster than pip for dependency resolution
RUN uv venv /app/.venv && \
    uv pip install --no-cache -r requirements.txt

# Copy application code
COPY . .

# Ensure SQL files are in the correct location for runtime access
RUN mkdir -p /app/core/sql && \
    cp -f sql/*.sql /app/core/sql/ 2>/dev/null || true

# Create necessary directories with appropriate permissions
RUN mkdir -p /data /output /logs && \
    chmod 755 /data /output /logs

# Activate virtual environment
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Add health check script
COPY docker/healthcheck/builder-healthcheck.py /healthcheck.py
RUN chmod +x /healthcheck.py

# Health check - verify PostgreSQL connectivity
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 /healthcheck.py || exit 1

# Default command shows help
CMD ["python3", "reddarc.py", "--help"]
