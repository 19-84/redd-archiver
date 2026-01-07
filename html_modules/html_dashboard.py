# ABOUTME: Dashboard and index system module for red-arch with Jinja2 templates
# ABOUTME: Handles index page generation using clean Jinja2 template system

from typing import Any


def write_index(
    postgres_db: "PostgresDatabase", seo_config: dict[str, Any] | None = None, min_score: int = 0, min_comments: int = 0
) -> bool:
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
