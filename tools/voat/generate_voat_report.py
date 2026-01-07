#!/usr/bin/env python3
"""
ABOUTME: Generate comprehensive Voat archive statistics report
ABOUTME: Creates markdown report with database statistics and top content
"""

import subprocess
from datetime import datetime

DB_USER = "reddarchiver"
DB_NAME = "reddarchiver"


def query_db(sql: str) -> str:
    """Execute SQL query via docker and return result."""
    result = subprocess.run([
        'sudo', 'docker', 'exec', 'reddarchiver-postgres',
        'psql', '-U', DB_USER, '-d', DB_NAME, '-t', '-c', sql
    ], capture_output=True, text=True)
    return result.stdout.strip()


def main():
    print("Generating Voat Archive Report...")

    report = []
    report.append("# Voat Archive Statistics Report")
    report.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    report.append("\n---\n")

    # Overall statistics
    report.append("## Overall Statistics\n")

    stats = query_db("""
        SELECT
            COUNT(DISTINCT id) as posts,
            COUNT(DISTINCT subreddit) as subverses,
            COUNT(DISTINCT author) as authors,
            MIN(created_utc) as earliest,
            MAX(created_utc) as latest
        FROM posts
        WHERE platform = 'voat';
    """)

    if stats:
        parts = [p.strip() for p in stats.split('|')]
        if len(parts) >= 5:
            report.append(f"- **Total Posts**: {int(parts[0]):,}")
            report.append(f"- **Total Subverses**: {int(parts[1]):,}")
            report.append(f"- **Total Authors**: {int(parts[2]):,}")
            report.append(f"- **Date Range**: {datetime.fromtimestamp(int(parts[3])).strftime('%Y-%m-%d')} to {datetime.fromtimestamp(int(parts[4])).strftime('%Y-%m-%d')}")

    # Comment statistics
    comment_stats = query_db("""
        SELECT
            COUNT(DISTINCT id) as comments,
            COUNT(DISTINCT author) as comment_authors
        FROM comments
        WHERE platform = 'voat';
    """)

    if comment_stats:
        parts = [p.strip() for p in comment_stats.split('|')]
        if len(parts) >= 2:
            report.append(f"- **Total Comments**: {int(parts[0]):,}")
            report.append(f"- **Comment Authors**: {int(parts[1]):,}")

    # Top subverses
    report.append("\n## Top 20 Subverses by Post Count\n")
    report.append("| Subverse | Posts | Comments | Top Score |")
    report.append("|----------|-------|----------|-----------|")

    top_subverses = query_db("""
        SELECT
            p.subreddit,
            COUNT(DISTINCT p.id) as posts,
            COUNT(DISTINCT c.id) as comments,
            MAX(p.score) as top_score
        FROM posts p
        LEFT JOIN comments c ON c.post_id = p.id AND c.platform = 'voat'
        WHERE p.platform = 'voat'
        GROUP BY p.subreddit
        ORDER BY posts DESC
        LIMIT 20;
    """)

    for line in top_subverses.split('\n'):
        if '|' in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 4:
                report.append(f"| {parts[0]} | {int(parts[1]):,} | {int(parts[2]):,} | {int(parts[3]):,} |")

    # Top posts
    report.append("\n## Top 20 Posts by Score\n")
    report.append("| Score | Subverse | Title | Author |")
    report.append("|-------|----------|-------|--------|")

    top_posts = query_db("""
        SELECT
            score,
            subreddit,
            LEFT(title, 80) as title,
            author
        FROM posts
        WHERE platform = 'voat'
        ORDER BY score DESC
        LIMIT 20;
    """)

    for line in top_posts.split('\n'):
        if '|' in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 4:
                report.append(f"| {parts[0]} | {parts[1]} | {parts[2]} | {parts[3]} |")

    # Most active authors
    report.append("\n## Top 20 Most Active Authors\n")
    report.append("| Author | Posts | Comments | Total Karma |")
    report.append("|--------|-------|----------|-------------|")

    top_authors = query_db("""
        SELECT
            p.author,
            COUNT(DISTINCT p.id) as posts,
            COUNT(DISTINCT c.id) as comments,
            SUM(p.score) as karma
        FROM posts p
        LEFT JOIN comments c ON c.author = p.author AND c.platform = 'voat'
        WHERE p.platform = 'voat'
          AND p.author NOT IN ('[deleted]', 'AutoModerator')
        GROUP BY p.author
        ORDER BY posts DESC
        LIMIT 20;
    """)

    for line in top_authors.split('\n'):
        if '|' in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 4:
                report.append(f"| {parts[0]} | {int(parts[1]):,} | {int(parts[2]):,} | {int(parts[3]):,} |")

    # Content type breakdown
    report.append("\n## Content Type Breakdown\n")

    content_types = query_db("""
        SELECT
            CASE
                WHEN is_self THEN 'Text Posts'
                ELSE 'Link Posts'
            END as type,
            COUNT(*) as count
        FROM posts
        WHERE platform = 'voat'
        GROUP BY is_self;
    """)

    for line in content_types.split('\n'):
        if '|' in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 2:
                report.append(f"- **{parts[0]}**: {int(parts[1]):,}")

    # Top domains
    report.append("\n## Top 20 Linked Domains\n")
    report.append("| Domain | Link Count |")
    report.append("|--------|------------|")

    top_domains = query_db("""
        SELECT
            domain,
            COUNT(*) as links
        FROM posts
        WHERE platform = 'voat'
          AND domain != ''
          AND domain IS NOT NULL
        GROUP BY domain
        ORDER BY links DESC
        LIMIT 20;
    """)

    for line in top_domains.split('\n'):
        if '|' in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 2:
                report.append(f"| {parts[0]} | {int(parts[1]):,} |")

    # Monthly activity
    report.append("\n## Activity by Year\n")
    report.append("| Year | Posts | Comments |")
    report.append("|------|-------|----------|")

    yearly_activity = query_db("""
        SELECT
            EXTRACT(YEAR FROM to_timestamp(p.created_utc)) as year,
            COUNT(DISTINCT p.id) as posts,
            COUNT(DISTINCT c.id) as comments
        FROM posts p
        LEFT JOIN comments c ON c.post_id = p.id AND c.platform = 'voat'
        WHERE p.platform = 'voat'
        GROUP BY year
        ORDER BY year;
    """)

    for line in yearly_activity.split('\n'):
        if '|' in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 3:
                report.append(f"| {int(float(parts[0]))} | {int(parts[1]):,} | {int(parts[2]):,} |")

    # Collection statistics
    report.append("\n## Curated Collection Statistics\n")
    report.append("| Collection | Subverses | Posts | Comments | Authors |")
    report.append("|------------|-----------|-------|----------|---------|")

    collections = {
        'Technology & Programming': ['technology', 'Linux', 'programming', 'privacy', 'linuxgaming', 'techhell', 'cryptocurrency', 'technews', 'tech', 'BigTech', 'learnprogramming', 'techsupport', 'software'],
        'Gaming': ['gaming', 'gamingfringe', 'GamerGate', 'CoOpGaming', 'linuxgaming', 'pcmasterrace', 'gametrailers', 'VideoGameMusic', 'pcgaming', 'games', 'IndieGames', 'xboxone', 'GameDeals', 'Playstation4', 'Nintendo', 'videogames', 'retrogaming'],
        'News & Current Events': ['news', 'politics', 'worldnews', 'WorldNews', 'technews', 'TheNewsFeed', 'news24seven'],
        'Culture & Entertainment': ['videos', 'funny', 'music', 'Television', 'movies', 'Art', 'books'],
        'Science & Education': ['science', 'space', 'askscience', 'Physics', 'biology', 'chemistry']
    }

    for name, subverses in collections.items():
        subverse_list = "', '".join(subverses)
        stats = query_db(f"""
            SELECT
                COUNT(DISTINCT p.id) as posts,
                COUNT(DISTINCT c.id) as comments,
                COUNT(DISTINCT p.author) as authors
            FROM posts p
            LEFT JOIN comments c ON c.post_id = p.id AND c.platform = 'voat'
            WHERE p.platform = 'voat'
              AND p.subreddit IN ('{subverse_list}');
        """)

        if stats:
            parts = [p.strip() for p in stats.split('|')]
            if len(parts) >= 3:
                report.append(f"| {name} | {len(subverses)} | {int(parts[0]):,} | {int(parts[1]):,} | {int(parts[2]):,} |")

    # Export options
    report.append("\n## Export Tools\n")
    report.append("\n### Per-Subverse Export\n")
    report.append("```bash")
    report.append("# Export single subverse")
    report.append("python tools/voat/export_subverse_sql.py --subverse retrogaming")
    report.append("")
    report.append("# Export top 10 subverses")
    report.append("python tools/voat/export_subverse_sql.py --top 10 --min-posts 100 --max-posts 5000")
    report.append("```\n")

    report.append("### Collection Export\n")
    report.append("```bash")
    report.append("# Export gaming collection")
    report.append("python tools/voat/export_voat_collections.py --collection gaming")
    report.append("")
    report.append("# Export all collections")
    report.append("python tools/voat/export_voat_collections.py --collection all")
    report.append("```\n")

    report.append("---\n")
    report.append("\n*Report generated by redd-archiver Voat statistics tool*")

    # Save report
    output_path = '/output/VOAT_ARCHIVE_REPORT.md'
    with open(output_path, 'w') as f:
        f.write('\n'.join(report))

    print(f"\n✓ Report saved to: {output_path}")

    # Also print to stdout
    print('\n' + '='*70)
    print('\n'.join(report))


if __name__ == '__main__':
    main()
