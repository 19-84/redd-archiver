"""
HTML Modules Package for red-arch
This package contains all modularized components for HTML generation.
"""

# Import constants
from .html_constants import (
    url_project,
    links_per_page,
    pager_skip,
    pager_skip_long,
    max_comment_depth,
    start_date,
    end_date,
    removed_content_identifiers,
    default_sort,
    sort_indexes,
    missing_comment_score_label
)

# Import utility functions
from .html_utils import (
    get_directory_size,
    format_file_size,
    validate_link,
    get_subs,
    get_pager_html
)

# Import URL and domain processing
from .html_url import (
    extract_root_domain,
    generate_domain_display_and_hover,
    generate_date_hover
)

# Import scoring system
from .html_scoring import (
    get_score_badge_class_dynamic,
    calculate_score_ranges,
    get_score_badge_class_subreddit_global,
    calculate_subreddit_score_ranges
)

# Import template management
from .html_templates import (
    load_template,
    load_all_templates,
    replace_template_variables,
    chunks
)

# Import comment system
from .html_comments import (
    sort_comments,
    get_comment_tree_list,
    render_comment_tree,
    render_single_comment
)

# Import statistics
from .html_statistics import (
    calculate_real_engagement_metrics,
    calculate_real_user_distribution,
    count_deleted_content,
    calculate_subreddit_statistics,
    calculate_global_statistics,
    calculate_final_output_sizes
)

# Import SEO functions
from .html_seo import (
    clean_html_and_markdown,
    truncate_smart,
    extract_keywords,
    generate_post_meta_description,
    generate_subreddit_meta_description,
    generate_user_meta_description,
    generate_index_meta_description,
    generate_search_meta_description,
    generate_search_seo_title,
    generate_search_keywords,
    generate_website_structured_data,
    generate_discussion_forum_posting_structured_data,
    generate_person_structured_data,
    generate_chunked_sitemaps,
    generate_robots_txt,
    generate_index_seo_title,
    generate_user_seo_title,
    generate_subreddit_seo_title,
    generate_index_keywords,
    generate_user_keywords,
    generate_subreddit_keywords,
    generate_pagination_tags,
    generate_seo_assets,
    generate_canonical_and_og_url,
    get_fallback_description,
    # Database-backed SEO functions
    get_subreddit_stats_from_database,
    extract_keywords_from_database,
    get_post_urls_for_sitemap,
    generate_sitemap_from_database,
    generate_robots_txt_from_database,
    generate_post_meta_from_database,
    generate_subreddit_meta_from_database,
    generate_structured_data_from_database,
    generate_index_meta_from_database,
    generate_search_meta_from_database
)

# Import dashboard functions
from .html_dashboard import (
    write_index
    # generate_global_summary_html - removed (now using Jinja2 templates)
    # generate_subreddit_dashboard_card - removed (now using Jinja2 templates)
)

# Import page generation functions
from .html_pages import (
    write_subreddit_pages,
    write_link_page,
    write_subreddit_search_page,
    write_user_page
)

# Define what's available when using "from html_modules import *"
__all__ = [
    # Constants
    'url_project',
    'links_per_page',
    'pager_skip',
    'pager_skip_long',
    'max_comment_depth',
    'start_date',
    'end_date',
    'removed_content_identifiers',
    'default_sort',
    'sort_indexes',
    'missing_comment_score_label',
    
    # Utility functions
    'get_directory_size',
    'format_file_size',
    'validate_link',
    'get_subs',
    'get_pager_html',
    
    # URL and domain processing
    'extract_root_domain',
    'generate_domain_display_and_hover',
    'generate_date_hover',
    
    # Scoring system
    'get_score_badge_class_dynamic',
    'calculate_score_ranges',
    'get_score_badge_class_subreddit_global',
    'calculate_subreddit_score_ranges',
    
    # Template management
    'load_template',
    'load_all_templates',
    'replace_template_variables',
    'chunks',
    
    # Comment system
    'sort_comments',
    'get_comment_tree_list',
    'render_comment_tree',
    'render_single_comment',
    
    # Statistics
    'calculate_real_engagement_metrics',
    'calculate_real_user_distribution',
    'count_deleted_content',
    'calculate_subreddit_statistics',
    'calculate_global_statistics',
    'calculate_final_output_sizes',
    
    # SEO functions
    'clean_html_and_markdown',
    'truncate_smart',
    'extract_keywords',
    'generate_post_meta_description',
    'generate_subreddit_meta_description',
    'generate_user_meta_description',
    'generate_index_meta_description',
    'generate_search_meta_description',
    'generate_search_seo_title',
    'generate_search_keywords',
    'generate_website_structured_data',
    'generate_discussion_forum_posting_structured_data',
    'generate_person_structured_data',
    'generate_chunked_sitemaps',
    'generate_robots_txt',
    'generate_index_seo_title',
    'generate_user_seo_title',
    'generate_subreddit_seo_title',
    'generate_index_keywords',
    'generate_user_keywords',
    'generate_subreddit_keywords',
    'generate_pagination_tags',
    'generate_seo_assets',
    'generate_canonical_and_og_url',
    'get_fallback_description',
    # Database-backed SEO functions
    'get_subreddit_stats_from_database',
    'extract_keywords_from_database',
    'get_post_urls_for_sitemap',
    'generate_sitemap_from_database',
    'generate_robots_txt_from_database',
    'generate_post_meta_from_database',
    'generate_subreddit_meta_from_database',
    'generate_structured_data_from_database',
    'generate_index_meta_from_database',
    'generate_search_meta_from_database',
    
    # Dashboard functions
    'write_index',
    # 'generate_global_summary_html',  # Removed - now using Jinja2
    # 'generate_subreddit_dashboard_card',  # Removed - now using Jinja2
    
    # Page generation functions
    'write_subreddit_pages',
    'write_link_page',
    'write_subreddit_search_page',
    'write_user_page'
]
