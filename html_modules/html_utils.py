#!/usr/bin/env python
"""
Utility functions module for red-arch.
Handles file sizes, validation, pagination, and other utility functions.
"""

import os
import math
from typing import Dict, List, Any
from html_modules.html_constants import removed_content_identifiers

def get_directory_size(directory: str) -> int:
    """Calculate total size of directory and all subdirectories"""
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(directory):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                if os.path.exists(filepath):
                    total_size += os.path.getsize(filepath)
    except OSError:
        pass
    return total_size

def format_file_size(size_bytes: int) -> str:
    """Convert bytes to human readable format"""
    # Handle edge cases that would cause math domain errors
    if size_bytes <= 0:
        return "0 B"
    
    try:
        size_names = ["B", "KB", "MB", "GB"]
        i = int(math.floor(math.log(size_bytes, 1024)))
        # Ensure i is within valid range
        i = max(0, min(i, len(size_names) - 1))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 1)
        return f"{s} {size_names[i]}"
    except (ValueError, OverflowError, ZeroDivisionError) as e:
        # Fallback for any mathematical errors
        return f"{size_bytes} B"

def validate_link(link: Dict[str, Any], min_score: int = 0, min_comments: int = 0) -> bool:
    """Validate if a link meets the filtering criteria"""
    if not link:
        return False
    elif not 'id' in link.keys():
        return False
    # Apply OR logic: pass if EITHER condition is met (high score OR high comments)
    # This keeps both highly-scored posts with few comments AND highly-discussed posts with lower scores
    if min_score > 0 and min_comments > 0:
        if int(link['score']) < min_score and int(link['num_comments']) < min_comments:
            return False
    else:
        if min_score > 0 and int(link['score']) < min_score:
            return False
        if min_comments > 0 and int(link['num_comments']) < min_comments:
            return False

    return True

def get_subs() -> List[str]:
    """Get list of subreddits from data directory"""
    subs = []
    if not os.path.isdir('data'):
        print('ERROR: no data, run fetch_links.py first')
        return subs
    for d in os.listdir('data'):
        if os.path.isdir('data' + '/' + d):
            subs.append(d.lower())
    return subs

def get_pager_html(page_num: int = 1, pages: int = 1) -> str:
    """Generate pagination HTML"""
    from html_modules.html_constants import pager_skip
    from html_modules.html_templates import load_all_templates
    
    # Get templates
    templates = load_all_templates()
    template_index_pager_link = templates['index_pager_link']
    template_index_pager_link_disabled = templates['index_pager_link_disabled']
    
    html_pager = ''

    # First page (<<<)
    css = 'first-page'
    is_disabled = page_num == 1
    if is_disabled:
        css += ' disabled'
    url = 'index.html'
    template = template_index_pager_link_disabled if is_disabled else template_index_pager_link
    html_pager += template.replace('#URL#', url).replace('#TEXT#', '&lsaquo;&lsaquo;&lsaquo;').replace('#CSS_CLASS#', css)
    
    # Skip back 10 pages (<<)
    css = 'skip-back'
    is_disabled = page_num == 1
    if is_disabled:
        css += ' disabled'
    prev_skip = max(1, page_num - pager_skip)
    url = 'index.html' if prev_skip == 1 else f'index-{prev_skip}.html'
    template = template_index_pager_link_disabled if is_disabled else template_index_pager_link
    html_pager += template.replace('#URL#', url).replace('#TEXT#', '&lsaquo;&lsaquo;').replace('#CSS_CLASS#', css)
    
    # Previous page (<)
    css = 'prev-page'
    is_disabled = page_num == 1
    if is_disabled:
        css += ' disabled'
    prev_page = page_num - 1
    url = 'index.html' if prev_page == 1 else f'index-{prev_page}.html'
    template = template_index_pager_link_disabled if is_disabled else template_index_pager_link
    html_pager += template.replace('#URL#', url).replace('#TEXT#', '&lsaquo;').replace('#CSS_CLASS#', css)

    # Three numbered page buttons (prev, current, next)
    # Calculate the 3-page window centered on current page
    if page_num == 1:
        # At start: show 1, 2, 3
        page_range = [1, 2, 3]
    elif page_num == pages:
        # At end: show (n-2), (n-1), n
        page_range = [max(1, pages-2), max(1, pages-1), pages]
    else:
        # In middle: show (current-1), current, (current+1)
        page_range = [page_num-1, page_num, page_num+1]
    
    # Only show pages that exist
    page_range = [p for p in page_range if 1 <= p <= pages]
    
    # Remove duplicates and sort
    page_range = sorted(list(set(page_range)))
    
    # Ensure we have exactly 3 pages when possible
    if len(page_range) < 3 and pages >= 3:
        if page_num <= 2:
            page_range = [1, 2, 3]
        elif page_num >= pages - 1:
            page_range = [pages-2, pages-1, pages]
    
    for p in page_range:
        if p <= pages:  # Safety check
            css = 'active' if p == page_num else ''
            url = 'index.html' if p == 1 else f'index-{p}.html'
            # Numbered pages are never disabled, always use regular template
            html_pager += template_index_pager_link.replace('#URL#', url).replace('#TEXT#', str(p)).replace('#CSS_CLASS#', css)

    # Next page (>)
    css = 'next-page'
    is_disabled = page_num == pages
    if is_disabled:
        css += ' disabled'
    next_page = page_num + 1
    url = f'index-{next_page}.html' if next_page <= pages else f'index-{pages}.html'
    template = template_index_pager_link_disabled if is_disabled else template_index_pager_link
    html_pager += template.replace('#URL#', url).replace('#TEXT#', '&rsaquo;').replace('#CSS_CLASS#', css)
    
    # Skip forward 10 pages (>>)
    css = 'skip-forward'
    is_disabled = page_num == pages
    if is_disabled:
        css += ' disabled'
    next_skip = min(pages, page_num + pager_skip)
    url = 'index.html' if next_skip == 1 else f'index-{next_skip}.html'
    template = template_index_pager_link_disabled if is_disabled else template_index_pager_link
    html_pager += template.replace('#URL#', url).replace('#TEXT#', '&rsaquo;&rsaquo;').replace('#CSS_CLASS#', css)

    # Last page (>>>)
    css = 'last-page'
    is_disabled = page_num == pages
    if is_disabled:
        css += ' disabled'
    url = 'index.html' if pages == 1 else f'index-{pages}.html'
    template = template_index_pager_link_disabled if is_disabled else template_index_pager_link
    html_pager += template.replace('#URL#', url).replace('#TEXT#', '&rsaquo;&rsaquo;&rsaquo;').replace('#CSS_CLASS#', css)

    return html_pager
