#!/usr/bin/env python3
# ABOUTME: Health check script for redd-archiver-builder container
# ABOUTME: Tests PostgreSQL connectivity via Unix socket (primary) and TCP (fallback)

import os
import sys

def test_connection(conn_str: str, name: str) -> bool:
    """Test database connection and return success status"""
    try:
        import psycopg

        with psycopg.connect(conn_str, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                result = cur.fetchone()

                if result and result[0] == 1:
                    print(f"✅ {name} connection successful")
                    return True
                else:
                    print(f"❌ {name} connection returned unexpected result")
                    return False

    except Exception as e:
        print(f"❌ {name} connection failed: {e}")
        return False

def main():
    """Main health check logic"""

    # Try Unix socket first (primary connection method)
    unix_socket_url = os.getenv('DATABASE_URL')
    if unix_socket_url:
        if test_connection(unix_socket_url, "Unix socket"):
            sys.exit(0)  # Success!
    else:
        print("⚠️  DATABASE_URL not set")

    # Fallback to TCP socket
    tcp_socket_url = os.getenv('DATABASE_URL_TCP')
    if tcp_socket_url:
        if test_connection(tcp_socket_url, "TCP socket"):
            print("⚠️  Using TCP fallback (Unix socket unavailable)")
            sys.exit(0)  # Success with fallback
    else:
        print("⚠️  DATABASE_URL_TCP not set")

    # No connection method worked
    print("❌ No database connection available")
    print("\nTroubleshooting:")
    print("1. Ensure PostgreSQL container is running and healthy")
    print("2. Check DATABASE_URL environment variable")
    print("3. Verify Unix socket volume is mounted (/var/run/postgresql)")
    print("4. Check network connectivity between containers")

    sys.exit(1)  # Failure

if __name__ == "__main__":
    main()
