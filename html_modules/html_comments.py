#!/usr/bin/env python
"""
Comment system module for red-arch.
Handles comment threading, sorting, rendering, and hierarchical structure.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from html_modules.html_constants import removed_content_identifiers
from html_modules.html_url import generate_date_hover
from html_modules.html_scoring import calculate_score_ranges, get_score_badge_class_dynamic
from html_modules.html_templates import load_all_templates

def safe_int_conversion(value: Any, default_time: Optional[int] = None) -> int:
    """
    Safely convert various timestamp formats to integer.
    Handles: int, float, string (int format), string (float format)
    """
    if isinstance(value, int):
        return value
    elif isinstance(value, float):
        return int(value)
    elif isinstance(value, str):
        try:
            # Handle both integer and float string formats
            return int(float(value.strip()))
        except (ValueError, TypeError):
            pass

    # Fallback to default or current time
    if default_time is not None:
        return default_time
    import time
    return int(time.time())

def sort_comments(comments: List[Dict[str, Any]], hide_deleted_comments: bool = False) -> List[Dict[str, Any]]:
    """Sort comments with stickied first, then by score, handling orphaned comments"""
    sorted_comments = []
    if len(comments) == 0:
        return sorted_comments
    parent_map = {}
    id_map = {}
    top_level_comments = []
    link_id = comments[0]['link_id']
    depth = 0

    for c in comments:
        c['depth'] = depth
        id_map[c['id']] = c
        parent_map[c['id']] = c['parent_id']
        # add stickied comments (handle missing stickied field)
        if c.get('stickied', False) == True:
            sorted_comments.append(c)
        # store top level comments      
        elif c['parent_id'] == c['link_id']:
            top_level_comments.append(c)

    # sort non stickied top level comments
    if len(top_level_comments) > 0:
        top_level_comments = sorted(top_level_comments, key=lambda k: (int(k['score']) if isinstance(k['score'], str) and k['score'] != '' else k['score'] if isinstance(k['score'], int) else 1), reverse=True)
        sorted_comments += top_level_comments

    # add each top level comment's child comments
    sorted_linear_comments = []
    for c in sorted_comments:
        # only remove deleted comments if no children
        if hide_deleted_comments and c['body'] in removed_content_identifiers and 't1_' + c['id'] not in parent_map.values():
            pass
        else:
            sorted_linear_comments.append(c)
            child_comments = get_comment_tree_list([], depth + 1, c, id_map, parent_map, hide_deleted_comments)
            if len(child_comments) > 0:
                sorted_linear_comments += child_comments

    # add orphaned comments
    for c in comments:
        if c['parent_id'] != link_id and str(c['parent_id']).replace('t1_', '') not in id_map.keys():
            if hide_deleted_comments and c['body'] in removed_content_identifiers:
                continue
            sorted_linear_comments.append(c)

    # print('sort_comments() in %s out %s show deleted: %s' % (len(comments), len(sorted_comments), hide_deleted_comments))
    return sorted_linear_comments

def get_comment_tree_list(tree: List[Dict[str, Any]], depth: int, parent_comment: Dict[str, Any],
                         id_map: Dict[str, Dict[str, Any]], parent_map: Dict[str, str],
                         hide_deleted_comments: bool) -> List[Dict[str, Any]]:
    """Recursively build comment tree list"""
    parent_id = 't1_' + parent_comment['id']
    child_comments = []
    for key, value in parent_map.items():
        if value == parent_id:
            if hide_deleted_comments and id_map[key]['body'] in removed_content_identifiers and 't1_' + key not in parent_map.values():
                pass
            else:
                child_comments.append(id_map[key])

    # Sort children by score (note: sorting by child comment count would require
    # expensive recursive counting - current score-only sort is performant)
    if len(child_comments) > 0:
        child_comments = sorted(child_comments, key=lambda k: (int(k['score']) if isinstance(k['score'], str) and k['score'] != '' else k['score'] if isinstance(k['score'], int) else 1), reverse=True)
        for child_comment in child_comments:
            child_comment['depth'] = depth
            tree.append(child_comment)
            tree = get_comment_tree_list(tree, depth + 1, child_comment, id_map, parent_map, hide_deleted_comments)
    return tree

def render_comment_tree(comments: List[Dict[str, Any]], static_include_path: str, created: datetime,
                       score_ranges: Dict[str, float], op_author: str) -> str:
    """Render comments in hierarchical structure for CSS-only collapsing"""
    if not comments:
        return ''
    
    # Build comment lookup maps
    comment_map = {c['id']: c for c in comments}
    children_map = {}
    
    # Group comments by parent
    for comment in comments:
        parent_id = str(comment['parent_id'])
        if parent_id.startswith('t1_'):
            parent_id = parent_id.replace('t1_', '')
        if parent_id not in children_map:
            children_map[parent_id] = []
        children_map[parent_id].append(comment)
    
    # Find top-level comments (parent_id equals link_id)
    top_level_comments = []
    link_id = str(comments[0]['link_id']) if comments else ''
    
    for comment in comments:
        if str(comment['parent_id']) == link_id:
            top_level_comments.append(comment)
    
    # Sort top-level comments by score
    top_level_comments.sort(key=lambda c: int(c['score']) if isinstance(c['score'], str) and c['score'] != '' else c['score'] if isinstance(c['score'], int) else 0, reverse=True)
    
    # Render the comment tree
    html = ''
    for comment in top_level_comments:
        html += render_single_comment(comment, comment_map, children_map, static_include_path, created, score_ranges, op_author)
    
    return html

def render_single_comment(comment: Dict[str, Any], comment_map: Dict[str, Dict[str, Any]],
                         children_map: Dict[str, List[Dict[str, Any]]], static_include_path: str,
                         created: datetime, score_ranges: Dict[str, float], op_author: str) -> str:
    """Render a single comment and its children recursively"""
    from html_modules.html_constants import missing_comment_score_label
    
    # Get templates
    templates = load_all_templates()
    template_comment = templates['comment']
    template_user_url = templates['user_url']
    
    # Build CSS classes (removed ml-X classes - now using hierarchical structure)
    css_classes = ''
    if comment['author'] == op_author and comment['author'] not in removed_content_identifiers:
        css_classes += 'op'
    if comment.get('stickied', False) is True:
        css_classes += ' stickied' if css_classes else 'stickied'
    
    # Author link (no longer used in template but kept for compatibility)
    url = static_include_path + 'user/' + comment['author'] + '/'
    author_link_html = template_user_url.replace('###URL_AUTHOR###', url).replace('###AUTHOR###', comment['author'])
    
    # Render children
    children_html = ''
    comment_id = comment['id']
    if comment_id in children_map:
        child_comments = children_map[comment_id]
        # Sort children by score
        child_comments.sort(key=lambda c: int(c['score']) if isinstance(c['score'], str) and c['score'] != '' else c['score'] if isinstance(c['score'], int) else 0, reverse=True)
        for child in child_comments:
            children_html += render_single_comment(child, comment_map, children_map, static_include_path, created, score_ranges, op_author)
    
    # Generate date hover attribute for comment
    date_hover = generate_date_hover(comment['created_utc'])
    
    # Generate tooltips for comments
    score_tooltip = f'title="Comment score: {comment["score"]}"'
    
    # Generate enhanced author age tooltip
    from html_modules.html_pages import generate_enhanced_author_tooltip
    author_age_tooltip = generate_enhanced_author_tooltip(comment)
    
    # Enhanced fields processing for comments
    author_flair = comment.get('author_flair_text', '') or ''
    
    # Edit indicator
    edited_indicator = ''
    if comment.get('edited', False):
        if isinstance(comment['edited'], (int, float)) and comment['edited']:
            edit_time = datetime.utcfromtimestamp(safe_int_conversion(comment['edited'])).strftime('%d %b %Y %H:%M')
            edited_indicator = f'<span class="edited-marker" title="Edited {edit_time}">*</span>'
        else:
            edited_indicator = '<span class="edited-marker" title="Edited">*</span>'
    
    # Distinguished badge (mod/admin)
    distinguished_badge = ''
    if comment.get('distinguished') == 'moderator':
        distinguished_badge = '<span class="mod-badge" title="Moderator">[M]</span>'
    elif comment.get('distinguished') == 'admin':
        distinguished_badge = '<span class="mod-badge admin-badge" title="Admin">[A]</span>'
    
    # Original Poster indicator
    op_indicator = ''
    if comment['author'] == op_author and comment['author'] not in removed_content_identifiers:
        op_indicator = '<span class="op-badge" title="Original Poster">[OP]</span>'
    
    # Controversiality marker
    controversy_indicator = ''
    if comment.get('controversiality', 0) == 1:
        controversy_indicator = '<span class="controversy-marker" title="Controversial comment">⚡</span>'
    
    # Comment locking indicator
    locked_indicator = ''
    if comment.get('locked', False):
        locked_indicator = '<span class="comment-locked-icon" title="Comment locked">🔒</span>'
    
    # Rich award display for comments
    awards_indicator = ''
    all_awardings = comment.get('all_awardings', [])
    
    if all_awardings:
        # Process detailed award information
        award_icons = []
        award_counts = {'silver': 0, 'gold': 0, 'platinum': 0, 'other': 0}
        
        for award in all_awardings:
            award_id = award.get('id', '')
            award_name = award.get('name', '')
            award_count = award.get('count', 1)
            
            if award_id == 'gid_1' or 'silver' in award_name.lower():
                award_counts['silver'] += award_count
            elif award_id == 'gid_2' or 'gold' in award_name.lower():
                award_counts['gold'] += award_count
            elif award_id == 'gid_3' or 'platinum' in award_name.lower():
                award_counts['platinum'] += award_count
            else:
                award_counts['other'] += award_count
        
        # Generate award icons (smaller for comments)
        if award_counts['platinum'] > 0:
            count_text = f" {award_counts['platinum']}" if award_counts['platinum'] > 1 else ""
            award_icons.append(f'<span class="comment-award-platinum" title="{award_counts["platinum"]} Platinum award(s)">💎{count_text}</span>')
        
        if award_counts['gold'] > 0:
            count_text = f" {award_counts['gold']}" if award_counts['gold'] > 1 else ""
            award_icons.append(f'<span class="comment-award-gold" title="{award_counts["gold"]} Gold award(s)">🥇{count_text}</span>')
        
        if award_counts['silver'] > 0:
            count_text = f" {award_counts['silver']}" if award_counts['silver'] > 1 else ""
            award_icons.append(f'<span class="comment-award-silver" title="{award_counts["silver"]} Silver award(s)">🥈{count_text}</span>')
        
        if award_counts['other'] > 0:
            count_text = f" {award_counts['other']}" if award_counts['other'] > 1 else ""
            award_icons.append(f'<span class="comment-award-other" title="{award_counts["other"]} other award(s)">🏆{count_text}</span>')
        
        awards_indicator = ''.join(award_icons)
    
    elif comment.get('gilded', 0) > 0:
        # Fallback to gilded for older comments
        awards_indicator = f'<span class="comment-gilded-icon" title="{comment["gilded"]} gold awards">🥇</span>'
    
    # Add user flair display
    author_flair_display = ''
    if author_flair:
        author_flair_display = f'<span class="user-flair">{author_flair}</span>'
    
    # Replace template variables
    comment_data_map = {
        '###ID###':                 comment['id'],
        '###PARENT_ID###':          comment['parent_id'],
        '###DEPTH###':              str(comment['depth']),
        '###DATE###':               datetime.utcfromtimestamp(safe_int_conversion(comment['created_utc'])).strftime('%d %b %Y %H:%M'),
        '###DATE_HOVER###':         date_hover,
        '###SCORE###':              str(comment['score']) if len(str(comment['score'])) > 0 else missing_comment_score_label,
        '###BODY###':               comment['body'],
        '###CSS_CLASSES###':        css_classes,
        '###CLASS_SCORE###':        get_score_badge_class_dynamic(comment['score'], score_ranges),
        '###AUTHOR_NAME###':        comment['author'],
        '###HTML_AUTHOR_URL###':    author_link_html,
        '###COMMENT_CHILDREN###':   children_html,
        # Enhanced display fields
        '###AUTHOR_FLAIR###':       author_flair_display,
        '###DISTINGUISHED_BADGE###': distinguished_badge,
        '###EDITED_INDICATOR###':   edited_indicator,
        '###OP_INDICATOR###':       op_indicator,
        # Award display fields
        '###CONTROVERSY_INDICATOR###': controversy_indicator,
        '###AWARDS_INDICATOR###':   awards_indicator,
        # Comment locking
        '###LOCKED_INDICATOR###':   locked_indicator,
        # Tooltips for enhanced metadata
        '###SCORE_TOOLTIP###':      score_tooltip,
        '###AUTHOR_AGE_TOOLTIP###': author_age_tooltip,
    }
    
    comment_html = template_comment
    for key, value in comment_data_map.items():
        comment_html = comment_html.replace(key, str(value))
    
    return comment_html
