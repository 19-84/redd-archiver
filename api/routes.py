#!/usr/bin/env python
# ABOUTME: REST API route handlers with comprehensive endpoint coverage for Redd Archiver
# ABOUTME: Public API with CORS, rate limiting, pagination, and SQL injection protection

import os
import re
from datetime import datetime
from typing import Any

from flask import jsonify, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from core.postgres_database import PostgresDatabase
from core.postgres_search import PostgresSearch, SearchQuery
from utils.error_handling import format_user_error
from utils.input_validation import validator
from utils.search_operators import parse_search_operators

from . import api_v1

# ============================================================================
# CORS AND RATE LIMITING CONFIGURATION
# ============================================================================

# Enable CORS for all API routes (user confirmed: allow all origins)
CORS(api_v1, origins="*", methods=["GET", "OPTIONS"], allow_headers=["Content-Type"])

# Separate rate limiter for API (100 req/min vs 30 for search UI)
# Using remote address for simple IP-based rate limiting
api_limiter = Limiter(key_func=get_remote_address, default_limits=["100 per minute"], storage_uri="memory://")

# ============================================================================
# DATABASE CONNECTION (SINGLETON)
# ============================================================================

_db = None


def get_db() -> PostgresDatabase:
    """Get or create global PostgresDatabase instance for API requests."""
    global _db
    if _db is None:
        connection_string = os.environ.get("DATABASE_URL")
        if not connection_string:
            raise ValueError("DATABASE_URL environment variable not set")
        _db = PostgresDatabase(connection_string=connection_string, workload_type="api")
    return _db


# ============================================================================
# INSTANCE METADATA CONFIGURATION
# ============================================================================

# Instance metadata for /api/v1/stats endpoint (used by registry leaderboard)
INSTANCE_NAME = os.environ.get("REDDARCHIVER_SITE_NAME", "Redd Archive")
INSTANCE_DESCRIPTION = os.environ.get("REDDARCHIVER_SITE_DESCRIPTION")
CONTACT = os.environ.get("REDDARCHIVER_CONTACT")
TEAM_ID = os.environ.get("REDDARCHIVER_TEAM_ID")
DONATION_ADDRESS = os.environ.get("REDDARCHIVER_DONATION_ADDRESS")
BASE_URL = os.environ.get("REDDARCHIVER_BASE_URL")

# Tor detection configuration
# Note: Reads from public location (copied by Tor container, world-readable)
# Private keys remain secure in /var/lib/tor/hidden_service/ (700 permissions)
TOR_PUBLIC_HOSTNAME_FILE = "/app/tor-public/hostname"

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def detect_tor_onion_address() -> str | None:
    """
    Detect Tor onion address from public hostname file.

    The Tor container copies hostname to /var/lib/tor/public/ (world-readable)
    while keeping private keys secure in /var/lib/tor/hidden_service/ (700 permissions).

    Returns:
        str or None: Onion URL if Tor is configured and running, None otherwise

    Note: Silently handles missing files and errors since Tor is optional.
    """
    try:
        # Check if public hostname file exists
        if not os.path.exists(TOR_PUBLIC_HOSTNAME_FILE):
            return None

        # Read hostname from public location
        with open(TOR_PUBLIC_HOSTNAME_FILE) as f:
            hostname = f.read().strip()
            if hostname and hostname.endswith(".onion"):
                return f"http://{hostname}"

        return None

    except Exception:
        # Silently fail - Tor is optional
        # File might not exist, permission issue (rare), or I/O error
        return None


def get_enhanced_features() -> dict[str, bool]:
    """
    Get feature availability with runtime detection.

    Returns:
        dict: Feature flags (currently only Tor)
    """
    return {"tor": detect_tor_onion_address() is not None}


def get_instance_metadata() -> dict[str, str]:
    """
    Get instance-specific metadata for API response.

    Returns:
        dict: Instance metadata including name, description, contact, team_id, donation_address, base_url, tor_url
    """
    metadata = {"name": INSTANCE_NAME}

    # Optional fields (only include if configured)
    if INSTANCE_DESCRIPTION:
        metadata["description"] = INSTANCE_DESCRIPTION
    if CONTACT:
        metadata["contact"] = CONTACT
    if TEAM_ID:
        metadata["team_id"] = TEAM_ID
    if DONATION_ADDRESS:
        metadata["donation_address"] = DONATION_ADDRESS
    if BASE_URL:
        metadata["base_url"] = BASE_URL

    # Detect Tor (runtime) - handles permission errors gracefully
    tor_url = detect_tor_onion_address()
    if tor_url:
        metadata["tor_url"] = tor_url

    return metadata


def build_pagination_response(data: list[dict], page: int, limit: int, total: int, endpoint: str, **filters) -> dict:
    """
    Build standardized paginated API response.

    Args:
        data: List of result items
        page: Current page number
        limit: Results per page
        total: Total result count
        endpoint: API endpoint path (e.g., '/api/v1/posts')
        **filters: Additional query parameters to include in links

    Returns:
        Standardized pagination response dict
    """
    total_pages = (total + limit - 1) // limit if total > 0 else 1

    # Build query string from filters
    filter_params = []
    for key, value in filters.items():
        if value is not None:
            filter_params.append(f"{key}={value}")
    filter_string = "&".join(filter_params)
    filter_prefix = "?" + filter_string + "&" if filter_string else "?"

    return {
        "data": data,
        "meta": {"page": page, "limit": limit, "total": total, "total_pages": total_pages},
        "links": {
            "self": f"{endpoint}{filter_prefix}page={page}&limit={limit}",
            "next": f"{endpoint}{filter_prefix}page={page+1}&limit={limit}" if page < total_pages else None,
            "prev": f"{endpoint}{filter_prefix}page={page-1}&limit={limit}" if page > 1 else None,
            "first": f"{endpoint}{filter_prefix}page=1&limit={limit}",
            "last": f"{endpoint}{filter_prefix}page={total_pages}&limit={limit}",
        },
    }


def format_unix_timestamp(timestamp: int | None) -> str | None:
    """Convert Unix timestamp to ISO 8601 string."""
    if timestamp is None:
        return None
    try:
        return datetime.fromtimestamp(timestamp).isoformat() + "Z"
    except (ValueError, OSError):
        return None


# ============================================================================
# FIELD SELECTION AND TRUNCATION (MCP-optimized)
# ============================================================================

# Valid fields per resource type (used for field selection validation)
VALID_POST_FIELDS = {
    "id",
    "subreddit",
    "author",
    "title",
    "selftext",
    "url",
    "domain",
    "score",
    "num_comments",
    "created_utc",
    "created_at",
    "permalink",
    "is_self",
    "nsfw",
    "over_18",
    "locked",
    "stickied",
}

VALID_COMMENT_FIELDS = {
    "id",
    "post_id",
    "parent_id",
    "author",
    "body",
    "score",
    "created_utc",
    "created_at",
    "subreddit",
    "permalink",
    "depth",
    "body_length",
    "body_truncated",
    "body_full_length",
}

VALID_USER_FIELDS = {
    "username",
    "post_count",
    "comment_count",
    "total_activity",
    "total_karma",
    "first_seen_utc",
    "first_seen_at",
    "last_seen_utc",
    "last_seen_at",
    "subreddit_activity",
}

VALID_SUBREDDIT_FIELDS = {
    "name",
    "subreddit",
    "total_posts",
    "total_comments",
    "unique_users",
    "earliest_post",
    "latest_post",
    "avg_post_score",
    "avg_score",
    "is_banned",
    "archived_posts",
    "coverage_percentage",
    "comments",
    "users",
    "latest_date",
    "filters",
    "filtered_posts",
    "filtered_comments",
}


def parse_fields_param(fields_param: str | None) -> list[str]:
    """
    Parse comma-separated fields parameter.

    Args:
        fields_param: Comma-separated field names or None

    Returns:
        List of field names (empty list if None or empty)
    """
    if not fields_param:
        return []
    return [f.strip().lower() for f in fields_param.split(",") if f.strip()]


def validate_fields(requested_fields: list[str], valid_fields: set) -> str | None:
    """
    Validate requested fields against valid set.

    Args:
        requested_fields: List of requested field names
        valid_fields: Set of valid field names

    Returns:
        Error message if invalid fields found, None otherwise
    """
    if not requested_fields:
        return None

    # Normalize valid fields to lowercase for comparison
    valid_lower = {f.lower() for f in valid_fields}
    invalid = [f for f in requested_fields if f.lower() not in valid_lower]

    if invalid:
        return f"Invalid fields: {', '.join(invalid)}. Valid fields: {', '.join(sorted(valid_fields))}"

    return None


def filter_fields(data: dict, requested_fields: list[str], valid_fields: set) -> dict:
    """
    Filter response to only include requested fields.

    Args:
        data: Original data dictionary
        requested_fields: List of field names to include (empty = all fields)
        valid_fields: Set of valid field names for this resource type

    Returns:
        Filtered dictionary with only requested fields
    """
    if not requested_fields:
        return data  # Return all fields if none specified

    # Normalize to lowercase for matching
    requested_lower = {f.lower() for f in requested_fields}

    return {k: v for k, v in data.items() if k.lower() in requested_lower}


def apply_truncation(data: dict, max_body_length: int | None, body_field: str = "body") -> dict:
    """
    Apply truncation to body/selftext fields with metadata.

    Args:
        data: Data dictionary
        max_body_length: Maximum characters for body (None = no truncation)
        body_field: Name of body field ('body' for comments, 'selftext' for posts)

    Returns:
        Data with truncation applied and metadata added
    """
    if max_body_length is None or max_body_length <= 0:
        return data

    result = data.copy()
    body_content = result.get(body_field)

    if body_content and len(body_content) > max_body_length:
        result[body_field] = body_content[:max_body_length] + "..."
        result[f"{body_field}_truncated"] = True
        result[f"{body_field}_full_length"] = len(body_content)
    elif body_content:
        result[f"{body_field}_truncated"] = False
        result[f"{body_field}_full_length"] = len(body_content)

    return result


def get_truncation_params() -> tuple:
    """
    Extract truncation parameters from request.

    Returns:
        Tuple of (max_body_length, include_body)
    """
    max_body_length = request.args.get("max_body_length", type=int, default=None)
    include_body = request.args.get("include_body", type=str, default="true").lower() != "false"
    return max_body_length, include_body


def process_post_response(
    post: dict, requested_fields: list[str] = None, max_body_length: int = None, include_body: bool = True
) -> dict:
    """
    Process a post response with field selection and truncation.

    Args:
        post: Raw post data dictionary
        requested_fields: Fields to include (None = all)
        max_body_length: Max selftext length (None = no truncation)
        include_body: Whether to include selftext at all

    Returns:
        Processed post dictionary
    """
    result = post.copy()

    # Handle include_body=false
    if not include_body and "selftext" in result:
        result["selftext"] = None

    # Apply truncation to selftext
    if include_body and max_body_length:
        result = apply_truncation(result, max_body_length, "selftext")

    # Apply field selection
    if requested_fields:
        result = filter_fields(result, requested_fields, VALID_POST_FIELDS)

    return result


def process_comment_response(
    comment: dict, requested_fields: list[str] = None, max_body_length: int = None, include_body: bool = True
) -> dict:
    """
    Process a comment response with field selection and truncation.

    Args:
        comment: Raw comment data dictionary
        requested_fields: Fields to include (None = all)
        max_body_length: Max body length (None = no truncation)
        include_body: Whether to include body at all

    Returns:
        Processed comment dictionary
    """
    result = comment.copy()

    # Handle include_body=false
    if not include_body and "body" in result:
        result["body"] = None

    # Apply truncation to body
    if include_body and max_body_length:
        result = apply_truncation(result, max_body_length, "body")

    # Apply field selection
    if requested_fields:
        result = filter_fields(result, requested_fields, VALID_COMMENT_FIELDS)

    return result


def process_user_response(user: dict, requested_fields: list[str] = None) -> dict:
    """
    Process a user response with field selection.

    Args:
        user: Raw user data dictionary
        requested_fields: Fields to include (None = all)

    Returns:
        Processed user dictionary
    """
    if requested_fields:
        return filter_fields(user, requested_fields, VALID_USER_FIELDS)
    return user


def process_subreddit_response(subreddit: dict, requested_fields: list[str] = None) -> dict:
    """
    Process a subreddit response with field selection.

    Args:
        subreddit: Raw subreddit data dictionary
        requested_fields: Fields to include (None = all)

    Returns:
        Processed subreddit dictionary
    """
    if requested_fields:
        return filter_fields(subreddit, requested_fields, VALID_SUBREDDIT_FIELDS)
    return subreddit


# ============================================================================
# CSV/NDJSON EXPORT HELPERS
# ============================================================================

# Valid export formats
VALID_EXPORT_FORMATS = {"json", "csv", "ndjson"}


def get_export_format() -> str:
    """
    Extract export format from request parameters.

    Returns:
        str: Format string ('json', 'csv', or 'ndjson')
    """
    format_param = request.args.get("format", "json").lower()
    if format_param not in VALID_EXPORT_FORMATS:
        return "json"  # Default to JSON for invalid format
    return format_param


def validate_export_format() -> str | None:
    """
    Validate export format parameter.

    Returns:
        Error message if invalid, None if valid
    """
    format_param = request.args.get("format", "json").lower()
    if format_param and format_param not in VALID_EXPORT_FORMATS:
        return f"Invalid format: {format_param}. Valid formats: {', '.join(sorted(VALID_EXPORT_FORMATS))}"
    return None


def flatten_dict_for_csv(data: dict, prefix: str = "") -> dict:
    """
    Flatten nested dictionaries for CSV export.

    Args:
        data: Dictionary to flatten
        prefix: Key prefix for nested items

    Returns:
        Flattened dictionary with dot-notation keys
    """
    items = {}
    for key, value in data.items():
        new_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            items.update(flatten_dict_for_csv(value, new_key))
        elif isinstance(value, list):
            # Convert lists to JSON string for CSV
            import json

            items[new_key] = json.dumps(value)
        else:
            items[new_key] = value
    return items


def data_to_csv(data: list[dict], filename_prefix: str = "export") -> Any:
    """
    Convert list of dictionaries to CSV response.

    Args:
        data: List of data dictionaries
        filename_prefix: Prefix for download filename

    Returns:
        Flask Response with CSV content
    """
    import csv
    import io

    from flask import Response

    if not data:
        return Response(
            "",
            mimetype="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{filename_prefix}_{datetime.utcnow().strftime("%Y-%m-%d")}.csv"'
            },
        )

    # Flatten nested data for CSV
    flattened_data = [flatten_dict_for_csv(item) for item in data]

    # Get all unique keys across all items
    all_keys = set()
    for item in flattened_data:
        all_keys.update(item.keys())

    # Sort keys for consistent column order
    fieldnames = sorted(all_keys)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()

    for item in flattened_data:
        # Convert None to empty string for CSV
        row = {k: ("" if v is None else v) for k, v in item.items()}
        writer.writerow(row)

    csv_content = output.getvalue()
    output.close()

    return Response(
        csv_content,
        mimetype="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename_prefix}_{datetime.utcnow().strftime("%Y-%m-%d")}.csv"'
        },
    )


def data_to_ndjson(data: list[dict], filename_prefix: str = "export") -> Any:
    """
    Convert list of dictionaries to NDJSON (newline-delimited JSON) response.

    Args:
        data: List of data dictionaries
        filename_prefix: Prefix for download filename

    Returns:
        Flask Response with NDJSON content
    """
    import json

    from flask import Response

    # Build NDJSON content (one JSON object per line)
    lines = [json.dumps(item, default=str) for item in data]
    ndjson_content = "\n".join(lines)

    return Response(
        ndjson_content,
        mimetype="application/x-ndjson",
        headers={
            "Content-Disposition": f'attachment; filename="{filename_prefix}_{datetime.utcnow().strftime("%Y-%m-%d")}.ndjson"'
        },
    )


def format_response(data: list[dict], format_type: str, filename_prefix: str = "export") -> Any:
    """
    Format response based on requested format.

    Args:
        data: List of data dictionaries
        format_type: 'json', 'csv', or 'ndjson'
        filename_prefix: Prefix for download filename (CSV/NDJSON)

    Returns:
        Formatted response (jsonify for JSON, Response for others)
    """
    if format_type == "csv":
        return data_to_csv(data, filename_prefix)
    elif format_type == "ndjson":
        return data_to_ndjson(data, filename_prefix)
    else:
        return None  # Return None to indicate JSON (caller handles pagination)


# ============================================================================
# API ENDPOINTS
# ============================================================================


@api_v1.route("/health", methods=["GET"])
def api_health():
    """
    Health check endpoint for monitoring.

    Returns:
        JSON with health status and timestamp
    """
    try:
        db = get_db()
        health_ok = db.health_check()

        if health_ok:
            return jsonify(
                {
                    "status": "healthy",
                    "database": "connected",
                    "api_version": "1.0",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
            ), 200
        else:
            return jsonify(
                {
                    "status": "unhealthy",
                    "database": "disconnected",
                    "api_version": "1.0",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
            ), 503

    except Exception as e:
        format_user_error(e, "api_health")
        return jsonify(
            {"status": "unhealthy", "error": "Service unavailable", "timestamp": datetime.utcnow().isoformat() + "Z"}
        ), 503


@api_v1.route("/stats", methods=["GET"])
@api_limiter.limit("100 per minute")
def get_stats():
    """
    Get archive statistics from pre-calculated metadata (fast query).

    Returns:
        JSON with archive statistics including posts, comments, users, subreddits
    """
    try:
        db = get_db()

        with db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                # Get pre-calculated statistics from metadata table (fast!)
                cur.execute("""
                    SELECT
                        subreddit,
                        platform,
                        total_posts,
                        archived_posts,
                        total_comments,
                        archived_comments,
                        unique_users,
                        earliest_date,
                        latest_date,
                        avg_post_score,
                        avg_comment_score,
                        is_banned
                    FROM subreddit_statistics
                    ORDER BY total_posts DESC
                """)

                subreddits = []
                total_posts_sum = 0
                total_comments_sum = 0
                total_users_sum = 0
                earliest_timestamp = None
                latest_timestamp = None

                for row in cur.fetchall():
                    total_posts = row["total_posts"] or 0
                    archived_posts = row["archived_posts"] or 0

                    # Calculate coverage percentage
                    coverage_pct = round((archived_posts / total_posts * 100), 1) if total_posts > 0 else 0

                    subreddits.append(
                        {
                            "name": row["subreddit"],
                            "platform": row["platform"],
                            "archived_posts": archived_posts,
                            "total_posts": total_posts,
                            "coverage_percentage": coverage_pct,
                            "comments": row["total_comments"],
                            "users": row["unique_users"],
                            "avg_score": float(row["avg_post_score"]) if row["avg_post_score"] else 0,
                            "is_banned": row["is_banned"] if row["is_banned"] is not None else False,
                            "latest_date": format_unix_timestamp(row["latest_date"]) if row["latest_date"] else None,
                        }
                    )

                    total_posts_sum += archived_posts  # Use archived, not total
                    total_comments_sum += row["total_comments"] or 0
                    total_users_sum += row["unique_users"] or 0

                    if row["earliest_date"]:
                        if earliest_timestamp is None or row["earliest_date"] < earliest_timestamp:
                            earliest_timestamp = row["earliest_date"]

                    if row["latest_date"]:
                        if latest_timestamp is None or row["latest_date"] > latest_timestamp:
                            latest_timestamp = row["latest_date"]

                return jsonify(
                    {
                        "archive_version": "1.0.0",
                        "api_version": "1.0",
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "instance": get_instance_metadata(),
                        "content": {
                            "total_posts": total_posts_sum,
                            "total_comments": total_comments_sum,
                            "total_users": total_users_sum,
                            "total_subreddits": len(subreddits),
                            "subreddits": subreddits,
                        },
                        "date_range": {
                            "earliest_post": format_unix_timestamp(earliest_timestamp) if earliest_timestamp else None,
                            "latest_post": format_unix_timestamp(latest_timestamp) if latest_timestamp else None,
                        },
                        "features": get_enhanced_features(),
                        "status": "operational",
                    }
                ), 200

    except Exception as e:
        format_user_error(e, "api_stats")
        return jsonify({"error": "Failed to retrieve statistics"}), 500


@api_v1.route("/platforms", methods=["GET"])
@api_limiter.limit("100 per minute")
def get_platforms():
    """
    Get list of platforms in archive with statistics.

    Returns:
        JSON array of platform objects with post/comment/user counts
    """
    try:
        db = get_db()

        with db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                # Get platform statistics
                cur.execute("""
                    SELECT
                        platform,
                        COUNT(DISTINCT subreddit) as communities,
                        COUNT(*) as total_posts
                    FROM posts
                    GROUP BY platform
                    ORDER BY total_posts DESC
                """)

                platforms = []
                for row in cur.fetchall():
                    platform_id = row["platform"]

                    # Get comment count for this platform
                    cur.execute(
                        """
                        SELECT COUNT(*) as count FROM comments WHERE platform = %s
                    """,
                        (platform_id,),
                    )
                    comment_count = cur.fetchone()["count"]

                    # Get user count for this platform
                    cur.execute(
                        """
                        SELECT COUNT(*) as count FROM users WHERE platform = %s
                    """,
                        (platform_id,),
                    )
                    user_count = cur.fetchone()["count"]

                    # Platform metadata
                    platform_info = {
                        "reddit": {"display_name": "Reddit", "community_term": "subreddit", "url_prefix": "r"},
                        "voat": {"display_name": "Voat", "community_term": "subverse", "url_prefix": "v"},
                        "ruqqus": {"display_name": "Ruqqus", "community_term": "guild", "url_prefix": "g"},
                    }.get(
                        platform_id,
                        {"display_name": platform_id.title(), "community_term": "community", "url_prefix": "c"},
                    )

                    platforms.append(
                        {
                            "platform": platform_id,
                            "display_name": platform_info["display_name"],
                            "community_term": platform_info["community_term"],
                            "url_prefix": platform_info["url_prefix"],
                            "communities": row["communities"],
                            "total_posts": row["total_posts"],
                            "total_comments": comment_count,
                            "total_users": user_count,
                        }
                    )

                return jsonify({"data": platforms}), 200

    except Exception as e:
        format_user_error(e, "api_platforms")
        return jsonify({"error": "Failed to retrieve platforms"}), 500


@api_v1.route("/platforms/<platform>/communities", methods=["GET"])
@api_limiter.limit("100 per minute")
def get_platform_communities(platform: str):
    """
    Get list of communities for a specific platform.

    Args:
        platform: Platform identifier (reddit, voat, ruqqus)

    Query Parameters:
        limit (int): Results per page (default: 100, max: 100)
        page (int): Page number (default: 1)
        sort (str): Sort by posts|comments|name (default: posts)

    Returns:
        Paginated list of communities for the platform
    """
    # Validate platform
    VALID_PLATFORMS = {"reddit", "voat", "ruqqus"}
    if platform not in VALID_PLATFORMS:
        return jsonify({"error": f"Invalid platform. Must be one of: {', '.join(VALID_PLATFORMS)}"}), 400

    # Extract parameters
    limit = request.args.get("limit", type=int, default=100)
    page = request.args.get("page", type=int, default=1)
    sort = request.args.get("sort", default="posts")

    # Validate parameters
    if limit < 1 or limit > 100:
        return jsonify({"error": "Limit must be between 1 and 100"}), 400
    if page < 1:
        return jsonify({"error": "Page must be >= 1"}), 400

    VALID_SORT = {"posts", "comments", "name"}
    if sort not in VALID_SORT:
        return jsonify({"error": f"Invalid sort. Must be one of: {', '.join(VALID_SORT)}"}), 400

    # Map sort to SQL
    sort_map = {"posts": "total_posts DESC", "comments": "total_comments DESC", "name": "subreddit ASC"}
    order_by = sort_map[sort]

    try:
        db = get_db()
        offset = (page - 1) * limit

        with db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                # Get total count
                cur.execute(
                    """
                    SELECT COUNT(DISTINCT subreddit) as count
                    FROM posts
                    WHERE platform = %s
                """,
                    (platform,),
                )
                total_count = cur.fetchone()["count"]

                # Get communities with statistics
                query = f"""
                    SELECT
                        subreddit as name,
                        COUNT(*) as post_count,
                        (SELECT COUNT(*) FROM comments c WHERE c.subreddit = p.subreddit AND c.platform = %s) as comment_count
                    FROM posts p
                    WHERE platform = %s
                    GROUP BY subreddit
                    ORDER BY {order_by}
                    LIMIT %s OFFSET %s
                """
                cur.execute(query, (platform, platform, limit, offset))

                communities = []
                for row in cur.fetchall():
                    communities.append(
                        {"name": row["name"], "posts": row["post_count"], "comments": row["comment_count"]}
                    )

                return jsonify(
                    build_pagination_response(
                        data=communities,
                        page=page,
                        limit=limit,
                        total=total_count,
                        endpoint=f"/api/v1/platforms/{platform}/communities",
                        sort=sort,
                    )
                ), 200

    except Exception as e:
        format_user_error(e, "api_platform_communities")
        return jsonify({"error": "Failed to retrieve communities"}), 500


@api_v1.route("/posts", methods=["GET"])
@api_limiter.limit("100 per minute")
def get_posts():
    """
    Get paginated list of posts with filtering.

    Query Parameters:
        subreddit (str): Filter by subreddit
        author (str): Filter by author username
        min_score (int): Minimum score threshold
        limit (int): Results per page (default: 25, max: 100)
        page (int): Page number (default: 1)
        sort (str): Sort order (score|created_utc|num_comments, default: score)
        fields (str): Comma-separated list of fields to return (default: all)
        max_body_length (int): Truncate selftext to N characters (default: no truncation)
        include_body (bool): Include selftext field (default: true)
        format (str): Response format (json|csv|ndjson, default: json)

    Returns:
        Paginated JSON response with posts, or CSV/NDJSON download
    """
    # Extract and validate parameters
    subreddit = request.args.get("subreddit")
    author = request.args.get("author")
    platform = request.args.get("platform")
    min_score = request.args.get("min_score", type=int, default=0)
    limit = request.args.get("limit", type=int, default=25)
    page = request.args.get("page", type=int, default=1)
    sort = request.args.get("sort", default="score")

    # Export format parameter
    export_format = get_export_format()
    format_error = validate_export_format()
    if format_error:
        return jsonify({"error": format_error}), 400

    # Field selection and truncation parameters
    fields_param = request.args.get("fields")
    requested_fields = parse_fields_param(fields_param)
    max_body_length, include_body = get_truncation_params()

    # Validate field selection
    if requested_fields:
        field_error = validate_fields(requested_fields, VALID_POST_FIELDS)
        if field_error:
            return jsonify({"error": field_error}), 400

    # Validate parameters
    validation_result = validator.validate_all(
        subreddit=subreddit, author=author, min_score=min_score, limit=limit, page=page
    )

    if not validation_result.is_valid:
        return jsonify({"error": "Validation failed", "details": validation_result.get_error_messages()}), 400

    # Get sanitized values
    sanitized = validation_result.sanitized_values
    offset = sanitized["offset"]

    # Validate sort parameter (whitelist)
    VALID_SORT = {"score", "created_utc", "num_comments"}
    if sort not in VALID_SORT:
        return jsonify({"error": f"Invalid sort parameter. Must be one of: {', '.join(VALID_SORT)}"}), 400

    # Validate platform parameter (whitelist)
    VALID_PLATFORMS = {"reddit", "voat", "ruqqus"}
    if platform and platform not in VALID_PLATFORMS:
        return jsonify({"error": f"Invalid platform. Must be one of: {', '.join(VALID_PLATFORMS)}"}), 400

    # Map sort to SQL ORDER BY clause (whitelisted, safe)
    sort_map = {
        "score": "score DESC, created_utc DESC",
        "created_utc": "created_utc DESC, score DESC",
        "num_comments": "num_comments DESC, score DESC",
    }
    order_by = sort_map[sort]

    try:
        db = get_db()

        with db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                # Build WHERE clause dynamically with parameterized values
                where_conditions = []
                params = []

                if sanitized["subreddit"]:
                    where_conditions.append("LOWER(subreddit) = LOWER(%s)")
                    params.append(sanitized["subreddit"])

                if sanitized["author"]:
                    where_conditions.append("author = %s")
                    params.append(sanitized["author"])

                if platform:
                    where_conditions.append("platform = %s")
                    params.append(platform)

                if sanitized["min_score"] > 0:
                    where_conditions.append("score >= %s")
                    params.append(sanitized["min_score"])

                where_clause = " AND ".join(where_conditions) if where_conditions else "TRUE"

                # Get total count for pagination
                count_query = f"SELECT COUNT(*) as count FROM posts WHERE {where_clause}"
                cur.execute(count_query, tuple(params))
                total_count = cur.fetchone()["count"]

                # Get paginated posts (ORDER BY is from whitelist, safe)
                query = f"""
                    SELECT id, subreddit, author, title, selftext, url, domain,
                           permalink, created_utc, score, num_comments, is_self, over_18, platform
                    FROM posts
                    WHERE {where_clause}
                    ORDER BY {order_by}
                    LIMIT %s OFFSET %s
                """
                params.extend([sanitized["limit"], offset])
                cur.execute(query, tuple(params))

                posts = []
                for row in cur.fetchall():
                    post = {
                        "id": row["id"],
                        "platform": row["platform"],
                        "subreddit": row["subreddit"],
                        "author": row["author"],
                        "title": row["title"],
                        "selftext": row["selftext"],
                        "url": row["url"],
                        "domain": row["domain"],
                        "permalink": row["permalink"],
                        "created_utc": row["created_utc"],
                        "created_at": format_unix_timestamp(row["created_utc"]),
                        "score": row["score"],
                        "num_comments": row["num_comments"],
                        "is_self": row["is_self"],
                        "nsfw": row["over_18"],
                    }
                    # Apply truncation and field selection
                    post = process_post_response(post, requested_fields, max_body_length, include_body)
                    posts.append(post)

                # Handle CSV/NDJSON export
                if export_format in ("csv", "ndjson"):
                    filename = f"posts_{sanitized['subreddit'] or 'all'}"
                    return format_response(posts, export_format, filename), 200

                return jsonify(
                    build_pagination_response(
                        data=posts,
                        page=page,
                        limit=sanitized["limit"],
                        total=total_count,
                        endpoint="/api/v1/posts",
                        subreddit=sanitized["subreddit"],
                        author=sanitized["author"],
                        platform=platform,
                        min_score=sanitized["min_score"] if sanitized["min_score"] > 0 else None,
                        sort=sort,
                        fields=fields_param,
                        max_body_length=max_body_length if max_body_length else None,
                        include_body="false" if not include_body else None,
                    )
                ), 200

    except Exception as e:
        format_user_error(e, "api_posts")
        return jsonify({"error": "Failed to retrieve posts"}), 500


@api_v1.route("/posts/<post_id>", methods=["GET"])
@api_limiter.limit("100 per minute")
def get_post(post_id: str):
    """
    Get single post by ID.

    Args:
        post_id: Post ID (alphanumeric + underscore only)

    Query Parameters:
        fields (str): Comma-separated list of fields to return (default: all)
        max_body_length (int): Truncate selftext to N characters (default: no truncation)
        include_body (bool): Include selftext field (default: true)

    Returns:
        JSON with post details
    """
    # Validate post_id format to prevent SQL injection
    if not re.match(r"^[a-z0-9_]+$", post_id, re.IGNORECASE):
        return jsonify({"error": "Invalid post ID format"}), 400

    # Field selection and truncation parameters
    fields_param = request.args.get("fields")
    requested_fields = parse_fields_param(fields_param)
    max_body_length, include_body = get_truncation_params()

    # Validate field selection
    if requested_fields:
        field_error = validate_fields(requested_fields, VALID_POST_FIELDS)
        if field_error:
            return jsonify({"error": field_error}), 400

    try:
        db = get_db()

        with db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, subreddit, author, title, selftext, url, domain,
                           permalink, created_utc, score, num_comments, is_self, over_18,
                           locked, stickied, platform
                    FROM posts
                    WHERE id = %s
                """,
                    (post_id,),
                )

                row = cur.fetchone()

                if not row:
                    return jsonify({"error": "Post not found"}), 404

                post = {
                    "id": row["id"],
                    "subreddit": row["subreddit"],
                    "author": row["author"],
                    "title": row["title"],
                    "selftext": row["selftext"],
                    "url": row["url"],
                    "domain": row["domain"],
                    "permalink": row["permalink"],
                    "created_utc": row["created_utc"],
                    "created_at": format_unix_timestamp(row["created_utc"]),
                    "score": row["score"],
                    "num_comments": row["num_comments"],
                    "is_self": row["is_self"],
                    "nsfw": row["over_18"],
                    "locked": row["locked"],
                    "stickied": row["stickied"],
                    "platform": row.get("platform", "reddit"),
                }

                # Apply truncation and field selection
                post = process_post_response(post, requested_fields, max_body_length, include_body)

                return jsonify(post), 200

    except Exception as e:
        format_user_error(e, "api_post_single")
        return jsonify({"error": "Failed to retrieve post"}), 500


@api_v1.route("/posts/<post_id>/comments", methods=["GET"])
@api_limiter.limit("100 per minute")
def get_post_comments(post_id: str):
    """
    Get comments for a specific post.

    Args:
        post_id: Post ID

    Query Parameters:
        limit (int): Results per page (default: 25, max: 100)
        page (int): Page number (default: 1)
        fields (str): Comma-separated list of fields to return (default: all)
        max_body_length (int): Truncate body to N characters (default: no truncation)
        include_body (bool): Include body field (default: true)

    Returns:
        Paginated JSON response with comments
    """
    # Validate post_id format
    if not re.match(r"^[a-z0-9_]+$", post_id, re.IGNORECASE):
        return jsonify({"error": "Invalid post ID format"}), 400

    # Field selection and truncation parameters
    fields_param = request.args.get("fields")
    requested_fields = parse_fields_param(fields_param)
    max_body_length, include_body = get_truncation_params()

    # Validate field selection
    if requested_fields:
        field_error = validate_fields(requested_fields, VALID_COMMENT_FIELDS)
        if field_error:
            return jsonify({"error": field_error}), 400

    # Extract and validate pagination parameters
    limit = request.args.get("limit", type=int, default=25)
    page = request.args.get("page", type=int, default=1)

    validation_result = validator.validate_all(limit=limit, page=page)
    if not validation_result.is_valid:
        return jsonify({"error": "Validation failed", "details": validation_result.get_error_messages()}), 400

    sanitized = validation_result.sanitized_values
    offset = sanitized["offset"]

    try:
        db = get_db()

        with db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                # Get total count
                cur.execute("SELECT COUNT(*) as count FROM comments WHERE post_id = %s", (post_id,))
                total_count = cur.fetchone()["count"]

                # Get paginated comments
                cur.execute(
                    """
                    SELECT id, post_id, parent_id, author, body, permalink,
                           created_utc, score, depth
                    FROM comments
                    WHERE post_id = %s
                    ORDER BY created_utc ASC
                    LIMIT %s OFFSET %s
                """,
                    (post_id, sanitized["limit"], offset),
                )

                comments = []
                for row in cur.fetchall():
                    comment = {
                        "id": row["id"],
                        "post_id": row["post_id"],
                        "parent_id": row["parent_id"],
                        "author": row["author"],
                        "body": row["body"],
                        "permalink": row["permalink"],
                        "created_utc": row["created_utc"],
                        "created_at": format_unix_timestamp(row["created_utc"]),
                        "score": row["score"],
                        "depth": row["depth"],
                    }
                    # Apply truncation and field selection
                    comment = process_comment_response(comment, requested_fields, max_body_length, include_body)
                    comments.append(comment)

                return jsonify(
                    build_pagination_response(
                        data=comments,
                        page=page,
                        limit=sanitized["limit"],
                        total=total_count,
                        endpoint=f"/api/v1/posts/{post_id}/comments",
                        fields=fields_param,
                        max_body_length=max_body_length if max_body_length else None,
                        include_body="false" if not include_body else None,
                    )
                ), 200

    except Exception as e:
        format_user_error(e, "api_post_comments")
        return jsonify({"error": "Failed to retrieve comments"}), 500


@api_v1.route("/comments", methods=["GET"])
@api_limiter.limit("100 per minute")
def get_comments():
    """
    Get paginated list of comments with filtering.

    Query Parameters:
        subreddit (str): Filter by subreddit
        author (str): Filter by author username
        min_score (int): Minimum score threshold
        limit (int): Results per page (default: 25, max: 100)
        page (int): Page number (default: 1)
        fields (str): Comma-separated list of fields to return (default: all)
        max_body_length (int): Truncate body to N characters (default: 500 for list view)
        include_body (bool): Include body field (default: true)
        format (str): Response format (json|csv|ndjson, default: json)

    Returns:
        Paginated JSON response with comments, or CSV/NDJSON download
    """
    # Extract and validate parameters
    subreddit = request.args.get("subreddit")
    author = request.args.get("author")
    platform = request.args.get("platform")
    min_score = request.args.get("min_score", type=int, default=0)
    limit = request.args.get("limit", type=int, default=25)
    page = request.args.get("page", type=int, default=1)

    # Validate platform parameter (whitelist)
    VALID_PLATFORMS = {"reddit", "voat", "ruqqus"}
    if platform and platform not in VALID_PLATFORMS:
        return jsonify({"error": f"Invalid platform. Must be one of: {', '.join(VALID_PLATFORMS)}"}), 400

    # Export format parameter
    export_format = get_export_format()
    format_error = validate_export_format()
    if format_error:
        return jsonify({"error": format_error}), 400

    # Field selection and truncation parameters
    fields_param = request.args.get("fields")
    requested_fields = parse_fields_param(fields_param)
    max_body_length, include_body = get_truncation_params()

    # Default truncation for list view if not specified
    if max_body_length is None and include_body:
        max_body_length = 500

    # Validate field selection
    if requested_fields:
        field_error = validate_fields(requested_fields, VALID_COMMENT_FIELDS)
        if field_error:
            return jsonify({"error": field_error}), 400

    validation_result = validator.validate_all(
        subreddit=subreddit, author=author, min_score=min_score, limit=limit, page=page
    )

    if not validation_result.is_valid:
        return jsonify({"error": "Validation failed", "details": validation_result.get_error_messages()}), 400

    sanitized = validation_result.sanitized_values
    offset = sanitized["offset"]

    try:
        db = get_db()

        with db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                # Build WHERE clause
                where_conditions = []
                params = []

                if sanitized["subreddit"]:
                    where_conditions.append("LOWER(subreddit) = LOWER(%s)")
                    params.append(sanitized["subreddit"])

                if sanitized["author"]:
                    where_conditions.append("author = %s")
                    params.append(sanitized["author"])

                if platform:
                    where_conditions.append("platform = %s")
                    params.append(platform)

                if sanitized["min_score"] > 0:
                    where_conditions.append("score >= %s")
                    params.append(sanitized["min_score"])

                where_clause = " AND ".join(where_conditions) if where_conditions else "TRUE"

                # Get total count
                count_query = f"SELECT COUNT(*) as count FROM comments WHERE {where_clause}"
                cur.execute(count_query, tuple(params))
                total_count = cur.fetchone()["count"]

                # Get paginated comments
                query = f"""
                    SELECT id, post_id, parent_id, subreddit, author, body, permalink,
                           created_utc, score, depth, platform
                    FROM comments
                    WHERE {where_clause}
                    ORDER BY created_utc DESC
                    LIMIT %s OFFSET %s
                """
                params.extend([sanitized["limit"], offset])
                cur.execute(query, tuple(params))

                comments = []
                for row in cur.fetchall():
                    comment = {
                        "id": row["id"],
                        "platform": row["platform"],
                        "post_id": row["post_id"],
                        "parent_id": row["parent_id"],
                        "subreddit": row["subreddit"],
                        "author": row["author"],
                        "body": row["body"],
                        "permalink": row["permalink"],
                        "created_utc": row["created_utc"],
                        "created_at": format_unix_timestamp(row["created_utc"]),
                        "score": row["score"],
                        "depth": row["depth"],
                    }
                    # Apply truncation and field selection
                    comment = process_comment_response(comment, requested_fields, max_body_length, include_body)
                    comments.append(comment)

                # Handle CSV/NDJSON export
                if export_format in ("csv", "ndjson"):
                    filename = f"comments_{sanitized['subreddit'] or 'all'}"
                    return format_response(comments, export_format, filename), 200

                return jsonify(
                    build_pagination_response(
                        data=comments,
                        page=page,
                        limit=sanitized["limit"],
                        total=total_count,
                        endpoint="/api/v1/comments",
                        subreddit=sanitized["subreddit"],
                        author=sanitized["author"],
                        platform=platform,
                        min_score=sanitized["min_score"] if sanitized["min_score"] > 0 else None,
                        fields=fields_param,
                        max_body_length=max_body_length if max_body_length != 500 else None,
                        include_body="false" if not include_body else None,
                    )
                ), 200

    except Exception as e:
        format_user_error(e, "api_comments")
        return jsonify({"error": "Failed to retrieve comments"}), 500


@api_v1.route("/comments/<comment_id>", methods=["GET"])
@api_limiter.limit("100 per minute")
def get_comment(comment_id: str):
    """
    Get single comment by ID.

    Args:
        comment_id: Comment ID

    Query Parameters:
        fields (str): Comma-separated list of fields to return (default: all)
        max_body_length (int): Truncate body to N characters (default: no truncation)
        include_body (bool): Include body field (default: true)

    Returns:
        JSON with comment details
    """
    # Validate comment_id format
    if not re.match(r"^[a-z0-9_]+$", comment_id, re.IGNORECASE):
        return jsonify({"error": "Invalid comment ID format"}), 400

    # Field selection and truncation parameters
    fields_param = request.args.get("fields")
    requested_fields = parse_fields_param(fields_param)
    max_body_length, include_body = get_truncation_params()

    # Validate field selection
    if requested_fields:
        field_error = validate_fields(requested_fields, VALID_COMMENT_FIELDS)
        if field_error:
            return jsonify({"error": field_error}), 400

    try:
        db = get_db()

        with db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, post_id, parent_id, subreddit, author, body, permalink,
                           created_utc, score, depth
                    FROM comments
                    WHERE id = %s
                """,
                    (comment_id,),
                )

                row = cur.fetchone()

                if not row:
                    return jsonify({"error": "Comment not found"}), 404

                comment = {
                    "id": row["id"],
                    "post_id": row["post_id"],
                    "parent_id": row["parent_id"],
                    "subreddit": row["subreddit"],
                    "author": row["author"],
                    "body": row["body"],
                    "permalink": row["permalink"],
                    "created_utc": row["created_utc"],
                    "created_at": format_unix_timestamp(row["created_utc"]),
                    "score": row["score"],
                    "depth": row["depth"],
                }

                # Apply truncation and field selection
                comment = process_comment_response(comment, requested_fields, max_body_length, include_body)

                return jsonify(comment), 200

    except Exception as e:
        format_user_error(e, "api_comment_single")
        return jsonify({"error": "Failed to retrieve comment"}), 500


@api_v1.route("/users", methods=["GET"])
@api_limiter.limit("100 per minute")
def get_users():
    """
    Get paginated list of users.

    Query Parameters:
        limit (int): Results per page (default: 25, max: 100)
        page (int): Page number (default: 1)
        sort (str): Sort order (karma|activity|posts|comments, default: karma)
        fields (str): Comma-separated list of fields to return (default: all)
        format (str): Response format (json|csv|ndjson, default: json)

    Returns:
        Paginated JSON response with users, or CSV/NDJSON download
    """
    # Extract and validate parameters
    limit = request.args.get("limit", type=int, default=25)
    page = request.args.get("page", type=int, default=1)
    sort = request.args.get("sort", default="karma")

    # Export format parameter
    export_format = get_export_format()
    format_error = validate_export_format()
    if format_error:
        return jsonify({"error": format_error}), 400

    # Field selection parameter
    fields_param = request.args.get("fields")
    requested_fields = parse_fields_param(fields_param)

    # Validate field selection
    if requested_fields:
        field_error = validate_fields(requested_fields, VALID_USER_FIELDS)
        if field_error:
            return jsonify({"error": field_error}), 400

    validation_result = validator.validate_all(limit=limit, page=page)
    if not validation_result.is_valid:
        return jsonify({"error": "Validation failed", "details": validation_result.get_error_messages()}), 400

    sanitized = validation_result.sanitized_values
    offset = sanitized["offset"]

    # Validate sort parameter (whitelist)
    VALID_SORT = {"karma", "activity", "posts", "comments"}
    if sort not in VALID_SORT:
        return jsonify({"error": f"Invalid sort parameter. Must be one of: {', '.join(VALID_SORT)}"}), 400

    # Map sort to SQL ORDER BY clause (whitelisted, safe)
    sort_map = {
        "karma": "total_karma DESC",
        "activity": "total_activity DESC",
        "posts": "post_count DESC",
        "comments": "comment_count DESC",
    }
    order_by = sort_map[sort]

    try:
        db = get_db()

        with db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                # Get total count
                cur.execute("SELECT COUNT(*) as count FROM users")
                total_count = cur.fetchone()["count"]

                # Get paginated users
                query = f"""
                    SELECT username, post_count, comment_count, total_activity, total_karma,
                           first_seen_utc, last_seen_utc
                    FROM users
                    ORDER BY {order_by}
                    LIMIT %s OFFSET %s
                """
                cur.execute(query, (sanitized["limit"], offset))

                users = []
                for row in cur.fetchall():
                    user = {
                        "username": row["username"],
                        "post_count": row["post_count"],
                        "comment_count": row["comment_count"],
                        "total_activity": row["total_activity"],
                        "total_karma": row["total_karma"],
                        "first_seen_utc": row["first_seen_utc"],
                        "first_seen_at": format_unix_timestamp(row["first_seen_utc"]),
                        "last_seen_utc": row["last_seen_utc"],
                        "last_seen_at": format_unix_timestamp(row["last_seen_utc"]),
                    }
                    # Apply field selection
                    user = process_user_response(user, requested_fields)
                    users.append(user)

                # Handle CSV/NDJSON export
                if export_format in ("csv", "ndjson"):
                    return format_response(users, export_format, "users"), 200

                return jsonify(
                    build_pagination_response(
                        data=users,
                        page=page,
                        limit=sanitized["limit"],
                        total=total_count,
                        endpoint="/api/v1/users",
                        sort=sort,
                        fields=fields_param,
                    )
                ), 200

    except Exception as e:
        format_user_error(e, "api_users")
        return jsonify({"error": "Failed to retrieve users"}), 500


@api_v1.route("/users/<username>", methods=["GET"])
@api_limiter.limit("100 per minute")
def get_user(username: str):
    """
    Get user profile and statistics.

    Args:
        username: Username (alphanumeric + underscore + hyphen)

    Query Parameters:
        fields (str): Comma-separated list of fields to return (default: all)

    Returns:
        JSON with user profile and stats
    """
    # Validate username format
    if not re.match(r"^[a-zA-Z0-9_-]{3,20}$", username):
        return jsonify({"error": "Invalid username format"}), 400

    # Field selection parameter
    fields_param = request.args.get("fields")
    requested_fields = parse_fields_param(fields_param)

    # Validate field selection
    if requested_fields:
        field_error = validate_fields(requested_fields, VALID_USER_FIELDS)
        if field_error:
            return jsonify({"error": field_error}), 400

    try:
        db = get_db()

        with db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT username, post_count, comment_count, total_activity, total_karma,
                           first_seen_utc, last_seen_utc, subreddit_activity
                    FROM users
                    WHERE username = %s
                """,
                    (username,),
                )

                row = cur.fetchone()

                if not row:
                    return jsonify({"error": "User not found"}), 404

                user = {
                    "username": row["username"],
                    "post_count": row["post_count"],
                    "comment_count": row["comment_count"],
                    "total_activity": row["total_activity"],
                    "total_karma": row["total_karma"],
                    "first_seen_utc": row["first_seen_utc"],
                    "first_seen_at": format_unix_timestamp(row["first_seen_utc"]),
                    "last_seen_utc": row["last_seen_utc"],
                    "last_seen_at": format_unix_timestamp(row["last_seen_utc"]),
                    "subreddit_activity": row["subreddit_activity"] or {},
                }

                # Apply field selection
                user = process_user_response(user, requested_fields)

                return jsonify(user), 200

    except Exception as e:
        format_user_error(e, "api_user_single")
        return jsonify({"error": "Failed to retrieve user"}), 500


@api_v1.route("/users/<username>/posts", methods=["GET"])
@api_limiter.limit("100 per minute")
def get_user_posts(username: str):
    """
    Get posts by specific user.

    Args:
        username: Username

    Query Parameters:
        limit (int): Results per page (default: 25, max: 100)
        page (int): Page number (default: 1)
        fields (str): Comma-separated list of fields to return (default: all)

    Returns:
        Paginated JSON response with user's posts
    """
    # Validate username format
    if not re.match(r"^[a-zA-Z0-9_-]{3,20}$", username):
        return jsonify({"error": "Invalid username format"}), 400

    # Field selection parameter
    fields_param = request.args.get("fields")
    requested_fields = parse_fields_param(fields_param)

    # Validate field selection
    if requested_fields:
        field_error = validate_fields(requested_fields, VALID_POST_FIELDS)
        if field_error:
            return jsonify({"error": field_error}), 400

    # Extract and validate pagination parameters
    limit = request.args.get("limit", type=int, default=25)
    page = request.args.get("page", type=int, default=1)

    validation_result = validator.validate_all(limit=limit, page=page)
    if not validation_result.is_valid:
        return jsonify({"error": "Validation failed", "details": validation_result.get_error_messages()}), 400

    sanitized = validation_result.sanitized_values
    offset = sanitized["offset"]

    try:
        db = get_db()

        with db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                # Get total count
                cur.execute("SELECT COUNT(*) as count FROM posts WHERE author = %s", (username,))
                total_count = cur.fetchone()["count"]

                # Get paginated posts
                cur.execute(
                    """
                    SELECT id, subreddit, title, url, permalink, created_utc, score, num_comments
                    FROM posts
                    WHERE author = %s
                    ORDER BY created_utc DESC
                    LIMIT %s OFFSET %s
                """,
                    (username, sanitized["limit"], offset),
                )

                posts = []
                for row in cur.fetchall():
                    post = {
                        "id": row["id"],
                        "subreddit": row["subreddit"],
                        "title": row["title"],
                        "url": row["url"],
                        "permalink": row["permalink"],
                        "created_utc": row["created_utc"],
                        "created_at": format_unix_timestamp(row["created_utc"]),
                        "score": row["score"],
                        "num_comments": row["num_comments"],
                    }
                    # Apply field selection (no body to truncate in this endpoint)
                    if requested_fields:
                        post = filter_fields(post, requested_fields, VALID_POST_FIELDS)
                    posts.append(post)

                return jsonify(
                    build_pagination_response(
                        data=posts,
                        page=page,
                        limit=sanitized["limit"],
                        total=total_count,
                        endpoint=f"/api/v1/users/{username}/posts",
                        fields=fields_param,
                    )
                ), 200

    except Exception as e:
        format_user_error(e, "api_user_posts")
        return jsonify({"error": "Failed to retrieve user posts"}), 500


@api_v1.route("/users/<username>/comments", methods=["GET"])
@api_limiter.limit("100 per minute")
def get_user_comments(username: str):
    """
    Get comments by specific user.

    Args:
        username: Username

    Query Parameters:
        limit (int): Results per page (default: 25, max: 100)
        page (int): Page number (default: 1)
        fields (str): Comma-separated list of fields to return
        max_body_length (int): Maximum body length (truncation)
        include_body (bool): Whether to include body (default: true)

    Returns:
        Paginated JSON response with user's comments
    """
    # Validate username format
    if not re.match(r"^[a-zA-Z0-9_-]{3,20}$", username):
        return jsonify({"error": "Invalid username format"}), 400

    # Extract and validate pagination parameters
    limit = request.args.get("limit", type=int, default=25)
    page = request.args.get("page", type=int, default=1)

    # Field selection and truncation parameters
    fields_param = request.args.get("fields")
    requested_fields = parse_fields_param(fields_param)
    max_body_length, include_body = get_truncation_params()

    # Validate field selection
    if requested_fields:
        field_error = validate_fields(requested_fields, VALID_COMMENT_FIELDS)
        if field_error:
            return jsonify({"error": field_error}), 400

    validation_result = validator.validate_all(limit=limit, page=page)
    if not validation_result.is_valid:
        return jsonify({"error": "Validation failed", "details": validation_result.get_error_messages()}), 400

    sanitized = validation_result.sanitized_values
    offset = sanitized["offset"]

    try:
        db = get_db()

        with db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                # Get total count
                cur.execute("SELECT COUNT(*) as count FROM comments WHERE author = %s", (username,))
                total_count = cur.fetchone()["count"]

                # Get paginated comments
                cur.execute(
                    """
                    SELECT id, post_id, parent_id, subreddit, author, body, permalink,
                           created_utc, score, depth
                    FROM comments
                    WHERE author = %s
                    ORDER BY created_utc DESC
                    LIMIT %s OFFSET %s
                """,
                    (username, sanitized["limit"], offset),
                )

                comments = []
                for row in cur.fetchall():
                    comment_data = {
                        "id": row["id"],
                        "post_id": row["post_id"],
                        "parent_id": row["parent_id"],
                        "subreddit": row["subreddit"],
                        "author": row["author"],
                        "body": row["body"],
                        "body_length": len(row["body"]) if row["body"] else 0,
                        "permalink": row["permalink"],
                        "created_utc": row["created_utc"],
                        "created_at": format_unix_timestamp(row["created_utc"]),
                        "score": row["score"],
                        "depth": row["depth"],
                    }
                    # Apply truncation and field selection
                    comment_data = process_comment_response(
                        comment_data, requested_fields, max_body_length, include_body
                    )
                    comments.append(comment_data)

                return jsonify(
                    build_pagination_response(
                        data=comments,
                        page=page,
                        limit=sanitized["limit"],
                        total=total_count,
                        endpoint=f"/api/v1/users/{username}/comments",
                        fields=fields_param,
                    )
                ), 200

    except Exception as e:
        format_user_error(e, "api_user_comments")
        return jsonify({"error": "Failed to retrieve user comments"}), 500


@api_v1.route("/subreddits", methods=["GET"])
@api_limiter.limit("100 per minute")
def get_subreddits():
    """
    Get list of subreddits in archive with post and comment counts (total and filtered).

    Query Parameters:
        min_score (int, optional): Minimum post score filter
        min_comments (int, optional): Minimum comment count filter
        fields (str): Comma-separated list of fields to return
        format (str): Response format (json|csv|ndjson, default: json)

    Returns:
        JSON array of subreddit objects with:
        - total_posts: Total number of posts in subreddit
        - total_comments: Total number of comments in subreddit
        - filtered_posts: Number of posts meeting filter criteria (if filters applied)
        - filtered_comments: Number of comments from filtered posts (if filters applied)
    """
    # Export format parameter
    export_format = get_export_format()
    format_error = validate_export_format()
    if format_error:
        return jsonify({"error": format_error}), 400

    # Field selection parameters
    fields_param = request.args.get("fields")
    requested_fields = parse_fields_param(fields_param)

    # Validate field selection
    if requested_fields:
        field_error = validate_fields(requested_fields, VALID_SUBREDDIT_FIELDS)
        if field_error:
            return jsonify({"error": field_error}), 400

    try:
        # Extract filter parameters
        min_score = request.args.get("min_score", type=int, default=0)
        min_comments = request.args.get("min_comments", type=int, default=0)

        db = get_db()

        with db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                # Get total posts and comments per subreddit (unfiltered)
                cur.execute("""
                    SELECT
                        p.subreddit,
                        COUNT(DISTINCT p.id) as post_count,
                        COUNT(c.id) as comment_count
                    FROM posts p
                    LEFT JOIN comments c ON c.post_id = p.id
                    GROUP BY p.subreddit
                    ORDER BY post_count DESC
                """)

                subreddits = []
                for row in cur.fetchall():
                    subreddit_data = {
                        "name": row["subreddit"],
                        "total_posts": row["post_count"],
                        "total_comments": row["comment_count"],
                    }

                    # Get stored filters for this subreddit
                    stored_filters = db.get_subreddit_filters(row["subreddit"])

                    # Use query params as override, otherwise use stored filters
                    effective_min_score = min_score if min_score > 0 else stored_filters["min_score"]
                    effective_min_comments = min_comments if min_comments > 0 else stored_filters["min_comments"]

                    # Add filter info to response (only show the effective filters being applied)
                    subreddit_data["filters"] = {
                        "min_score": effective_min_score,
                        "min_comments": effective_min_comments,
                    }

                    # If filters applied (either from query or stored), get filtered counts
                    if effective_min_score > 0 or effective_min_comments > 0:
                        # Get filtered post count
                        cur.execute(
                            """
                            SELECT COUNT(*) as filtered_count
                            FROM posts
                            WHERE LOWER(subreddit) = LOWER(%s)
                            AND score >= %s
                            AND num_comments >= %s
                        """,
                            (row["subreddit"], effective_min_score, effective_min_comments),
                        )

                        filtered_row = cur.fetchone()
                        subreddit_data["filtered_posts"] = filtered_row["filtered_count"]

                        # Get filtered comment count (only comments from filtered posts)
                        cur.execute(
                            """
                            SELECT COUNT(*) as comment_count
                            FROM comments c
                            INNER JOIN posts p ON c.post_id = p.id
                            WHERE LOWER(p.subreddit) = LOWER(%s)
                            AND p.score >= %s
                            AND p.num_comments >= %s
                        """,
                            (row["subreddit"], effective_min_score, effective_min_comments),
                        )

                        filtered_comment_row = cur.fetchone()
                        subreddit_data["filtered_comments"] = filtered_comment_row["comment_count"]
                    else:
                        # No filters - filtered counts same as totals
                        subreddit_data["filtered_posts"] = row["post_count"]
                        subreddit_data["filtered_comments"] = row["comment_count"]

                    # Apply field selection
                    subreddit_data = process_subreddit_response(subreddit_data, requested_fields)
                    subreddits.append(subreddit_data)

                # Handle CSV/NDJSON export
                if export_format in ("csv", "ndjson"):
                    return format_response(subreddits, export_format, "subreddits"), 200

                response = {"data": subreddits, "meta": {"total": len(subreddits), "fields": fields_param}}

                return jsonify(response), 200

    except Exception as e:
        format_user_error(e, "api_subreddits")
        return jsonify({"error": "Failed to retrieve subreddits"}), 500


@api_v1.route("/subreddits/<subreddit>", methods=["GET"])
@api_limiter.limit("100 per minute")
def get_subreddit(subreddit: str):
    """
    Get subreddit statistics.

    Args:
        subreddit: Subreddit name

    Query Parameters:
        fields (str): Comma-separated list of fields to return

    Returns:
        JSON with subreddit statistics
    """
    # Validate subreddit format
    if not re.match(r"^[a-zA-Z0-9_]{2,21}$", subreddit):
        return jsonify({"error": "Invalid subreddit name format"}), 400

    # Field selection parameters
    fields_param = request.args.get("fields")
    requested_fields = parse_fields_param(fields_param)

    # Validate field selection
    if requested_fields:
        field_error = validate_fields(requested_fields, VALID_SUBREDDIT_FIELDS)
        if field_error:
            return jsonify({"error": field_error}), 400

    try:
        db = get_db()

        with db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                # Try to get from subreddit_statistics table first
                cur.execute(
                    """
                    SELECT total_posts, total_comments, unique_users,
                           earliest_date, latest_date, avg_post_score
                    FROM subreddit_statistics
                    WHERE LOWER(subreddit) = LOWER(%s)
                """,
                    (subreddit,),
                )

                stats_row = cur.fetchone()

                if stats_row:
                    subreddit_data = {
                        "name": subreddit,
                        "total_posts": stats_row["total_posts"],
                        "total_comments": stats_row["total_comments"],
                        "unique_users": stats_row["unique_users"],
                        "earliest_post": format_unix_timestamp(stats_row["earliest_date"]),
                        "latest_post": format_unix_timestamp(stats_row["latest_date"]),
                        "avg_post_score": float(stats_row["avg_post_score"]) if stats_row["avg_post_score"] else 0,
                    }
                    # Apply field selection
                    subreddit_data = process_subreddit_response(subreddit_data, requested_fields)
                    return jsonify(subreddit_data), 200

                # Fallback: Calculate stats on-the-fly
                cur.execute(
                    """
                    SELECT
                        COUNT(*) as post_count,
                        COUNT(DISTINCT author) as user_count,
                        MIN(created_utc) as earliest,
                        MAX(created_utc) as latest,
                        AVG(score) as avg_score
                    FROM posts
                    WHERE LOWER(subreddit) = LOWER(%s)
                """,
                    (subreddit,),
                )

                row = cur.fetchone()

                if row["post_count"] == 0:
                    return jsonify({"error": "Subreddit not found"}), 404

                # Get comment count
                cur.execute(
                    """
                    SELECT COUNT(*) as comment_count
                    FROM comments
                    WHERE LOWER(subreddit) = LOWER(%s)
                """,
                    (subreddit,),
                )

                comment_count = cur.fetchone()["comment_count"]

                subreddit_data = {
                    "name": subreddit,
                    "total_posts": row["post_count"],
                    "total_comments": comment_count,
                    "unique_users": row["user_count"],
                    "earliest_post": format_unix_timestamp(row["earliest"]),
                    "latest_post": format_unix_timestamp(row["latest"]),
                    "avg_post_score": float(row["avg_score"]) if row["avg_score"] else 0,
                }
                # Apply field selection
                subreddit_data = process_subreddit_response(subreddit_data, requested_fields)
                return jsonify(subreddit_data), 200

    except Exception as e:
        format_user_error(e, "api_subreddit_single")
        return jsonify({"error": "Failed to retrieve subreddit statistics"}), 500


# ============================================================================
# SEARCH ENDPOINTS (MCP-optimized)
# ============================================================================

# Search instance singleton
_search = None


def get_search():
    """Get or create search instance."""
    global _search
    if _search is None:
        connection_string = os.getenv("DATABASE_URL")
        if not connection_string:
            raise RuntimeError("DATABASE_URL environment variable not set")
        _search = PostgresSearch(connection_string=connection_string)
    return _search


@api_v1.route("/search", methods=["GET"])
@api_limiter.limit("100 per minute")
def api_search():
    """
    Full-text search across posts and comments.

    Query Parameters:
        q (str, required): Search query (supports "phrase", OR, -exclude, operators)
        type (str): Filter by type: 'posts', 'comments', or 'all' (default: 'all')
        subreddit (str): Filter by subreddit
        author (str): Filter by author
        min_score (int): Minimum score filter
        after (int): Unix timestamp - results after this date
        before (int): Unix timestamp - results before this date
        sort (str): Sort order: 'relevance', 'score', 'created_utc' (default: 'relevance')
        limit (int): Results per page (default: 25, max: 100)
        page (int): Page number (default: 1)
        max_body_length (int): Truncate body/selftext to this length
        include_body (bool): Include body content (default: true)

    Supported operators in query:
        sub:name, subreddit:name - Filter by subreddit
        author:name, user:name - Filter by author
        score:N+ or score:>N - Minimum score
        type:post or type:comment - Result type
        sort:score, sort:date, sort:relevance - Sort order

    Returns:
        Paginated JSON response with search results
    """
    # Get query parameter
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "Search query 'q' is required"}), 400

    # Parse search operators from query
    parsed = parse_search_operators(query)

    # Get filter parameters (query params override operators)
    type_param = request.args.get("type", "").lower()
    subreddit = request.args.get("subreddit", parsed.subreddit)
    author = request.args.get("author", parsed.author)
    min_score = request.args.get("min_score", type=int, default=parsed.min_score)
    after = request.args.get("after", type=int, default=None)
    before = request.args.get("before", type=int, default=None)
    sort = request.args.get("sort", parsed.sort_by or "relevance").lower()

    # Map sort values
    sort_mapping = {
        "relevance": "rank",
        "score": "score",
        "created_utc": "created_utc",
        "date": "created_utc",
        "new": "created_utc",
        "old": "created_utc_asc",
    }
    order_by = sort_mapping.get(sort, "rank")

    # Determine result type
    result_type = None
    if type_param in ("posts", "post"):
        result_type = "post"
    elif type_param in ("comments", "comment"):
        result_type = "comment"
    elif parsed.result_type:
        result_type = parsed.result_type

    # Pagination parameters
    limit = request.args.get("limit", type=int, default=25)
    page = request.args.get("page", type=int, default=1)

    # Validate pagination
    validation_result = validator.validate_all(limit=limit, page=page)
    if not validation_result.is_valid:
        return jsonify({"error": "Validation failed", "details": validation_result.get_error_messages()}), 400

    sanitized = validation_result.sanitized_values
    offset = sanitized["offset"]

    # Truncation parameters
    max_body_length, include_body = get_truncation_params()

    try:
        search = get_search()

        # Build search query
        search_query = SearchQuery(
            query_text=parsed.query_text,
            subreddit=subreddit,
            author=author,
            result_type=result_type,
            min_score=min_score,
            start_date=after,
            end_date=before,
            limit=sanitized["limit"],
            offset=offset,
            order_by=order_by,
        )

        # Execute search
        results, total_count = search.search(search_query)

        # Format results with truncation
        formatted_results = []
        for result in results:
            result_dict = result.to_dict()

            # Add formatted timestamp
            if "created_utc" in result_dict:
                result_dict["created_at"] = format_unix_timestamp(result_dict["created_utc"])

            # Rename 'headline' to 'snippet' for clarity and add <mark> tags
            if "headline" in result_dict:
                # Convert PostgreSQL default highlighting to <mark> tags
                snippet = result_dict.pop("headline")
                if snippet:
                    # PostgreSQL ts_headline uses <b> by default, convert to <mark>
                    snippet = snippet.replace("<b>", "<mark>").replace("</b>", "</mark>")
                    result_dict["snippet"] = snippet

            # Apply truncation based on result type
            if result.result_type == "post":
                if not include_body and "selftext" in result_dict:
                    result_dict["selftext"] = None
                elif include_body and max_body_length and result_dict.get("selftext"):
                    body = result_dict["selftext"]
                    if len(body) > max_body_length:
                        result_dict["selftext"] = body[:max_body_length] + "..."
                        result_dict["selftext_truncated"] = True
                        result_dict["selftext_full_length"] = len(body)
            elif result.result_type == "comment":
                if not include_body and "body" in result_dict:
                    result_dict["body"] = None
                elif include_body and max_body_length and result_dict.get("body"):
                    body = result_dict["body"]
                    if len(body) > max_body_length:
                        result_dict["body"] = body[:max_body_length] + "..."
                        result_dict["body_truncated"] = True
                        result_dict["body_full_length"] = len(body)

            # Rename rank to relevance_score
            if "rank" in result_dict:
                result_dict["relevance_score"] = result_dict.pop("rank")

            formatted_results.append(result_dict)

        # Build pagination response
        total_pages = (total_count + sanitized["limit"] - 1) // sanitized["limit"] if total_count > 0 else 1

        response = {
            "data": formatted_results,
            "meta": {
                "query": query,
                "parsed_query": parsed.query_text,
                "total": total_count,
                "page": page,
                "limit": sanitized["limit"],
                "total_pages": total_pages,
                "filters": {
                    "subreddit": subreddit,
                    "author": author,
                    "min_score": min_score,
                    "result_type": result_type,
                    "after": after,
                    "before": before,
                },
                "sort": sort,
            },
            "links": {"self": f"/api/v1/search?q={query}&page={page}&limit={sanitized['limit']}"},
        }

        # Add pagination links
        if page > 1:
            response["links"]["prev"] = f"/api/v1/search?q={query}&page={page - 1}&limit={sanitized['limit']}"
        if page < total_pages:
            response["links"]["next"] = f"/api/v1/search?q={query}&page={page + 1}&limit={sanitized['limit']}"

        return jsonify(response), 200

    except Exception as e:
        format_user_error(e, "api_search")
        return jsonify({"error": "Search failed. Please try a different query."}), 500


@api_v1.route("/schema", methods=["GET"])
@api_limiter.limit("100 per minute")
def api_schema():
    """
    API schema/discovery endpoint for MCP/AI introspection.

    Returns comprehensive API capabilities description including:
    - Available resources and endpoints
    - Valid fields for each resource
    - Supported filters and sort options
    - Search operators and syntax
    - Rate limits and constraints

    Returns:
        JSON schema describing API capabilities
    """
    schema = {
        "api_version": "1.0",
        "description": "Redd-Archiver REST API for Reddit archive access with 30+ endpoints",
        "total_endpoints": 33,
        "resources": {
            "posts": {
                "endpoints": [
                    "/posts",
                    "/posts/{id}",
                    "/posts/{id}/comments",
                    "/posts/{id}/context",
                    "/posts/{id}/comments/tree",
                    "/posts/{id}/related",
                    "/posts/random",
                    "/posts/aggregate",
                    "/posts/batch",
                ],
                "fields": list(VALID_POST_FIELDS),
                "searchable": True,
                "filterable_by": ["subreddit", "author", "min_score", "after", "before"],
                "sortable_by": ["score", "created_utc", "num_comments"],
                "supports_field_selection": True,
                "supports_truncation": True,
                "supports_export": True,
                "export_formats": ["json", "csv", "ndjson"],
                "truncation_field": "selftext",
            },
            "comments": {
                "endpoints": [
                    "/comments",
                    "/comments/{id}",
                    "/comments/random",
                    "/comments/aggregate",
                    "/comments/batch",
                ],
                "fields": list(VALID_COMMENT_FIELDS),
                "searchable": True,
                "filterable_by": ["subreddit", "author", "min_score", "after", "before"],
                "sortable_by": ["score", "created_utc"],
                "supports_field_selection": True,
                "supports_truncation": True,
                "supports_export": True,
                "export_formats": ["json", "csv", "ndjson"],
                "truncation_field": "body",
            },
            "users": {
                "endpoints": [
                    "/users",
                    "/users/{username}",
                    "/users/{username}/summary",
                    "/users/{username}/posts",
                    "/users/{username}/comments",
                    "/users/aggregate",
                    "/users/batch",
                ],
                "fields": list(VALID_USER_FIELDS),
                "filterable_by": ["min_posts", "min_comments"],
                "sortable_by": ["karma", "activity", "posts", "comments"],
                "supports_field_selection": True,
                "supports_export": True,
                "export_formats": ["json", "csv", "ndjson"],
            },
            "subreddits": {
                "endpoints": ["/subreddits", "/subreddits/{name}", "/subreddits/{name}/summary"],
                "fields": list(VALID_SUBREDDIT_FIELDS),
                "filterable_by": ["min_score", "min_comments"],
                "supports_field_selection": True,
                "supports_export": True,
                "export_formats": ["json", "csv", "ndjson"],
            },
        },
        "system": {
            "endpoints": ["/health", "/stats", "/schema", "/openapi.json"],
            "description": "Health checks, statistics, API discovery, and OpenAPI specification",
        },
        "search": {
            "endpoints": ["/search", "/search/explain"],
            "operators": [
                {"operator": "sub:", "aliases": ["subreddit:"], "description": "Filter by subreddit"},
                {"operator": "author:", "aliases": ["user:"], "description": "Filter by author"},
                {"operator": "score:", "syntax": "score:N+ or score:>N", "description": "Minimum score filter"},
                {"operator": "type:", "values": ["post", "comment"], "description": "Result type filter"},
                {
                    "operator": "sort:",
                    "values": ["relevance", "score", "date", "new", "old"],
                    "description": "Sort order",
                },
            ],
            "boolean_support": [
                {"syntax": '"phrase"', "description": "Exact phrase match"},
                {"syntax": "OR", "description": "Boolean OR (must be uppercase)"},
                {"syntax": "-term", "description": "Exclude term from results"},
            ],
            "sort_options": ["relevance", "score", "created_utc"],
            "default_sort": "relevance",
            "max_results_per_page": 100,
            "default_results_per_page": 25,
        },
        "pagination": {
            "parameters": ["page", "limit"],
            "max_limit": 100,
            "default_limit": 25,
            "format": "offset-based",
        },
        "field_selection": {
            "parameter": "fields",
            "description": "Comma-separated list of fields to return",
            "example": "?fields=id,title,score",
            "benefit": "Reduces response size and token usage for MCP/AI clients",
        },
        "truncation": {
            "parameters": [
                {"name": "max_body_length", "type": "int", "description": "Truncate body/selftext to N characters"},
                {
                    "name": "include_body",
                    "type": "bool",
                    "default": True,
                    "description": "Include body/selftext content",
                },
            ],
            "metadata_fields": ["body_truncated", "body_full_length", "selftext_truncated", "selftext_full_length"],
            "benefit": "Control response size while preserving length information",
        },
        "export_formats": {
            "formats": ["json", "csv", "ndjson"],
            "parameter": "format",
            "description": "Response format for list endpoints",
            "csv_notes": "Nested data flattened with dot notation (e.g., meta.page)",
            "ndjson_notes": "One JSON object per line, suitable for streaming",
        },
        "aggregation": {
            "endpoints": ["/posts/aggregate", "/comments/aggregate", "/users/aggregate"],
            "group_by_options": ["author", "subreddit", "created_utc"],
            "frequency_options": ["hour", "day", "week", "month", "year"],
            "timeout": "30 seconds",
            "description": "Group and analyze data with time-series support",
        },
        "batch_operations": {
            "endpoints": ["/posts/batch", "/comments/batch", "/users/batch"],
            "max_items": 100,
            "benefit": "Reduce N requests to 1 for MCP/AI efficiency",
            "description": "Fetch multiple resources in single request",
        },
        "context_endpoints": {
            "endpoints": [
                "/posts/{id}/context",
                "/posts/{id}/comments/tree",
                "/subreddits/{name}/summary",
                "/users/{username}/summary",
            ],
            "benefit": "Single-call data retrieval for MCP/AI clients",
            "description": "Get complete context without multiple round trips",
        },
        "advanced_features": {
            "random_sampling": {
                "endpoints": ["/posts/random", "/comments/random"],
                "supports_seed": True,
                "description": "Reproducible random sampling with optional seed parameter",
            },
            "related_content": {
                "endpoint": "/posts/{id}/related",
                "method": "FTS similarity ranking",
                "description": "Find similar posts using PostgreSQL full-text search",
            },
            "comment_tree": {
                "endpoint": "/posts/{id}/comments/tree",
                "method": "Recursive CTE",
                "max_depth": 20,
                "description": "Hierarchical comment structure with configurable depth",
            },
        },
        "rate_limits": {"requests_per_minute": 100, "description": "IP-based rate limiting"},
        "features": {
            "field_selection": True,
            "truncation_controls": True,
            "export_formats": True,
            "full_text_search": True,
            "search_operators": True,
            "aggregation": True,
            "batch_operations": True,
            "context_endpoints": True,
            "random_sampling": True,
            "related_content": True,
            "comment_tree": True,
            "pagination": True,
            "cors_enabled": True,
        },
    }

    return jsonify(schema), 200


@api_v1.route("/search/explain", methods=["GET"])
@api_limiter.limit("100 per minute")
def api_search_explain():
    """
    Debug/explain search query parsing.

    Shows how a search query will be interpreted without executing it.
    Useful for validating query construction before making actual searches.

    Query Parameters:
        q (str, required): Search query to explain

    Returns:
        JSON explanation of query parsing and filters
    """
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "Search query 'q' is required"}), 400

    # Parse search operators
    parsed = parse_search_operators(query)

    # Get additional parameters that would be applied
    type_param = request.args.get("type", "").lower()
    subreddit = request.args.get("subreddit", parsed.subreddit)
    author = request.args.get("author", parsed.author)
    min_score = request.args.get("min_score", type=int, default=parsed.min_score)
    after = request.args.get("after", type=int, default=None)
    before = request.args.get("before", type=int, default=None)
    sort = request.args.get("sort", parsed.sort_by or "relevance").lower()

    # Determine result type
    result_type = None
    if type_param in ("posts", "post"):
        result_type = "post"
    elif type_param in ("comments", "comment"):
        result_type = "comment"
    elif parsed.result_type:
        result_type = parsed.result_type

    # Build explanation
    explanation = {
        "input": query,
        "parsed": {
            "query_text": parsed.query_text,
            "extracted_operators": {
                "subreddit": parsed.subreddit,
                "author": parsed.author,
                "min_score": parsed.min_score,
                "result_type": parsed.result_type,
                "sort_by": parsed.sort_by,
            },
        },
        "effective_filters": {
            "subreddit": subreddit,
            "author": author,
            "min_score": min_score,
            "result_type": result_type,
            "after": after,
            "before": before,
        },
        "sort": sort,
        "search_mode": "PostgreSQL full-text search (websearch_to_tsquery)",
        "notes": [],
    }

    # Add helpful notes
    if parsed.query_text != query:
        explanation["notes"].append(f"Operators extracted from query, search text: '{parsed.query_text}'")
    if not parsed.query_text.strip():
        explanation["notes"].append("Warning: No search terms after operator extraction")
    if result_type:
        explanation["notes"].append(f"Results filtered to: {result_type}s only")
    if subreddit:
        explanation["notes"].append(f"Results filtered to subreddit: r/{subreddit}")
    if min_score > 0:
        explanation["notes"].append(f"Results filtered to score >= {min_score}")

    return jsonify(explanation), 200


# ============================================================================
# AGGREGATION ENDPOINTS
# ============================================================================

# Valid aggregation group_by values
VALID_GROUP_BY = {"author", "subreddit", "created_utc"}
VALID_FREQUENCY = {"hour", "day", "week", "month", "year"}


@api_v1.route("/posts/aggregate", methods=["GET"])
@api_limiter.limit("100 per minute")
def api_posts_aggregate():
    """
    Aggregate posts statistics grouped by author, subreddit, or time.

    Query Parameters:
        group_by (str, required): 'author', 'subreddit', or 'created_utc'
        frequency (str): Required if group_by=created_utc: 'hour', 'day', 'week', 'month', 'year'
        subreddit (str): Filter by subreddit
        author (str): Filter by author
        after (int): Unix timestamp - results after this date
        before (int): Unix timestamp - results before this date
        min_count (int): Minimum count threshold (default: 1)
        limit (int): Max results (default: 100, max: 1000)

    Returns:
        JSON with aggregated statistics
    """
    group_by = request.args.get("group_by", "").lower()
    if not group_by:
        return jsonify({"error": "group_by parameter is required. Valid values: author, subreddit, created_utc"}), 400
    if group_by not in VALID_GROUP_BY:
        return jsonify({"error": f"Invalid group_by value. Valid values: {', '.join(VALID_GROUP_BY)}"}), 400

    frequency = request.args.get("frequency", "").lower()
    if group_by == "created_utc" and not frequency:
        return jsonify(
            {
                "error": "frequency parameter required when group_by=created_utc. Valid values: hour, day, week, month, year"
            }
        ), 400
    if frequency and frequency not in VALID_FREQUENCY:
        return jsonify({"error": f"Invalid frequency value. Valid values: {', '.join(VALID_FREQUENCY)}"}), 400

    # Filter parameters
    subreddit = request.args.get("subreddit")
    author = request.args.get("author")
    after = request.args.get("after", type=int)
    before = request.args.get("before", type=int)
    min_count = request.args.get("min_count", type=int, default=1)
    limit = min(request.args.get("limit", type=int, default=100), 1000)

    try:
        db = get_db()

        with db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                # Set query timeout for expensive operations
                cur.execute("SET statement_timeout = '30000'")

                # Build query based on group_by
                if group_by == "created_utc":
                    # Time-based grouping
                    select_key = f"date_trunc('{frequency}', to_timestamp(created_utc)) as key"
                    group_key = "1"
                    order_by = "key ASC"
                else:
                    select_key = f"{group_by} as key"
                    group_key = group_by
                    order_by = "count DESC"

                # Build WHERE clauses
                where_clauses = []
                params = []

                if subreddit:
                    where_clauses.append("LOWER(subreddit) = LOWER(%s)")
                    params.append(subreddit)
                if author:
                    where_clauses.append("author = %s")
                    params.append(author)
                if after:
                    where_clauses.append("created_utc >= %s")
                    params.append(after)
                if before:
                    where_clauses.append("created_utc <= %s")
                    params.append(before)

                where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

                query = f"""
                    SELECT {select_key},
                           COUNT(*) as count,
                           SUM(score) as sum_score,
                           AVG(score)::numeric(10,2) as avg_score,
                           SUM(num_comments) as sum_comments
                    FROM posts
                    WHERE {where_sql}
                    GROUP BY {group_key}
                    HAVING COUNT(*) >= %s
                    ORDER BY {order_by}
                    LIMIT %s
                """
                params.extend([min_count, limit])

                cur.execute(query, params)
                rows = cur.fetchall()

                results = []
                for row in rows:
                    result = {
                        "key": str(row["key"]) if row["key"] else None,
                        "count": row["count"],
                        "sum_score": row["sum_score"],
                        "avg_score": float(row["avg_score"]) if row["avg_score"] else 0,
                        "sum_comments": row["sum_comments"],
                    }
                    results.append(result)

                return jsonify(
                    {
                        "data": results,
                        "meta": {
                            "group_by": group_by,
                            "frequency": frequency if group_by == "created_utc" else None,
                            "filters": {
                                "subreddit": subreddit,
                                "author": author,
                                "after": after,
                                "before": before,
                                "min_count": min_count,
                            },
                            "total_results": len(results),
                            "limit": limit,
                        },
                    }
                ), 200

    except Exception as e:
        format_user_error(e, "api_posts_aggregate")
        if "statement timeout" in str(e).lower():
            return jsonify({"error": "Query timed out. Try narrower filters or smaller limit."}), 408
        return jsonify({"error": "Aggregation failed."}), 500


@api_v1.route("/comments/aggregate", methods=["GET"])
@api_limiter.limit("100 per minute")
def api_comments_aggregate():
    """
    Aggregate comments statistics grouped by author, subreddit, or time.

    Query Parameters:
        group_by (str, required): 'author', 'subreddit', or 'created_utc'
        frequency (str): Required if group_by=created_utc: 'hour', 'day', 'week', 'month', 'year'
        subreddit (str): Filter by subreddit
        author (str): Filter by author
        after (int): Unix timestamp - results after this date
        before (int): Unix timestamp - results before this date
        min_count (int): Minimum count threshold (default: 1)
        limit (int): Max results (default: 100, max: 1000)

    Returns:
        JSON with aggregated statistics
    """
    group_by = request.args.get("group_by", "").lower()
    if not group_by:
        return jsonify({"error": "group_by parameter is required. Valid values: author, subreddit, created_utc"}), 400
    if group_by not in VALID_GROUP_BY:
        return jsonify({"error": f"Invalid group_by value. Valid values: {', '.join(VALID_GROUP_BY)}"}), 400

    frequency = request.args.get("frequency", "").lower()
    if group_by == "created_utc" and not frequency:
        return jsonify(
            {
                "error": "frequency parameter required when group_by=created_utc. Valid values: hour, day, week, month, year"
            }
        ), 400
    if frequency and frequency not in VALID_FREQUENCY:
        return jsonify({"error": f"Invalid frequency value. Valid values: {', '.join(VALID_FREQUENCY)}"}), 400

    # Filter parameters
    subreddit = request.args.get("subreddit")
    author = request.args.get("author")
    after = request.args.get("after", type=int)
    before = request.args.get("before", type=int)
    min_count = request.args.get("min_count", type=int, default=1)
    limit = min(request.args.get("limit", type=int, default=100), 1000)

    try:
        db = get_db()

        with db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                # Set query timeout
                cur.execute("SET statement_timeout = '30000'")

                # Build query based on group_by
                if group_by == "created_utc":
                    select_key = f"date_trunc('{frequency}', to_timestamp(created_utc)) as key"
                    group_key = "1"
                    order_by = "key ASC"
                else:
                    select_key = f"{group_by} as key"
                    group_key = group_by
                    order_by = "count DESC"

                # Build WHERE clauses
                where_clauses = []
                params = []

                if subreddit:
                    where_clauses.append("LOWER(subreddit) = LOWER(%s)")
                    params.append(subreddit)
                if author:
                    where_clauses.append("author = %s")
                    params.append(author)
                if after:
                    where_clauses.append("created_utc >= %s")
                    params.append(after)
                if before:
                    where_clauses.append("created_utc <= %s")
                    params.append(before)

                where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

                query = f"""
                    SELECT {select_key},
                           COUNT(*) as count,
                           SUM(score) as sum_score,
                           AVG(score)::numeric(10,2) as avg_score
                    FROM comments
                    WHERE {where_sql}
                    GROUP BY {group_key}
                    HAVING COUNT(*) >= %s
                    ORDER BY {order_by}
                    LIMIT %s
                """
                params.extend([min_count, limit])

                cur.execute(query, params)
                rows = cur.fetchall()

                results = []
                for row in rows:
                    result = {
                        "key": str(row["key"]) if row["key"] else None,
                        "count": row["count"],
                        "sum_score": row["sum_score"],
                        "avg_score": float(row["avg_score"]) if row["avg_score"] else 0,
                    }
                    results.append(result)

                return jsonify(
                    {
                        "data": results,
                        "meta": {
                            "group_by": group_by,
                            "frequency": frequency if group_by == "created_utc" else None,
                            "filters": {
                                "subreddit": subreddit,
                                "author": author,
                                "after": after,
                                "before": before,
                                "min_count": min_count,
                            },
                            "total_results": len(results),
                            "limit": limit,
                        },
                    }
                ), 200

    except Exception as e:
        format_user_error(e, "api_comments_aggregate")
        if "statement timeout" in str(e).lower():
            return jsonify({"error": "Query timed out. Try narrower filters or smaller limit."}), 408
        return jsonify({"error": "Aggregation failed."}), 500


@api_v1.route("/users/aggregate", methods=["GET"])
@api_limiter.limit("100 per minute")
def api_users_aggregate():
    """
    Aggregate user statistics with activity filters.

    Query Parameters:
        subreddit (str): Filter users active in this subreddit
        min_posts (int): Minimum post count (default: 0)
        min_comments (int): Minimum comment count (default: 0)
        min_total (int): Minimum total activity (default: 0)
        sort_by (str): Sort field: 'posts', 'comments', 'total', 'karma' (default: 'total')
        sort (str): Sort order: 'asc' or 'desc' (default: 'desc')
        limit (int): Max results (default: 100, max: 1000)
        page (int): Page number (default: 1)

    Returns:
        JSON with aggregated user statistics
    """
    subreddit = request.args.get("subreddit")
    min_posts = request.args.get("min_posts", type=int, default=0)
    min_comments = request.args.get("min_comments", type=int, default=0)
    min_total = request.args.get("min_total", type=int, default=0)
    sort_by = request.args.get("sort_by", "total").lower()
    sort_order = request.args.get("sort", "desc").lower()
    limit = min(request.args.get("limit", type=int, default=100), 1000)
    page = request.args.get("page", type=int, default=1)
    offset = (page - 1) * limit

    # Validate sort_by
    valid_sort_by = {
        "posts": "post_count",
        "comments": "comment_count",
        "total": "total_activity",
        "karma": "total_karma",
        "username": "username",
    }
    sort_column = valid_sort_by.get(sort_by, "total_activity")
    sort_dir = "ASC" if sort_order == "asc" else "DESC"

    try:
        db = get_db()

        with db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SET statement_timeout = '30000'")

                # Build WHERE clauses
                where_clauses = ["post_count >= %s", "comment_count >= %s", "total_activity >= %s"]
                params = [min_posts, min_comments, min_total]

                if subreddit:
                    # If filtering by subreddit, need a different approach
                    # For now, just filter from the users table if subreddit activity exists
                    where_clauses.append("subreddit_activity ? %s")
                    params.append(subreddit.lower())

                where_sql = " AND ".join(where_clauses)

                # Count total
                count_query = f"""
                    SELECT COUNT(*) as count FROM users WHERE {where_sql}
                """
                cur.execute(count_query, params)
                total_count = cur.fetchone()["count"]

                # Get paginated results
                query = f"""
                    SELECT username, post_count, comment_count, total_activity, total_karma
                    FROM users
                    WHERE {where_sql}
                    ORDER BY {sort_column} {sort_dir}
                    LIMIT %s OFFSET %s
                """
                params.extend([limit, offset])
                cur.execute(query, params)
                rows = cur.fetchall()

                results = []
                for row in rows:
                    results.append(
                        {
                            "username": row["username"],
                            "post_count": row["post_count"],
                            "comment_count": row["comment_count"],
                            "total_activity": row["total_activity"],
                            "total_karma": row["total_karma"],
                        }
                    )

                return jsonify(
                    {
                        "data": results,
                        "meta": {
                            "filters": {
                                "subreddit": subreddit,
                                "min_posts": min_posts,
                                "min_comments": min_comments,
                                "min_total": min_total,
                            },
                            "sort_by": sort_by,
                            "sort": sort_order,
                            "total": total_count,
                            "page": page,
                            "limit": limit,
                            "total_pages": (total_count + limit - 1) // limit if total_count > 0 else 1,
                        },
                    }
                ), 200

    except Exception as e:
        format_user_error(e, "api_users_aggregate")
        if "statement timeout" in str(e).lower():
            return jsonify({"error": "Query timed out. Try narrower filters."}), 408
        return jsonify({"error": "User aggregation failed."}), 500


# ============================================================================
# BATCH LOOKUP ENDPOINTS
# ============================================================================


@api_v1.route("/posts/batch", methods=["POST"])
@api_limiter.limit("100 per minute")
def api_posts_batch():
    """
    Batch lookup multiple posts by ID.

    Request Body (JSON):
        {"ids": ["post_id1", "post_id2", ...]}

    Query Parameters:
        fields (str): Comma-separated list of fields to return
        max_body_length (int): Truncate selftext to this length
        include_body (bool): Include selftext (default: true)

    Returns:
        JSON with found posts and list of not_found IDs
    """
    data = request.get_json()
    if not data or "ids" not in data:
        return jsonify({"error": "Request body must include 'ids' array"}), 400

    ids = data.get("ids", [])
    if not isinstance(ids, list):
        return jsonify({"error": "'ids' must be an array"}), 400
    if len(ids) > 100:
        return jsonify({"error": "Maximum 100 IDs per request"}), 400
    if len(ids) == 0:
        return jsonify({"data": [], "not_found": [], "meta": {"requested": 0, "found": 0, "not_found": 0}}), 200

    # Field selection and truncation
    fields_param = request.args.get("fields")
    requested_fields = parse_fields_param(fields_param)
    max_body_length, include_body = get_truncation_params()

    if requested_fields:
        field_error = validate_fields(requested_fields, VALID_POST_FIELDS)
        if field_error:
            return jsonify({"error": field_error}), 400

    try:
        db = get_db()

        with db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, subreddit, author, title, selftext, url, domain,
                           score, num_comments, created_utc, permalink,
                           is_self, over_18, locked, stickied
                    FROM posts
                    WHERE id = ANY(%s)
                """,
                    (ids,),
                )

                found_ids = set()
                posts = []
                for row in cur.fetchall():
                    found_ids.add(row["id"])
                    post_data = {
                        "id": row["id"],
                        "subreddit": row["subreddit"],
                        "author": row["author"],
                        "title": row["title"],
                        "selftext": row["selftext"],
                        "url": row["url"],
                        "domain": row["domain"],
                        "score": row["score"],
                        "num_comments": row["num_comments"],
                        "created_utc": row["created_utc"],
                        "created_at": format_unix_timestamp(row["created_utc"]),
                        "permalink": row["permalink"],
                        "is_self": row["is_self"],
                        "nsfw": row["over_18"],
                        "locked": row["locked"],
                        "stickied": row["stickied"],
                    }
                    post_data = process_post_response(post_data, requested_fields, max_body_length, include_body)
                    posts.append(post_data)

                not_found = [id for id in ids if id not in found_ids]

                return jsonify(
                    {
                        "data": posts,
                        "not_found": not_found,
                        "meta": {"requested": len(ids), "found": len(posts), "not_found": len(not_found)},
                    }
                ), 200

    except Exception as e:
        format_user_error(e, "api_posts_batch")
        return jsonify({"error": "Batch lookup failed."}), 500


@api_v1.route("/comments/batch", methods=["POST"])
@api_limiter.limit("100 per minute")
def api_comments_batch():
    """
    Batch lookup multiple comments by ID.

    Request Body (JSON):
        {"ids": ["comment_id1", "comment_id2", ...]}

    Query Parameters:
        fields (str): Comma-separated list of fields to return
        max_body_length (int): Truncate body to this length
        include_body (bool): Include body (default: true)

    Returns:
        JSON with found comments and list of not_found IDs
    """
    data = request.get_json()
    if not data or "ids" not in data:
        return jsonify({"error": "Request body must include 'ids' array"}), 400

    ids = data.get("ids", [])
    if not isinstance(ids, list):
        return jsonify({"error": "'ids' must be an array"}), 400
    if len(ids) > 100:
        return jsonify({"error": "Maximum 100 IDs per request"}), 400
    if len(ids) == 0:
        return jsonify({"data": [], "not_found": [], "meta": {"requested": 0, "found": 0, "not_found": 0}}), 200

    # Field selection and truncation
    fields_param = request.args.get("fields")
    requested_fields = parse_fields_param(fields_param)
    max_body_length, include_body = get_truncation_params()

    if requested_fields:
        field_error = validate_fields(requested_fields, VALID_COMMENT_FIELDS)
        if field_error:
            return jsonify({"error": field_error}), 400

    try:
        db = get_db()

        with db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, post_id, parent_id, author, body, score,
                           created_utc, subreddit, permalink, depth
                    FROM comments
                    WHERE id = ANY(%s)
                """,
                    (ids,),
                )

                found_ids = set()
                comments = []
                for row in cur.fetchall():
                    found_ids.add(row["id"])
                    comment_data = {
                        "id": row["id"],
                        "post_id": row["post_id"],
                        "parent_id": row["parent_id"],
                        "author": row["author"],
                        "body": row["body"],
                        "score": row["score"],
                        "created_utc": row["created_utc"],
                        "created_at": format_unix_timestamp(row["created_utc"]),
                        "subreddit": row["subreddit"],
                        "permalink": row["permalink"],
                        "depth": row["depth"],
                    }
                    comment_data = process_comment_response(
                        comment_data, requested_fields, max_body_length, include_body
                    )
                    comments.append(comment_data)

                not_found = [id for id in ids if id not in found_ids]

                return jsonify(
                    {
                        "data": comments,
                        "not_found": not_found,
                        "meta": {"requested": len(ids), "found": len(comments), "not_found": len(not_found)},
                    }
                ), 200

    except Exception as e:
        format_user_error(e, "api_comments_batch")
        return jsonify({"error": "Batch lookup failed."}), 500


@api_v1.route("/users/batch", methods=["POST"])
@api_limiter.limit("100 per minute")
def api_users_batch():
    """
    Batch lookup multiple users by username.

    Request Body (JSON):
        {"usernames": ["username1", "username2", ...]}

    Query Parameters:
        fields (str): Comma-separated list of fields to return

    Returns:
        JSON with found users and list of not_found usernames
    """
    data = request.get_json()
    if not data or "usernames" not in data:
        return jsonify({"error": "Request body must include 'usernames' array"}), 400

    usernames = data.get("usernames", [])
    if not isinstance(usernames, list):
        return jsonify({"error": "'usernames' must be an array"}), 400
    if len(usernames) > 100:
        return jsonify({"error": "Maximum 100 usernames per request"}), 400
    if len(usernames) == 0:
        return jsonify({"data": [], "not_found": [], "meta": {"requested": 0, "found": 0, "not_found": 0}}), 200

    # Field selection
    fields_param = request.args.get("fields")
    requested_fields = parse_fields_param(fields_param)

    if requested_fields:
        field_error = validate_fields(requested_fields, VALID_USER_FIELDS)
        if field_error:
            return jsonify({"error": field_error}), 400

    try:
        db = get_db()

        with db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT username, post_count, comment_count, total_activity,
                           total_karma, first_seen_utc, last_seen_utc
                    FROM users
                    WHERE username = ANY(%s)
                """,
                    (usernames,),
                )

                found_usernames = set()
                users = []
                for row in cur.fetchall():
                    found_usernames.add(row["username"])
                    user_data = {
                        "username": row["username"],
                        "post_count": row["post_count"],
                        "comment_count": row["comment_count"],
                        "total_activity": row["total_activity"],
                        "total_karma": row["total_karma"],
                        "first_seen_utc": row["first_seen_utc"],
                        "first_seen_at": format_unix_timestamp(row["first_seen_utc"]),
                        "last_seen_utc": row["last_seen_utc"],
                        "last_seen_at": format_unix_timestamp(row["last_seen_utc"]),
                    }
                    user_data = process_user_response(user_data, requested_fields)
                    users.append(user_data)

                not_found = [username for username in usernames if username not in found_usernames]

                return jsonify(
                    {
                        "data": users,
                        "not_found": not_found,
                        "meta": {"requested": len(usernames), "found": len(users), "not_found": len(not_found)},
                    }
                ), 200

    except Exception as e:
        format_user_error(e, "api_users_batch")
        return jsonify({"error": "Batch lookup failed."}), 500


# ============================================================================
# CONTEXT AND SUMMARY ENDPOINTS (MCP-Critical)
# ============================================================================


@api_v1.route("/posts/<post_id>/context", methods=["GET"])
@api_limiter.limit("100 per minute")
def api_post_context(post_id: str):
    """
    Get complete context for a discussion in a single call.

    Returns the post with its top comments and metadata, optimized for
    AI/MCP clients to understand a discussion in one request.

    Args:
        post_id: Post ID

    Query Parameters:
        top_comments (int): Number of top-level comments (default: 10, max: 50)
        max_depth (int): Maximum reply depth (default: 2, max: 5)
        max_body_length (int): Truncate comment bodies (default: 500)
        sort (str): Comment sort: 'score', 'created_utc' (default: 'score')

    Returns:
        JSON with post, comments tree, and discussion metadata
    """
    # Validate post_id format
    if not re.match(r"^[a-z0-9_]+$", post_id, re.IGNORECASE):
        return jsonify({"error": "Invalid post ID format"}), 400

    top_comments = min(request.args.get("top_comments", type=int, default=10), 50)
    max_depth = min(request.args.get("max_depth", type=int, default=2), 5)
    max_body_length = request.args.get("max_body_length", type=int, default=500)
    sort = request.args.get("sort", "score").lower()
    sort_column = "score DESC" if sort == "score" else "created_utc ASC"

    try:
        db = get_db()

        with db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                # Get the post
                cur.execute(
                    """
                    SELECT id, subreddit, author, title, selftext, url, domain,
                           score, num_comments, created_utc, permalink,
                           is_self, over_18, locked, stickied, platform
                    FROM posts WHERE id = %s
                """,
                    (post_id,),
                )

                post_row = cur.fetchone()
                if not post_row:
                    return jsonify({"error": "Post not found"}), 404

                post_data = {
                    "id": post_row["id"],
                    "subreddit": post_row["subreddit"],
                    "author": post_row["author"],
                    "title": post_row["title"],
                    "selftext": post_row["selftext"],
                    "url": post_row["url"],
                    "domain": post_row["domain"],
                    "score": post_row["score"],
                    "num_comments": post_row["num_comments"],
                    "created_utc": post_row["created_utc"],
                    "created_at": format_unix_timestamp(post_row["created_utc"]),
                    "permalink": post_row["permalink"],
                    "is_self": post_row["is_self"],
                    "nsfw": post_row["over_18"],
                    "locked": post_row["locked"],
                    "stickied": post_row["stickied"],
                    "platform": post_row.get("platform", "reddit"),
                }

                # Get top-level comments IDs first
                # Top-level comments have parent_id like 't3_{post_id}'
                cur.execute(
                    f"""
                    SELECT id
                    FROM comments
                    WHERE post_id = %s AND parent_id LIKE 't3_%%'
                    ORDER BY {sort_column}
                    LIMIT %s
                """,
                    (post_id, top_comments),
                )

                top_comment_ids = [row["id"] for row in cur.fetchall()]

                if not top_comment_ids:
                    # No comments - return post only
                    return jsonify(
                        {
                            "post": post_data,
                            "comments": [],
                            "meta": {
                                "total_comments": 0,
                                "returned_comments": 0,
                                "unique_authors": 0,
                                "max_depth_returned": 0,
                            },
                        }
                    ), 200

                # Get top-level comments with replies using recursive CTE
                cur.execute(
                    """
                    WITH RECURSIVE comment_tree AS (
                        -- Top-level comments (pre-selected)
                        SELECT id, parent_id, author, body, score, created_utc, depth, permalink,
                               0 as tree_depth
                        FROM comments
                        WHERE id = ANY(%s)

                        UNION ALL

                        -- Replies up to max_depth
                        SELECT c.id, c.parent_id, c.author, c.body, c.score, c.created_utc,
                               c.depth, c.permalink, ct.tree_depth + 1
                        FROM comments c
                        JOIN comment_tree ct ON c.parent_id = ct.id
                        WHERE ct.tree_depth < %s
                    )
                    SELECT * FROM comment_tree
                    ORDER BY tree_depth, score DESC
                """,
                    (top_comment_ids, max_depth),
                )

                # Build comment tree
                comments_by_id = {}
                top_level_comments = []

                for row in cur.fetchall():
                    body = row["body"] or ""
                    truncated = len(body) > max_body_length
                    comment = {
                        "id": row["id"],
                        "author": row["author"],
                        "body": body[:max_body_length] + "..." if truncated else body,
                        "body_truncated": truncated,
                        "score": row["score"],
                        "created_utc": row["created_utc"],
                        "created_at": format_unix_timestamp(row["created_utc"]),
                        "depth": row["tree_depth"],
                        "permalink": row["permalink"],
                        "replies": [],
                    }
                    comments_by_id[row["id"]] = comment

                    parent_id = row["parent_id"]
                    if parent_id and parent_id in comments_by_id:
                        comments_by_id[parent_id]["replies"].append(comment)
                    elif row["tree_depth"] == 0:
                        top_level_comments.append(comment)

                # Get comment statistics
                cur.execute(
                    """
                    SELECT COUNT(*) as total,
                           COUNT(DISTINCT author) as unique_authors,
                           AVG(score)::numeric(10,2) as avg_score,
                           MAX(depth) as max_depth
                    FROM comments WHERE post_id = %s
                """,
                    (post_id,),
                )
                stats_row = cur.fetchone()

                return jsonify(
                    {
                        "post": post_data,
                        "comments": top_level_comments,
                        "meta": {
                            "total_comments": post_row["num_comments"],
                            "shown_comments": len(comments_by_id),
                            "unique_authors": stats_row["unique_authors"] or 0,
                            "avg_comment_score": float(stats_row["avg_score"]) if stats_row["avg_score"] else 0,
                            "max_depth_found": stats_row["max_depth"] or 0,
                            "requested_depth": max_depth,
                            "sort": sort,
                        },
                    }
                ), 200

    except Exception as e:
        format_user_error(e, "api_post_context")
        return jsonify({"error": "Failed to retrieve post context."}), 500


@api_v1.route("/subreddits/<subreddit>/summary", methods=["GET"])
@api_limiter.limit("100 per minute")
def api_subreddit_summary(subreddit: str):
    """
    Get quick overview statistics for a subreddit.

    Returns comprehensive stats without fetching detailed lists,
    optimized for AI/MCP clients to quickly orient themselves.

    Args:
        subreddit: Subreddit name

    Returns:
        JSON with subreddit statistics, time range, and top contributors
    """
    if not re.match(r"^[a-zA-Z0-9_]{2,21}$", subreddit):
        return jsonify({"error": "Invalid subreddit name format"}), 400

    try:
        db = get_db()

        with db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SET statement_timeout = '30000'")

                # Get basic stats
                cur.execute(
                    """
                    SELECT
                        COUNT(*) as total_posts,
                        COUNT(DISTINCT author) as unique_users,
                        MIN(created_utc) as earliest,
                        MAX(created_utc) as latest,
                        AVG(score)::numeric(10,2) as avg_score,
                        SUM(num_comments) as total_comments_on_posts
                    FROM posts
                    WHERE LOWER(subreddit) = LOWER(%s)
                """,
                    (subreddit,),
                )

                stats = cur.fetchone()
                if stats["total_posts"] == 0:
                    return jsonify({"error": "Subreddit not found"}), 404

                # Get comment count
                cur.execute(
                    """
                    SELECT COUNT(*) as comment_count
                    FROM comments
                    WHERE LOWER(subreddit) = LOWER(%s)
                """,
                    (subreddit,),
                )
                comment_count = cur.fetchone()["comment_count"]

                # Get top authors by post count
                cur.execute(
                    """
                    SELECT author, COUNT(*) as posts,
                           COALESCE((SELECT COUNT(*) FROM comments c
                                     WHERE c.author = p.author
                                     AND LOWER(c.subreddit) = LOWER(%s)), 0) as comments
                    FROM posts p
                    WHERE LOWER(subreddit) = LOWER(%s)
                    AND author != '[deleted]'
                    GROUP BY author
                    ORDER BY posts DESC
                    LIMIT 5
                """,
                    (subreddit, subreddit),
                )

                top_authors = []
                for row in cur.fetchall():
                    top_authors.append({"username": row["author"], "posts": row["posts"], "comments": row["comments"]})

                # Get recent activity (last 7 and 30 days)
                import time

                now = int(time.time())
                week_ago = now - (7 * 24 * 60 * 60)
                month_ago = now - (30 * 24 * 60 * 60)

                cur.execute(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE created_utc >= %s) as posts_7d,
                        COUNT(*) FILTER (WHERE created_utc >= %s) as posts_30d
                    FROM posts
                    WHERE LOWER(subreddit) = LOWER(%s)
                """,
                    (week_ago, month_ago, subreddit),
                )
                recent = cur.fetchone()

                # Calculate time span
                time_span_days = 0
                if stats["earliest"] and stats["latest"]:
                    time_span_days = (stats["latest"] - stats["earliest"]) // (24 * 60 * 60)

                # Determine activity trend
                avg_daily = stats["total_posts"] / max(time_span_days, 1)
                recent_daily = recent["posts_7d"] / 7 if recent["posts_7d"] else 0

                if recent_daily > avg_daily * 1.5:
                    activity_trend = "increasing"
                elif recent_daily < avg_daily * 0.5:
                    activity_trend = "decreasing"
                else:
                    activity_trend = "stable"

                return jsonify(
                    {
                        "subreddit": subreddit,
                        "stats": {
                            "total_posts": stats["total_posts"],
                            "total_comments": comment_count,
                            "unique_users": stats["unique_users"],
                            "avg_posts_per_day": round(avg_daily, 2),
                            "avg_score": float(stats["avg_score"]) if stats["avg_score"] else 0,
                        },
                        "time_range": {
                            "earliest": format_unix_timestamp(stats["earliest"]),
                            "latest": format_unix_timestamp(stats["latest"]),
                            "span_days": time_span_days,
                        },
                        "top_authors": top_authors,
                        "activity_trend": activity_trend,
                        "recent_activity": {"posts_7d": recent["posts_7d"], "posts_30d": recent["posts_30d"]},
                    }
                ), 200

    except Exception as e:
        format_user_error(e, "api_subreddit_summary")
        return jsonify({"error": "Failed to retrieve subreddit summary."}), 500


@api_v1.route("/users/<username>/summary", methods=["GET"])
@api_limiter.limit("100 per minute")
def api_user_summary(username: str):
    """
    Get quick overview statistics for a user.

    Returns comprehensive stats without fetching detailed lists,
    optimized for AI/MCP clients to quickly orient themselves.

    Args:
        username: Username

    Returns:
        JSON with user statistics, activity patterns, and top subreddits
    """
    if not re.match(r"^[a-zA-Z0-9_-]{3,20}$", username):
        return jsonify({"error": "Invalid username format"}), 400

    try:
        db = get_db()

        with db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SET statement_timeout = '30000'")

                # Get user from users table
                cur.execute(
                    """
                    SELECT username, post_count, comment_count, total_activity,
                           total_karma, first_seen_utc, last_seen_utc, subreddit_activity
                    FROM users
                    WHERE username = %s
                """,
                    (username,),
                )

                user = cur.fetchone()
                if not user:
                    return jsonify({"error": "User not found"}), 404

                # Get average scores
                cur.execute(
                    """
                    SELECT AVG(score)::numeric(10,2) as avg_post_score
                    FROM posts WHERE author = %s
                """,
                    (username,),
                )
                avg_post = cur.fetchone()

                cur.execute(
                    """
                    SELECT AVG(score)::numeric(10,2) as avg_comment_score
                    FROM comments WHERE author = %s
                """,
                    (username,),
                )
                avg_comment = cur.fetchone()

                # Parse subreddit_activity JSON for top subreddits
                top_subreddits = []
                if user["subreddit_activity"]:
                    activity = user["subreddit_activity"]
                    if isinstance(activity, dict):
                        sorted_subs = sorted(
                            activity.items(),
                            key=lambda x: x[1].get("total", 0) if isinstance(x[1], dict) else x[1],
                            reverse=True,
                        )[:5]
                        for sub, data in sorted_subs:
                            if isinstance(data, dict):
                                top_subreddits.append(
                                    {"name": sub, "posts": data.get("posts", 0), "comments": data.get("comments", 0)}
                                )
                            else:
                                top_subreddits.append({"name": sub, "activity": data})

                # Calculate active days
                active_days = 0
                if user["first_seen_utc"] and user["last_seen_utc"]:
                    active_days = (user["last_seen_utc"] - user["first_seen_utc"]) // (24 * 60 * 60)

                # Determine activity pattern
                if user["total_activity"] == 0:
                    activity_pattern = "inactive"
                elif user["post_count"] > user["comment_count"] * 2:
                    activity_pattern = "primarily posts"
                elif user["comment_count"] > user["post_count"] * 5:
                    activity_pattern = "primarily comments"
                else:
                    activity_pattern = "balanced contributor"

                return jsonify(
                    {
                        "username": username,
                        "stats": {
                            "total_posts": user["post_count"],
                            "total_comments": user["comment_count"],
                            "total_karma": user["total_karma"],
                            "avg_post_score": float(avg_post["avg_post_score"]) if avg_post["avg_post_score"] else 0,
                            "avg_comment_score": float(avg_comment["avg_comment_score"])
                            if avg_comment["avg_comment_score"]
                            else 0,
                        },
                        "time_range": {
                            "first_seen": format_unix_timestamp(user["first_seen_utc"]),
                            "last_seen": format_unix_timestamp(user["last_seen_utc"]),
                            "active_days": active_days,
                        },
                        "top_subreddits": top_subreddits,
                        "activity_pattern": activity_pattern,
                    }
                ), 200

    except Exception as e:
        format_user_error(e, "api_user_summary")
        return jsonify({"error": "Failed to retrieve user summary."}), 500


# ============================================================================
# ADVANCED ENDPOINTS (Comment Tree, Random, Related)
# ============================================================================


@api_v1.route("/posts/<post_id>/comments/tree", methods=["GET"])
@api_limiter.limit("100 per minute")
def api_post_comments_tree(post_id: str):
    """
    Get hierarchical comment tree for a post.

    Returns all comments in a nested tree structure for thread analysis.

    Args:
        post_id: Post ID

    Query Parameters:
        max_depth (int): Maximum nesting depth (default: 10, max: 20)
        sort (str): Sort order: 'score', 'created_utc' (default: 'score')
        limit (int): Max top-level comments (default: 100, max: 500)
        max_body_length (int): Truncate bodies (default: unlimited)

    Returns:
        JSON with hierarchical comment tree and metadata
    """
    if not re.match(r"^[a-zA-Z0-9]{1,10}$", post_id):
        return jsonify({"error": "Invalid post ID format"}), 400

    max_depth = min(request.args.get("max_depth", type=int, default=10), 20)
    sort = request.args.get("sort", "score").lower()
    limit = min(request.args.get("limit", type=int, default=100), 500)
    max_body_length = request.args.get("max_body_length", type=int, default=None)

    try:
        db = get_db()

        with db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SET statement_timeout = '30000'")

                # Use recursive CTE to build full tree
                # Top-level comments have parent_id like 't3_{post_id}'
                cur.execute(
                    """
                    WITH RECURSIVE comment_tree AS (
                        -- Top-level comments
                        SELECT id, parent_id, author, body, score, created_utc, depth, permalink,
                               0 as tree_depth,
                               ARRAY[id] as path
                        FROM comments
                        WHERE post_id = %s AND parent_id LIKE 't3_%%'

                        UNION ALL

                        -- Recursive replies
                        SELECT c.id, c.parent_id, c.author, c.body, c.score, c.created_utc,
                               c.depth, c.permalink, ct.tree_depth + 1,
                               ct.path || c.id
                        FROM comments c
                        JOIN comment_tree ct ON c.parent_id = ('t1_' || ct.id)
                        WHERE ct.tree_depth < %s
                    )
                    SELECT * FROM comment_tree
                    ORDER BY path
                """,
                    (post_id, max_depth),
                )

                # Build nested tree structure
                comments_by_id = {}
                top_level = []
                max_depth_found = 0

                for row in cur.fetchall():
                    body = row["body"] or ""
                    truncated = False
                    if max_body_length and len(body) > max_body_length:
                        body = body[:max_body_length] + "..."
                        truncated = True

                    comment = {
                        "id": row["id"],
                        "author": row["author"],
                        "body": body,
                        "score": row["score"],
                        "created_utc": row["created_utc"],
                        "created_at": format_unix_timestamp(row["created_utc"]),
                        "depth": row["tree_depth"],
                        "permalink": row["permalink"],
                        "children": [],
                    }
                    if truncated:
                        comment["body_truncated"] = True

                    comments_by_id[row["id"]] = comment
                    max_depth_found = max(max_depth_found, row["tree_depth"])

                    parent_id = row["parent_id"]
                    if parent_id and parent_id in comments_by_id:
                        comments_by_id[parent_id]["children"].append(comment)
                    elif row["tree_depth"] == 0:
                        top_level.append(comment)

                # Sort top-level and limit
                if sort == "score":
                    top_level.sort(key=lambda x: x["score"], reverse=True)
                else:
                    top_level.sort(key=lambda x: x["created_utc"])
                top_level = top_level[:limit]

                return jsonify(
                    {
                        "post_id": post_id,
                        "comments": top_level,
                        "meta": {
                            "total_comments": len(comments_by_id),
                            "top_level_shown": len(top_level),
                            "max_depth_found": max_depth_found,
                            "requested_depth": max_depth,
                            "sort": sort,
                            "truncated": len(top_level) < len([c for c in comments_by_id.values() if c["depth"] == 0]),
                        },
                    }
                ), 200

    except Exception as e:
        format_user_error(e, "api_post_comments_tree")
        if "statement timeout" in str(e).lower():
            return jsonify({"error": "Query timed out. Try smaller depth or limit."}), 408
        return jsonify({"error": "Failed to retrieve comment tree."}), 500


@api_v1.route("/posts/random", methods=["GET"])
@api_limiter.limit("100 per minute")
def api_posts_random():
    """
    Get random sample of posts for statistical analysis.

    Uses PostgreSQL's random sampling for efficient retrieval.

    Query Parameters:
        n (int): Number of samples (default: 10, max: 100)
        subreddit (str): Filter to subreddit
        after (int): Unix timestamp - posts after this date
        before (int): Unix timestamp - posts before this date
        seed (int): Random seed for reproducibility

    Returns:
        JSON with random post samples and sampling metadata
    """
    n = min(request.args.get("n", type=int, default=10), 100)
    subreddit = request.args.get("subreddit")
    after = request.args.get("after", type=int)
    before = request.args.get("before", type=int)
    seed = request.args.get("seed", type=int)

    try:
        db = get_db()

        with db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                # Build WHERE clauses
                where_clauses = []
                params = []

                if subreddit:
                    where_clauses.append("LOWER(subreddit) = LOWER(%s)")
                    params.append(subreddit)
                if after:
                    where_clauses.append("created_utc >= %s")
                    params.append(after)
                if before:
                    where_clauses.append("created_utc <= %s")
                    params.append(before)

                where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

                # Get population count
                cur.execute(f"SELECT COUNT(*) as count FROM posts WHERE {where_sql}", params)
                population_size = cur.fetchone()["count"]

                # Use seeded random if seed provided
                if seed is not None:
                    # Use md5 hash with seed for reproducible random
                    order_by = f"md5(id || '{seed}')"
                else:
                    order_by = "RANDOM()"

                # Get random samples
                cur.execute(
                    f"""
                    SELECT id, subreddit, author, title, selftext, url, domain,
                           score, num_comments, created_utc, permalink
                    FROM posts
                    WHERE {where_sql}
                    ORDER BY {order_by}
                    LIMIT %s
                """,
                    params + [n],
                )

                posts = []
                for row in cur.fetchall():
                    posts.append(
                        {
                            "id": row["id"],
                            "subreddit": row["subreddit"],
                            "author": row["author"],
                            "title": row["title"],
                            "selftext": row["selftext"][:500] if row["selftext"] else None,
                            "url": row["url"],
                            "score": row["score"],
                            "num_comments": row["num_comments"],
                            "created_utc": row["created_utc"],
                            "created_at": format_unix_timestamp(row["created_utc"]),
                            "permalink": row["permalink"],
                        }
                    )

                return jsonify(
                    {
                        "data": posts,
                        "meta": {
                            "sample_size": len(posts),
                            "population_size": population_size,
                            "seed": seed,
                            "method": "seeded_hash" if seed else "random",
                            "filters": {"subreddit": subreddit, "after": after, "before": before},
                        },
                    }
                ), 200

    except Exception as e:
        format_user_error(e, "api_posts_random")
        return jsonify({"error": "Random sampling failed."}), 500


@api_v1.route("/comments/random", methods=["GET"])
@api_limiter.limit("100 per minute")
def api_comments_random():
    """
    Get random sample of comments for statistical analysis.

    Query Parameters:
        n (int): Number of samples (default: 10, max: 100)
        subreddit (str): Filter to subreddit
        after (int): Unix timestamp - comments after this date
        before (int): Unix timestamp - comments before this date
        seed (int): Random seed for reproducibility

    Returns:
        JSON with random comment samples and sampling metadata
    """
    n = min(request.args.get("n", type=int, default=10), 100)
    subreddit = request.args.get("subreddit")
    after = request.args.get("after", type=int)
    before = request.args.get("before", type=int)
    seed = request.args.get("seed", type=int)

    try:
        db = get_db()

        with db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                # Build WHERE clauses
                where_clauses = []
                params = []

                if subreddit:
                    where_clauses.append("LOWER(subreddit) = LOWER(%s)")
                    params.append(subreddit)
                if after:
                    where_clauses.append("created_utc >= %s")
                    params.append(after)
                if before:
                    where_clauses.append("created_utc <= %s")
                    params.append(before)

                where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

                # Get population count
                cur.execute(f"SELECT COUNT(*) as count FROM comments WHERE {where_sql}", params)
                population_size = cur.fetchone()["count"]

                # Use seeded random if seed provided
                if seed is not None:
                    order_by = f"md5(id || '{seed}')"
                else:
                    order_by = "RANDOM()"

                # Get random samples
                cur.execute(
                    f"""
                    SELECT id, post_id, author, body, score, created_utc, subreddit, permalink
                    FROM comments
                    WHERE {where_sql}
                    ORDER BY {order_by}
                    LIMIT %s
                """,
                    params + [n],
                )

                comments = []
                for row in cur.fetchall():
                    comments.append(
                        {
                            "id": row["id"],
                            "post_id": row["post_id"],
                            "subreddit": row["subreddit"],
                            "author": row["author"],
                            "body": row["body"][:500] if row["body"] else None,
                            "score": row["score"],
                            "created_utc": row["created_utc"],
                            "created_at": format_unix_timestamp(row["created_utc"]),
                            "permalink": row["permalink"],
                        }
                    )

                return jsonify(
                    {
                        "data": comments,
                        "meta": {
                            "sample_size": len(comments),
                            "population_size": population_size,
                            "seed": seed,
                            "method": "seeded_hash" if seed else "random",
                            "filters": {"subreddit": subreddit, "after": after, "before": before},
                        },
                    }
                ), 200

    except Exception as e:
        format_user_error(e, "api_comments_random")
        return jsonify({"error": "Random sampling failed."}), 500


@api_v1.route("/posts/<post_id>/related", methods=["GET"])
@api_limiter.limit("100 per minute")
def api_post_related(post_id: str):
    """
    Find posts related to a given post using text similarity.

    Uses PostgreSQL full-text search to find similar discussions.

    Args:
        post_id: Source post ID

    Query Parameters:
        limit (int): Number of related posts (default: 5, max: 20)
        same_subreddit (bool): Only from same subreddit (default: false)

    Returns:
        JSON with related posts and similarity scores
    """
    if not re.match(r"^[a-zA-Z0-9]{1,10}$", post_id):
        return jsonify({"error": "Invalid post ID format"}), 400

    limit = min(request.args.get("limit", type=int, default=5), 20)
    same_subreddit = request.args.get("same_subreddit", "false").lower() == "true"

    try:
        db = get_db()

        with db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SET statement_timeout = '30000'")

                # Get source post
                cur.execute(
                    """
                    SELECT id, title, selftext, subreddit
                    FROM posts WHERE id = %s
                """,
                    (post_id,),
                )

                source = cur.fetchone()
                if not source:
                    return jsonify({"error": "Post not found"}), 404

                # Extract keywords from title (remove stopwords for better matching)
                # This creates an OR query instead of restrictive AND query
                stopwords = {
                    "the",
                    "a",
                    "an",
                    "and",
                    "or",
                    "but",
                    "in",
                    "on",
                    "at",
                    "to",
                    "for",
                    "of",
                    "from",
                    "by",
                    "with",
                    "is",
                    "was",
                    "are",
                    "been",
                    "be",
                    "has",
                    "have",
                    "had",
                    "do",
                    "does",
                    "did",
                    "will",
                    "would",
                    "could",
                    "should",
                    "may",
                    "might",
                    "can",
                    "r/",
                    "u/",
                    "it",
                    "this",
                    "that",
                    "as",
                    "so",
                    "if",
                    "than",
                    "when",
                    "where",
                    "who",
                    "which",
                    "what",
                }

                # Split title into words, clean punctuation, filter stopwords
                title_words = source["title"].lower().split()
                keywords = []
                for word in title_words:
                    # Remove punctuation
                    clean_word = word.strip(".,!?:;/()[]{}\"'*#@")
                    # Keep if not stopword and length >3
                    if clean_word not in stopwords and len(clean_word) > 3:
                        keywords.append(clean_word)

                # Take top 8 keywords, build OR query for PostgreSQL
                keywords = keywords[:8]
                if not keywords:
                    # Fallback: if no keywords extracted, use first 5 words of title
                    keywords = [w.strip(".,!?:;") for w in title_words[:5] if len(w) > 2]

                # Build OR query (| is PostgreSQL OR operator for to_tsquery)
                search_text = " | ".join(keywords) if keywords else source["title"]

                # Build WHERE clause
                where_extra = ""
                params = [search_text, post_id]
                if same_subreddit:
                    where_extra = "AND LOWER(subreddit) = LOWER(%s)"
                    params.append(source["subreddit"])

                # Find similar posts using FTS with OR logic (to_tsquery)
                # Changed from websearch_to_tsquery (AND) to to_tsquery (OR)
                cur.execute(
                    f"""
                    SELECT id, title, subreddit, author, score, created_utc, permalink,
                           ts_rank(
                               to_tsvector('english', title || ' ' || COALESCE(selftext, '')),
                               to_tsquery('english', %s)
                           ) as similarity
                    FROM posts
                    WHERE to_tsvector('english', title || ' ' || COALESCE(selftext, ''))
                          @@ to_tsquery('english', %s)
                    AND id != %s
                    {where_extra}
                    ORDER BY similarity DESC
                    LIMIT %s
                """,
                    [search_text, search_text, post_id] + ([source["subreddit"]] if same_subreddit else []) + [limit],
                )

                related = []
                for row in cur.fetchall():
                    related.append(
                        {
                            "id": row["id"],
                            "title": row["title"],
                            "subreddit": row["subreddit"],
                            "author": row["author"],
                            "score": row["score"],
                            "created_utc": row["created_utc"],
                            "created_at": format_unix_timestamp(row["created_utc"]),
                            "permalink": row["permalink"],
                            "similarity": round(float(row["similarity"]), 4) if row["similarity"] else 0,
                        }
                    )

                return jsonify(
                    {
                        "source_post": {"id": source["id"], "title": source["title"], "subreddit": source["subreddit"]},
                        "related": related,
                        "meta": {"count": len(related), "same_subreddit": same_subreddit, "method": "postgresql_fts"},
                    }
                ), 200

    except Exception as e:
        format_user_error(e, "api_post_related")
        if "statement timeout" in str(e).lower():
            return jsonify({"error": "Query timed out."}), 408
        return jsonify({"error": "Failed to find related posts."}), 500


# ============================================================================
# OPENAPI SPECIFICATION
# ============================================================================


@api_v1.route("/openapi.json", methods=["GET"])
def get_openapi_spec():
    """
    Get OpenAPI 3.0 specification for the API.

    Returns:
        JSON OpenAPI specification document
    """
    spec = {
        "openapi": "3.0.3",
        "info": {
            "title": "Redd-Archiver API",
            "description": "REST API for Reddit archive data with full-text search, aggregation, and export capabilities. Optimized for MCP/AI tool calling.",
            "version": "1.0.0",
            "contact": {"name": "API Support"},
            "license": {"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
        },
        "servers": [{"url": "/api/v1", "description": "API v1 server"}],
        "paths": {
            "/health": {
                "get": {
                    "summary": "Health check",
                    "description": "Check API and database health status",
                    "tags": ["System"],
                    "responses": {
                        "200": {"description": "Service healthy"},
                        "503": {"description": "Service unhealthy"},
                    },
                }
            },
            "/stats": {
                "get": {
                    "summary": "Archive statistics",
                    "description": "Get overall archive statistics and instance metadata",
                    "tags": ["System"],
                    "responses": {"200": {"description": "Statistics response"}},
                }
            },
            "/schema": {
                "get": {
                    "summary": "API schema discovery",
                    "description": "Get API capabilities and schema for MCP/AI integration",
                    "tags": ["System"],
                    "responses": {"200": {"description": "Schema response"}},
                }
            },
            "/posts": {
                "get": {
                    "summary": "List posts",
                    "description": """Get paginated list of posts with filtering and sorting.

💡 TOKEN TIP: Use 'fields' parameter for 62% token savings on large queries.
✅ RECOMMENDED: limit=15-25, fields=id,title,score,subreddit,num_comments

EFFICIENT USAGE:
- Small queries: limit=10-15 with fields parameter
- Browsing: limit=25 (default) with filtering
- Large datasets: Use pagination (page parameter)

EXAMPLE: /posts?limit=15&fields=id,title,score&min_score=50&sort=score""",
                    "tags": ["Posts"],
                    "parameters": [
                        {
                            "name": "subreddit",
                            "in": "query",
                            "schema": {"type": "string"},
                            "description": "Filter by subreddit",
                        },
                        {
                            "name": "author",
                            "in": "query",
                            "schema": {"type": "string"},
                            "description": "Filter by author",
                        },
                        {
                            "name": "min_score",
                            "in": "query",
                            "schema": {"type": "integer"},
                            "description": "Minimum score threshold",
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "schema": {"type": "integer", "default": 25, "maximum": 100},
                            "description": "⚠️  Use 10-25 for safety. Higher limits may cause token overflow with full text.",
                        },
                        {
                            "name": "page",
                            "in": "query",
                            "schema": {"type": "integer", "default": 1},
                            "description": "Page number (use for large result sets)",
                        },
                        {
                            "name": "sort",
                            "in": "query",
                            "schema": {"type": "string", "enum": ["score", "created_utc", "num_comments"]},
                            "description": "Sort order",
                        },
                        {
                            "name": "fields",
                            "in": "query",
                            "schema": {"type": "string"},
                            "description": "✅ RECOMMENDED: Comma-separated fields (62% token savings). Example: 'id,title,score,subreddit'",
                        },
                        {
                            "name": "max_body_length",
                            "in": "query",
                            "schema": {"type": "integer"},
                            "description": "💡 Truncate selftext to N characters (reduces tokens significantly)",
                        },
                        {
                            "name": "include_body",
                            "in": "query",
                            "schema": {"type": "boolean", "default": True},
                            "description": "Set false to exclude selftext entirely",
                        },
                        {
                            "name": "format",
                            "in": "query",
                            "schema": {"type": "string", "enum": ["json", "csv", "ndjson"]},
                            "description": "Response format",
                        },
                    ],
                    "responses": {
                        "200": {"description": "Paginated posts response"},
                        "400": {"description": "Validation error"},
                    },
                }
            },
            "/posts/{post_id}": {
                "get": {
                    "summary": "Get post",
                    "description": "Get single post by ID with field selection and truncation",
                    "tags": ["Posts"],
                    "parameters": [
                        {
                            "name": "post_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                            "description": "Post ID",
                        },
                        {
                            "name": "fields",
                            "in": "query",
                            "schema": {"type": "string"},
                            "description": "Comma-separated fields to return",
                        },
                        {
                            "name": "max_body_length",
                            "in": "query",
                            "schema": {"type": "integer"},
                            "description": "Truncate selftext to N characters",
                        },
                        {
                            "name": "include_body",
                            "in": "query",
                            "schema": {"type": "boolean", "default": True},
                            "description": "Include selftext field",
                        },
                    ],
                    "responses": {"200": {"description": "Post details"}, "404": {"description": "Post not found"}},
                }
            },
            "/posts/{post_id}/comments": {
                "get": {
                    "summary": "Get post comments",
                    "description": "Get paginated comments for a post",
                    "tags": ["Posts"],
                    "parameters": [{"name": "post_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "Paginated comments"}},
                }
            },
            "/posts/{post_id}/context": {
                "get": {
                    "summary": "Get post context",
                    "description": """Get post with top comments in one request (MCP-optimized - replaces 11+ API calls).

🏆 EFFICIENCY: This endpoint reduces 11+ calls to 1 call (91% reduction).
✅ RECOMMENDED: top_comments=5, max_depth=2, max_body_length=150

💡 TOKEN TIP: Set max_body_length to truncate ALL text (post + comments) for manageable responses.

USAGE: /posts/{id}/context?top_comments=5&max_depth=2&max_body_length=150""",
                    "tags": ["Posts"],
                    "parameters": [
                        {
                            "name": "post_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                            "description": "Post ID",
                        },
                        {
                            "name": "top_comments",
                            "in": "query",
                            "schema": {"type": "integer", "default": 10, "maximum": 50},
                            "description": "✅ RECOMMENDED: Use 5-10 (not 50). Number of top-level comments to include.",
                        },
                        {
                            "name": "max_depth",
                            "in": "query",
                            "schema": {"type": "integer", "default": 2, "maximum": 5},
                            "description": "✅ RECOMMENDED: Use 1-2 (not 5). Maximum reply nesting depth.",
                        },
                        {
                            "name": "max_body_length",
                            "in": "query",
                            "schema": {"type": "integer", "default": 500},
                            "description": "✅ CRITICAL: Set to 150-200 to truncate ALL text content (post + comments). Default 500 can produce large responses.",
                        },
                    ],
                    "responses": {"200": {"description": "Post context with comments"}},
                }
            },
            "/posts/{post_id}/comments/tree": {
                "get": {
                    "summary": "Get comment tree",
                    "description": "Get hierarchical comment structure",
                    "tags": ["Posts"],
                    "parameters": [
                        {"name": "post_id", "in": "path", "required": True, "schema": {"type": "string"}},
                        {
                            "name": "max_depth",
                            "in": "query",
                            "schema": {"type": "integer", "default": 10, "maximum": 20},
                        },
                        {"name": "sort", "in": "query", "schema": {"type": "string", "enum": ["score", "created_utc"]}},
                        {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 100}},
                    ],
                    "responses": {"200": {"description": "Comment tree"}},
                }
            },
            "/posts/{post_id}/related": {
                "get": {
                    "summary": "Find related posts",
                    "description": "Find similar posts using FTS",
                    "tags": ["Posts"],
                    "parameters": [
                        {"name": "post_id", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 5, "maximum": 20}},
                        {"name": "same_subreddit", "in": "query", "schema": {"type": "boolean", "default": False}},
                    ],
                    "responses": {"200": {"description": "Related posts"}},
                }
            },
            "/posts/random": {
                "get": {
                    "summary": "Random posts",
                    "description": "Get random sample of posts",
                    "tags": ["Posts"],
                    "parameters": [
                        {"name": "n", "in": "query", "schema": {"type": "integer", "default": 10, "maximum": 100}},
                        {"name": "subreddit", "in": "query", "schema": {"type": "string"}},
                        {
                            "name": "seed",
                            "in": "query",
                            "schema": {"type": "integer"},
                            "description": "Random seed for reproducibility",
                        },
                    ],
                    "responses": {"200": {"description": "Random posts"}},
                }
            },
            "/posts/aggregate": {
                "get": {
                    "summary": "Aggregate posts",
                    "description": "Get aggregated post statistics",
                    "tags": ["Analytics"],
                    "parameters": [
                        {
                            "name": "group_by",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string", "enum": ["author", "subreddit", "created_utc"]},
                        },
                        {
                            "name": "frequency",
                            "in": "query",
                            "schema": {"type": "string", "enum": ["hour", "day", "week", "month", "year"]},
                        },
                        {"name": "subreddit", "in": "query", "schema": {"type": "string"}},
                        {
                            "name": "limit",
                            "in": "query",
                            "schema": {"type": "integer", "default": 100, "maximum": 1000},
                        },
                    ],
                    "responses": {"200": {"description": "Aggregation results"}},
                }
            },
            "/posts/batch": {
                "post": {
                    "summary": "Batch lookup posts",
                    "description": "Fetch multiple posts by ID (MCP-optimized)",
                    "tags": ["Posts"],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "ids": {"type": "array", "items": {"type": "string"}, "maxItems": 100}
                                    },
                                    "required": ["ids"],
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "Batch results"}},
                }
            },
            "/comments": {
                "get": {
                    "summary": "List comments",
                    "description": """Get paginated list of comments with filtering, field selection, and truncation.

⚠️  TOKEN WARNING: Comment bodies can be very large. Always use max_body_length parameter.
✅ RECOMMENDED: limit=10-25, max_body_length=200, fields=id,author,score

Comments default to max_body_length=500. For smaller responses, use 200 or set include_body=false.

EFFICIENT USAGE: /comments?limit=15&max_body_length=200&fields=id,author,score,body""",
                    "tags": ["Comments"],
                    "parameters": [
                        {
                            "name": "subreddit",
                            "in": "query",
                            "schema": {"type": "string"},
                            "description": "Filter by subreddit",
                        },
                        {
                            "name": "author",
                            "in": "query",
                            "schema": {"type": "string"},
                            "description": "Filter by author",
                        },
                        {
                            "name": "min_score",
                            "in": "query",
                            "schema": {"type": "integer"},
                            "description": "Minimum score threshold",
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "schema": {"type": "integer", "default": 25, "maximum": 100},
                            "description": "⚠️  Use 10-25 for safety. Comment bodies can be large.",
                        },
                        {
                            "name": "page",
                            "in": "query",
                            "schema": {"type": "integer", "default": 1},
                            "description": "Page number for pagination",
                        },
                        {
                            "name": "fields",
                            "in": "query",
                            "schema": {"type": "string"},
                            "description": "✅ RECOMMENDED: 'id,author,score,body' for essential fields only",
                        },
                        {
                            "name": "max_body_length",
                            "in": "query",
                            "schema": {"type": "integer"},
                            "description": "✅ CRITICAL: Set to 200 to truncate comment bodies. Default is 500 which can be large.",
                        },
                        {
                            "name": "include_body",
                            "in": "query",
                            "schema": {"type": "boolean", "default": True},
                            "description": "Set false to exclude body text entirely (smaller responses)",
                        },
                        {
                            "name": "format",
                            "in": "query",
                            "schema": {"type": "string", "enum": ["json", "csv", "ndjson"]},
                            "description": "Response format",
                        },
                    ],
                    "responses": {"200": {"description": "Paginated comments"}},
                }
            },
            "/comments/{comment_id}": {
                "get": {
                    "summary": "Get comment",
                    "description": "Get single comment by ID with field selection and truncation",
                    "tags": ["Comments"],
                    "parameters": [
                        {
                            "name": "comment_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                            "description": "Comment ID",
                        },
                        {
                            "name": "fields",
                            "in": "query",
                            "schema": {"type": "string"},
                            "description": "Comma-separated fields to return",
                        },
                        {
                            "name": "max_body_length",
                            "in": "query",
                            "schema": {"type": "integer"},
                            "description": "Truncate body to N characters",
                        },
                        {
                            "name": "include_body",
                            "in": "query",
                            "schema": {"type": "boolean", "default": True},
                            "description": "Include body field",
                        },
                    ],
                    "responses": {
                        "200": {"description": "Comment details"},
                        "404": {"description": "Comment not found"},
                    },
                }
            },
            "/comments/random": {
                "get": {
                    "summary": "Random comments",
                    "description": "Get random sample of comments",
                    "tags": ["Comments"],
                    "parameters": [
                        {"name": "n", "in": "query", "schema": {"type": "integer", "default": 10, "maximum": 100}},
                        {"name": "subreddit", "in": "query", "schema": {"type": "string"}},
                        {"name": "seed", "in": "query", "schema": {"type": "integer"}},
                    ],
                    "responses": {"200": {"description": "Random comments"}},
                }
            },
            "/comments/aggregate": {
                "get": {
                    "summary": "Aggregate comments",
                    "description": "Get aggregated comment statistics",
                    "tags": ["Analytics"],
                    "parameters": [
                        {
                            "name": "group_by",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string", "enum": ["author", "subreddit", "created_utc"]},
                        },
                        {
                            "name": "frequency",
                            "in": "query",
                            "schema": {"type": "string", "enum": ["hour", "day", "week", "month", "year"]},
                        },
                    ],
                    "responses": {"200": {"description": "Aggregation results"}},
                }
            },
            "/comments/batch": {
                "post": {
                    "summary": "Batch lookup comments",
                    "description": "Fetch multiple comments by ID",
                    "tags": ["Comments"],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "ids": {"type": "array", "items": {"type": "string"}, "maxItems": 100}
                                    },
                                    "required": ["ids"],
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "Batch results"}},
                }
            },
            "/users": {
                "get": {
                    "summary": "List users",
                    "description": "Get paginated list of users with sorting and field selection",
                    "tags": ["Users"],
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "schema": {"type": "integer", "default": 25, "maximum": 100},
                            "description": "Results per page",
                        },
                        {
                            "name": "page",
                            "in": "query",
                            "schema": {"type": "integer", "default": 1},
                            "description": "Page number",
                        },
                        {
                            "name": "sort",
                            "in": "query",
                            "schema": {"type": "string", "enum": ["karma", "activity", "posts", "comments"]},
                            "description": "Sort order",
                        },
                        {
                            "name": "fields",
                            "in": "query",
                            "schema": {"type": "string"},
                            "description": "Comma-separated fields to return",
                        },
                        {
                            "name": "format",
                            "in": "query",
                            "schema": {"type": "string", "enum": ["json", "csv", "ndjson"]},
                            "description": "Response format",
                        },
                    ],
                    "responses": {"200": {"description": "Paginated users"}},
                }
            },
            "/users/{username}": {
                "get": {
                    "summary": "Get user",
                    "description": "Get user profile and statistics with field selection",
                    "tags": ["Users"],
                    "parameters": [
                        {
                            "name": "username",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                            "description": "Username",
                        },
                        {
                            "name": "fields",
                            "in": "query",
                            "schema": {"type": "string"},
                            "description": "Comma-separated fields to return",
                        },
                    ],
                    "responses": {"200": {"description": "User profile"}, "404": {"description": "User not found"}},
                }
            },
            "/users/{username}/summary": {
                "get": {
                    "summary": "User summary",
                    "description": "Get user overview with activity statistics",
                    "tags": ["Users"],
                    "parameters": [{"name": "username", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "User summary"}},
                }
            },
            "/users/{username}/posts": {
                "get": {
                    "summary": "User's posts",
                    "description": "Get paginated posts by user",
                    "tags": ["Users"],
                    "parameters": [{"name": "username", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "User's posts"}},
                }
            },
            "/users/{username}/comments": {
                "get": {
                    "summary": "User's comments",
                    "description": "Get paginated comments by user",
                    "tags": ["Users"],
                    "parameters": [{"name": "username", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "User's comments"}},
                }
            },
            "/users/aggregate": {
                "get": {
                    "summary": "Aggregate users",
                    "description": "Get aggregated user statistics",
                    "tags": ["Analytics"],
                    "parameters": [
                        {"name": "subreddit", "in": "query", "schema": {"type": "string"}},
                        {
                            "name": "sort_by",
                            "in": "query",
                            "schema": {"type": "string", "enum": ["posts", "comments", "total", "karma"]},
                        },
                    ],
                    "responses": {"200": {"description": "Aggregation results"}},
                }
            },
            "/users/batch": {
                "post": {
                    "summary": "Batch lookup users",
                    "description": "Fetch multiple users by username",
                    "tags": ["Users"],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "usernames": {"type": "array", "items": {"type": "string"}, "maxItems": 100}
                                    },
                                    "required": ["usernames"],
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "Batch results"}},
                }
            },
            "/subreddits": {
                "get": {
                    "summary": "List subreddits",
                    "description": "Get list of subreddits with statistics and field selection",
                    "tags": ["Subreddits"],
                    "parameters": [
                        {
                            "name": "min_score",
                            "in": "query",
                            "schema": {"type": "integer"},
                            "description": "Minimum post score filter",
                        },
                        {
                            "name": "min_comments",
                            "in": "query",
                            "schema": {"type": "integer"},
                            "description": "Minimum comment count filter",
                        },
                        {
                            "name": "fields",
                            "in": "query",
                            "schema": {"type": "string"},
                            "description": "Comma-separated fields to return",
                        },
                        {
                            "name": "format",
                            "in": "query",
                            "schema": {"type": "string", "enum": ["json", "csv", "ndjson"]},
                            "description": "Response format",
                        },
                    ],
                    "responses": {"200": {"description": "Subreddit list"}},
                }
            },
            "/subreddits/{subreddit}": {
                "get": {
                    "summary": "Get subreddit",
                    "description": "Get subreddit statistics with field selection",
                    "tags": ["Subreddits"],
                    "parameters": [
                        {
                            "name": "subreddit",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                            "description": "Subreddit name",
                        },
                        {
                            "name": "fields",
                            "in": "query",
                            "schema": {"type": "string"},
                            "description": "Comma-separated fields to return",
                        },
                    ],
                    "responses": {
                        "200": {"description": "Subreddit statistics"},
                        "404": {"description": "Subreddit not found"},
                    },
                }
            },
            "/subreddits/{subreddit}/summary": {
                "get": {
                    "summary": "Subreddit summary",
                    "description": "Get subreddit overview with top contributors",
                    "tags": ["Subreddits"],
                    "parameters": [{"name": "subreddit", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "Subreddit summary"}},
                }
            },
            "/search": {
                "get": {
                    "summary": "Full-text search",
                    "description": """Search posts and comments with Google-style operators.

⚠️  TOKEN WARNING: Responses can exceed 200KB at limit=50. Use limit=10-25 to prevent overflow.
✅ SAFE USAGE: limit=10-25, max_body_length=200, fields parameter recommended

OPERATORS: "phrase", OR, -exclude, sub:, author:, score:, type:, sort:
EXAMPLE: q=censorship&limit=10&max_body_length=200&type=posts

Best practice: Start with limit=10, increase if needed. Use pagination for large result sets.""",
                    "tags": ["Search"],
                    "parameters": [
                        {
                            "name": "q",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                            "description": "Search query with operators",
                        },
                        {
                            "name": "type",
                            "in": "query",
                            "schema": {"type": "string", "enum": ["posts", "comments", "all"]},
                            "description": "Result type filter",
                        },
                        {
                            "name": "subreddit",
                            "in": "query",
                            "schema": {"type": "string"},
                            "description": "Filter by subreddit",
                        },
                        {
                            "name": "author",
                            "in": "query",
                            "schema": {"type": "string"},
                            "description": "Filter by author",
                        },
                        {
                            "name": "min_score",
                            "in": "query",
                            "schema": {"type": "integer"},
                            "description": "Minimum score threshold",
                        },
                        {
                            "name": "sort",
                            "in": "query",
                            "schema": {"type": "string", "enum": ["relevance", "score", "created_utc"]},
                            "description": "Sort order",
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "schema": {"type": "integer", "default": 25, "maximum": 100},
                            "description": "🔴 CRITICAL: Use 10-25 (not 50-100). Responses at limit=50 can exceed 200KB causing token overflow.",
                        },
                        {
                            "name": "page",
                            "in": "query",
                            "schema": {"type": "integer", "default": 1},
                            "description": "Page number for pagination",
                        },
                        {
                            "name": "max_body_length",
                            "in": "query",
                            "schema": {"type": "integer"},
                            "description": "✅ RECOMMENDED: Set to 200 to truncate snippets and reduce response size by 40-60%",
                        },
                        {
                            "name": "fields",
                            "in": "query",
                            "schema": {"type": "string"},
                            "description": "✅ RECOMMENDED: Comma-separated field names. Reduces response by 60%. Example: 'id,title,score,snippet'",
                        },
                    ],
                    "responses": {
                        "200": {"description": "Search results with snippets"},
                        "400": {"description": "Invalid query"},
                    },
                }
            },
            "/search/explain": {
                "get": {
                    "summary": "Explain search query",
                    "description": "Debug and validate search query parsing",
                    "tags": ["Search"],
                    "parameters": [{"name": "q", "in": "query", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "Query explanation"}},
                }
            },
        },
        "components": {
            "schemas": {
                "Post": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "subreddit": {"type": "string"},
                        "author": {"type": "string"},
                        "title": {"type": "string"},
                        "selftext": {"type": "string"},
                        "url": {"type": "string"},
                        "score": {"type": "integer"},
                        "num_comments": {"type": "integer"},
                        "created_utc": {"type": "integer"},
                        "created_at": {"type": "string", "format": "date-time"},
                    },
                },
                "Comment": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "post_id": {"type": "string"},
                        "parent_id": {"type": "string"},
                        "author": {"type": "string"},
                        "body": {"type": "string"},
                        "score": {"type": "integer"},
                        "depth": {"type": "integer"},
                        "created_utc": {"type": "integer"},
                        "created_at": {"type": "string", "format": "date-time"},
                    },
                },
                "User": {
                    "type": "object",
                    "properties": {
                        "username": {"type": "string"},
                        "post_count": {"type": "integer"},
                        "comment_count": {"type": "integer"},
                        "total_activity": {"type": "integer"},
                        "total_karma": {"type": "integer"},
                    },
                },
                "Subreddit": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "total_posts": {"type": "integer"},
                        "total_comments": {"type": "integer"},
                        "unique_users": {"type": "integer"},
                    },
                },
                "PaginatedResponse": {
                    "type": "object",
                    "properties": {
                        "data": {"type": "array"},
                        "meta": {
                            "type": "object",
                            "properties": {
                                "page": {"type": "integer"},
                                "limit": {"type": "integer"},
                                "total": {"type": "integer"},
                                "total_pages": {"type": "integer"},
                            },
                        },
                        "links": {
                            "type": "object",
                            "properties": {
                                "self": {"type": "string"},
                                "next": {"type": "string"},
                                "prev": {"type": "string"},
                                "first": {"type": "string"},
                                "last": {"type": "string"},
                            },
                        },
                    },
                },
                "Error": {"type": "object", "properties": {"error": {"type": "string"}}},
            }
        },
        "tags": [
            {"name": "System", "description": "Health, stats, and meta endpoints"},
            {"name": "Posts", "description": "Post operations"},
            {"name": "Comments", "description": "Comment operations"},
            {"name": "Users", "description": "User operations"},
            {"name": "Subreddits", "description": "Subreddit operations"},
            {"name": "Search", "description": "Full-text search operations"},
            {"name": "Analytics", "description": "Aggregation and analytics endpoints"},
        ],
    }

    return jsonify(spec), 200


# ============================================================================
# ERROR HANDLERS
# ============================================================================


@api_v1.errorhandler(404)
def api_not_found(error):
    """Handle 404 errors for API routes."""
    return jsonify({"error": "Endpoint not found"}), 404


@api_v1.errorhandler(429)
def api_rate_limit(error):
    """Handle rate limit errors for API routes."""
    return jsonify({"error": "Rate limit exceeded. Please wait and try again."}), 429


@api_v1.errorhandler(500)
def api_internal_error(error):
    """Handle 500 errors for API routes with safe error messages."""
    format_user_error(error, "api_internal")
    return jsonify({"error": "Internal server error"}), 500
