#!/usr/bin/env python
"""
ABOUTME: Constants and configuration for Redd-Archiver HTML generation
ABOUTME: Defines pagination, display settings, and content identifiers
"""

# Project info
url_project = 'https://github.com/19-84/redd-archiver'

# Pagination and display settings
links_per_page = 100
pager_skip = 10
pager_skip_long = 100
max_comment_depth = 8  # mostly for mobile, which might be silly

# Date range for filtering
from datetime import date, datetime, timedelta
start_date = date(2005, 1, 1)
end_date = datetime.today().date() + timedelta(days=1)

# Content identifiers for deleted/removed content (be specific to avoid false positives)
removed_content_identifiers = ['[deleted]', '[removed]']

# Default sort type
default_sort = 'score'

# Sort configuration
sort_indexes = {
    'score': {
        'default': 1,
        'slug': 'score'
    },
    'num_comments': {
        'default': 0,
        'slug': 'comments',
    },
    'created_utc': {
        'default': 1000198000,
        'slug': 'date',
    }
}

# Missing comment score label
missing_comment_score_label = 'n/a'
