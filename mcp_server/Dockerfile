# ABOUTME: Single-stage Dockerfile for reddarchiver-mcp server using system Python
# ABOUTME: Avoids multi-stage Python version mismatch by installing everything in runtime image

FROM python:3.12-slim-bookworm

# Install uv for fast dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash mcp && \
    mkdir -p /app && \
    chown -R mcp:mcp /app

WORKDIR /app

# Copy dependency files first for better caching
COPY --chown=mcp:mcp pyproject.toml uv.lock README.md ./

# Switch to non-root user for venv creation
USER mcp

# Create virtual environment with system Python and install dependencies
# Using --no-dev skips development dependencies for smaller image
RUN uv venv .venv && uv sync --no-dev --frozen

# Copy application code
COPY --chown=mcp:mcp . .

# Activate virtual environment
# Set PYTHONPATH explicitly to include venv site-packages
ENV VIRTUAL_ENV="/app/.venv"
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/.venv/lib/python3.12/site-packages:$PYTHONPATH"
ENV PYTHONUNBUFFERED=1

# Default API URL (can be overridden via environment variable)
ENV REDDARCHIVER_API_URL="http://search-server:5000"

# Health check - verify Python and dependencies are available
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import fastmcp; import httpx; print('OK')" || exit 1

# Run the MCP server
# Note: MCP servers communicate via stdio, so we use the default entrypoint
CMD ["python", "server.py"]
