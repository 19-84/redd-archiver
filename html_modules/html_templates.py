#!/usr/bin/env python
"""
Template management module for red-arch.
Handles template loading, caching, and template variable replacement.
"""

import os

# Template cache
_template_cache = {}

# Get absolute path to templates directory (works regardless of current working directory)
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_MODULE_DIR)
_TEMPLATES_DIR = os.path.join(_PROJECT_ROOT, 'templates')

def load_template(template_path):
    """Load a template file and cache it using absolute paths.

    Args:
        template_path: Relative path to template (e.g., 'templates/index.html')

    Returns:
        Template content string

    Raises:
        FileNotFoundError: If template file does not exist
    """
    if template_path in _template_cache:
        return _template_cache[template_path]

    # Convert relative template path to absolute path
    # Handle both 'templates/index.html' and 'index.html' formats
    if template_path.startswith('templates/'):
        # Remove 'templates/' prefix and build absolute path
        template_name = template_path[len('templates/'):]
        absolute_path = os.path.join(_TEMPLATES_DIR, template_name)
    else:
        # Assume it's just the template name
        absolute_path = os.path.join(_TEMPLATES_DIR, template_path)

    # Load template using absolute path
    if os.path.exists(absolute_path):
        with open(absolute_path, 'r', encoding='utf-8') as file:
            content = file.read()
            _template_cache[template_path] = content
            return content

    # If not found, raise error with helpful message
    raise FileNotFoundError(f'Template not found: {template_path} (tried {absolute_path}, templates dir: {_TEMPLATES_DIR})')

def load_all_templates():
    """Load all templates at startup"""
    templates = {
        'index': load_template('templates/index.html'),
        'subreddit': load_template('templates/subreddit.html'),
        'link': load_template('templates/link.html'),
        'comment': load_template('templates/partial_comment.html'),
        'search': load_template('templates/search.html'),
        'user': load_template('templates/user.html'),
        'sub_link': load_template('templates/partial_menu_item.html'),
        'user_url': load_template('templates/partial_user.html'),
        'link_url': load_template('templates/partial_link.html'),
        'search_link': load_template('templates/partial_search_link.html'),
        'index_sub': load_template('templates/partial_index_subreddit.html'),
        'index_pager_link': load_template('templates/partial_subreddit_pager_link.html'),
        'index_pager_link_disabled': '<li class="page-item #CSS_CLASS#"><a class="page-link" href="#URL#" tabindex="-1">#TEXT#</a></li>',
        'selftext': load_template('templates/partial_link_selftext.html'),
        'user_page_link': load_template('templates/partial_user_link.html'),
        'user_page_comment': load_template('templates/partial_user_comment.html'),
        'url': load_template('templates/partial_url.html'),
    }
    return templates

def replace_template_variables(template, variables):
    """Replace ###VARIABLE### markers in template with values"""
    result = template
    for key, value in variables.items():
        result = result.replace(key, str(value))
    return result

def clear_template_cache():
    """Clear the template cache to free memory (called between subreddit processing)"""
    global _template_cache
    cache_size = len(_template_cache)
    _template_cache.clear()
    return cache_size

def get_cache_stats():
    """Get template cache statistics for memory monitoring"""
    return {
        'template_count': len(_template_cache),
        'template_names': list(_template_cache.keys())
    }

def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

