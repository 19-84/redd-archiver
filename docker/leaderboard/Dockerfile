# ABOUTME: Dockerfile for registry leaderboard generator
# ABOUTME: Standalone container that fetches instance stats and generates markdown

FROM python:3.12-alpine

WORKDIR /app

# Install aiohttp
RUN pip install --no-cache-dir aiohttp==3.13.2

# Copy leaderboard script
COPY scripts/update_leaderboard.py /app/update_leaderboard.py
RUN chmod +x /app/update_leaderboard.py

# Default command
CMD ["python", "/app/update_leaderboard.py"]
