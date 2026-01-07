# Redd Archiver REST API Documentation

**Version**: 1.0
**Base URL**: `https://your-archive.com/api/v1`
**Authentication**: None (Public API)
**Rate Limiting**: 100 requests per minute per IP

---

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Common Parameters](#common-parameters)
- [Response Format](#response-format)
- [System Endpoints](#system-endpoints)
- [Posts Endpoints](#posts-endpoints)
- [Comments Endpoints](#comments-endpoints)
- [Users Endpoints](#users-endpoints)
- [Subreddits Endpoints](#subreddits-endpoints)
- [Search Endpoints](#search-endpoints)
- [Field Selection](#field-selection)
- [Truncation Controls](#truncation-controls)
- [Export Formats](#export-formats)
- [Aggregation](#aggregation)
- [Batch Operations](#batch-operations)
- [Context & Summary](#context--summary)
- [Error Handling](#error-handling)
- [Rate Limiting](#rate-limiting)
- [Best Practices](#best-practices)
- [Code Examples](#code-examples)

---

## Overview

The Redd Archiver REST API provides programmatic access to archived Reddit data with comprehensive filtering, search, aggregation, and export capabilities.

### Features

- ✅ **Public Access**: No authentication required
- ✅ **CORS Enabled**: Accessible from any origin
- ✅ **Multi-Platform**: Filter by platform (Reddit, Voat, Ruqqus)
- ✅ **Field Selection**: Choose which fields to return (token optimization)
- ✅ **Truncation Controls**: Limit body text length with metadata
- ✅ **Export Formats**: JSON (default), CSV, NDJSON
- ✅ **Full-Text Search**: PostgreSQL FTS with Google-style operators
- ✅ **Aggregation**: Group and analyze data by time, author, subreddit
- ✅ **Batch Operations**: Fetch multiple resources in one request
- ✅ **MCP-Optimized**: Context/summary endpoints reduce API calls
- ✅ **MCP Server**: 29 tools auto-generated from OpenAPI for AI assistants
- ✅ **SQL Injection Protected**: All inputs validated and parameterized
- ✅ **Rate Limited**: 100 requests/minute per IP

---

## Quick Start

### Get Archive Statistics

```bash
curl https://archive.example.com/api/v1/stats | jq
```

### List Top Posts

```bash
curl "https://archive.example.com/api/v1/posts?limit=10&sort=score" | jq
```

### Search Posts

```bash
curl "https://archive.example.com/api/v1/search?q=censorship&type:post&limit=10" | jq
```

### Export to CSV

```bash
curl "https://archive.example.com/api/v1/posts?format=csv&limit=100" -o posts.csv
```

---

## Common Parameters

These parameters are supported by most list endpoints:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 25 | Results per page (10-100) |
| `page` | integer | 1 | Page number (≥ 1) |
| `sort` | string | varies | Sort order (endpoint-specific) |
| `fields` | string | all | Comma-separated field names |
| `max_body_length` | integer | none | Truncate body to N characters |
| `include_body` | boolean | true | Include body/selftext fields |
| `format` | string | json | Response format (json\|csv\|ndjson) |

---

## Response Format

### Successful Paginated Response

```json
{
  "data": [...],
  "meta": {
    "page": 1,
    "limit": 25,
    "total": 1000,
    "total_pages": 40
  },
  "links": {
    "self": "/api/v1/posts?page=1&limit=25",
    "next": "/api/v1/posts?page=2&limit=25",
    "prev": null,
    "first": "/api/v1/posts?page=1&limit=25",
    "last": "/api/v1/posts?page=40&limit=25"
  }
}
```

### Error Response

```json
{
  "error": "Error message",
  "details": ["Validation error 1", "Validation error 2"]
}
```

---

## System Endpoints

### GET /health

Health check endpoint for monitoring.

**Response**:
```json
{
  "status": "healthy",
  "database": "connected",
  "api_version": "1.0",
  "timestamp": "2025-01-23T12:00:00Z"
}
```

**Status Codes**:
- `200 OK` - Service healthy
- `503 Service Unavailable` - Service unhealthy

**Example**:
```bash
curl https://archive.example.com/api/v1/health
```

---

### GET /stats

Get archive statistics and instance metadata.

**Response**:
```json
{
  "archive_version": "1.0.0",
  "api_version": "1.0",
  "timestamp": "2025-01-23T12:00:00Z",
  "instance": {
    "name": "Privacy Archive",
    "description": "Community-maintained archive of r/Privacy",
    "contact": "admin@example.com",
    "team_id": "privacy-advocates",
    "donation_address": "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
    "base_url": "https://archive.example.com",
    "tor_url": "http://abc123.onion"
  },
  "content": {
    "total_posts": 50000,
    "total_comments": 500000,
    "total_users": 5000,
    "total_subreddits": 5,
    "subreddits": [
      {"name": "privacy", "posts": 10000}
    ]
  },
  "date_range": {
    "earliest_post": "2018-01-01T00:00:00Z",
    "latest_post": "2024-12-31T23:59:59Z"
  },
  "features": {
    "tor": true
  },
  "status": "operational"
}
```

**Instance Metadata Fields**:

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `name` | string | `REDDARCHIVER_SITE_NAME` or `--site-name` | Instance display name |
| `description` | string | `REDDARCHIVER_SITE_DESCRIPTION` or `--site-description` | Instance description |
| `contact` | string | `REDDARCHIVER_CONTACT` or `--contact` | Contact method |
| `team_id` | string | `REDDARCHIVER_TEAM_ID` or `--team-id` | Team identifier |
| `donation_address` | string | `REDDARCHIVER_DONATION_ADDRESS` or `--donation-address` | Donation method |
| `base_url` | string | `REDDARCHIVER_BASE_URL` or `--base-url` | Clearnet URL |
| `tor_url` | string | Auto-detected | Onion URL (runtime detected) |

**Example**:
```bash
curl https://archive.example.com/api/v1/stats | jq .content
```

---

### GET /schema

MCP/AI discovery endpoint describing API capabilities.

**Response**:
```json
{
  "api_version": "1.0",
  "endpoints": {
    "posts": {
      "list": "/api/v1/posts",
      "single": "/api/v1/posts/{id}",
      "comments": "/api/v1/posts/{id}/comments",
      "...": "..."
    }
  },
  "features": {
    "field_selection": true,
    "truncation": true,
    "full_text_search": true,
    "aggregation": true,
    "batch_operations": true,
    "export_formats": ["csv", "ndjson"]
  },
  "search_operators": ["\"phrase\"", "OR", "-exclude", "sub:", "author:", "score:", "type:", "sort:"]
}
```

**Example**:
```bash
curl https://archive.example.com/api/v1/schema | jq .features
```

---

### GET /openapi.json

OpenAPI 3.0.3 specification for the API.

**Response**: Complete OpenAPI specification document

**Use Case**: Generate client SDKs, API documentation, testing tools

**Example**:
```bash
# Download OpenAPI spec
curl https://archive.example.com/api/v1/openapi.json -o openapi.json

# Generate Python client
openapi-generator-cli generate -i openapi.json -g python -o client/
```

---

## Posts Endpoints

### GET /posts

Get paginated list of posts with filtering and sorting.

**Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `platform` | string | none | Filter by platform (reddit\|voat\|ruqqus) |
| `subreddit` | string | none | Filter by subreddit/subverse/guild name (case-insensitive) |
| `author` | string | none | Filter by author username |
| `min_score` | integer | 0 | Minimum score threshold |
| `limit` | integer | 25 | Results per page (10-100) |
| `page` | integer | 1 | Page number (≥ 1) |
| `sort` | string | score | Sort order (score\|created_utc\|num_comments) |
| `fields` | string | all | Comma-separated field names |
| `max_body_length` | integer | none | Truncate selftext to N characters |
| `include_body` | boolean | true | Include selftext field |
| `format` | string | json | Response format (json\|csv\|ndjson) |

**Example Request**:
```bash
curl "https://archive.example.com/api/v1/posts?subreddit=privacy&min_score=100&limit=10"
```

**Example Response**:
```json
{
  "data": [
    {
      "id": "abc123",
      "subreddit": "privacy",
      "author": "username",
      "title": "Post title",
      "selftext": "Post content...",
      "url": "https://example.com",
      "domain": "example.com",
      "permalink": "/r/privacy/comments/abc123/post_title/",
      "created_utc": 1640000000,
      "created_at": "2021-12-20T00:00:00Z",
      "score": 150,
      "num_comments": 25,
      "is_self": false,
      "nsfw": false
    }
  ],
  "meta": {...},
  "links": {...}
}
```

**Status Codes**:
- `200 OK` - Success
- `400 Bad Request` - Invalid parameters
- `429 Too Many Requests` - Rate limit exceeded

---

### GET /posts/{id}

Get single post by ID.

**URL Parameters**:
- `id` (string): Post ID (alphanumeric + underscore)

**Query Parameters**:
- `fields` (string): Comma-separated field names
- `max_body_length` (integer): Truncate selftext
- `include_body` (boolean): Include selftext field

**Example Request**:
```bash
curl "https://archive.example.com/api/v1/posts/abc123"
```

**Example Response**:
```json
{
  "id": "abc123",
  "subreddit": "privacy",
  "author": "username",
  "title": "Post title",
  "selftext": "Full post content...",
  "url": "https://example.com",
  "domain": "example.com",
  "permalink": "/r/privacy/comments/abc123/post_title/",
  "created_utc": 1640000000,
  "created_at": "2021-12-20T00:00:00Z",
  "score": 150,
  "num_comments": 25,
  "is_self": false,
  "nsfw": false,
  "locked": false,
  "stickied": false
}
```

**Status Codes**:
- `200 OK` - Post found
- `400 Bad Request` - Invalid post ID format
- `404 Not Found` - Post not found

---

### GET /posts/{id}/comments

Get comments for a specific post (flat list).

**URL Parameters**:
- `id` (string): Post ID

**Query Parameters**:
- `limit` (integer, default: 25): Results per page (10-100)
- `page` (integer, default: 1): Page number
- `sort` (string, default: score): Sort order (score\|created_utc)
- `fields` (string): Comma-separated field names
- `max_body_length` (integer): Truncate body
- `include_body` (boolean): Include body field

**Example Request**:
```bash
curl "https://archive.example.com/api/v1/posts/abc123/comments?limit=50&sort=score"
```

**Example Response**:
```json
{
  "data": [
    {
      "id": "xyz789",
      "post_id": "abc123",
      "parent_id": "t3_abc123",
      "author": "commenter",
      "body": "Comment text...",
      "permalink": "/r/privacy/comments/abc123/post_title/xyz789/",
      "created_utc": 1640001000,
      "created_at": "2021-12-20T00:16:40Z",
      "score": 25,
      "depth": 0
    }
  ],
  "meta": {...},
  "links": {...}
}
```

---

### GET /posts/{id}/comments/tree

Get hierarchical comment tree structure with recursive nesting.

**URL Parameters**:
- `id` (string): Post ID

**Query Parameters**:
- `limit` (integer, default: 100): Maximum total comments (10-500)
- `max_depth` (integer, default: 10): Maximum nesting depth (1-20)
- `sort` (string, default: score): Sort order (score\|created_utc)
- `max_body_length` (integer): Truncate body

**Example Request**:
```bash
curl "https://archive.example.com/api/v1/posts/abc123/comments/tree?max_depth=3&limit=100"
```

**Example Response**:
```json
{
  "post_id": "abc123",
  "total_comments": 45,
  "returned_comments": 45,
  "max_depth": 3,
  "tree": [
    {
      "id": "xyz789",
      "author": "user1",
      "body": "Top-level comment",
      "score": 50,
      "created_utc": 1640001000,
      "depth": 0,
      "children": [
        {
          "id": "xyz790",
          "author": "user2",
          "body": "Reply to comment",
          "score": 20,
          "created_utc": 1640002000,
          "depth": 1,
          "children": []
        }
      ]
    }
  ]
}
```

**Status Codes**:
- `200 OK` - Success
- `404 Not Found` - Post not found

**Use Case**: Build threaded comment UI, analyze discussion structure

---

### GET /posts/{id}/context

Get post with top comments in one request (MCP-optimized).

**URL Parameters**:
- `id` (string): Post ID

**Query Parameters**:
- `top_comments` (integer, default: 10): Number of top-level comments (1-50)
- `max_depth` (integer, default: 2): Maximum reply depth (1-5)
- `sort` (string, default: score): Sort order (score\|created_utc)
- `max_body_length` (integer): Truncate all text

**Example Request**:
```bash
curl "https://archive.example.com/api/v1/posts/abc123/context?top_comments=5&max_depth=2&max_body_length=200"
```

**Example Response**:
```json
{
  "post": {
    "id": "abc123",
    "title": "Post title",
    "selftext": "Truncated to 200 chars...",
    "selftext_truncated": true,
    "selftext_full_length": 850,
    "score": 150,
    "num_comments": 45
  },
  "comments": [
    {
      "id": "xyz789",
      "body": "Top comment truncated...",
      "body_truncated": true,
      "body_full_length": 450,
      "score": 50,
      "depth": 0,
      "children": [...]
    }
  ],
  "metadata": {
    "top_comments_requested": 5,
    "top_comments_returned": 5,
    "max_depth": 2,
    "total_comments_in_post": 45
  }
}
```

**Status Codes**:
- `200 OK` - Success
- `404 Not Found` - Post not found

**Use Case**: Get discussion overview in one API call (reduces 11+ calls to 1)

---

### GET /posts/{id}/related

Find related posts using full-text search similarity.

**URL Parameters**:
- `id` (string): Post ID

**Query Parameters**:
- `limit` (integer, default: 10): Number of related posts (3-20)
- `same_subreddit` (boolean, default: true): Restrict to same subreddit

**Example Request**:
```bash
curl "https://archive.example.com/api/v1/posts/abc123/related?limit=5"
```

**Example Response**:
```json
{
  "post_id": "abc123",
  "related_posts": [
    {
      "id": "def456",
      "title": "Similar post title",
      "subreddit": "privacy",
      "score": 120,
      "similarity_score": 0.87,
      "num_comments": 30
    }
  ]
}
```

**Status Codes**:
- `200 OK` - Success
- `404 Not Found` - Post not found

**Use Case**: Content discovery, recommendation systems

---

### GET /posts/random

Get random sample of posts.

**Query Parameters**:
- `n` (integer, default: 10): Number of random posts (1-100)
- `subreddit` (string): Filter by subreddit
- `seed` (integer): Random seed for reproducibility
- `fields` (string): Comma-separated field names

**Example Request**:
```bash
# Random posts
curl "https://archive.example.com/api/v1/posts/random?n=20"

# Reproducible random sample
curl "https://archive.example.com/api/v1/posts/random?n=50&seed=42"
```

**Example Response**:
```json
{
  "data": [...],
  "meta": {
    "n": 20,
    "seed": null,
    "subreddit": null
  }
}
```

**Status Codes**:
- `200 OK` - Success
- `400 Bad Request` - Invalid parameters

**Use Case**: Quality assurance, content sampling, randomized testing

---

### GET /posts/aggregate

Aggregate posts by author, subreddit, or time period.

**Query Parameters**:
- `group_by` (string, required): Grouping field (author\|subreddit\|created_utc)
- `frequency` (string): Time frequency for created_utc (hour\|day\|week\|month\|year)
- `limit` (integer, default: 100): Maximum groups (10-1000)
- `subreddit` (string): Filter by subreddit
- `author` (string): Filter by author
- `min_score` (integer): Minimum score threshold

**Example Request**:
```bash
# Top contributors
curl "https://archive.example.com/api/v1/posts/aggregate?group_by=author&limit=20"

# Activity over time (monthly)
curl "https://archive.example.com/api/v1/posts/aggregate?group_by=created_utc&frequency=month&limit=12"

# Subreddit comparison
curl "https://archive.example.com/api/v1/posts/aggregate?group_by=subreddit"
```

**Example Response**:
```json
{
  "data": [
    {
      "author": "username",
      "count": 150,
      "total_score": 12000,
      "avg_score": 80,
      "total_comments": 3500
    }
  ],
  "meta": {
    "group_by": "author",
    "limit": 20
  }
}
```

**Status Codes**:
- `200 OK` - Success
- `400 Bad Request` - Invalid parameters
- `408 Request Timeout` - Query exceeded 30 seconds

**Use Case**: Analytics, leaderboards, trend analysis

---

### POST /posts/batch

Fetch multiple posts by ID in one request (MCP-optimized).

**Request Body**:
```json
{
  "ids": ["abc123", "def456", "ghi789"]
}
```

**Query Parameters**:
- `fields` (string): Comma-separated field names
- `max_body_length` (integer): Truncate selftext
- `include_body` (boolean): Include selftext field

**Example Request**:
```bash
curl -X POST "https://archive.example.com/api/v1/posts/batch" \
  -H "Content-Type: application/json" \
  -d '{"ids":["abc123","def456","ghi789"]}'
```

**Example Response**:
```json
{
  "found": [
    {
      "id": "abc123",
      "title": "Post title",
      "score": 150
    }
  ],
  "not_found": ["ghi789"],
  "meta": {
    "requested": 3,
    "found": 2,
    "not_found": 1
  }
}
```

**Status Codes**:
- `200 OK` - Success (even if some IDs not found)
- `400 Bad Request` - Invalid request body or too many IDs (max 100)

**Use Case**: Reduce N API calls to 1, bulk lookups

---

## Comments Endpoints

### GET /comments

Get paginated list of comments with filtering.

**Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `platform` | string | none | Filter by platform (reddit\|voat\|ruqqus) |
| `subreddit` | string | none | Filter by subreddit/subverse/guild |
| `author` | string | none | Filter by author username |
| `min_score` | integer | 0 | Minimum score threshold |
| `limit` | integer | 25 | Results per page (10-100) |
| `page` | integer | 1 | Page number (≥ 1) |
| `sort` | string | score | Sort order (score\|created_utc) |
| `fields` | string | all | Comma-separated field names |
| `max_body_length` | integer | 500 | Truncate body (default: 500) |
| `include_body` | boolean | true | Include body field |
| `format` | string | json | Response format (json\|csv\|ndjson) |

**Example Request**:
```bash
curl "https://archive.example.com/api/v1/comments?author=username&limit=50"
```

**Example Response**:
```json
{
  "data": [
    {
      "id": "xyz789",
      "post_id": "abc123",
      "parent_id": "t3_abc123",
      "subreddit": "privacy",
      "author": "username",
      "body": "Truncated to 500 characters...",
      "body_length": 1250,
      "body_truncated": true,
      "body_full_length": 1250,
      "permalink": "/r/privacy/comments/abc123/post_title/xyz789/",
      "created_utc": 1640001000,
      "created_at": "2021-12-20T00:16:40Z",
      "score": 25,
      "depth": 0
    }
  ],
  "meta": {...},
  "links": {...}
}
```

**Note**: Body is truncated to 500 characters by default in list view. Use `max_body_length` to adjust or `include_body=false` to exclude.

---

### GET /comments/{id}

Get single comment by ID.

**URL Parameters**:
- `id` (string): Comment ID

**Query Parameters**:
- `fields` (string): Comma-separated field names
- `max_body_length` (integer): Truncate body
- `include_body` (boolean): Include body field

**Example Request**:
```bash
curl "https://archive.example.com/api/v1/comments/xyz789"
```

**Example Response**:
```json
{
  "id": "xyz789",
  "post_id": "abc123",
  "parent_id": "t3_abc123",
  "subreddit": "privacy",
  "author": "username",
  "body": "Full comment text...",
  "permalink": "/r/privacy/comments/abc123/post_title/xyz789/",
  "created_utc": 1640001000,
  "created_at": "2021-12-20T00:16:40Z",
  "score": 25,
  "depth": 0
}
```

**Status Codes**:
- `200 OK` - Comment found
- `400 Bad Request` - Invalid comment ID format
- `404 Not Found` - Comment not found

---

### GET /comments/random

Get random sample of comments.

**Query Parameters**:
- `n` (integer, default: 10): Number of random comments (1-100)
- `subreddit` (string): Filter by subreddit
- `seed` (integer): Random seed for reproducibility
- `fields` (string): Comma-separated field names

**Example Request**:
```bash
curl "https://archive.example.com/api/v1/comments/random?n=50&subreddit=privacy"
```

**Example Response**:
```json
{
  "data": [...],
  "meta": {
    "n": 50,
    "seed": null,
    "subreddit": "privacy"
  }
}
```

---

### GET /comments/aggregate

Aggregate comments by author, subreddit, or time period.

**Query Parameters**:
- `group_by` (string, required): Grouping field (author\|subreddit\|created_utc)
- `frequency` (string): Time frequency for created_utc (hour\|day\|week\|month\|year)
- `limit` (integer, default: 100): Maximum groups (10-1000)
- `subreddit` (string): Filter by subreddit
- `author` (string): Filter by author
- `min_score` (integer): Minimum score threshold

**Example Request**:
```bash
# Most active commenters
curl "https://archive.example.com/api/v1/comments/aggregate?group_by=author&limit=50"

# Comments over time
curl "https://archive.example.com/api/v1/comments/aggregate?group_by=created_utc&frequency=day"
```

**Example Response**:
```json
{
  "data": [
    {
      "author": "username",
      "count": 1500,
      "total_score": 25000,
      "avg_score": 16.67
    }
  ],
  "meta": {
    "group_by": "author",
    "limit": 50
  }
}
```

---

### POST /comments/batch

Fetch multiple comments by ID in one request.

**Request Body**:
```json
{
  "ids": ["xyz789", "xyz790", "xyz791"]
}
```

**Query Parameters**:
- `fields` (string): Comma-separated field names
- `max_body_length` (integer): Truncate body
- `include_body` (boolean): Include body field

**Example Request**:
```bash
curl -X POST "https://archive.example.com/api/v1/comments/batch" \
  -H "Content-Type: application/json" \
  -d '{"ids":["xyz789","xyz790"]}'
```

**Example Response**:
```json
{
  "found": [...],
  "not_found": [],
  "meta": {
    "requested": 2,
    "found": 2,
    "not_found": 0
  }
}
```

**Status Codes**:
- `200 OK` - Success
- `400 Bad Request` - Invalid request or too many IDs (max 100)

---

## Users Endpoints

### GET /users

Get paginated list of users with sorting.

**Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 25 | Results per page (10-100) |
| `page` | integer | 1 | Page number (≥ 1) |
| `sort` | string | karma | Sort order (karma\|activity\|posts\|comments) |
| `fields` | string | all | Comma-separated field names |
| `format` | string | json | Response format (json\|csv\|ndjson) |

**Example Request**:
```bash
curl "https://archive.example.com/api/v1/users?sort=activity&limit=20"
```

**Example Response**:
```json
{
  "data": [
    {
      "username": "username",
      "post_count": 150,
      "comment_count": 1500,
      "total_activity": 1650,
      "total_karma": 25000,
      "first_seen_utc": 1600000000,
      "first_seen_at": "2020-09-13T12:26:40Z",
      "last_seen_utc": 1640000000,
      "last_seen_at": "2021-12-20T00:00:00Z"
    }
  ],
  "meta": {...},
  "links": {...}
}
```

---

### GET /users/{username}

Get user profile and statistics.

**URL Parameters**:
- `username` (string): Username (3-20 alphanumeric + underscore + hyphen)

**Query Parameters**:
- `fields` (string): Comma-separated field names

**Example Request**:
```bash
curl "https://archive.example.com/api/v1/users/username"
```

**Example Response**:
```json
{
  "username": "username",
  "post_count": 150,
  "comment_count": 1500,
  "total_activity": 1650,
  "total_karma": 25000,
  "first_seen_utc": 1600000000,
  "first_seen_at": "2020-09-13T12:26:40Z",
  "last_seen_utc": 1640000000,
  "last_seen_at": "2021-12-20T00:00:00Z",
  "subreddit_activity": {
    "privacy": 500,
    "degoogle": 300
  }
}
```

**Status Codes**:
- `200 OK` - User found
- `400 Bad Request` - Invalid username format
- `404 Not Found` - User not found

---

### GET /users/{username}/summary

Get quick user overview (MCP-optimized).

**URL Parameters**:
- `username` (string): Username

**Example Request**:
```bash
curl "https://archive.example.com/api/v1/users/username/summary"
```

**Example Response**:
```json
{
  "username": "username",
  "total_activity": 1650,
  "total_karma": 25000,
  "top_subreddits": [
    {"subreddit": "privacy", "count": 500},
    {"subreddit": "degoogle", "count": 300}
  ],
  "recent_posts": [...],
  "recent_comments": [...]
}
```

**Status Codes**:
- `200 OK` - Success
- `404 Not Found` - User not found

**Use Case**: User overview in one API call

---

### GET /users/{username}/posts

Get posts by specific user.

**URL Parameters**:
- `username` (string): Username

**Query Parameters**:
- `limit` (integer, default: 25): Results per page (10-100)
- `page` (integer, default: 1): Page number
- `sort` (string, default: score): Sort order (score\|created_utc\|num_comments)
- `fields` (string): Comma-separated field names
- `max_body_length` (integer): Truncate selftext
- `include_body` (boolean): Include selftext field

**Example Request**:
```bash
curl "https://archive.example.com/api/v1/users/username/posts?limit=50"
```

**Response**: Same format as `/posts` endpoint

---

### GET /users/{username}/comments

Get comments by specific user.

**URL Parameters**:
- `username` (string): Username

**Query Parameters**:
- `limit` (integer, default: 25): Results per page (10-100)
- `page` (integer, default: 1): Page number
- `sort` (string, default: score): Sort order (score\|created_utc)
- `fields` (string): Comma-separated field names
- `max_body_length` (integer): Truncate body
- `include_body` (boolean): Include body field

**Example Request**:
```bash
curl "https://archive.example.com/api/v1/users/username/comments?limit=100"
```

**Response**: Same format as `/comments` endpoint

---

### GET /users/aggregate

Aggregate user statistics.

**Query Parameters**:
- `sort_by` (string, default: karma): Sort field (karma\|activity\|posts\|comments)
- `limit` (integer, default: 100): Maximum users (10-1000)

**Example Request**:
```bash
curl "https://archive.example.com/api/v1/users/aggregate?sort_by=activity&limit=50"
```

**Example Response**:
```json
{
  "data": [
    {
      "username": "username",
      "total_activity": 1650,
      "total_karma": 25000,
      "post_count": 150,
      "comment_count": 1500
    }
  ],
  "meta": {
    "sort_by": "activity",
    "limit": 50
  }
}
```

---

### POST /users/batch

Fetch multiple user profiles in one request.

**Request Body**:
```json
{
  "usernames": ["user1", "user2", "user3"]
}
```

**Query Parameters**:
- `fields` (string): Comma-separated field names

**Example Request**:
```bash
curl -X POST "https://archive.example.com/api/v1/users/batch" \
  -H "Content-Type: application/json" \
  -d '{"usernames":["user1","user2","user3"]}'
```

**Example Response**:
```json
{
  "found": [...],
  "not_found": ["user3"],
  "meta": {
    "requested": 3,
    "found": 2,
    "not_found": 1
  }
}
```

**Status Codes**:
- `200 OK` - Success
- `400 Bad Request` - Invalid request or too many usernames (max 100)

---

## Subreddits Endpoints

### GET /subreddits

Get list of subreddits in archive with post counts.

**Query Parameters**:
- `format` (string): Response format (json\|csv\|ndjson)

**Example Request**:
```bash
curl "https://archive.example.com/api/v1/subreddits"
```

**Example Response**:
```json
{
  "data": [
    {
      "name": "privacy",
      "post_count": 25000
    },
    {
      "name": "degoogle",
      "post_count": 10000
    }
  ],
  "meta": {
    "total": 2
  }
}
```

---

### GET /subreddits/{name}

Get subreddit statistics and metadata.

**URL Parameters**:
- `name` (string): Subreddit name (2-21 alphanumeric + underscore)

**Example Request**:
```bash
curl "https://archive.example.com/api/v1/subreddits/privacy"
```

**Example Response**:
```json
{
  "subreddit": "privacy",
  "total_posts": 25000,
  "total_comments": 250000,
  "unique_users": 5000,
  "earliest_post": "2010-01-01T00:00:00Z",
  "latest_post": "2024-12-31T23:59:59Z",
  "avg_post_score": 45.5
}
```

**Status Codes**:
- `200 OK` - Subreddit found
- `400 Bad Request` - Invalid subreddit name
- `404 Not Found` - Subreddit not found

---

### GET /subreddits/{name}/summary

Get quick subreddit overview (MCP-optimized).

**URL Parameters**:
- `name` (string): Subreddit name

**Example Request**:
```bash
curl "https://archive.example.com/api/v1/subreddits/privacy/summary"
```

**Example Response**:
```json
{
  "subreddit": "privacy",
  "total_posts": 25000,
  "total_comments": 250000,
  "unique_users": 5000,
  "top_posts": [...],
  "top_contributors": [...],
  "recent_activity": [...]
}
```

**Status Codes**:
- `200 OK` - Success
- `404 Not Found` - Subreddit not found

**Use Case**: Subreddit overview in one API call

---

## Platforms Endpoints (Multi-Platform Archives)

For archives containing content from multiple platforms (Reddit, Voat, Ruqqus).

### GET /platforms

Get list of platforms in the archive with statistics.

**Example Request**:
```bash
curl "https://archive.example.com/api/v1/platforms"
```

**Example Response**:
```json
{
  "data": [
    {
      "platform": "reddit",
      "display_name": "Reddit",
      "url_prefix": "/r/",
      "post_count": 50000,
      "comment_count": 500000,
      "community_count": 5
    },
    {
      "platform": "voat",
      "display_name": "Voat",
      "url_prefix": "/v/",
      "post_count": 10000,
      "comment_count": 80000,
      "community_count": 3
    },
    {
      "platform": "ruqqus",
      "display_name": "Ruqqus",
      "url_prefix": "/g/",
      "post_count": 5000,
      "comment_count": 30000,
      "community_count": 2
    }
  ],
  "meta": {
    "total_platforms": 3
  }
}
```

---

### GET /platforms/{platform}/communities

Get list of communities for a specific platform.

**URL Parameters**:
- `platform` (string): Platform name (reddit|voat|ruqqus)

**Query Parameters**:
- `limit` (integer, default: 25): Results per page (10-100)
- `page` (integer, default: 1): Page number
- `sort` (string, default: posts): Sort order (posts|comments|name)

**Example Request**:
```bash
curl "https://archive.example.com/api/v1/platforms/voat/communities?sort=posts&limit=10"
```

**Example Response**:
```json
{
  "data": [
    {
      "name": "voatdev",
      "platform": "voat",
      "post_count": 5000,
      "comment_count": 40000,
      "unique_users": 500
    },
    {
      "name": "technology",
      "platform": "voat",
      "post_count": 3000,
      "comment_count": 25000,
      "unique_users": 350
    }
  ],
  "meta": {
    "page": 1,
    "limit": 10,
    "total": 3,
    "platform": "voat"
  }
}
```

---

## Search Endpoints

### GET /search

Full-text search with Google-style operators.

**Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `q` | string | required | Search query with operators |
| `type` | string | both | Result type (post\|comment\|both) |
| `limit` | integer | 25 | Results per page (10-100) |
| `page` | integer | 1 | Page number (≥ 1) |
| `sort` | string | relevance | Sort order (relevance\|score\|created_utc) |
| `fields` | string | all | Comma-separated field names |
| `max_body_length` | integer | 500 | Truncate text (default: 500) |

**Search Operators**:

| Operator | Example | Description |
|----------|---------|-------------|
| `"phrase"` | `"reddit censorship"` | Exact phrase search |
| `OR` | `banned OR removed` | Boolean OR (uppercase) |
| `-exclude` | `censorship -moderator` | Exclude term |
| `sub:` | `sub:privacy` | Filter by subreddit |
| `author:` | `author:username` | Filter by author |
| `score:` | `score:100` | Minimum score |
| `type:` | `type:post` | Result type (post\|comment) |
| `sort:` | `sort:score` | Sort order |

**Example Request**:
```bash
# Simple search
curl "https://archive.example.com/api/v1/search?q=censorship&limit=10"

# Advanced search with operators
curl 'https://archive.example.com/api/v1/search?q="reddit+censorship"+OR+banned+-spam+sub:privacy+score:10+type:post&sort=score'
```

**Example Response**:
```json
{
  "data": [
    {
      "type": "post",
      "id": "abc123",
      "title": "Post about censorship",
      "snippet": "...reddit <b>censorship</b> is...",
      "score": 150,
      "subreddit": "privacy",
      "author": "username",
      "created_at": "2021-12-20T00:00:00Z"
    }
  ],
  "meta": {
    "page": 1,
    "limit": 10,
    "total": 245,
    "query": "censorship",
    "filters": {
      "subreddit": null,
      "author": null,
      "min_score": 0,
      "type": "both"
    }
  },
  "links": {...}
}
```

**Status Codes**:
- `200 OK` - Success
- `400 Bad Request` - Invalid query or parameters

**Use Case**: Full-text search, content discovery

---

### GET /search/explain

Query parsing debugger showing how operators are interpreted.

**Query Parameters**:
- `q` (string, required): Search query to explain

**Example Request**:
```bash
curl 'https://archive.example.com/api/v1/search/explain?q="censorship"+OR+banned+-spam+sub:privacy+score:10'
```

**Example Response**:
```json
{
  "original_query": "\"censorship\" OR banned -spam sub:privacy score:10",
  "parsed": {
    "base_query": "censorship OR banned",
    "excluded_terms": ["spam"],
    "filters": {
      "subreddit": "privacy",
      "author": null,
      "min_score": 10,
      "type": null,
      "sort": null
    }
  },
  "sql_query": "SELECT ... WHERE to_tsquery('websearch', 'censorship OR banned') @@ fts ...",
  "explanation": "This query searches for posts/comments containing 'censorship' OR 'banned', excluding 'spam', filtered to subreddit 'privacy' with minimum score of 10."
}
```

**Status Codes**:
- `200 OK` - Success
- `400 Bad Request` - Invalid query

**Use Case**: Debugging search queries, understanding operator precedence

---

## Field Selection

Reduce response size and token usage by selecting specific fields.

### Valid Fields Per Resource

**Posts**:
```
id, subreddit, author, title, selftext, url, domain, score, num_comments,
created_utc, created_at, permalink, is_self, nsfw, over_18, locked, stickied
```

**Comments**:
```
id, post_id, parent_id, author, body, score, created_utc, created_at,
subreddit, permalink, depth, body_length, body_truncated, body_full_length
```

**Users**:
```
username, post_count, comment_count, total_activity, total_karma,
first_seen_utc, first_seen_at, last_seen_utc, last_seen_at, subreddit_activity
```

**Subreddits**:
```
name, subreddit, total_posts, total_comments, unique_users, earliest_post,
latest_post, avg_post_score, avg_score
```

### Usage Examples

```bash
# Get only IDs and titles
curl "https://archive.example.com/api/v1/posts?fields=id,title,score&limit=50"

# Get user karma only
curl "https://archive.example.com/api/v1/users?fields=username,total_karma&limit=100"

# Get comment metadata without body
curl "https://archive.example.com/api/v1/comments?fields=id,author,score,created_at&limit=50"
```

### Benefits

- **Token Reduction**: 50-90% fewer tokens for MCP/AI applications
- **Bandwidth Savings**: Smaller response sizes
- **Faster Processing**: Less JSON parsing overhead

### Error Handling

```json
{
  "error": "Invalid fields: invalid_field1, invalid_field2",
  "valid_fields": ["id", "title", "score", "..."]
}
```

---

## Truncation Controls

Limit body text length with metadata about truncation.

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_body_length` | integer | none | Truncate to N characters |
| `include_body` | boolean | true | Include body/selftext fields |

### Truncation Metadata

When text is truncated, additional fields are added:

| Field | Type | Description |
|-------|------|-------------|
| `{field}_truncated` | boolean | Whether text was truncated |
| `{field}_full_length` | integer | Original text length |

### Usage Examples

```bash
# Limit selftext to 200 characters
curl "https://archive.example.com/api/v1/posts?max_body_length=200&limit=10"

# Exclude body entirely
curl "https://archive.example.com/api/v1/comments?include_body=false&limit=50"

# Combine with field selection
curl "https://archive.example.com/api/v1/posts?fields=id,title,selftext&max_body_length=100"
```

### Example Response

```json
{
  "id": "abc123",
  "title": "Post title",
  "selftext": "This is the first 200 characters of a much longer post...",
  "selftext_truncated": true,
  "selftext_full_length": 1850,
  "score": 150
}
```

### Benefits

- **Token Control**: Prevent response size overflow
- **Preview Generation**: Show snippets with full text available
- **Bandwidth Optimization**: Reduce data transfer

---

## Export Formats

Export data in CSV or NDJSON formats for analysis and processing.

### Supported Formats

| Format | MIME Type | Description |
|--------|-----------|-------------|
| `json` | application/json | Default with pagination |
| `csv` | text/csv | Comma-separated values with headers |
| `ndjson` | application/x-ndjson | Newline-delimited JSON |

### Usage

```bash
# Export posts to CSV
curl "https://archive.example.com/api/v1/posts?subreddit=privacy&format=csv&limit=100" -o posts.csv

# Export comments to NDJSON
curl "https://archive.example.com/api/v1/comments?format=ndjson&limit=1000" -o comments.ndjson

# Export users to CSV
curl "https://archive.example.com/api/v1/users?format=csv&limit=500" -o users.csv
```

### CSV Format

- **Headers**: Column names in first row
- **Nested Data**: Flattened with dot notation (e.g., `subreddit_activity.privacy`)
- **Null Values**: Empty strings
- **Timestamps**: ISO 8601 format
- **Filename**: Automatic with timestamp (e.g., `posts_privacy_2025-01-23.csv`)

### NDJSON Format

- **Structure**: One JSON object per line
- **Streaming**: Suitable for large datasets
- **Processing**: Line-by-line parsing
- **Filename**: Automatic with timestamp (e.g., `comments_2025-01-23.ndjson`)

### Limitations

- **No Pagination**: Export returns single page (max 100 items)
- **No Streaming**: Full response buffered in memory
- **Rate Limited**: Same 100 req/min limit applies

### Example CSV Output

```csv
id,subreddit,author,title,score,num_comments,created_at
abc123,privacy,user1,Post title,150,25,2021-12-20T00:00:00Z
def456,privacy,user2,Another post,120,30,2021-12-21T00:00:00Z
```

### Example NDJSON Output

```json
{"id":"abc123","subreddit":"privacy","author":"user1","title":"Post title","score":150}
{"id":"def456","subreddit":"privacy","author":"user2","title":"Another post","score":120}
```

---

## Aggregation

Group and analyze data by time, author, or subreddit.

### Grouping Options

| `group_by` | Description | Time Frequency |
|------------|-------------|----------------|
| `author` | Group by username | N/A |
| `subreddit` | Group by subreddit | N/A |
| `created_utc` | Group by time | hour\|day\|week\|month\|year |

### Time Frequencies

Available when `group_by=created_utc`:

- `hour` - Hourly aggregation
- `day` - Daily aggregation
- `week` - Weekly aggregation (Monday start)
- `month` - Monthly aggregation
- `year` - Yearly aggregation

### Aggregation Fields

Returned for each group:

| Field | Type | Description |
|-------|------|-------------|
| `{group_field}` | varies | Group identifier |
| `count` | integer | Number of items in group |
| `total_score` | integer | Sum of scores |
| `avg_score` | float | Average score |
| `total_comments` | integer | Sum of comment counts (posts only) |

### Usage Examples

```bash
# Top 20 contributors by post count
curl "https://archive.example.com/api/v1/posts/aggregate?group_by=author&limit=20"

# Monthly activity over past year
curl "https://archive.example.com/api/v1/posts/aggregate?group_by=created_utc&frequency=month&limit=12"

# Compare subreddit activity
curl "https://archive.example.com/api/v1/comments/aggregate?group_by=subreddit"

# Daily comment patterns
curl "https://archive.example.com/api/v1/comments/aggregate?group_by=created_utc&frequency=day&limit=30"
```

### Example Response

```json
{
  "data": [
    {
      "author": "username",
      "count": 150,
      "total_score": 12000,
      "avg_score": 80.0,
      "total_comments": 3500
    }
  ],
  "meta": {
    "group_by": "author",
    "frequency": null,
    "limit": 20,
    "filters": {
      "subreddit": null,
      "min_score": 0
    }
  }
}
```

### Performance

- **Query Timeout**: 30 seconds for expensive aggregations
- **Indexing**: Optimized with database indexes
- **Caching**: Consider caching results for repeated queries

### Use Cases

- **Leaderboards**: Top contributors by karma/activity
- **Trend Analysis**: Activity patterns over time
- **Content Analysis**: Subreddit comparison
- **User Research**: Behavior patterns

---

## Batch Operations

Fetch multiple resources in one request to reduce API calls.

### Available Batch Endpoints

| Endpoint | Request Body | Max Items |
|----------|--------------|-----------|
| `POST /posts/batch` | `{"ids": [...]}` | 100 |
| `POST /comments/batch` | `{"ids": [...]}` | 100 |
| `POST /users/batch` | `{"usernames": [...]}` | 100 |

### Usage Examples

```bash
# Batch fetch posts
curl -X POST "https://archive.example.com/api/v1/posts/batch" \
  -H "Content-Type: application/json" \
  -d '{"ids":["abc123","def456","ghi789"]}'

# Batch fetch comments with field selection
curl -X POST "https://archive.example.com/api/v1/comments/batch?fields=id,author,score" \
  -H "Content-Type: application/json" \
  -d '{"ids":["xyz789","xyz790"]}'

# Batch fetch users with truncation
curl -X POST "https://archive.example.com/api/v1/users/batch" \
  -H "Content-Type: application/json" \
  -d '{"usernames":["user1","user2","user3"]}'
```

### Response Format

```json
{
  "found": [
    {"id": "abc123", "title": "Post 1", "...": "..."},
    {"id": "def456", "title": "Post 2", "...": "..."}
  ],
  "not_found": ["ghi789"],
  "meta": {
    "requested": 3,
    "found": 2,
    "not_found": 1
  }
}
```

### Benefits

- **Request Reduction**: 50 requests → 1 request
- **Token Savings**: Single API call overhead
- **Latency Reduction**: Parallel database lookups

### Limitations

- **Maximum Items**: 100 per request
- **No Sorting**: Results returned in arbitrary order
- **No Pagination**: All found items returned at once

### Error Handling

```bash
# Invalid request body
{"error": "Request body must be JSON with 'ids' or 'usernames' array"}

# Too many items
{"error": "Maximum 100 items per batch request"}

# Empty array
{"found": [], "not_found": [], "meta": {"requested": 0, "found": 0, "not_found": 0}}
```

---

## Context & Summary

MCP-optimized endpoints that combine multiple queries into one.

### GET /posts/{id}/context

Get post with top comments in one request.

**Benefits**: Reduces 11+ API calls to 1

**Parameters**:
- `top_comments` (integer, default: 10): Number of top-level comments (1-50)
- `max_depth` (integer, default: 2): Maximum reply depth (1-5)
- `sort` (string, default: score): Sort order (score\|created_utc)
- `max_body_length` (integer): Truncate all text

**Example**:
```bash
curl "https://archive.example.com/api/v1/posts/abc123/context?top_comments=5&max_depth=2&max_body_length=200"
```

---

### GET /users/{username}/summary

Get user overview with recent activity.

**Benefits**: Combines profile + recent posts/comments

**Example**:
```bash
curl "https://archive.example.com/api/v1/users/username/summary"
```

---

### GET /subreddits/{name}/summary

Get subreddit overview with top content.

**Benefits**: Combines stats + top posts + top contributors

**Example**:
```bash
curl "https://archive.example.com/api/v1/subreddits/privacy/summary"
```

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | Example |
|------|---------|---------|
| 200 | Success | Request successful |
| 400 | Bad Request | Invalid parameters, validation errors |
| 404 | Not Found | Resource doesn't exist |
| 408 | Request Timeout | Aggregation query exceeded 30s |
| 429 | Too Many Requests | Rate limit exceeded (100 req/min) |
| 500 | Internal Server Error | Unexpected server error |
| 503 | Service Unavailable | Database connection failed |

### Error Response Format

```json
{
  "error": "Error message describing what went wrong",
  "details": ["Additional detail 1", "Additional detail 2"]
}
```

### Common Validation Errors

```json
// Invalid limit
{"error": "Validation failed", "details": ["limit must be between 10 and 100"]}

// Invalid page
{"error": "Validation failed", "details": ["page must be >= 1"]}

// Invalid sort
{"error": "Invalid sort parameter. Must be one of: score, created_utc, num_comments"}

// Invalid fields
{"error": "Invalid fields: invalid_field", "valid_fields": ["id", "title", "..."]}

// Invalid ID format
{"error": "Invalid post ID format"}

// Invalid username
{"error": "Invalid username format"}
```

### Security Validation

All inputs are validated for:

- **SQL Injection**: Parameterized queries
- **XSS Prevention**: Escaped output
- **Regex Whitelists**: Post/comment IDs, usernames, subreddit names
- **Bounds Checking**: Numeric parameters

### Handling Errors in Code

**Python**:
```python
import requests

response = requests.get("https://archive.example.com/api/v1/posts")

if response.status_code == 200:
    data = response.json()
elif response.status_code == 400:
    error = response.json()
    print(f"Validation error: {error['error']}")
elif response.status_code == 429:
    print("Rate limited - wait 60 seconds")
    time.sleep(60)
elif response.status_code >= 500:
    print("Server error - retry with exponential backoff")
```

**JavaScript**:
```javascript
fetch('https://archive.example.com/api/v1/posts')
  .then(response => {
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return response.json();
  })
  .then(data => console.log(data))
  .catch(error => console.error('Error:', error));
```

---

## Rate Limiting

### Limits

- **Requests**: 100 per minute per IP address
- **Window**: Rolling 60-second window
- **Scope**: Per IP address

### Response Headers

Rate limit information in response headers:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1640000060
```

### Rate Limit Exceeded Response

```json
{
  "error": "Rate limit exceeded. Please wait and try again.",
  "retry_after": 42
}
```

**Status Code**: `429 Too Many Requests`

### Best Practices

1. **Monitor Headers**: Check remaining requests
2. **Implement Backoff**: Exponential backoff on errors
3. **Batch Requests**: Use batch endpoints to reduce calls
4. **Cache Responses**: Store results locally when possible
5. **Respect Limits**: Don't implement aggressive retry loops

### Example Rate Limit Handling

**Python**:
```python
import requests
import time

def api_request_with_retry(url, max_retries=3):
    for attempt in range(max_retries):
        response = requests.get(url)

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:
            retry_after = int(response.headers.get('X-RateLimit-Reset', 60))
            print(f"Rate limited - waiting {retry_after}s")
            time.sleep(retry_after)
        else:
            raise Exception(f"HTTP {response.status_code}")

    raise Exception("Max retries exceeded")
```

---

## Best Practices

### 1. Use Pagination Efficiently

```bash
# Good: Reasonable page size
curl "https://archive.example.com/api/v1/posts?limit=50&page=1"

# Bad: Requesting too many at once
curl "https://archive.example.com/api/v1/posts?limit=100&page=1000"
```

### 2. Combine Filters

```bash
# Efficient: Filter at API level
curl "https://archive.example.com/api/v1/posts?subreddit=privacy&min_score=100&limit=25"

# Inefficient: Fetch all and filter locally
curl "https://archive.example.com/api/v1/posts?limit=100" | jq 'filter...'
```

### 3. Use Field Selection

```bash
# Good: Only request needed fields
curl "https://archive.example.com/api/v1/posts?fields=id,title,score&limit=100"

# Bad: Fetch everything and discard
curl "https://archive.example.com/api/v1/posts?limit=100"
```

### 4. Leverage Batch Endpoints

```bash
# Good: Batch fetch
curl -X POST "https://archive.example.com/api/v1/posts/batch" \
  -d '{"ids":["id1","id2","id3"]}'

# Bad: Sequential requests
for id in id1 id2 id3; do
  curl "https://archive.example.com/api/v1/posts/$id"
done
```

### 5. Use Context Endpoints

```bash
# Good: Single context call
curl "https://archive.example.com/api/v1/posts/abc123/context?top_comments=10"

# Bad: Multiple calls
curl "https://archive.example.com/api/v1/posts/abc123"
curl "https://archive.example.com/api/v1/posts/abc123/comments"
```

### 6. Export Large Datasets

```bash
# Good: Export to CSV/NDJSON for analysis
curl "https://archive.example.com/api/v1/posts?format=csv&limit=100" -o data.csv

# Bad: Multiple JSON API calls
```

### 7. Cache Results

```python
import requests
from functools import lru_cache

@lru_cache(maxsize=128)
def get_user_profile(username):
    response = requests.get(f"https://archive.example.com/api/v1/users/{username}")
    return response.json()
```

### 8. Handle Errors Gracefully

```python
try:
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()
except requests.exceptions.HTTPError as e:
    if e.response.status_code == 404:
        print("Resource not found")
    elif e.response.status_code == 429:
        time.sleep(60)
    else:
        print(f"Error: {e}")
```

### 9. Optimize Search Queries

```bash
# Good: Specific query with filters
curl "https://archive.example.com/api/v1/search?q=privacy&sub:privacy&score:10&limit=25"

# Bad: Broad query without filters
curl "https://archive.example.com/api/v1/search?q=the&limit=100"
```

### 10. Monitor Rate Limits

```python
response = requests.get(url)
remaining = int(response.headers.get('X-RateLimit-Remaining', 100))
if remaining < 10:
    print(f"Warning: Only {remaining} requests remaining")
```

---

## Code Examples

### Python

#### Basic Usage

```python
import requests

# Get archive stats
response = requests.get("https://archive.example.com/api/v1/stats")
stats = response.json()
print(f"Total posts: {stats['content']['total_posts']}")

# Get posts from subreddit
response = requests.get(
    "https://archive.example.com/api/v1/posts",
    params={
        "subreddit": "privacy",
        "limit": 50,
        "min_score": 100,
        "sort": "score"
    }
)
posts = response.json()

for post in posts['data']:
    print(f"{post['title']} - Score: {post['score']}")
```

#### Pagination

```python
def fetch_all_posts(subreddit, min_score=0):
    """Fetch all posts from subreddit using pagination."""
    all_posts = []
    page = 1

    while True:
        response = requests.get(
            "https://archive.example.com/api/v1/posts",
            params={
                "subreddit": subreddit,
                "min_score": min_score,
                "page": page,
                "limit": 100
            }
        )

        data = response.json()
        all_posts.extend(data['data'])

        # Check if there are more pages
        if not data['links']['next']:
            break

        page += 1

    return all_posts
```

#### Error Handling

```python
import time

def api_request_with_retry(url, params=None, max_retries=3):
    """Make API request with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                # Rate limited - wait and retry
                wait_time = 2 ** attempt * 60
                print(f"Rate limited - waiting {wait_time}s")
                time.sleep(wait_time)
            elif e.response.status_code >= 500:
                # Server error - retry with backoff
                wait_time = 2 ** attempt
                print(f"Server error - retrying in {wait_time}s")
                time.sleep(wait_time)
            else:
                raise
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            if attempt == max_retries - 1:
                raise

    raise Exception("Max retries exceeded")
```

#### Field Selection

```python
# Get only IDs and titles to minimize response size
response = requests.get(
    "https://archive.example.com/api/v1/posts",
    params={
        "fields": "id,title,score",
        "limit": 100
    }
)
```

#### Export to CSV

```python
import csv

# Export posts to CSV
response = requests.get(
    "https://archive.example.com/api/v1/posts",
    params={
        "subreddit": "privacy",
        "format": "csv",
        "limit": 100
    }
)

with open('posts.csv', 'wb') as f:
    f.write(response.content)
```

#### Search

```python
# Full-text search with operators
response = requests.get(
    "https://archive.example.com/api/v1/search",
    params={
        "q": "censorship OR banned -spam sub:privacy score:10",
        "limit": 50,
        "sort": "score"
    }
)
results = response.json()

for item in results['data']:
    print(f"[{item['type']}] {item.get('title', item.get('snippet'))}")
```

#### Batch Operations

```python
# Batch fetch posts
post_ids = ["abc123", "def456", "ghi789"]
response = requests.post(
    "https://archive.example.com/api/v1/posts/batch",
    json={"ids": post_ids},
    headers={"Content-Type": "application/json"}
)
data = response.json()

print(f"Found {len(data['found'])} of {len(post_ids)} posts")
for post in data['found']:
    print(f"- {post['title']}")
```

---

### JavaScript

#### Basic Usage

```javascript
// Get archive stats
fetch('https://archive.example.com/api/v1/stats')
  .then(response => response.json())
  .then(data => {
    console.log(`Total posts: ${data.content.total_posts}`);
  });

// Get posts from subreddit
async function getPosts(subreddit, page = 1) {
  const url = new URL('https://archive.example.com/api/v1/posts');
  url.searchParams.set('subreddit', subreddit);
  url.searchParams.set('page', page);
  url.searchParams.set('limit', 25);
  url.searchParams.set('sort', 'score');

  const response = await fetch(url);
  return await response.json();
}
```

#### Pagination

```javascript
async function fetchAllPosts(subreddit, minScore = 0) {
  let allPosts = [];
  let page = 1;
  let hasMore = true;

  while (hasMore) {
    const url = new URL('https://archive.example.com/api/v1/posts');
    url.searchParams.set('subreddit', subreddit);
    url.searchParams.set('min_score', minScore);
    url.searchParams.set('page', page);
    url.searchParams.set('limit', 100);

    const response = await fetch(url);
    const data = await response.json();

    allPosts = allPosts.concat(data.data);
    hasMore = data.links.next !== null;
    page++;
  }

  return allPosts;
}
```

#### Error Handling

```javascript
async function apiRequest(url, options = {}) {
  const maxRetries = 3;
  let attempt = 0;

  while (attempt < maxRetries) {
    try {
      const response = await fetch(url, options);

      if (!response.ok) {
        if (response.status === 429) {
          // Rate limited
          const retryAfter = parseInt(response.headers.get('X-RateLimit-Reset')) || 60;
          console.log(`Rate limited - waiting ${retryAfter}s`);
          await sleep(retryAfter * 1000);
          attempt++;
          continue;
        } else if (response.status >= 500) {
          // Server error - retry with backoff
          const waitTime = Math.pow(2, attempt) * 1000;
          console.log(`Server error - retrying in ${waitTime}ms`);
          await sleep(waitTime);
          attempt++;
          continue;
        } else {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
      }

      return await response.json();
    } catch (error) {
      if (attempt === maxRetries - 1) {
        throw error;
      }
      attempt++;
    }
  }
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}
```

#### React Hook Example

```javascript
import { useState, useEffect } from 'react';

function useArchivePosts(subreddit, minScore = 0) {
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function fetchPosts() {
      try {
        setLoading(true);
        const url = new URL('https://archive.example.com/api/v1/posts');
        url.searchParams.set('subreddit', subreddit);
        url.searchParams.set('min_score', minScore);
        url.searchParams.set('limit', 50);

        const response = await fetch(url);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        setPosts(data.data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }

    fetchPosts();
  }, [subreddit, minScore]);

  return { posts, loading, error };
}

// Usage
function PostList() {
  const { posts, loading, error } = useArchivePosts('privacy', 100);

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;

  return (
    <ul>
      {posts.map(post => (
        <li key={post.id}>{post.title} - {post.score}</li>
      ))}
    </ul>
  );
}
```

---

### cURL

#### Basic Requests

```bash
# Health check
curl https://archive.example.com/api/v1/health

# Get statistics
curl https://archive.example.com/api/v1/stats | jq

# List posts
curl "https://archive.example.com/api/v1/posts?limit=10" | jq

# Get specific post
curl "https://archive.example.com/api/v1/posts/abc123" | jq

# Get user profile
curl "https://archive.example.com/api/v1/users/username" | jq
```

#### Filtering and Sorting

```bash
# Posts from subreddit with minimum score
curl "https://archive.example.com/api/v1/posts?subreddit=privacy&min_score=100&limit=25" | jq

# Comments by author
curl "https://archive.example.com/api/v1/comments?author=username&limit=50" | jq

# Top users by karma
curl "https://archive.example.com/api/v1/users?sort=karma&limit=20" | jq
```

#### Field Selection

```bash
# Only IDs and titles
curl "https://archive.example.com/api/v1/posts?fields=id,title,score&limit=50" | jq

# User karma only
curl "https://archive.example.com/api/v1/users?fields=username,total_karma&limit=100" | jq
```

#### Truncation

```bash
# Limit selftext to 200 characters
curl "https://archive.example.com/api/v1/posts?max_body_length=200&limit=10" | jq

# Exclude body entirely
curl "https://archive.example.com/api/v1/comments?include_body=false&limit=50" | jq
```

#### Export Formats

```bash
# Download posts as CSV
curl "https://archive.example.com/api/v1/posts?subreddit=privacy&format=csv&limit=100" -o posts.csv

# Download comments as NDJSON
curl "https://archive.example.com/api/v1/comments?format=ndjson&limit=1000" -o comments.ndjson
```

#### Search

```bash
# Simple search
curl "https://archive.example.com/api/v1/search?q=censorship&limit=10" | jq

# Search with operators
curl "https://archive.example.com/api/v1/search?q=banned+OR+removed+-spam+sub:privacy+score:10" | jq

# Explain query
curl "https://archive.example.com/api/v1/search/explain?q=censorship+OR+banned" | jq
```

#### Aggregation

```bash
# Top contributors
curl "https://archive.example.com/api/v1/posts/aggregate?group_by=author&limit=20" | jq

# Activity over time
curl "https://archive.example.com/api/v1/posts/aggregate?group_by=created_utc&frequency=month&limit=12" | jq
```

#### Batch Operations

```bash
# Batch fetch posts
curl -X POST "https://archive.example.com/api/v1/posts/batch" \
  -H "Content-Type: application/json" \
  -d '{"ids":["abc123","def456","ghi789"]}' | jq

# Batch fetch users
curl -X POST "https://archive.example.com/api/v1/users/batch" \
  -H "Content-Type: application/json" \
  -d '{"usernames":["user1","user2","user3"]}' | jq
```

#### Context & Summary

```bash
# Get post with top comments
curl "https://archive.example.com/api/v1/posts/abc123/context?top_comments=10&max_depth=2" | jq

# User summary
curl "https://archive.example.com/api/v1/users/username/summary" | jq

# Subreddit summary
curl "https://archive.example.com/api/v1/subreddits/privacy/summary" | jq
```

---

## MCP Server (AI Integration)

The REST API can be accessed through an MCP (Model Context Protocol) server for AI assistant integration:

### Features
- **29 MCP Tools**: Auto-generated from OpenAPI specification
- **5 MCP Resources**: Quick access to common data
- **2 MCP Prompts**: LLM guidance for token management
- **Token Overflow Prevention**: Built-in guidance for safe parameter selection

### Setup
```bash
cd mcp_server/
uv run python server.py --api-url http://localhost:5000
```

### Claude Desktop Configuration
```json
{
  "mcpServers": {
    "reddarchiver": {
      "command": "uv",
      "args": ["--directory", "/path/to/mcp_server", "run", "python", "server.py"],
      "env": { "REDDARCHIVER_API_URL": "http://localhost:5000" }
    }
  }
}
```

See [MCP Server Documentation](../mcp_server/README.md) for complete setup guide.

---

## Support

- **Documentation**: See README.md and other docs/
- **Issues**: Open an issue on GitHub
- **Security**: See SECURITY.md for reporting vulnerabilities
- **Registry**: See REGISTRY_SETUP.md for joining public registry

---

**API Version**: 1.0
**Documentation Last Updated**: 2025-12-30
**Validation**: 100% endpoint validation with comprehensive test coverage
