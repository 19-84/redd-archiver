#!/usr/bin/env python
# ABOUTME: Flask search server for PostgreSQL full-text search with Google-style operators
# ABOUTME: Secure, Alpine-ready, with rate limiting and HTML rendering via Jinja2

import os
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

from flask import Flask, request, render_template, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from markupsafe import escape

from core.postgres_search import PostgresSearch, SearchQuery
from utils.search_operators import parse_search_operators, format_search_breadcrumb
from utils.console_output import print_error, print_info, print_success, print_warning
from utils.error_handling import format_user_error
from utils.input_validation import validator


# ============================================================================
# FLASK APPLICATION SETUP
# ============================================================================

app = Flask(__name__)

# Security configuration
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024  # 1MB max request size

# Enforce SECRET_KEY in production
if os.environ.get('FLASK_ENV') == 'production' and not os.environ.get('FLASK_SECRET_KEY'):
    raise ValueError(
        "FLASK_SECRET_KEY must be set in production! "
        "Generate with: python3 -c 'import secrets; print(secrets.token_urlsafe(32))'"
    )

# Site configuration
SITE_NAME = os.environ.get('REDDARCHIVER_SITE_NAME', 'Redd Archive')
PROJECT_URL = os.environ.get('REDDARCHIVER_PROJECT_URL', 'https://github.com/19-84/redd-archiver')

# CSRF protection configuration
# Note: Search uses GET method (inherently safe from CSRF), but we add
# CSRF protection for consistency and future POST endpoints
app.config['WTF_CSRF_ENABLED'] = True
app.config['WTF_CSRF_CHECK_DEFAULT'] = True
app.config['WTF_CSRF_METHODS'] = ['POST', 'PUT', 'PATCH', 'DELETE']  # Not GET
app.config['WTF_CSRF_TIME_LIMIT'] = None  # No expiry for tokens
csrf = CSRFProtect(app)

# Rate limiting configuration
# 30 requests per minute per IP (generous for search)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["30 per minute"],
    storage_uri="memory://"
)

# ============================================================================
# API REGISTRATION
# ============================================================================

# Register REST API v1 blueprint at /api/v1
from api import register_api, api_v1
register_api(app)

# Exempt API from CSRF protection (API uses CORS and rate limiting instead)
csrf.exempt(api_v1)

# ============================================================================
# GLOBAL SEARCH ENGINE (reused across all requests)
# ============================================================================

# Initialize search engine once at startup (not per-request)
# This reuses the database connection pool and avoids schema recreation
_search_engine = None

def get_search_engine():
    """Get or create global search engine instance."""
    global _search_engine
    if _search_engine is None:
        print_info("Initializing global search engine...")
        _search_engine = PostgresSearch()
        print_success("Search engine ready for requests")
    return _search_engine


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def sanitize_query(query: str) -> str:
    """
    Sanitize search query for safety.

    Args:
        query: Raw query string

    Returns:
        Sanitized query (length-limited, stripped)
    """
    if not query:
        return ''

    # Strip whitespace
    query = query.strip()

    # Limit length to prevent abuse
    MAX_QUERY_LENGTH = 500
    if len(query) > MAX_QUERY_LENGTH:
        query = query[:MAX_QUERY_LENGTH]

    return query


def format_date(timestamp: int) -> str:
    """
    Format Unix timestamp to human-readable date.

    Args:
        timestamp: Unix timestamp

    Returns:
        Formatted date string (e.g., "2024-01-15")
    """
    try:
        dt = datetime.utcfromtimestamp(timestamp)
        return dt.strftime('%Y-%m-%d')
    except (ValueError, OSError):
        return 'Unknown date'


def format_relative_date(timestamp: int) -> str:
    """
    Format Unix timestamp to relative date (e.g., "2 days ago").

    Args:
        timestamp: Unix timestamp

    Returns:
        Relative date string
    """
    try:
        dt = datetime.utcfromtimestamp(timestamp)
        now = datetime.utcnow()
        delta = now - dt

        if delta.days > 365:
            years = delta.days // 365
            return f"{years} year{'s' if years > 1 else ''} ago"
        elif delta.days > 30:
            months = delta.days // 30
            return f"{months} month{'s' if months > 1 else ''} ago"
        elif delta.days > 0:
            return f"{delta.days} day{'s' if delta.days > 1 else ''} ago"
        elif delta.seconds > 3600:
            hours = delta.seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif delta.seconds > 60:
            minutes = delta.seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        else:
            return "just now"
    except (ValueError, OSError):
        return 'Unknown'


def get_score_badge_class(score: int) -> str:
    """
    Get Bootstrap badge class for score display.

    Args:
        score: Post/comment score

    Returns:
        CSS class name for badge
    """
    if score < 0:
        return 'badge-danger'
    elif score == 0:
        return 'badge-warning-orange'
    elif score < 10:
        return 'badge-warning'
    elif score < 100:
        return 'badge-light'
    elif score < 1000:
        return 'badge-success'
    else:
        return 'badge-success-bright'


# ============================================================================
# ROUTES
# ============================================================================

@app.route('/')
def index():
    """Redirect to search page."""
    return render_template('pages/search_form.html', site_name=SITE_NAME, url_project=PROJECT_URL)


@app.route('/search')
@limiter.limit("30 per minute")
def search():
    """
    Main search endpoint.

    Query parameters:
        q: Search query (with optional operators)
        page: Page number (default: 1)
        limit: Results per page (default: 25, max: 100)

    Returns:
        Rendered HTML with search results
    """
    # Get raw parameters
    raw_query = request.args.get('q', '').strip()
    raw_page = request.args.get('page', '1')
    raw_limit = request.args.get('limit', '25')

    # Convert pagination parameters to integers
    try:
        page = int(raw_page)
        limit = int(raw_limit)
    except (ValueError, TypeError):
        return render_template('pages/search_form.html',
                             error='Invalid pagination parameters',
                             site_name=SITE_NAME,
                             url_project=PROJECT_URL), 400

    # Parse search operators first (extracts filters from query text)
    parsed_query = parse_search_operators(raw_query)

    # Validate all parameters comprehensively
    # Use parsed query text (may be empty after operator extraction) or empty string
    # Don't fall back to raw_query as it includes operators we already extracted
    validation_result = validator.validate_all(
        query=parsed_query.query_text or '',
        subreddit=parsed_query.subreddit,
        author=parsed_query.author,
        min_score=parsed_query.min_score,
        limit=limit,
        page=page,
        result_type=parsed_query.result_type,
        sort_by=parsed_query.sort_by
    )

    # Check validation result
    if not validation_result.is_valid:
        error_messages = validation_result.get_error_messages()
        return render_template('pages/search_form.html',
                             error='; '.join(error_messages),
                             site_name=SITE_NAME,
                             url_project=PROJECT_URL), 400

    # Use sanitized values
    sanitized = validation_result.sanitized_values
    query_text = sanitized['query']
    offset = sanitized['offset']

    # Check if query is empty after operator extraction
    if not query_text or query_text.strip() == '':
        # User only provided operators (e.g., "sub:example" with no search terms)
        # Use wildcard search to show all results matching filters
        query_text = '*'

    # Build search query with validated/sanitized parameters
    search_query = SearchQuery(
        query_text=query_text,
        subreddit=sanitized['subreddit'],
        author=sanitized['author'],
        min_score=sanitized['min_score'],
        result_type=sanitized['result_type'],
        limit=sanitized['limit'],
        offset=sanitized['offset'],
        order_by=sanitized['sort_by']
    )

    # Execute search
    start_time = time.time()

    # DEBUG: Log search parameters
    print(f"[DEBUG] Executing search: query_text='{search_query.query_text}', subreddit={search_query.subreddit}, limit={search_query.limit}")

    try:
        search_engine = get_search_engine()
        results, total_count = search_engine.search(search_query)
        # Don't cleanup - reuse connection pool

        search_time = time.time() - start_time
        print(f"[DEBUG] Search returned: {len(results)} results, {total_count} total")

    except Exception as e:
        # Use safe error handler - prevents information disclosure
        safe_error = format_user_error(e, 'search')
        return render_template('pages/search_error.html',
                             error=safe_error,
                             query=raw_query,
                             site_name=SITE_NAME,
                             url_project=PROJECT_URL), 500

    # Format results for display
    formatted_results = []
    for result in results:
        formatted_result = {
            'type': result.result_type,
            'id': result.id,
            'subreddit': result.subreddit,
            'platform': result.platform,
            'author': result.author,
            'score': result.score,
            'score_badge_class': get_score_badge_class(result.score),
            'date': format_date(result.created_utc),
            'relative_date': format_relative_date(result.created_utc),
            'rank': result.rank,
        }

        if result.result_type == 'post':
            # Use permalink from database (preserves original case)
            permalink = result.permalink

            formatted_result.update({
                'title': result.title,
                'num_comments': result.num_comments,
                'permalink': permalink,
                'url': result.url,
                'is_self': result.selftext and result.selftext.strip() != '',
                'excerpt': result.headline or (result.selftext[:200] if result.selftext else ''),
            })
        else:  # comment
            # Fix permalink for comments - convert from /path/comment_id/ to /path/#comment_id
            # Comments don't have separate HTML files, they're anchored in post pages
            permalink = result.permalink
            if permalink and (permalink.startswith('/r/') or permalink.startswith('/v/') or permalink.startswith('/g/')):
                parts = permalink.split('/')

                # Platform-specific permalink handling
                if permalink.startswith('/r/'):
                    # Reddit: /r/sub/comments/post_id/slug/comment_id/
                    if len(parts) >= 7 and parts[-2]:
                        # Remove comment_id directory and trailing slash, use prefixed ID from database
                        permalink = '/'.join(parts[:-2]) + '/#comment-' + result.id
                    else:
                        permalink = '/'.join(parts)

                elif permalink.startswith('/v/'):
                    # Voat: /v/subverse/comments/post_id#raw_comment_id
                    if '#' in permalink:
                        # Replace raw anchor with prefixed format
                        post_part, raw_comment_id = permalink.split('#', 1)
                        permalink = post_part + '#comment-' + result.id
                    else:
                        permalink = permalink + '#comment-' + result.id

                elif permalink.startswith('/g/'):
                    # Ruqqus: /g/guild/post/post_id/slug/raw_comment_id
                    if len(parts) >= 6 and parts[-1]:
                        # Last part is raw comment ID, remove it and add as anchor with prefix
                        permalink = '/'.join(parts[:-1]) + '#comment-' + result.id
                    else:
                        permalink = '/'.join(parts) + '#comment-' + result.id

            formatted_result.update({
                'title': result.post_title or 'Comment',
                'body': result.body,
                'permalink': permalink,
                'post_id': result.post_id,
                'excerpt': result.headline or (result.body[:200] if result.body else ''),
            })

        formatted_results.append(formatted_result)

    # Calculate pagination
    total_pages = (total_count + limit - 1) // limit
    has_prev = page > 1
    has_next = page < total_pages

    # Generate breadcrumb
    breadcrumb = format_search_breadcrumb(parsed_query)

    # Render results
    return render_template('pages/search_results.html',
                         query=raw_query,
                         parsed_query=parsed_query,
                         breadcrumb=breadcrumb,
                         results=formatted_results,
                         total_count=total_count,
                         search_time=search_time,
                         page=page,
                         limit=limit,
                         total_pages=total_pages,
                         has_prev=has_prev,
                         has_next=has_next,
                         site_name=SITE_NAME,
                         url_project=PROJECT_URL)


@app.route('/health')
def health():
    """
    Health check endpoint for Docker.

    Returns:
        JSON with health status
    """
    try:
        # Test database connection
        search_engine = get_search_engine()
        health_ok = search_engine.db.health_check()
        # Don't cleanup - reuse connection pool

        if health_ok:
            return jsonify({
                'status': 'healthy',
                'database': 'connected',
                'timestamp': datetime.utcnow().isoformat()
            }), 200
        else:
            return jsonify({
                'status': 'unhealthy',
                'database': 'disconnected',
                'timestamp': datetime.utcnow().isoformat()
            }), 503

    except Exception as e:
        # Use safe error handler - don't expose exception details
        safe_error = format_user_error(e, 'healthcheck')
        return jsonify({
            'status': 'unhealthy',
            'error': 'Service unavailable',
            'timestamp': datetime.utcnow().isoformat()
        }), 503


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return render_template('pages/search_error.html',
                         error='Page not found',
                         query='',
                         site_name=SITE_NAME,
                         url_project=PROJECT_URL), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors with safe error messages."""
    # Log error internally but show generic message to user
    safe_error = format_user_error(error, 'server')
    return render_template('pages/search_error.html',
                         error='An internal error occurred. Please try again.',
                         query='',
                         site_name=SITE_NAME,
                         url_project=PROJECT_URL), 500


@app.errorhandler(429)
def rate_limit_exceeded(error):
    """Handle rate limit errors."""
    return render_template('pages/search_error.html',
                         error='Rate limit exceeded. Please wait a moment and try again.',
                         query='',
                         site_name=SITE_NAME,
                         url_project=PROJECT_URL), 429


@app.errorhandler(400)
def csrf_error(error):
    """Handle CSRF validation errors."""
    # Log the error but show generic message
    format_user_error(error, 'csrf')
    return render_template('pages/search_error.html',
                         error='Invalid request. Please refresh the page and try again.',
                         query='',
                         site_name=SITE_NAME,
                         url_project=PROJECT_URL), 400


# ============================================================================
# JINJA2 FILTERS
# ============================================================================

@app.template_filter('highlight')
def highlight_filter(text: str, query: str) -> str:
    """
    Highlight search terms in text (simple version).

    Args:
        text: Text to highlight
        query: Search query

    Returns:
        HTML with highlighted terms (already escaped)
    """
    if not text or not query:
        return escape(text)

    # Basic HTML escaping for now
    # Feature planned for v2.1: PostgreSQL ts_headline for advanced highlighting
    # See CHANGELOG.md roadmap for details
    return escape(text)


@app.template_filter('number_format')
def number_format_filter(value: int) -> str:
    """
    Format numbers with thousands separators (e.g., 1000 → "1,000").

    Args:
        value: Integer value to format

    Returns:
        Formatted string with comma separators
    """
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return str(value)


# ============================================================================
# GUNICORN HOOKS (pre-initialize search engine in each worker)
# ============================================================================

def on_starting(server):
    """Called just before the master process is initialized."""
    print_info("Gunicorn master process starting...")

def post_worker_init(worker):
    """Called just after a worker has been initialized.

    This ensures each Gunicorn worker pre-initializes the search engine
    before handling any requests, avoiding 3-second delay on first request.
    """
    print_info(f"Worker {worker.pid}: Pre-initializing search engine...")
    try:
        # Force initialization now instead of waiting for first request
        search_engine = get_search_engine()
        print_success(f"Worker {worker.pid}: Search engine ready")
    except Exception as e:
        print_error(f"Worker {worker.pid}: Failed to initialize search engine: {e}")


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    # Development server
    print_info("Starting Flask search server...")
    print_info("Access at: http://localhost:5000")
    print_info("Health check: http://localhost:5000/health")

    # Run with debug mode in development
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'

    app.run(
        host='0.0.0.0',
        port=5000,
        debug=debug_mode
    )
