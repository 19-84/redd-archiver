#!/usr/bin/env python
"""
URL and domain processing module for red-arch.
Handles domain extraction, link generation, and date hover functionality.
"""

from urllib.parse import urlparse
from datetime import datetime
from typing import Union, Any

def extract_root_domain(url: str) -> str:
    """Extract root domain from URL: https://www.example.com/path -> example.com"""
    if not url or not isinstance(url, str):
        return ''
    
    try:
        # Handle URLs without protocol
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        if not domain:
            return ''
        
        # Remove www. prefix for cleaner display
        if domain.startswith('www.'):
            domain = domain[4:]
        
        # Remove port numbers if present
        if ':' in domain:
            domain = domain.split(':')[0]
        
        return domain
    except Exception:
        return ''

def generate_domain_display_and_hover(url: str, is_self: Union[bool, str], subreddit: str) -> str:
    """Generate complete domain HTML with conditional linking"""
    if is_self is True or str(is_self).lower() == 'true':
        # Self-post: not clickable, just text
        return f'(self.{subreddit})'
    else:
        # External link: extract domain and create clickable link
        if not url or not url.strip():
            return ''
        
        root_domain = extract_root_domain(url)
        if root_domain:
            domain_text = f'({root_domain})'
            # Generate complete clickable link HTML
            return f'<a href="{url}" class="link-domain" title="{url}">{domain_text}</a>'
        else:
            return ''

def generate_date_hover(timestamp: Union[int, float, str]) -> str:
    """Generate date hover text: Monday, 15 January 2024, 14:30 UTC"""
    try:
        dt = datetime.utcfromtimestamp(int(timestamp))
        # Format: Monday, 15 January 2024, 14:30 UTC
        hover_text = dt.strftime('%A, %d %B %Y, %H:%M UTC')
        return f'title="{hover_text}"'
    except (ValueError, TypeError):
        return ''
