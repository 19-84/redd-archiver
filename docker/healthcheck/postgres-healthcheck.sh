#!/bin/sh
# ABOUTME: Health check script for PostgreSQL container
# ABOUTME: Verifies both Unix socket and TCP connectivity are available

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Database credentials from environment
POSTGRES_USER="${POSTGRES_USER:-archive_db}"
POSTGRES_DB="${POSTGRES_DB:-archive_db}"

echo "PostgreSQL Health Check Starting..."

# Test 1: Check if PostgreSQL is accepting connections via Unix socket
echo "Testing Unix socket connection..."
if pg_isready -U "$POSTGRES_USER" -h /var/run/postgresql -d "$POSTGRES_DB" > /dev/null 2>&1; then
    echo "${GREEN}✅ Unix socket connection successful${NC}"
    UNIX_SOCKET_OK=1
else
    echo "${RED}❌ Unix socket connection failed${NC}"
    UNIX_SOCKET_OK=0
fi

# Test 2: Check if PostgreSQL is accepting connections via TCP
echo "Testing TCP connection..."
if pg_isready -U "$POSTGRES_USER" -h localhost -p 5432 -d "$POSTGRES_DB" > /dev/null 2>&1; then
    echo "${GREEN}✅ TCP connection successful${NC}"
    TCP_OK=1
else
    echo "${RED}❌ TCP connection failed${NC}"
    TCP_OK=0
fi

# Test 3: Verify socket file exists
if [ -S /var/run/postgresql/.s.PGSQL.5432 ]; then
    echo "${GREEN}✅ Socket file exists: /var/run/postgresql/.s.PGSQL.5432${NC}"
    SOCKET_FILE_OK=1
else
    echo "${YELLOW}⚠️  Socket file not found: /var/run/postgresql/.s.PGSQL.5432${NC}"
    SOCKET_FILE_OK=0
fi

# Overall health status
if [ $UNIX_SOCKET_OK -eq 1 ] && [ $TCP_OK -eq 1 ] && [ $SOCKET_FILE_OK -eq 1 ]; then
    echo "${GREEN}✅ PostgreSQL is healthy (Unix socket + TCP)${NC}"
    exit 0
elif [ $UNIX_SOCKET_OK -eq 1 ] || [ $TCP_OK -eq 1 ]; then
    echo "${YELLOW}⚠️  PostgreSQL is partially healthy${NC}"
    exit 0
else
    echo "${RED}❌ PostgreSQL is unhealthy${NC}"
    exit 1
fi
