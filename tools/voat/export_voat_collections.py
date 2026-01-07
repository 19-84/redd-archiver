#!/usr/bin/env python3
"""
ABOUTME: Export curated Voat subverse collections to SQL or HTML
ABOUTME: Predefined collections: tech, gaming, news, culture, etc.
"""

import os
import sys
import subprocess
from pathlib import Path

# Curated Voat Collections
COLLECTIONS = {
    'tech': {
        'name': 'Technology & Programming',
        'description': 'Tech news, Linux, programming, privacy, and cryptocurrency',
        'subverses': [
            'technology',
            'Linux',
            'programming',
            'privacy',
            'linuxgaming',
            'techhell',
            'cryptocurrency',
            'technews',
            'tech',
            'BigTech',
            'learnprogramming',
            'techsupport',
            'software'
        ]
    },
    'gaming': {
        'name': 'Gaming',
        'description': 'All things gaming - PC, console, retro, and indie',
        'subverses': [
            'gaming',
            'gamingfringe',
            'GamerGate',
            'CoOpGaming',
            'linuxgaming',
            'pcmasterrace',
            'gametrailers',
            'VideoGameMusic',
            'pcgaming',
            'games',
            'IndieGames',
            'xboxone',
            'GameDeals',
            'Playstation4',
            'Nintendo',
            'videogames',
            'retrogaming'
        ]
    },
    'news': {
        'name': 'News & Current Events',
        'description': 'News from around the world',
        'subverses': [
            'news',
            'politics',
            'worldnews',
            'WorldNews',
            'technews',
            'TheNewsFeed',
            'news24seven'
        ]
    },
    'culture': {
        'name': 'Culture & Entertainment',
        'description': 'Movies, TV, music, and art',
        'subverses': [
            'videos',
            'funny',
            'music',
            'Television',
            'movies',
            'Art',
            'books'
        ]
    },
    'science': {
        'name': 'Science & Education',
        'description': 'Science, space, and learning',
        'subverses': [
            'science',
            'space',
            'askscience',
            'Physics',
            'biology',
            'chemistry'
        ]
    }
}

OUTPUT_DIR = '/tmp/voat-collections'
Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

DB_HOST = "localhost"
DB_PORT = "5435"
DB_NAME = "reddarchiver"
DB_USER = "reddarchiver"


def export_collection_sql(collection_name: str, subverses: list, output_path: str):
    """Export a collection of subverses to single SQL file."""

    print(f"\nExporting collection: {collection_name}")
    print(f"Subverses: {', '.join(subverses)}")

    subverse_list = "', '".join(subverses)

    # Export posts
    posts_sql = f"""
    COPY (
        SELECT * FROM posts
        WHERE platform = 'voat'
          AND subreddit IN ('{subverse_list}')
        ORDER BY subreddit, created_utc DESC
    ) TO STDOUT WITH (FORMAT text, DELIMITER E'\\t', NULL '\\N');
    """

    # Export comments
    comments_sql = f"""
    COPY (
        SELECT c.* FROM comments c
        INNER JOIN posts p ON c.post_id = p.id
        WHERE c.platform = 'voat'
          AND p.subreddit IN ('{subverse_list}')
        ORDER BY p.subreddit, c.created_utc DESC
    ) TO STDOUT WITH (FORMAT text, DELIMITER E'\\t', NULL '\\N');
    """

    with open(output_path, 'w') as f:
        # Write header
        f.write(f"-- Voat Collection: {collection_name}\n")
        f.write(f"-- Subverses: {', '.join(subverses)}\n")
        f.write(f"-- Generated from redd-archiver PostgreSQL database\n\n")

        # Export posts
        f.write(f"-- Posts for collection '{collection_name}'\n")
        result = subprocess.run([
            'sudo', 'docker', 'exec', 'reddarchiver-postgres',
            'psql', '-U', DB_USER, '-d', DB_NAME,
            '-c', posts_sql
        ], capture_output=True, text=True)

        if result.returncode == 0:
            f.write(result.stdout)
            post_count = len(result.stdout.strip().split('\n'))
            print(f"  ✓ Exported {post_count:,} posts")
        else:
            print(f"  ERROR: {result.stderr}")
            return False

        # Export comments
        f.write(f"\n-- Comments for collection '{collection_name}'\n")
        result = subprocess.run([
            'sudo', 'docker', 'exec', 'reddarchiver-postgres',
            'psql', '-U', DB_USER, '-d', DB_NAME,
            '-c', comments_sql
        ], capture_output=True, text=True)

        if result.returncode == 0:
            f.write(result.stdout)
            comment_count = len(result.stdout.strip().split('\n'))
            print(f"  ✓ Exported {comment_count:,} comments")
        else:
            print(f"  ERROR: {result.stderr}")
            return False

    # Get file size
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"  ✓ Saved to {output_path} ({size_mb:.1f} MB)")
    return True


def list_collections():
    """List all available collections."""
    print("\nAvailable Voat Collections:\n")
    for key, info in COLLECTIONS.items():
        print(f"  {key:12} - {info['name']}")
        print(f"              {info['description']}")
        print(f"              {len(info['subverses'])} subverses")
        print()


def generate_stats():
    """Generate statistics for all collections."""
    print("\n" + "="*70)
    print("VOAT COLLECTION STATISTICS")
    print("="*70 + "\n")

    for key, info in COLLECTIONS.items():
        subverse_list = "', '".join(info['subverses'])

        result = subprocess.run([
            'sudo', 'docker', 'exec', 'reddarchiver-postgres',
            'psql', '-U', DB_USER, '-d', DB_NAME, '-t', '-c',
            f"""
            SELECT
                COUNT(DISTINCT p.id) as posts,
                COUNT(DISTINCT c.id) as comments,
                COUNT(DISTINCT p.author) as authors
            FROM posts p
            LEFT JOIN comments c ON c.post_id = p.id AND c.platform = 'voat'
            WHERE p.platform = 'voat'
              AND p.subreddit IN ('{subverse_list}');
            """
        ], capture_output=True, text=True)

        if result.returncode == 0:
            stats = result.stdout.strip().split('|')
            if len(stats) == 3:
                posts = int(stats[0].strip())
                comments = int(stats[1].strip())
                authors = int(stats[2].strip())

                print(f"{info['name']}")
                print(f"  Subverses: {len(info['subverses'])}")
                print(f"  Posts: {posts:,}")
                print(f"  Comments: {comments:,}")
                print(f"  Authors: {authors:,}")
                print()


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Export curated Voat collections')
    parser.add_argument('--collection', choices=list(COLLECTIONS.keys()) + ['all'],
                        help='Collection to export')
    parser.add_argument('--list', action='store_true',
                        help='List available collections')
    parser.add_argument('--stats', action='store_true',
                        help='Generate statistics for all collections')
    parser.add_argument('--format', choices=['sql', 'html'], default='sql',
                        help='Export format (default: sql)')

    args = parser.parse_args()

    if args.list:
        list_collections()
        return

    if args.stats:
        generate_stats()
        return

    if not args.collection:
        parser.print_help()
        print("\nUse --list to see available collections")
        sys.exit(1)

    # Export collection(s)
    if args.collection == 'all':
        collections_to_export = COLLECTIONS.items()
    else:
        collections_to_export = [(args.collection, COLLECTIONS[args.collection])]

    for key, info in collections_to_export:
        output_path = os.path.join(OUTPUT_DIR, f"voat-{key}-collection.sql")

        if args.format == 'sql':
            export_collection_sql(info['name'], info['subverses'], output_path)
        else:
            print(f"HTML export not yet implemented (TODO)")

    print(f"\nDone! Collections saved to: {OUTPUT_DIR}")


if __name__ == '__main__':
    main()
