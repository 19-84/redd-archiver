#!/usr/bin/env python3
"""
ABOUTME: Export individual Voat subverses as standalone SQL dumps
ABOUTME: Creates per-subverse .sql files for distributed archiving
"""

import os
import sys
import subprocess
from pathlib import Path

# Database connection
DB_HOST = "localhost"
DB_PORT = "5435"
DB_NAME = "reddarchiver"
DB_USER = "reddarchiver"
DB_PASS = "CHANGE_THIS_PASSWORD"

OUTPUT_DIR = "/tmp/voat-subverse-exports"
Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

def export_subverse_sql(subverse: str, output_path: str):
    """Export a single subverse to SQL file."""

    # Build WHERE clause
    where_clause = f"WHERE platform = 'voat' AND subreddit = '{subverse}'"

    # Export posts
    posts_sql = f"""
    COPY (
        SELECT * FROM posts {where_clause}
    ) TO STDOUT WITH (FORMAT text, DELIMITER E'\\t', NULL '\\N');
    """

    # Export comments (join to get only comments for posts in this subverse)
    comments_sql = f"""
    COPY (
        SELECT c.* FROM comments c
        INNER JOIN posts p ON c.post_id = p.id
        WHERE c.platform = 'voat' AND p.subreddit = '{subverse}'
    ) TO STDOUT WITH (FORMAT text, DELIMITER E'\\t', NULL '\\N');
    """

    print(f"Exporting v/{subverse}...")

    with open(output_path, 'w') as f:
        # Write header
        f.write(f"-- Voat subverse: {subverse}\n")
        f.write(f"-- Generated from redd-archiver PostgreSQL database\n\n")

        # Export posts
        f.write(f"-- Posts for v/{subverse}\n")
        result = subprocess.run([
            'sudo', 'docker', 'exec', 'reddarchiver-postgres',
            'psql', '-U', DB_USER, '-d', DB_NAME,
            '-c', posts_sql
        ], capture_output=True, text=True)

        if result.returncode == 0:
            f.write(result.stdout)
        else:
            print(f"  ERROR: {result.stderr}")
            return False

        # Export comments
        f.write(f"\n-- Comments for v/{subverse}\n")
        result = subprocess.run([
            'sudo', 'docker', 'exec', 'reddarchiver-postgres',
            'psql', '-U', DB_USER, '-d', DB_NAME,
            '-c', comments_sql
        ], capture_output=True, text=True)

        if result.returncode == 0:
            f.write(result.stdout)
        else:
            print(f"  ERROR: {result.stderr}")
            return False

    # Get file size
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"  ✓ Exported to {output_path} ({size_mb:.1f} MB)")
    return True


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Export Voat subverses to individual SQL files')
    parser.add_argument('--subverse', help='Export single subverse')
    parser.add_argument('--top', type=int, help='Export top N subverses by post count')
    parser.add_argument('--min-posts', type=int, default=50, help='Minimum post count (default: 50)')
    parser.add_argument('--max-posts', type=int, default=10000, help='Maximum post count (default: 10000)')

    args = parser.parse_args()

    if args.subverse:
        # Export single subverse
        output_path = os.path.join(OUTPUT_DIR, f"{args.subverse}.sql")
        export_subverse_sql(args.subverse, output_path)

    elif args.top:
        # Get top N subverses
        result = subprocess.run([
            'sudo', 'docker', 'exec', 'reddarchiver-postgres',
            'psql', '-U', DB_USER, '-d', DB_NAME, '-t', '-c',
            f"""
            SELECT subreddit, COUNT(*) as posts
            FROM posts
            WHERE platform = 'voat'
              AND subreddit != ''
            GROUP BY subreddit
            HAVING COUNT(*) BETWEEN {args.min_posts} AND {args.max_posts}
            ORDER BY COUNT(*) DESC
            LIMIT {args.top};
            """
        ], capture_output=True, text=True)

        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if '|' in line:
                    subverse = line.split('|')[0].strip()
                    output_path = os.path.join(OUTPUT_DIR, f"{subverse}.sql")
                    export_subverse_sql(subverse, output_path)
        else:
            print(f"ERROR: {result.stderr}")

    else:
        parser.print_help()
        sys.exit(1)

    print(f"\nDone! Exports saved to: {OUTPUT_DIR}")


if __name__ == '__main__':
    main()
