#!/usr/bin/env python3
"""
ABOUTME: Import specific Voat subverses only (filtered import example)
ABOUTME: Demonstrates how to import a subset of communities from full Voat archive
"""

import os
import sys
import time
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.postgres_database import PostgresDatabase
from core.importers.voat_importer import VoatImporter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    # ============================================================
    # CONFIGURATION: Edit this list to choose subverses
    # ============================================================
    FILTER_SUBVERSES = [
        'technology',
        'privacy',
        'linux',
        'programming',
        'AskVoat',
        'news',
        'whatever',  # Voat's /r/all equivalent
    ]
    # ============================================================

    connection_string = os.environ.get(
        'DATABASE_URL',
        'postgresql://reddarchiver:CHANGE_THIS_PASSWORD@localhost:5435/reddarchiver'
    )

    db = PostgresDatabase(connection_string)
    importer = VoatImporter()

    data_dir = '/data/voat'
    detected = importer.detect_files(data_dir)

    logger.info(f"\n{'='*60}")
    logger.info(f"Voat Filtered Import - {len(FILTER_SUBVERSES)} subverses")
    logger.info(f"{'='*60}")
    for subverse in FILTER_SUBVERSES:
        logger.info(f"  - v/{subverse}")
    logger.info(f"{'='*60}\n")

    # Import posts
    logger.info("=== Importing Posts ===")
    post_files = detected.get('posts', [])
    total_posts = 0
    start_time = time.time()

    for file_path in post_files:
        batch = []
        batch_size = 10000

        for post in importer.stream_posts(file_path, filter_communities=FILTER_SUBVERSES):
            batch.append(post)
            if len(batch) >= batch_size:
                success, errors = db.insert_posts_batch(batch)
                total_posts += success
                logger.info(f"  Posts imported: {total_posts:,}")
                batch = []

        if batch:
            success, errors = db.insert_posts_batch(batch)
            total_posts += success

    post_elapsed = time.time() - start_time
    logger.info(f"✓ Posts: {total_posts:,} in {post_elapsed:.1f}s\n")

    # Import comments
    logger.info("=== Importing Comments ===")
    comment_files = detected.get('comments', [])
    total_comments = 0
    start_time = time.time()

    for file_path in comment_files:
        batch = []
        batch_size = 10000

        for comment in importer.stream_comments(file_path, filter_communities=FILTER_SUBVERSES):
            batch.append(comment)
            if len(batch) >= batch_size:
                success, errors = db.insert_comments_batch(batch)
                total_comments += success
                logger.info(f"  Comments imported: {total_comments:,}")
                batch = []

        if batch:
            success, errors = db.insert_comments_batch(batch)
            total_comments += success

    comment_elapsed = time.time() - start_time
    logger.info(f"✓ Comments: {total_comments:,} in {comment_elapsed:.1f}s\n")

    # Summary
    logger.info("=== Import Complete ===")
    logger.info(f"Posts: {total_posts:,}")
    logger.info(f"Comments: {total_comments:,}")
    logger.info(f"Subverses: {len(FILTER_SUBVERSES)}")

    db.close()


if __name__ == '__main__':
    main()
