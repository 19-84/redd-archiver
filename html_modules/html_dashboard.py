# ABOUTME: Dashboard and index system module for red-arch with Jinja2 templates
# ABOUTME: Handles index page generation using clean Jinja2 template system

import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from html_modules.html_utils import format_file_size, get_directory_size
from html_modules.html_seo import (
    generate_index_seo_title, generate_index_meta_description,
    generate_index_keywords, generate_seo_assets,
    generate_canonical_and_og_url
)
from utils.console_output import print_info, print_warning


def write_index(postgres_db: 'PostgresDatabase', seo_config: Optional[Dict[str, Any]] = None,
               min_score: int = 0, min_comments: int = 0) -> bool:
    """
    Write the main index page with dashboard using Jinja2 templates.

    Queries statistics directly from PostgreSQL database, making it the single source of truth.

    Args:
        postgres_db: PostgresDatabase instance (required)
        seo_config: SEO configuration
        min_score: Minimum score filter (for display)
        min_comments: Minimum comments filter (for display)

    Returns:
        bool: True if successful, False otherwise
    """
    from html_modules.html_dashboard_jinja import write_index_jinja2
    return write_index_jinja2(postgres_db, seo_config, min_score, min_comments)


# Legacy f-string functions removed (2025-01-10)
#
# Previously this file contained:
# - generate_global_summary_html() - 148-line f-string (now global_summary.html template)
# - generate_subreddit_dashboard_card() - 314-line f-string (now dashboard_card.html template)
# Total: ~460 lines of f-string HTML eliminated
#
# Replacements:
# - Data preparation: dashboard_helpers.py
# - Jinja2 rendering: html_dashboard_jinja.py
# - Templates: templates_jinja2/pages/index.html and components/
#
# Benefits:
# - Separation of concerns (data vs presentation)
# - Maintainable templates (no f-strings)
# - Reusable logic (data prep functions)
# - 73% code reduction
