# ABOUTME: Alpine-based Dockerfile for Flask search server with PostgreSQL FTS integration
# ABOUTME: Secure, minimal, production-ready with non-root user and read-only filesystem

# ============================================================================
# Alpine-based build for minimal image size and security
# ============================================================================
FROM python:3.12-alpine

# Set working directory
WORKDIR /app

# Install system dependencies (minimal set for PostgreSQL and Flask)
# - build-base: Essential build tools (gcc, make, etc.)
# - postgresql-dev: PostgreSQL development headers for psycopg
# - postgresql-libs: PostgreSQL runtime libraries
# - musl-dev: C library for Alpine (required for Python extensions)
# - linux-headers: Linux kernel headers (required for psutil compilation)
# - ca-certificates: SSL/TLS certificate bundle
RUN apk add --no-cache \
    build-base \
    postgresql-dev \
    postgresql-libs \
    musl-dev \
    linux-headers \
    ca-certificates

# Install uv (Python package manager - 10-100x faster than pip)
# Using official installation script from astral.sh
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy requirements file first for better caching
COPY docker/search-server/requirements.txt /app/requirements.txt

# Create virtual environment and install dependencies using uv
# uv is 10-100x faster than pip for dependency resolution
# Use --quiet to prevent excessive build output (avoids overwhelming Claude Code terminal)
# Remove --quiet flag if you need to debug compilation issues with psutil
RUN uv venv /app/.venv && \
    uv pip install --no-cache-dir --quiet -r requirements.txt

# Activate virtual environment
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Verify critical dependencies installed correctly (especially psutil for Alpine)
RUN python3 -c "import psutil; import psycopg; import flask; print('✓ All dependencies verified')"

# Copy application code (only files needed for search server)
COPY search_server.py /app/

# Copy core and utils directories (maintaining package structure)
COPY core/ /app/core/
COPY utils/ /app/utils/

# Copy API endpoints (required by search_server.py)
COPY api/ /app/api/

COPY sql/ /app/sql/

# Copy templates and static files
COPY templates_jinja2/ /app/templates/
COPY static/ /app/static/

# Copy Gunicorn configuration
COPY docker/search-server/gunicorn.conf.py /app/gunicorn.conf.py

# Create non-root user for security
# UID 1001 to avoid conflicts with existing users
RUN adduser -D -u 1001 -s /bin/false search && \
    chown -R search:search /app

# Create /tmp directory for Flask sessions (writable by non-root user)
RUN mkdir -p /tmp/flask-sessions && \
    chown search:search /tmp/flask-sessions

# Switch to non-root user
USER search

# Health check - verify Flask server is responding
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1

# Expose Flask port
EXPOSE 5000

# Default command: Run Flask with Gunicorn (production-ready)
# - bind to 0.0.0.0:5000 (accessible from outside container)
# - 4 worker processes for concurrency
# - config file with hooks to pre-initialize search engine in each worker
# - access log to stdout for Docker logging
CMD ["gunicorn", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "4", \
     "--worker-class", "sync", \
     "--config", "/app/gunicorn.conf.py", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--log-level", "info", \
     "search_server:app"]
