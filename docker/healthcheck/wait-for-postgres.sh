#!/bin/sh
# ABOUTME: Wait script for PostgreSQL readiness before starting dependent services
# ABOUTME: Prevents race conditions during container startup by polling health status

set -e

# Configuration
MAX_RETRIES=30
RETRY_INTERVAL=2
POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-archive_db}"
POSTGRES_DB="${POSTGRES_DB:-archive_db}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "Waiting for PostgreSQL to become ready..."
echo "Host: $POSTGRES_HOST:$POSTGRES_PORT"
echo "Database: $POSTGRES_DB"
echo "User: $POSTGRES_USER"
echo "Max retries: $MAX_RETRIES (${RETRY_INTERVAL}s interval)"
echo ""

# Try Unix socket first if available
if [ -d "/var/run/postgresql" ]; then
    echo "Attempting Unix socket connection..."
    RETRY_COUNT=0

    until pg_isready -U "$POSTGRES_USER" -h /var/run/postgresql -d "$POSTGRES_DB" > /dev/null 2>&1; do
        RETRY_COUNT=$((RETRY_COUNT + 1))

        if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
            echo "${YELLOW}⚠️  Unix socket timeout, falling back to TCP...${NC}"
            break
        fi

        echo "Unix socket not ready yet (attempt $RETRY_COUNT/$MAX_RETRIES)..."
        sleep $RETRY_INTERVAL
    done

    if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
        echo "${GREEN}✅ PostgreSQL ready via Unix socket${NC}"
        exit 0
    fi
fi

# TCP connection as fallback
echo "Attempting TCP connection..."
RETRY_COUNT=0

until pg_isready -U "$POSTGRES_USER" -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -d "$POSTGRES_DB" > /dev/null 2>&1; do
    RETRY_COUNT=$((RETRY_COUNT + 1))

    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo "${RED}❌ PostgreSQL failed to become ready after $MAX_RETRIES attempts${NC}"
        echo ""
        echo "Troubleshooting:"
        echo "1. Check if postgres container is running: docker-compose ps postgres"
        echo "2. Check postgres logs: docker-compose logs postgres"
        echo "3. Verify network connectivity: docker-compose exec builder ping postgres"
        echo "4. Check DATABASE_URL environment variable"
        exit 1
    fi

    echo "TCP connection not ready yet (attempt $RETRY_COUNT/$MAX_RETRIES)..."
    sleep $RETRY_INTERVAL
done

echo "${GREEN}✅ PostgreSQL ready via TCP${NC}"
exit 0
