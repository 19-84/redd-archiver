#!/usr/bin/env python3
"""
Quick script to generate split_metadata.json from existing split files
"""
import sys
import re
from pathlib import Path
from datetime import datetime, timezone

try:
    import orjson
    def json_dumps(obj):
        return orjson.dumps(obj, option=orjson.OPT_INDENT_2).decode('utf-8')
except ImportError:
    import json
    def json_dumps(obj):
        return json.dumps(obj, indent=2)

def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_split_metadata.py <voat_split_dir>")
        sys.exit(1)

    split_dir = Path(sys.argv[1])
    submissions_dir = split_dir / 'submissions'
    comments_dir = split_dir / 'comments'

    if not split_dir.exists():
        print(f"Error: {split_dir} does not exist")
        sys.exit(1)

    print(f"Scanning {split_dir}...")

    # Scan submission files
    submission_files = list(submissions_dir.glob('*_submissions.sql.gz')) if submissions_dir.exists() else []
    comment_files = list(comments_dir.glob('*_comments.sql.gz')) if comments_dir.exists() else []

    # Extract subverse names
    subverses = {}

    for sub_file in submission_files:
        # Extract subverse name from filename (remove _submissions.sql.gz)
        name = sub_file.name.replace('_submissions.sql.gz', '')
        if name not in subverses:
            subverses[name] = {'name': name, 'posts': 0, 'comments': 0}
        subverses[name]['submission_file'] = f"submissions/{sub_file.name}"
        subverses[name]['submission_size_mb'] = round(sub_file.stat().st_size / 1024 / 1024, 2)

    for com_file in comment_files:
        # Extract subverse name from filename (remove _comments.sql.gz)
        name = com_file.name.replace('_comments.sql.gz', '')
        if name not in subverses:
            subverses[name] = {'name': name, 'posts': 0, 'comments': 0}
        subverses[name]['comment_file'] = f"comments/{com_file.name}"
        subverses[name]['comment_size_mb'] = round(com_file.stat().st_size / 1024 / 1024, 2)

    # Calculate totals
    for name, data in subverses.items():
        data['total_size_mb'] = round(
            data.get('submission_size_mb', 0) + data.get('comment_size_mb', 0),
            2
        )

    # Sort by name
    subverse_list = sorted(subverses.values(), key=lambda x: x['name'])

    # Calculate metadata
    total_size_mb = sum(s['total_size_mb'] for s in subverse_list)

    metadata = {
        'split_metadata': {
            'split_date': datetime.now(timezone.utc).isoformat(),
            'source_files': ['submission.sql.gz', 'comment.sql.gz', 'comment.sql.gz.0', 'comment.sql.gz.1'],
            'total_subverses': len(subverse_list),
            'total_posts': 'unknown',  # Would need to parse SQL files
            'total_comments': 'unknown',  # Would need to parse SQL files
            'total_size_mb': round(total_size_mb, 2),
            'processing_time_seconds': 'unknown',
            'processing_time_human': 'unknown',
            'errors': 0,
            'configuration': {
                'max_open_files': 100,
                'buffer_size': 200,
                'compression_level': 6,
                'skip_empty_subverses': False
            },
            'note': 'Metadata generated from existing split files'
        },
        'subverses': subverse_list
    }

    # Write metadata
    output_file = split_dir / 'split_metadata.json'
    with open(output_file, 'w') as f:
        f.write(json_dumps(metadata))

    print(f"✓ Generated {output_file}")
    print(f"  Total subverses: {len(subverse_list):,}")
    print(f"  Total size: {total_size_mb:.2f} MB ({total_size_mb/1024:.2f} GB)")
    print(f"  Submission files: {len(submission_files):,}")
    print(f"  Comment files: {len(comment_files):,}")

if __name__ == '__main__':
    main()
