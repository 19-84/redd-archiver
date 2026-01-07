#!/usr/bin/env python
"""
SEO and metadata generation module for red-arch.
Handles meta tags, sitemaps, structured data, and robots.txt generation.
"""

import re
import os
import json
import xml.etree.ElementTree as ET
from datetime import datetime
from html import unescape
from collections import Counter
from typing import Dict, List, Optional, Any, Tuple
from utils.console_output import print_info, print_error, print_success
from core.postgres_database import PostgresDatabase
from html_modules.platform_utils import get_url_prefix

# Module-level stop words set (created once, not recreated per function call)
# Using frozenset for immutability and O(1) lookup performance
_STOP_WORDS = frozenset({
    # Articles, prepositions, conjunctions
    'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
    'as', 'up', 'out', 'off', 'over', 'under', 'above', 'below', 'through', 'into',
    'onto', 'upon', 'across', 'along', 'around', 'behind', 'beside', 'between',
    'beyond', 'during', 'except', 'inside', 'outside', 'toward', 'towards', 'within',
    'without', 'against', 'among', 'beneath', 'throughout', 'underneath',

    # Pronouns
    'i', 'me', 'my', 'mine', 'myself', 'you', 'your', 'yours', 'yourself', 'he',
    'him', 'his', 'himself', 'she', 'her', 'hers', 'herself', 'it', 'its', 'itself',
    'we', 'us', 'our', 'ours', 'ourselves', 'they', 'them', 'their', 'theirs',
    'themselves', 'this', 'that', 'these', 'those', 'who', 'whom', 'whose', 'which',

    # Verbs (common)
    'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'having',
    'do', 'does', 'did', 'doing', 'will', 'would', 'could', 'should', 'may', 'might',
    'must', 'can', 'shall', 'ought', 'dare', 'need', 'used', 'get', 'got', 'getting',
    'go', 'goes', 'went', 'going', 'come', 'comes', 'came', 'coming', 'take', 'takes',
    'took', 'taking', 'make', 'makes', 'made', 'making', 'see', 'sees', 'saw', 'seeing',
    'know', 'knows', 'knew', 'knowing', 'think', 'thinks', 'thought', 'thinking',
    'want', 'wants', 'wanted', 'wanting', 'work', 'works', 'worked', 'working',
    'use', 'uses', 'used', 'using', 'find', 'finds', 'found', 'finding',

    # Question words and common adverbs
    'how', 'what', 'when', 'where', 'why', 'who', 'which', 'whose', 'whom',
    'here', 'there', 'now', 'then', 'today', 'yesterday', 'tomorrow', 'always',
    'never', 'often', 'sometimes', 'usually', 'rarely', 'seldom', 'frequently',
    'occasionally', 'generally', 'typically', 'normally', 'commonly', 'regularly',
    'constantly', 'continuously', 'immediately', 'instantly', 'quickly', 'slowly',
    'carefully', 'easily', 'hardly', 'nearly', 'almost', 'quite', 'rather', 'very',
    'too', 'so', 'such', 'much', 'many', 'more', 'most', 'less', 'least', 'few',
    'little', 'enough', 'several', 'some', 'any', 'all', 'both', 'each', 'every',
    'either', 'neither', 'none', 'no', 'not', 'yes',

    # Numbers and quantifiers
    'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten',
    'first', 'second', 'third', 'fourth', 'fifth', 'last', 'next', 'previous',
    'another', 'other', 'others', 'same', 'different', 'new', 'old', 'young',
    'big', 'small', 'large', 'little', 'long', 'short', 'high', 'low', 'wide',
    'narrow', 'thick', 'thin', 'heavy', 'light', 'strong', 'weak', 'fast', 'slow',
    'hot', 'cold', 'warm', 'cool', 'good', 'bad', 'best', 'worst', 'better', 'worse',
    'great', 'excellent', 'poor', 'fine', 'nice', 'beautiful', 'ugly', 'clean', 'dirty',
    'right', 'wrong', 'correct', 'incorrect', 'true', 'false', 'real', 'fake',
    'original', 'copy', 'main', 'major', 'minor', 'important', 'significant',
    'relevant', 'irrelevant', 'necessary', 'unnecessary', 'possible', 'impossible',
    'likely', 'unlikely', 'certain', 'uncertain', 'sure', 'unsure', 'clear', 'unclear',
    'obvious', 'hidden', 'visible', 'invisible', 'available', 'unavailable',
    'free', 'busy', 'open', 'closed', 'public', 'private', 'personal', 'professional',
    'official', 'unofficial', 'formal', 'informal', 'legal', 'illegal', 'valid', 'invalid',

    # Time and location
    'time', 'times', 'day', 'days', 'week', 'weeks', 'month', 'months', 'year', 'years',
    'hour', 'hours', 'minute', 'minutes', 'second', 'seconds', 'moment', 'moments',
    'period', 'periods', 'while', 'during', 'before', 'after', 'since', 'until',
    'place', 'places', 'location', 'locations', 'area', 'areas', 'region', 'regions',
    'country', 'countries', 'city', 'cities', 'town', 'towns', 'home', 'house',
    'office', 'building', 'room', 'rooms', 'space', 'spaces', 'site', 'sites',
    'page', 'pages', 'website', 'websites', 'link', 'links', 'url', 'urls',

    # Generic terms
    'thing', 'things', 'stuff', 'item', 'items', 'object', 'objects', 'part', 'parts',
    'piece', 'pieces', 'bit', 'bits', 'section', 'sections', 'portion', 'portions',
    'type', 'types', 'kind', 'kinds', 'sort', 'sorts', 'way', 'ways', 'method', 'methods',
    'means', 'approach', 'approaches', 'technique', 'techniques', 'process', 'processes',
    'procedure', 'procedures', 'step', 'steps', 'stage', 'stages', 'phase', 'phases',
    'level', 'levels', 'degree', 'degrees', 'amount', 'amounts', 'number', 'numbers',
    'quantity', 'quantities', 'size', 'sizes', 'length', 'lengths', 'width', 'widths',
    'height', 'heights', 'depth', 'depths', 'weight', 'weights', 'speed', 'speeds',
    'rate', 'rates', 'price', 'prices', 'cost', 'costs', 'value', 'values',
    'quality', 'qualities', 'feature', 'features', 'characteristic', 'characteristics',
    'property', 'properties', 'attribute', 'attributes', 'aspect', 'aspects',
    'element', 'elements', 'component', 'components', 'factor', 'factors',
    'detail', 'details', 'point', 'points', 'issue', 'issues', 'problem', 'problems',
    'solution', 'solutions', 'answer', 'answers', 'question', 'questions',
    'example', 'examples', 'case', 'cases', 'instance', 'instances', 'situation',
    'situations', 'condition', 'conditions', 'state', 'states', 'status', 'result',
    'results', 'outcome', 'outcomes', 'effect', 'effects', 'impact', 'impacts',
    'influence', 'influences', 'change', 'changes', 'difference', 'differences',
    'comparison', 'comparisons', 'relationship', 'relationships', 'connection',
    'connections', 'association', 'associations', 'interaction', 'interactions',

    # Reddit/forum specific
    'reddit', 'post', 'posts', 'comment', 'comments', 'discussion', 'discussions',
    'thread', 'threads', 'topic', 'topics', 'subreddit', 'subreddits', 'user', 'users',
    'member', 'members', 'community', 'communities', 'forum', 'forums', 'board', 'boards',
    'message', 'messages', 'reply', 'replies', 'response', 'responses', 'feedback',
    'opinion', 'opinions', 'view', 'views', 'thought', 'thoughts', 'idea', 'ideas',
    'suggestion', 'suggestions', 'recommendation', 'recommendations', 'advice',
    'tip', 'tips', 'help', 'support', 'assistance', 'guide', 'guides', 'tutorial',
    'tutorials', 'instruction', 'instructions', 'manual', 'manuals', 'documentation',
    'info', 'information', 'data', 'content', 'material', 'materials', 'resource',
    'resources', 'source', 'sources', 'reference', 'references', 'article', 'articles',
    'report', 'reports', 'news', 'update', 'updates', 'announcement', 'announcements',

    # Deleted/removed content indicators
    'deleted', 'removed', 'unavailable', 'missing', 'gone', 'lost', 'broken',

    # HTML/web artifacts
    'amp', 'html', 'www', 'http', 'https', 'com', 'org', 'net', 'edu', 'gov',
    'jpg', 'png', 'gif', 'pdf', 'doc', 'docx', 'txt', 'csv', 'xml', 'json'
})

# SEO Utility Functions
def clean_html_and_markdown(text: str) -> str:
    """Remove HTML tags, markdown formatting, and extra whitespace"""
    if not text:
        return ""
    
    # Remove markdown links [text](url)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # Remove markdown formatting **bold** *italic*
    text = re.sub(r'\*\*([^\*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^\*]+)\*', r'\1', text)
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Decode HTML entities
    text = unescape(text)
    # Clean up whitespace and newlines
    text = ' '.join(text.split())
    return text

def truncate_smart(text: str, max_length: int) -> str:
    """Truncate text at word boundary, add ellipsis if needed"""
    if len(text) <= max_length:
        return text
    
    # Find last space before max_length
    truncated = text[:max_length]
    last_space = truncated.rfind(' ')
    
    if last_space > max_length * 0.8:  # If space is reasonably close to end
        return text[:last_space] + "..."
    else:
        return text[:max_length-3] + "..."

def extract_keywords(title: str, content: str, subreddit: str) -> str:
    """Extract relevant keywords for meta keywords tag

    Uses module-level _STOP_WORDS frozenset for O(1) lookup performance.
    """
    if not title:
        title = ""
    if not content:
        content = ""

    # Combine title and content
    text = f"{title} {content}".lower()

    # Extract words and filter using module-level stop words (no set creation overhead)
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text)
    keywords = [word for word in words if word not in _STOP_WORDS]
    
    # Get most common keywords
    common_keywords = [word for word, count in Counter(keywords).most_common(10)]
    
    # Always include subreddit
    final_keywords = [subreddit] + common_keywords[:9]
    
    return ', '.join(final_keywords)

def generate_post_meta_description(post_data: Dict[str, Any], platform: str = 'reddit') -> str:
    """Generate meta description for individual post pages"""
    subreddit = post_data.get('subreddit', 'reddit')
    title = post_data.get('title', '')
    selftext = post_data.get('selftext', '')
    num_comments = post_data.get('num_comments', 0)
    url_prefix = get_url_prefix(platform)

    # Priority 1: Use selftext if available (self posts)
    if selftext and len(selftext.strip()) > 20:
        clean_text = clean_html_and_markdown(selftext)
        description = truncate_smart(clean_text, 140)
        return f"{description} - {url_prefix}/{subreddit}"

    # Priority 2: Use title + context for link posts
    else:
        title_truncated = truncate_smart(title, 100)
        return f"{title_truncated} - Discussion in {url_prefix}/{subreddit} with {num_comments} comments"

def generate_subreddit_meta_description(subreddit: str, sort_type: str, page_num: Any, total_posts: Any, platform: str = 'reddit') -> str:
    """Generate meta description for subreddit pages"""
    sort_descriptions = {
        'score': 'top-rated posts',
        'num_comments': 'most discussed posts',
        'created_utc': 'latest posts'
    }

    # Convert parameters to proper types to handle database floats/strings
    page_num = int(float(page_num)) if page_num is not None else 1
    total_posts = int(float(total_posts)) if total_posts is not None else 0

    url_prefix = get_url_prefix(platform)
    base = f"Browse {sort_descriptions.get(sort_type, 'posts')} from {url_prefix}/{subreddit}"
    stats = f"Archive contains {total_posts:,} posts"
    page_info = f" - Page {page_num}" if page_num > 1 else ""

    description = f"{base}. {stats}{page_info}"
    return truncate_smart(description, 160)

def generate_user_meta_description(username: str, post_count: int, top_subreddits: List[str], subreddit_platforms: Optional[Dict[str, str]] = None) -> str:
    """Generate meta description for user pages

    Args:
        username: Username
        post_count: Number of posts/comments
        top_subreddits: List of top subreddit names
        subreddit_platforms: Optional dict mapping subreddit name to platform (reddit/voat/ruqqus)
    """
    if not subreddit_platforms:
        subreddit_platforms = {}

    def get_community_text(sub: str) -> str:
        """Get platform-aware community prefix"""
        platform = subreddit_platforms.get(sub, 'reddit')
        prefix = get_url_prefix(platform)
        return f"{prefix}/{sub}"

    if post_count == 1:
        community_text = get_community_text(top_subreddits[0]) if top_subreddits else 'reddit'
        return f"View archived post by u/{username} in {community_text}"
    else:
        if len(top_subreddits) >= 3:
            subs_text = ", ".join(get_community_text(sub) for sub in top_subreddits[:3])
            return f"View {post_count} archived posts by u/{username} in {subs_text} and other subreddits"
        elif top_subreddits:
            subs_text = ", ".join(get_community_text(sub) for sub in top_subreddits)
            return f"View {post_count} archived posts by u/{username} in {subs_text}"
        else:
            return f"View {post_count} archived posts by u/{username}"

def generate_index_meta_description(subreddits_data: List[Dict[str, Any]], platform: str = 'reddit') -> str:
    """Generate meta description for index page"""
    if not subreddits_data:
        return "Multi-platform archive - Browse archived discussions and posts from multiple communities"

    # Fix: Access stats from correct nested structure (sub['stats']['archived_posts'])
    total_posts = sum(sub.get('stats', {}).get('archived_posts', 0) for sub in subreddits_data)
    subreddit_count = len(subreddits_data)

    # Get top 3 subreddit names with platform-aware prefixes
    top_subs_with_prefix = []
    for sub in subreddits_data[:3]:
        if sub.get('name'):
            sub_platform = sub.get('platform', 'reddit')
            sub_prefix = get_url_prefix(sub_platform)
            top_subs_with_prefix.append(f"{sub_prefix}/{sub['name']}")

    subs_text = ', '.join(top_subs_with_prefix)

    description = f"Multi-platform archive with {total_posts:,} posts across {subreddit_count} communities including {subs_text}"
    return truncate_smart(description, 160)

def generate_search_meta_description(subreddit: str, total_posts: int, total_comments: int) -> str:
    """Generate meta description for search pages"""
    return f"Search {total_posts:,} archived posts and {total_comments:,} comments in r/{subreddit}. Find discussions, solutions, and insights from the community archive."

def generate_search_seo_title(subreddit: str) -> str:
    """Generate SEO-optimized title for search pages"""
    return f"Search r/{subreddit} Archive - Find Discussions and Insights"

def generate_search_keywords(subreddit: str) -> str:
    """Generate keywords for search pages"""
    return f"{subreddit}, search, archive, reddit, discussions, find, posts, comments, community"

def generate_website_structured_data(site_name: str, base_url: str, subreddit: Optional[str] = None) -> str:
    """Generate WebSite structured data"""
    structured_data = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": site_name,
        "url": base_url,
        "description": f"Archive of Reddit discussions and posts from r/{subreddit}" if subreddit else "Archive of Reddit discussions and posts"
    }
    
    return f'<script type="application/ld+json">\n{json.dumps(structured_data, indent=2)}\n</script>'

def generate_discussion_forum_posting_structured_data(post_data: Dict[str, Any], base_url: str, subreddit: str, platform: str = 'reddit') -> str:
    """Generate DiscussionForumPosting structured data for individual posts"""
    url_prefix = get_url_prefix(platform)

    # Convert timestamp to ISO format
    created_date = datetime.utcfromtimestamp(int(post_data['created_utc']) if isinstance(post_data['created_utc'], str) else post_data['created_utc']).isoformat() + 'Z'

    structured_data = {
        "@context": "https://schema.org",
        "@type": "DiscussionForumPosting",
        "headline": post_data['title'],
        "author": {
            "@type": "Person",
            "name": post_data['author']
        },
        "datePublished": created_date,
        "interactionStatistic": {
            "@type": "InteractionCounter",
            "interactionType": "https://schema.org/CommentAction",
            "userInteractionCount": len(post_data.get('comments', []))
        },
        "isPartOf": {
            "@type": "WebSite",
            "name": f"{url_prefix}/{subreddit} Archive",
            "url": base_url
        }
    }
    
    # Handle different submission types
    is_self_post = post_data.get('is_self', False)
    if is_self_post is True or str(is_self_post).lower() == 'true':
        # Self post - include text content
        if post_data.get('selftext') and len(post_data['selftext'].strip()) > 0:
            clean_text = clean_html_and_markdown(post_data['selftext'])
            structured_data["text"] = truncate_smart(clean_text, 500)
    else:
        # Link post - include external URL reference
        external_url = post_data.get('url', '')
        if external_url and external_url.strip():
            structured_data["url"] = external_url
            structured_data["mentions"] = {
                "@type": "WebPage",
                "url": external_url
            }
    
    return f'<script type="application/ld+json">\n{json.dumps(structured_data, indent=2)}\n</script>'

def generate_person_structured_data(username: str, post_count: int, top_subreddits: List[str]) -> str:
    """Generate Person structured data for user pages"""
    description = f"Reddit user with {post_count} archived posts"
    if top_subreddits:
        subs_text = ", ".join(f"r/{sub}" for sub in top_subreddits[:3])
        description += f" in {subs_text}"
    
    structured_data = {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": username,
        "description": description,
        "identifier": f"u/{username}"
    }
    
    return f'<script type="application/ld+json">\n{json.dumps(structured_data, indent=2)}\n</script>'

def generate_chunked_sitemaps(processed_subs: List[Dict[str, Any]], user_index: Dict[str, Any],
                             seo_config: Optional[Dict[str, Any]] = None) -> bool:
    """Generate chunked XML sitemaps according to SEO best practices"""
    # SEO limits: 50k URLs per sitemap, 50MB file size
    # We'll use 45k as safety margin
    MAX_URLS_PER_SITEMAP = 45000
    
    # Get base URL from SEO config
    base_url = ''
    if seo_config and processed_subs:
        primary_subreddit = processed_subs[0]['name']
        seo_data = seo_config.get(primary_subreddit, {})
        base_url = seo_data.get('base_url', '').rstrip('/')
    
    current_date = datetime.now().strftime('%Y-%m-%d')
    sitemap_files = []
    
    # 1. Generate main sitemap (high-priority pages)
    main_sitemap = generate_main_sitemap(processed_subs, base_url, current_date)
    sitemap_files.append('sitemap-main.xml')
    
    # 2. Generate per-subreddit sitemaps (chunked if needed)
    for sub_data in processed_subs:
        subreddit = sub_data['name']
        subreddit_files = generate_subreddit_sitemaps(subreddit, sub_data, base_url, current_date, MAX_URLS_PER_SITEMAP)
        sitemap_files.extend(subreddit_files)
    
    # 3. Generate users sitemap (chunked if needed)
    if user_index:
        user_files = generate_users_sitemaps(user_index, base_url, current_date, MAX_URLS_PER_SITEMAP)
        sitemap_files.extend(user_files)
    
    # 4. Generate sitemap index
    generate_sitemap_index(sitemap_files, base_url, current_date)
    
    return True

def generate_main_sitemap(processed_subs: List[Dict[str, Any]], base_url: str, current_date: str) -> bool:
    """Generate main sitemap with high-priority pages"""
    urlset = ET.Element('urlset')
    urlset.set('xmlns', 'http://www.sitemaps.org/schemas/sitemap/0.9')
    
    # Add index page
    url_elem = ET.SubElement(urlset, 'url')
    ET.SubElement(url_elem, 'loc').text = f"{base_url}/" if base_url else ""
    ET.SubElement(url_elem, 'lastmod').text = current_date
    ET.SubElement(url_elem, 'changefreq').text = 'weekly'
    ET.SubElement(url_elem, 'priority').text = '1.0'
    
    # Import sort_indexes from constants module (will be created)
    from .html_constants import sort_indexes, default_sort
    
    # Add main subreddit pages (first page of each sort)
    for sub_data in processed_subs:
        subreddit = sub_data['name']
        platform = sub_data.get('platform', 'reddit')
        url_prefix = get_url_prefix(platform)

        for sort in sort_indexes.keys():
            sort_slug = sort_indexes[sort]['slug']

            url_elem = ET.SubElement(urlset, 'url')
            if sort == default_sort:
                loc = f"{base_url}/{url_prefix}/{subreddit}/" if base_url else f"{url_prefix}/{subreddit}/"
                priority = '0.9'
            else:
                loc = f"{base_url}/{url_prefix}/{subreddit}/index-{sort_slug}/" if base_url else f"{url_prefix}/{subreddit}/index-{sort_slug}/"
                priority = '0.8'
            
            ET.SubElement(url_elem, 'loc').text = loc
            ET.SubElement(url_elem, 'lastmod').text = current_date
            ET.SubElement(url_elem, 'changefreq').text = 'weekly'
            ET.SubElement(url_elem, 'priority').text = priority
    
    # Add global search page
    url_elem = ET.SubElement(urlset, 'url')
    loc = f"{base_url}/search" if base_url else "search"
    ET.SubElement(url_elem, 'loc').text = loc
    ET.SubElement(url_elem, 'lastmod').text = current_date
    ET.SubElement(url_elem, 'changefreq').text = 'monthly'
    ET.SubElement(url_elem, 'priority').text = '0.6'
    
    # Write main sitemap
    tree = ET.ElementTree(urlset)
    ET.indent(tree, space="  ", level=0)
    
    sitemap_path = 'sitemap-main.xml'
    
    # Check for resume mode before writing main sitemap
    if os.environ.get('ARCHIVE_RESUME_MODE') == 'true':
        print(f"RESUME MODE: Skipping main sitemap write to preserve existing files: {sitemap_path}")
        return True
        
    tree.write(sitemap_path, encoding='utf-8', xml_declaration=True)
    
    return True

def generate_subreddit_sitemaps(subreddit: str, sub_data: Dict[str, Any], base_url: str,
                               current_date: str, max_urls: int) -> List[str]:
    """Generate chunked sitemaps for a subreddit"""
    # Import needed constants
    from .html_constants import sort_indexes, default_sort, links_per_page

    platform = sub_data.get('platform', 'reddit')
    url_prefix = get_url_prefix(platform)

    sitemap_files = []
    urls_collected = []

    # Calculate pagination for this subreddit
    num_posts = sub_data['num_links']
    total_pages = max(1, (num_posts + links_per_page - 1) // links_per_page)

    # Collect all URLs for this subreddit (excluding main pages already in main sitemap)
    for sort in sort_indexes.keys():
        sort_slug = sort_indexes[sort]['slug']

        # Skip first page (already in main sitemap)
        for page_num in range(2, total_pages + 1):
            if sort == default_sort:
                loc = f"{base_url}/{url_prefix}/{subreddit}/index-{page_num}.html" if base_url else f"{url_prefix}/{subreddit}/index-{page_num}.html"
            else:
                loc = f"{base_url}/{url_prefix}/{subreddit}/index-{sort_slug}/index-{page_num}.html" if base_url else f"{url_prefix}/{subreddit}/index-{sort_slug}/index-{page_num}.html"
            
            urls_collected.append({
                'loc': loc,
                'lastmod': current_date,
                'changefreq': 'weekly',
                'priority': '0.7'
            })
    
    # Chunk URLs into multiple sitemaps if needed
    if len(urls_collected) == 0:
        return sitemap_files
    
    chunks = [urls_collected[i:i + max_urls] for i in range(0, len(urls_collected), max_urls)]
    
    for chunk_num, chunk in enumerate(chunks, 1):
        urlset = ET.Element('urlset')
        urlset.set('xmlns', 'http://www.sitemaps.org/schemas/sitemap/0.9')
        
        for url_data in chunk:
            url_elem = ET.SubElement(urlset, 'url')
            ET.SubElement(url_elem, 'loc').text = url_data['loc']
            ET.SubElement(url_elem, 'lastmod').text = url_data['lastmod']
            ET.SubElement(url_elem, 'changefreq').text = url_data['changefreq']
            ET.SubElement(url_elem, 'priority').text = url_data['priority']
        
        # Write chunked sitemap
        if len(chunks) == 1:
            filename = f'sitemap-subreddit-{subreddit}.xml'
        else:
            filename = f'sitemap-subreddit-{subreddit}-{chunk_num}.xml'
        
        tree = ET.ElementTree(urlset)
        ET.indent(tree, space="  ", level=0)
        
        sitemap_path = filename
        
        # Check for resume mode before writing subreddit sitemap
        if os.environ.get('ARCHIVE_RESUME_MODE') == 'true':
            print(f"RESUME MODE: Skipping subreddit sitemap write to preserve existing files: {sitemap_path}")
            sitemap_files.append(filename)  # Still track filename for consistency
            continue
            
        tree.write(sitemap_path, encoding='utf-8', xml_declaration=True)
        
        sitemap_files.append(filename)
    
    return sitemap_files

def generate_users_sitemaps(user_index: Dict[str, Any], base_url: str, current_date: str, max_urls: int) -> List[str]:
    """Generate chunked sitemaps for user pages"""
    sitemap_files = []
    urls_collected = []
    
    # Collect all user URLs
    for username in user_index.keys():
        loc = f"{base_url}/user/{username}/" if base_url else f"user/{username}/"
        urls_collected.append({
            'loc': loc,
            'lastmod': current_date,
            'changefreq': 'monthly',
            'priority': '0.5'
        })
    
    # Chunk URLs into multiple sitemaps if needed
    if len(urls_collected) == 0:
        return sitemap_files
    
    chunks = [urls_collected[i:i + max_urls] for i in range(0, len(urls_collected), max_urls)]
    
    for chunk_num, chunk in enumerate(chunks, 1):
        urlset = ET.Element('urlset')
        urlset.set('xmlns', 'http://www.sitemaps.org/schemas/sitemap/0.9')
        
        for url_data in chunk:
            url_elem = ET.SubElement(urlset, 'url')
            ET.SubElement(url_elem, 'loc').text = url_data['loc']
            ET.SubElement(url_elem, 'lastmod').text = url_data['lastmod']
            ET.SubElement(url_elem, 'changefreq').text = url_data['changefreq']
            ET.SubElement(url_elem, 'priority').text = url_data['priority']
        
        # Write chunked sitemap
        if len(chunks) == 1:
            filename = 'sitemap-users.xml'
        else:
            filename = f'sitemap-users-{chunk_num}.xml'
        
        tree = ET.ElementTree(urlset)
        ET.indent(tree, space="  ", level=0)
        
        sitemap_path = filename
        
        # Check for resume mode before writing users sitemap
        if os.environ.get('ARCHIVE_RESUME_MODE') == 'true':
            print(f"RESUME MODE: Skipping users sitemap write to preserve existing files: {sitemap_path}")
            sitemap_files.append(filename)  # Still track filename for consistency
            continue
            
        tree.write(sitemap_path, encoding='utf-8', xml_declaration=True)
        
        sitemap_files.append(filename)
    
    return sitemap_files

def generate_sitemap_index(sitemap_files: List[str], base_url: str, current_date: str) -> bool:
    """Generate sitemap index file"""
    sitemapindex = ET.Element('sitemapindex')
    sitemapindex.set('xmlns', 'http://www.sitemaps.org/schemas/sitemap/0.9')
    
    for filename in sitemap_files:
        sitemap_elem = ET.SubElement(sitemapindex, 'sitemap')
        loc = f"{base_url}/{filename}" if base_url else filename
        ET.SubElement(sitemap_elem, 'loc').text = loc
        ET.SubElement(sitemap_elem, 'lastmod').text = current_date
    
    # Write sitemap index
    tree = ET.ElementTree(sitemapindex)
    ET.indent(tree, space="  ", level=0)
    
    index_path = 'sitemap.xml'
    
    # Check for resume mode before writing sitemap index
    if os.environ.get('ARCHIVE_RESUME_MODE') == 'true':
        print(f"RESUME MODE: Skipping sitemap index write to preserve existing files: {index_path}")
        return True
        
    tree.write(index_path, encoding='utf-8', xml_declaration=True)
    
    return True

def generate_robots_txt(seo_config: Optional[Dict[str, Any]] = None,
                       processed_subs: Optional[List[Dict[str, Any]]] = None) -> bool:
    """Generate robots.txt file"""
    
    # Get base URL for sitemap reference (must be absolute URL per robots.txt spec)
    sitemap_line = ""

    if seo_config and processed_subs:
        primary_subreddit = processed_subs[0]['name'] if processed_subs else None
        if primary_subreddit:
            seo_data = seo_config.get(primary_subreddit, {})
            base_url = seo_data.get('base_url', '').rstrip('/')
            if base_url:
                sitemap_line = f"Sitemap: {base_url}/sitemap.xml\n"

    # If no base_url configured, comment out Sitemap directive
    if not sitemap_line:
        sitemap_line = "# Sitemap: https://example.com/sitemap.xml (configure base_url to enable)\n"

    robots_content = f"""User-agent: *
Allow: /

# Sitemap location
{sitemap_line}
# Optional: Crawl-delay for respectful crawling
# Crawl-delay: 1
"""
    
    robots_path = 'robots.txt'
    
    # Check for resume mode before writing robots.txt
    if os.environ.get('ARCHIVE_RESUME_MODE') == 'true':
        print(f"RESUME MODE: Skipping robots.txt write to preserve existing files: {robots_path}")
        return True
    
    with open(robots_path, 'w', encoding='utf-8') as file:
        file.write(robots_content)
    
    return True

def generate_index_seo_title(subreddits_data: List[Dict[str, Any]]) -> str:
    """Generate SEO-optimized title for index page"""
    if not subreddits_data:
        return "Redd Archive - Browse Archived Discussions"

    # Fix: Access stats from correct nested structure (sub['stats']['archived_posts'])
    total_posts = sum(sub.get('stats', {}).get('archived_posts', 0) for sub in subreddits_data)
    subreddit_count = len(subreddits_data)

    return f"Redd Archive - Browse {total_posts:,} Posts Across {subreddit_count} Communities"

def generate_user_seo_title(username: str, post_count: int, top_subreddits: List[str], subreddit_platforms: Optional[Dict[str, str]] = None) -> str:
    """Generate SEO-optimized title for user pages

    Args:
        username: Username
        post_count: Number of posts/comments
        top_subreddits: List of top subreddit names
        subreddit_platforms: Optional dict mapping subreddit name to platform (reddit/voat/ruqqus)
    """
    if not subreddit_platforms:
        subreddit_platforms = {}

    def get_community_text(sub: str) -> str:
        """Get platform-aware community prefix"""
        platform = subreddit_platforms.get(sub, 'reddit')
        prefix = get_url_prefix(platform)
        return f"{prefix}/{sub}"

    # Determine primary platform for "Archived X Posts" text
    primary_platform = subreddit_platforms.get(top_subreddits[0], 'reddit') if top_subreddits else 'reddit'
    platform_name = {'reddit': 'Reddit', 'voat': 'Voat', 'ruqqus': 'Ruqqus'}.get(primary_platform, 'Reddit')

    if post_count == 1:
        sub_text = f" in {get_community_text(top_subreddits[0])}" if top_subreddits else ""
        return f"u/{username} - Archived {platform_name} Post{sub_text}"
    else:
        if len(top_subreddits) >= 2:
            subs_text = f" in {get_community_text(top_subreddits[0])}, {get_community_text(top_subreddits[1])}"
            if len(top_subreddits) > 2:
                subs_text += f" and {len(top_subreddits)-2} more"
        elif top_subreddits:
            subs_text = f" in {get_community_text(top_subreddits[0])}"
        else:
            subs_text = ""

        # If multiple platforms, use generic "Posts" instead of platform-specific
        platforms_used = set(subreddit_platforms.get(sub, 'reddit') for sub in top_subreddits)
        if len(platforms_used) > 1:
            return f"u/{username} - {post_count} Archived Posts{subs_text}"
        else:
            return f"u/{username} - {post_count} Archived {platform_name} Posts{subs_text}"

def generate_subreddit_seo_title(subreddit: str, sort_type: str, page_num: Any, total_pages: Any, total_posts: Any, platform: str = 'reddit') -> str:
    """Generate SEO-optimized title for subreddit pages"""
    url_prefix = get_url_prefix(platform)

    sort_descriptions = {
        'score': 'Top Posts',
        'num_comments': 'Most Discussed Posts',
        'created_utc': 'Latest Posts'
    }

    # Convert parameters to proper types to handle database floats/strings
    page_num = int(float(page_num)) if page_num is not None else 1
    total_pages = int(float(total_pages)) if total_pages is not None else 1
    total_posts = int(float(total_posts)) if total_posts is not None else 0

    sort_text = sort_descriptions.get(sort_type, 'Posts')
    page_text = f" - Page {page_num} of {total_pages}" if total_pages > 1 else ""

    return f"{url_prefix}/{subreddit} - {sort_text} ({total_posts:,} Total){page_text}"

def generate_index_keywords(subreddits_data: List[Dict[str, Any]]) -> str:
    """Generate keywords for index page"""
    if not subreddits_data:
        return "reddit, archive, discussions, posts, comments"
    
    # Get top subreddit names
    top_subs = [sub.get('name', '') for sub in subreddits_data[:8] if sub.get('name')]
    keywords = ['reddit', 'archive', 'discussions', 'posts', 'comments'] + top_subs
    
    return ', '.join(keywords)

def generate_user_keywords(username: str, top_subreddits: List[str]) -> str:
    """Generate keywords for user pages"""
    keywords = ['reddit', 'user', 'posts', 'archive', username]
    if top_subreddits:
        keywords.extend(top_subreddits[:5])
    
    return ', '.join(keywords)

def generate_subreddit_keywords(subreddit: str, sort_type: str, top_post_titles: List[str]) -> str:
    """Generate keywords for subreddit pages based on content"""
    keywords = [subreddit, 'reddit', 'archive']
    
    # Add sort-specific keywords
    if sort_type == 'score':
        keywords.extend(['top', 'popular', 'best'])
    elif sort_type == 'num_comments':
        keywords.extend(['discussion', 'comments', 'active'])
    elif sort_type == 'created_utc':
        keywords.extend(['latest', 'recent', 'new'])
    
    # Extract keywords from top post titles
    if top_post_titles:
        combined_titles = ' '.join(top_post_titles[:10])  # Top 10 posts
        title_keywords = extract_keywords('', combined_titles, subreddit)
        # Remove subreddit name to avoid duplication
        title_keywords = title_keywords.replace(f'{subreddit}, ', '').replace(f', {subreddit}', '')
        if title_keywords:
            keywords.extend(title_keywords.split(', ')[:5])  # Top 5 content keywords
    
    return ', '.join(keywords[:12])  # Limit to 12 keywords

def generate_pagination_tags(page_num: int, total_pages: int, base_url: str, sort_type: str) -> str:
    """Generate rel=prev/next tags for paginated content"""
    tags = []
    
    if page_num > 1:
        # Previous page
        if page_num == 2:
            prev_url = f"{base_url}index.html"
        else:
            prev_url = f"{base_url}index-{page_num-1}.html"
        tags.append(f'<link rel="prev" href="{prev_url}">')
    
    if page_num < total_pages:
        # Next page
        next_url = f"{base_url}index-{page_num+1}.html"
        tags.append(f'<link rel="next" href="{next_url}">')
    
    return '\n    '.join(tags) if tags else ''

def generate_seo_assets(seo_config: Optional[Dict[str, Any]], subreddit: str, include_path: str) -> Tuple[str, str]:
    """Generate comprehensive favicon and og:image tags from SEO config"""
    og_image_tag = ''

    # Generate comprehensive favicon tags (default for all archives)
    # Includes support for: ICO (legacy), SVG (modern), Apple iOS, Android, PWA
    favicon_tags = f'''<link rel="icon" href="{include_path}static/favicon.ico" sizes="32x32">
    <link rel="icon" href="{include_path}static/favicon.svg" type="image/svg+xml">
    <link rel="apple-touch-icon" href="{include_path}static/apple-touch-icon.png">
    <link rel="manifest" href="{include_path}static/site.webmanifest">'''

    if seo_config and subreddit in seo_config:
        seo_data = seo_config[subreddit]

        # Override with custom favicon if specified in config
        if seo_data.get('favicon'):
            favicon_path = include_path + seo_data['favicon']
            # Custom favicon overrides defaults
            if seo_data['favicon'].endswith('.svg'):
                favicon_tags = f'<link rel="icon" href="{favicon_path}" type="image/svg+xml">'
            else:
                favicon_tags = f'<link rel="icon" href="{favicon_path}" sizes="any">'

        # Generate og:image tag
        if seo_data.get('og_image'):
            og_image_path = include_path + seo_data['og_image']
            if seo_data.get('base_url'):
                og_image_url = seo_data['base_url'].rstrip('/') + '/' + seo_data['og_image']
            else:
                og_image_url = og_image_path
            og_image_tag = f'<meta property="og:image" content="{og_image_url}">'

    return favicon_tags, og_image_tag

def generate_canonical_and_og_url(base_url: str, relative_path: str) -> Tuple[str, str]:
    """Generate canonical URL and og:url tags"""
    canonical_tag = ''
    og_url_tag = ''
    
    if base_url:
        full_url = base_url.rstrip('/') + '/' + relative_path.lstrip('/')
        canonical_tag = f'<link rel="canonical" href="{full_url}">'
        og_url_tag = f'<meta property="og:url" content="{full_url}">'
    
    return canonical_tag, og_url_tag

def get_fallback_description(page_type: str, basic_data: Dict[str, Any]) -> str:
    """Fallback descriptions when content extraction fails"""
    fallbacks = {
        'post': f"Discussion in r/{basic_data.get('subreddit', 'reddit')} - Archived subreddit post with comments",
        'subreddit': f"Browse archived posts from r/{basic_data.get('subreddit', 'reddit')} - Subreddit archive",
        'user': f"View archived subreddit posts by u/{basic_data.get('username', 'user')}",
        'index': "Redd Archive - Browse discussions and posts from multiple subreddits",
        'search': f"Search archived subreddit discussions in r/{basic_data.get('subreddit', 'reddit')}"
    }
    return fallbacks.get(page_type, "Redd Archive - Subreddit discussions and posts")

# Database-Backed SEO Functions

def get_subreddit_stats_from_database(postgres_db: 'PostgresDatabase') -> List[Dict[str, Any]]:
    """Get subreddit statistics from PostgreSQL database for SEO generation"""

    try:
        with postgres_db.pool.get_connection() as conn:
            from psycopg.rows import dict_row
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute("""
                    SELECT subreddit, COUNT(*) as num_links
                    FROM posts
                    GROUP BY subreddit
                    ORDER BY num_links DESC
                """)
                results = [{'name': row['subreddit'], 'num_links': row['num_links']} for row in cursor]

        print_info(f"Retrieved SEO statistics for {len(results)} subreddits from PostgreSQL")
        return results

    except Exception as e:
        print_error(f"Error retrieving subreddit statistics from PostgreSQL: {e}")
        return []

def extract_keywords_from_database(postgres_db: 'PostgresDatabase', subreddit: str, limit: int = 10) -> str:
    """Extract keywords from PostgreSQL database post titles and content for SEO meta tags"""

    try:
        with postgres_db.pool.get_connection() as conn:
            from psycopg.rows import dict_row
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute("""
                    SELECT title, selftext
                    FROM posts
                    WHERE subreddit = %s
                    ORDER BY score DESC
                    LIMIT %s
                """, (subreddit, limit * 2))

                combined_text = ""
                for row in cursor:
                    title = row['title'] or ''
                    selftext = row['selftext'] or ''
                    combined_text += f" {title} {selftext}"

        # Use existing keyword extraction function
        if combined_text.strip():
            return extract_keywords('', combined_text, subreddit)
        else:
            return f"{subreddit}, reddit, archive, posts, discussions"

    except Exception as e:
        print_error(f"Error extracting keywords from PostgreSQL: {e}")
        return f"{subreddit}, reddit, archive, posts, discussions"

def get_post_urls_for_sitemap(postgres_db: 'PostgresDatabase', subreddit: str, base_url: str, platform: str = 'reddit', limit: int = 1000) -> List[Dict[str, str]]:
    """Get post URLs from PostgreSQL database for sitemap generation"""
    url_prefix = get_url_prefix(platform)

    try:
        urls = []

        with postgres_db.pool.get_connection() as conn:
            from psycopg.rows import dict_row
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute("""
                    SELECT permalink, created_utc, score
                    FROM posts
                    WHERE subreddit = %s AND platform = %s
                    ORDER BY score DESC
                    LIMIT %s
                """, (subreddit, platform, limit))

                for row in cursor:
                    # Convert timestamp to ISO date
                    try:
                        created_date = datetime.utcfromtimestamp(int(row['created_utc'])).strftime('%Y-%m-%d')
                    except:
                        created_date = datetime.now().strftime('%Y-%m-%d')

                    # Calculate priority based on score (0.3-0.8 range)
                    score = row['score'] or 0
                    if score > 100:
                        priority = '0.8'
                    elif score > 50:
                        priority = '0.7'
                    elif score > 20:
                        priority = '0.6'
                    elif score > 5:
                        priority = '0.5'
                    else:
                        priority = '0.3'

                    # Build full URL from permalink
                    permalink = row['permalink'] or ''
                    if permalink.startswith(f'/{url_prefix}/'):
                        # Remove leading slash and build relative URL
                        relative_url = permalink[1:]  # Remove leading /
                        full_url = f"{base_url}/{relative_url}" if base_url else relative_url
                    else:
                        # Fallback URL construction
                        post_id = permalink.split('/')[-2] if '/' in permalink else permalink
                        relative_url = f"{url_prefix}/{subreddit}/comments/{post_id}/"
                        full_url = f"{base_url}/{relative_url}" if base_url else relative_url

                    urls.append({
                        'loc': full_url,
                        'lastmod': created_date,
                        'changefreq': 'monthly',
                        'priority': priority
                    })

        print_info(f"Retrieved {len(urls)} post URLs for sitemap from PostgreSQL")
        return urls

    except Exception as e:
        print_error(f"Error retrieving post URLs from PostgreSQL: {e}")
        return []

def generate_sitemap_from_database(postgres_db: 'PostgresDatabase', output_dir: str, seo_config: Optional[Dict] = None, max_urls_per_file: int = 45000) -> bool:
    """Generate complete sitemap system using PostgreSQL database queries"""
    try:
        # Get subreddit statistics from database
        processed_subs = get_subreddit_stats_from_database(postgres_db)

        if not processed_subs:
            print_info("No subreddits found in database, skipping sitemap generation")
            return True

        # Get base URL from SEO config - use global base_url or subreddit-specific
        base_url = ''
        if seo_config:
            # Try global base_url first
            base_url = seo_config.get('base_url', '')
            # Override with subreddit-specific if available
            if processed_subs:
                primary_subreddit = processed_subs[0]['name']
                seo_data = seo_config.get(primary_subreddit, {})
                base_url = seo_data.get('base_url', base_url)
            base_url = base_url.rstrip('/')

        current_date = datetime.now().strftime('%Y-%m-%d')
        sitemap_files = []

        # Generate main sitemap (high-priority pages)
        main_sitemap_success = generate_main_sitemap_from_database(processed_subs, base_url, current_date, output_dir)
        if main_sitemap_success:
            sitemap_files.append('sitemap-main.xml')

        # Generate post-level sitemaps for each subreddit (database-backed)
        for sub_data in processed_subs:
            subreddit = sub_data['name']
            post_files = generate_post_sitemaps_from_database(postgres_db, subreddit, base_url, current_date, output_dir, max_urls_per_file)
            sitemap_files.extend(post_files)

        # Generate users sitemap (empty for now, would be populated if user pages generated)
        user_index = {}  # Empty for now
        if user_index:
            user_files = generate_users_sitemaps(user_index, base_url, current_date, max_urls_per_file)
            sitemap_files.extend(user_files)

        # Generate sitemap index
        index_success = generate_sitemap_index(sitemap_files, base_url, current_date)

        if index_success:
            print_success(f"Generated database-backed sitemaps with {len(sitemap_files)} sitemap files")
            return True
        else:
            print_error("Failed to generate sitemap index")
            return False

    except Exception as e:
        print_error(f"Error in database-backed sitemap generation: {e}")
        return False

def generate_main_sitemap_from_database(processed_subs: List[Dict], base_url: str, current_date: str, output_dir: str) -> bool:
    """Generate main sitemap with high-priority pages using database statistics"""
    try:
        urlset = ET.Element('urlset')
        urlset.set('xmlns', 'http://www.sitemaps.org/schemas/sitemap/0.9')
        
        # Add index page
        url_elem = ET.SubElement(urlset, 'url')
        ET.SubElement(url_elem, 'loc').text = f"{base_url}/" if base_url else ""
        ET.SubElement(url_elem, 'lastmod').text = current_date
        ET.SubElement(url_elem, 'changefreq').text = 'weekly'
        ET.SubElement(url_elem, 'priority').text = '1.0'
        
        # Import sort_indexes from constants module if available
        try:
            from .html_constants import sort_indexes, default_sort
        except ImportError:
            # Fallback if constants not available
            sort_indexes = {
                'score': {'slug': 'score'},
                'created_utc': {'slug': 'date'},
                'num_comments': {'slug': 'comments'}
            }
            default_sort = 'score'
        
        # Add main subreddit pages (first page of each sort)
        for sub_data in processed_subs:
            subreddit = sub_data['name']
            
            for sort in sort_indexes.keys():
                sort_slug = sort_indexes[sort]['slug']
                
                url_elem = ET.SubElement(urlset, 'url')
                if sort == default_sort:
                    loc = f"{base_url}/r/{subreddit}/" if base_url else f"r/{subreddit}/"
                    priority = '0.9'
                else:
                    loc = f"{base_url}/r/{subreddit}/index-{sort_slug}/" if base_url else f"r/{subreddit}/index-{sort_slug}/"
                    priority = '0.8'
                
                ET.SubElement(url_elem, 'loc').text = loc
                ET.SubElement(url_elem, 'lastmod').text = current_date
                ET.SubElement(url_elem, 'changefreq').text = 'weekly'
                ET.SubElement(url_elem, 'priority').text = priority
        
        # Add global search page
        url_elem = ET.SubElement(urlset, 'url')
        loc = f"{base_url}/search" if base_url else "search"
        ET.SubElement(url_elem, 'loc').text = loc
        ET.SubElement(url_elem, 'lastmod').text = current_date
        ET.SubElement(url_elem, 'changefreq').text = 'monthly'
        ET.SubElement(url_elem, 'priority').text = '0.6'
        
        # Write main sitemap
        tree = ET.ElementTree(urlset)
        ET.indent(tree, space="  ", level=0)
        
        sitemap_path = os.path.join(output_dir, 'sitemap-main.xml')
        
        # Check for resume mode before writing main sitemap
        if os.environ.get('ARCHIVE_RESUME_MODE') == 'true':
            print_info(f"RESUME MODE: Skipping main sitemap write to preserve existing files: {sitemap_path}")
            return True
            
        tree.write(sitemap_path, encoding='utf-8', xml_declaration=True)
        print_info(f"Generated database-backed main sitemap: {sitemap_path}")
        
        return True
        
    except Exception as e:
        print_error(f"Error generating main sitemap from database: {e}")
        return False

def generate_post_sitemaps_from_database(postgres_db: 'PostgresDatabase', subreddit: str, base_url: str, current_date: str, output_dir: str, max_urls: int) -> List[str]:
    """Generate sitemaps for individual posts using PostgreSQL database queries"""
    sitemap_files = []

    try:
        # Get post URLs from database
        post_urls = get_post_urls_for_sitemap(postgres_db, subreddit, base_url, limit=max_urls * 2)  # Get more than we need
        
        if not post_urls:
            print_info(f"No post URLs found for {subreddit}, skipping post sitemap")
            return sitemap_files
        
        # Chunk URLs into multiple sitemaps if needed  
        chunks = [post_urls[i:i + max_urls] for i in range(0, len(post_urls), max_urls)]
        
        for chunk_num, chunk in enumerate(chunks, 1):
            urlset = ET.Element('urlset')
            urlset.set('xmlns', 'http://www.sitemaps.org/schemas/sitemap/0.9')
            
            for url_data in chunk:
                url_elem = ET.SubElement(urlset, 'url')
                ET.SubElement(url_elem, 'loc').text = url_data['loc']
                ET.SubElement(url_elem, 'lastmod').text = url_data['lastmod']
                ET.SubElement(url_elem, 'changefreq').text = url_data['changefreq']
                ET.SubElement(url_elem, 'priority').text = url_data['priority']
            
            # Write chunked sitemap
            if len(chunks) == 1:
                filename = f'sitemap-posts-{subreddit}.xml'
            else:
                filename = f'sitemap-posts-{subreddit}-{chunk_num}.xml'
            
            tree = ET.ElementTree(urlset)
            ET.indent(tree, space="  ", level=0)
            
            sitemap_path = os.path.join(output_dir, filename)
            
            # Check for resume mode before writing post sitemap
            if os.environ.get('ARCHIVE_RESUME_MODE') == 'true':
                print_info(f"RESUME MODE: Skipping post sitemap write to preserve existing files: {sitemap_path}")
                sitemap_files.append(filename)  # Still track filename for consistency
                continue
                
            tree.write(sitemap_path, encoding='utf-8', xml_declaration=True)
            sitemap_files.append(filename)
        
        if sitemap_files:
            print_info(f"Generated {len(sitemap_files)} database-backed post sitemaps for {subreddit}")
        
        return sitemap_files
        
    except Exception as e:
        print_error(f"Error generating post sitemaps for {subreddit} from database: {e}")
        return sitemap_files

def generate_robots_txt_from_database(postgres_db: 'PostgresDatabase', output_dir: str, seo_config: Optional[Dict] = None) -> bool:
    """Generate robots.txt using PostgreSQL database-derived subreddit information"""
    try:
        # Get subreddit statistics from database to determine primary subreddit
        processed_subs = get_subreddit_stats_from_database(postgres_db)
        
        # Get base URL for sitemap reference (must be absolute URL per robots.txt spec)
        sitemap_line = ""

        if seo_config:
            # Try global base_url first
            base_url = seo_config.get('base_url', '')
            # Override with subreddit-specific if available
            if processed_subs:
                primary_subreddit = processed_subs[0]['name']
                seo_data = seo_config.get(primary_subreddit, {})
                base_url = seo_data.get('base_url', base_url)
            base_url = base_url.rstrip('/')
            if base_url:
                sitemap_line = f"Sitemap: {base_url}/sitemap.xml\n"

        # If no base_url configured, comment out Sitemap directive
        if not sitemap_line:
            sitemap_line = "# Sitemap: https://example.com/sitemap.xml (configure base_url to enable)\n"

        robots_content = f"""User-agent: *
Allow: /

# Sitemap location
{sitemap_line}
# Optional: Crawl-delay for respectful crawling
# Crawl-delay: 1
"""
        
        robots_path = os.path.join(output_dir, 'robots.txt')
        
        # Check for resume mode before writing robots.txt
        if os.environ.get('ARCHIVE_RESUME_MODE') == 'true':
            print_info(f"RESUME MODE: Skipping robots.txt write to preserve existing files: {robots_path}")
            return True
        
        with open(robots_path, 'w', encoding='utf-8') as file:
            file.write(robots_content)
        
        print_info(f"Generated database-backed robots.txt: {robots_path}")
        return True
        
    except Exception as e:
        print_error(f"Error generating robots.txt from database: {e}")
        return False

def generate_post_meta_from_database(postgres_db: 'PostgresDatabase', post_id: str, subreddit: str) -> Dict[str, str]:
    """Generate meta tags for individual post pages using PostgreSQL database data"""

    try:
        with postgres_db.pool.get_connection() as conn:
            from psycopg.rows import dict_row
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute("""
                    SELECT title, selftext, author, num_comments, score, created_utc
                    FROM posts
                    WHERE id = %s AND subreddit = %s
                    LIMIT 1
                """, (post_id, subreddit))

                row = cursor.fetchone()

                if not row:
                    return {
                        'description': f"Reddit discussion in r/{subreddit} - Archived post with community comments",
                        'keywords': f"{subreddit}, reddit, archive, post, discussion",
                        'title': f"r/{subreddit} - Archived Post"
                    }

                # Generate meta description using existing function logic
                post_data = {
                    'title': row['title'] or '',
                    'selftext': row['selftext'] or '',
                    'subreddit': subreddit,
                    'num_comments': row['num_comments'] or 0
                }

                description = generate_post_meta_description(post_data)

                # Generate keywords from title and content
                title = row['title'] or ''
                selftext = row['selftext'] or ''
                keywords = extract_keywords(title, selftext, subreddit)

                # Generate title
                title_text = title[:60] + '...' if len(title) > 60 else title
                seo_title = f"{title_text} - r/{subreddit}"

                return {
                    'description': description,
                    'keywords': keywords,
                    'title': seo_title
                }

    except Exception as e:
        print_error(f"Error generating post meta from PostgreSQL: {e}")
        return {
            'description': f"Reddit discussion in r/{subreddit} - Archived post with community comments",
            'keywords': f"{subreddit}, reddit, archive, post, discussion",
            'title': f"r/{subreddit} - Archived Post"
        }

def generate_subreddit_meta_from_database(postgres_db: 'PostgresDatabase', subreddit: str, sort_type: str, page_num: int) -> Dict[str, str]:
    """Generate meta tags for subreddit pages using PostgreSQL database statistics"""

    try:
        with postgres_db.pool.get_connection() as conn:
            from psycopg.rows import dict_row
            with conn.cursor(row_factory=dict_row) as cursor:
                # Get total post count
                cursor.execute("SELECT COUNT(*) as total_posts FROM posts WHERE subreddit = %s", (subreddit,))
                total_posts = cursor.fetchone()['total_posts']

                # Get top post titles for keyword extraction
                cursor.execute("""
                    SELECT title
                    FROM posts
                    WHERE subreddit = %s
                    ORDER BY score DESC
                    LIMIT 10
                """, (subreddit,))
                top_titles = [row['title'] for row in cursor if row['title']]

        # Calculate total pages (assuming 50 posts per page)
        links_per_page = 50  # Default from constants
        total_pages = max(1, (total_posts + links_per_page - 1) // links_per_page)

        # Generate meta description
        description = generate_subreddit_meta_description(subreddit, sort_type, page_num, total_posts)

        # Generate keywords from top post titles
        keywords = generate_subreddit_keywords(subreddit, sort_type, top_titles)

        # Generate title
        title = generate_subreddit_seo_title(subreddit, sort_type, page_num, total_pages, total_posts)

        return {
            'description': description,
            'keywords': keywords,
            'title': title
        }

    except Exception as e:
        print_error(f"Error generating subreddit meta from PostgreSQL: {e}")
        return {
            'description': f"Browse archived posts from r/{subreddit} - Reddit community archive",
            'keywords': f"{subreddit}, reddit, archive, posts, discussions",
            'title': f"r/{subreddit} - Redd Archive"
        }

def generate_structured_data_from_database(postgres_db: 'PostgresDatabase', post_id: str, subreddit: str, base_url: str) -> str:
    """Generate JSON-LD structured data for individual posts using PostgreSQL database data"""

    try:
        with postgres_db.pool.get_connection() as conn:
            from psycopg.rows import dict_row
            with conn.cursor(row_factory=dict_row) as cursor:
                # Get post data for structured data generation
                cursor.execute("""
                    SELECT title, selftext, author, created_utc, score, url, is_self, permalink
                    FROM posts
                    WHERE id = %s AND subreddit = %s
                    LIMIT 1
                """, (post_id, subreddit))

                row = cursor.fetchone()

                if not row:
                    return ''

                # Get comment count for this post
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM comments
                    WHERE link_id = %s OR link_id = %s
                """, (post_id, f't3_{post_id}'))
                comment_result = cursor.fetchone()
                comment_count = comment_result['count'] if comment_result else 0

        # Create post data structure for existing function
        post_data = {
            'title': row['title'] or '',
            'selftext': row['selftext'] or '',
            'author': row['author'] or 'deleted',
            'created_utc': row['created_utc'] or 0,
            'url': row['url'] or '',
            'is_self': row['is_self'],
            'comments': [''] * comment_count  # Mock comment list for count
        }

        # Use existing structured data generation function
        return generate_discussion_forum_posting_structured_data(post_data, base_url, subreddit)

    except Exception as e:
        print_error(f"Error generating structured data from PostgreSQL: {e}")
        return ''

def generate_index_meta_from_database(postgres_db: 'PostgresDatabase') -> Dict[str, str]:
    """Generate meta tags for index page using PostgreSQL database statistics"""
    try:
        # Get subreddit statistics from database
        subreddits_data = get_subreddit_stats_from_database(postgres_db)
        
        if not subreddits_data:
            return {
                'description': "Reddit archive - Browse archived discussions and posts from multiple subreddits",
                'keywords': "reddit, archive, discussions, posts, comments",
                'title': "Redd Archive - Browse Archived Discussions"
            }
        
        # Use existing functions with database-derived data
        description = generate_index_meta_description(subreddits_data)
        keywords = generate_index_keywords(subreddits_data)
        title = generate_index_seo_title(subreddits_data)
        
        return {
            'description': description,
            'keywords': keywords,
            'title': title
        }
        
    except Exception as e:
        print_error(f"Error generating index meta from database: {e}")
        return {
            'description': "Reddit archive - Browse archived discussions and posts from multiple subreddits",
            'keywords': "reddit, archive, discussions, posts, comments",
            'title': "Redd Archive - Browse Archived Discussions"
        }

def generate_search_meta_from_database(postgres_db: 'PostgresDatabase', subreddit: str) -> Dict[str, str]:
    """Generate meta tags for search pages using PostgreSQL database statistics"""

    try:
        with postgres_db.pool.get_connection() as conn:
            from psycopg.rows import dict_row
            with conn.cursor(row_factory=dict_row) as cursor:
                # Get post count
                cursor.execute("SELECT COUNT(*) as count FROM posts WHERE subreddit = %s", (subreddit,))
                total_posts = cursor.fetchone()['count']

                # Get comment count
                cursor.execute("SELECT COUNT(*) as count FROM comments WHERE subreddit = %s", (subreddit,))
                total_comments = cursor.fetchone()['count']

        # Use existing functions
        description = generate_search_meta_description(subreddit, total_posts, total_comments)
        title = generate_search_seo_title(subreddit)
        keywords = generate_search_keywords(subreddit)

        return {
            'description': description,
            'keywords': keywords,
            'title': title
        }

    except Exception as e:
        print_error(f"Error generating search meta from PostgreSQL: {e}")
        return {
            'description': f"Search archived Reddit discussions in r/{subreddit}",
            'keywords': f"{subreddit}, search, archive, reddit, discussions",
            'title': f"Search r/{subreddit} Archive"
        }
