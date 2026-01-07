#!/usr/bin/env python3
"""
ABOUTME: Import Voat comments from multi-part SQL dump files into PostgreSQL
ABOUTME: Handles comment.sql.gz, comment.sql.gz.0, comment.sql.gz.1 sequentially
"""

import os
import sys
import time
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.postgres_database import PostgresDatabase
from core.importers.voat_importer import VoatImporter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    # Database connection
    connection_string = os.environ.get(
        'DATABASE_URL',
        'postgresql://reddarchiver:CHANGE_THIS_PASSWORD@localhost:5435/reddarchiver'
    )

    # Initialize database
    logger.info("Connecting to PostgreSQL...")
    logger.info("(FK constraint already disabled via Docker)")
    db = PostgresDatabase(connection_string)

    # Initialize Voat importer
    importer = VoatImporter()

    # Detect comment files
    data_dir = '/data/voat'
    detected = importer.detect_files(data_dir)
    comment_files = detected.get('comments', [])

    if not comment_files:
        logger.error(f"No comment files found in {data_dir}")
        sys.exit(1)

    logger.info(f"Found {len(comment_files)} comment file(s):")
    for f in comment_files:
        size_mb = os.path.getsize(f) / (1024 * 1024)
        logger.info(f"  - {os.path.basename(f)} ({size_mb:.1f} MB)")

    # Import comments
    total_imported = 0
    total_errors = 0
    start_time = time.time()

    logger.info("\n=== Starting Voat Comment Import ===\n")

    for file_path in comment_files:
        file_start = time.time()
        file_imported = 0
        file_errors = 0

        logger.info(f"Processing: {os.path.basename(file_path)}")

        # Stream comments from this file
        batch = []
        batch_size = 10000

        try:
            for comment in importer.stream_comments(file_path):
                batch.append(comment)

                if len(batch) >= batch_size:
                    # Insert batch
                    success, errors = db.insert_comments_batch(batch)
                    file_imported += success
                    file_errors += errors
                    total_imported += success
                    total_errors += errors

                    # Progress
                    elapsed = time.time() - file_start
                    rate = file_imported / elapsed if elapsed > 0 else 0
                    logger.info(
                        f"  Progress: {file_imported:,} comments ({rate:.0f}/sec), "
                        f"{file_errors} errors"
                    )

                    batch = []

            # Insert remaining batch
            if batch:
                success, errors = db.insert_comments_batch(batch)
                file_imported += success
                file_errors += errors
                total_imported += success
                total_errors += errors

        except Exception as e:
            logger.error(f"Error processing {os.path.basename(file_path)}: {e}", exc_info=True)
            continue

        file_elapsed = time.time() - file_start
        file_rate = file_imported / file_elapsed if file_elapsed > 0 else 0

        logger.info(
            f"✓ {os.path.basename(file_path)}: {file_imported:,} comments "
            f"in {file_elapsed:.1f}s ({file_rate:.0f}/sec), {file_errors} errors\n"
        )

    # Final statistics
    total_elapsed = time.time() - start_time
    avg_rate = total_imported / total_elapsed if total_elapsed > 0 else 0

    logger.info("\n=== Import Complete ===")
    logger.info(f"Total comments: {total_imported:,}")
    logger.info(f"Total errors: {total_errors:,}")
    logger.info(f"Total time: {total_elapsed:.1f}s")
    logger.info(f"Average rate: {avg_rate:.0f} comments/sec")

    # Verify database contents
    logger.info("\n=== Database Verification ===")
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                # Total Voat comments
                cur.execute("""
                    SELECT
                        'Comments' as type,
                        COUNT(*) as count,
                        COUNT(DISTINCT subreddit) as communities,
                        COUNT(DISTINCT author) as authors
                    FROM comments
                    WHERE platform = 'voat'
                """)
                result = cur.fetchone()
                if result:
                    logger.info(f"Voat comments in database: {result[1]:,}")
                    logger.info(f"Communities: {result[2]:,}")
                    logger.info(f"Authors: {result[3]:,}")

                # Orphaned comments (no matching post)
                cur.execute("""
                    SELECT COUNT(*)
                    FROM comments c
                    WHERE c.platform = 'voat'
                      AND NOT EXISTS (
                          SELECT 1 FROM posts p
                          WHERE p.id = c.post_id
                      )
                """)
                orphaned = cur.fetchone()[0]
                if orphaned > 0:
                    logger.info(f"Orphaned comments (no matching post): {orphaned:,}")

    except Exception as e:
        logger.error(f"Verification query failed: {e}")

    # Re-enable foreign key constraint (optional, for data integrity)
    logger.info("\n=== Re-enabling Foreign Key Constraint ===")
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                # Note: We don't re-add the constraint because many comments
                # reference deleted/missing posts, which is expected in archives
                logger.info("Skipping FK constraint re-enable (archived data with deletions)")
    except Exception as e:
        logger.warning(f"Could not re-enable FK constraint: {e}")

    db.close()
    logger.info("\nDone!")


if __name__ == '__main__':
    main()
