#!/usr/bin/env python3
"""
ABOUTME: Populate users table from posts and comments
ABOUTME: Calls update_user_statistics() to build user profiles
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.postgres_database import PostgresDatabase

connection_string = os.environ.get(
    'DATABASE_URL',
    'postgresql://reddarchiver:CHANGE_THIS_PASSWORD@localhost:5435/reddarchiver'
)

print("Connecting to PostgreSQL...")
db = PostgresDatabase(connection_string)

print("Updating user statistics...")
db.update_user_statistics()

print("\nVerifying users table...")
with db.pool.get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT platform, COUNT(*) as users, SUM(post_count) as posts, SUM(comment_count) as comments
            FROM users
            GROUP BY platform
            ORDER BY platform;
        """)

        print(f"\n{'Platform':<10} {'Users':<10} {'Posts':<10} {'Comments':<10}")
        print("=" * 40)
        for row in cur.fetchall():
            print(f"{row[0]:<10} {row[1]:<10} {row[2]:<10} {row[3]:<10}")

print("\n✓ Users table populated!")
