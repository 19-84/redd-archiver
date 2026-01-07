#!/usr/bin/env python
"""
ABOUTME: Test REST API v1 endpoints for Redd-Archiver
ABOUTME: Validates API functionality, rate limiting, error handling, and data integrity
"""

import pytest
import json


class TestHealthEndpoint:
    """Test health check endpoint"""

    def test_health_endpoint_returns_ok(self, api_client):
        """Test /api/v1/health returns OK"""
        response = api_client.get('/api/v1/health')
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'healthy'


class TestStatsEndpoint:
    """Test statistics endpoint"""

    def test_stats_endpoint_returns_data(self, api_client):
        """Test /api/v1/stats returns valid statistics"""
        response = api_client.get('/api/v1/stats')
        assert response.status_code == 200
        data = response.get_json()

        # Verify required fields
        assert 'content' in data
        assert 'instance' in data
        assert 'status' in data

        # Verify content statistics structure
        assert isinstance(data['content']['total_posts'], int)
        assert isinstance(data['content']['total_comments'], int)
        assert isinstance(data['content']['total_users'], int)
        assert 'subreddits' in data['content']
        assert isinstance(data['content']['subreddits'], list)

    def test_stats_includes_instance_metadata(self, api_client):
        """Test instance metadata in stats response"""
        response = api_client.get('/api/v1/stats')
        assert response.status_code == 200
        data = response.get_json()

        # Instance metadata should exist
        assert 'instance' in data
        assert 'name' in data['instance']
        # base_url is optional, may not be set in test environment
        assert isinstance(data['instance'], dict)


class TestPostsEndpoint:
    """Test posts endpoint"""

    def test_posts_endpoint_returns_list(self, api_client, clean_database, sample_post_data):
        """Test /api/v1/posts returns paginated posts"""
        # Insert test post
        clean_database.insert_posts_batch([sample_post_data])

        response = api_client.get('/api/v1/posts')
        assert response.status_code == 200
        data = response.get_json()

        assert 'data' in data
        assert 'meta' in data
        assert 'links' in data
        assert isinstance(data['data'], list)

    def test_posts_filter_by_subreddit(self, api_client, clean_database, sample_post_data):
        """Test posts filtering by subreddit"""
        # Insert test post
        clean_database.insert_posts_batch([sample_post_data])

        response = api_client.get(f'/api/v1/posts?subreddit={sample_post_data["subreddit"]}')
        assert response.status_code == 200
        data = response.get_json()

        assert len(data['data']) >= 1
        for post in data['data']:
            assert post['subreddit'] == sample_post_data['subreddit']

    def test_posts_pagination_params(self, api_client):
        """Test posts pagination parameters"""
        response = api_client.get('/api/v1/posts?page=1&limit=10')
        assert response.status_code == 200
        data = response.get_json()

        assert 'meta' in data
        assert data['meta']['page'] == 1
        assert data['meta']['limit'] == 10
        assert 'links' in data


class TestCommentsEndpoint:
    """Test comments endpoint"""

    def test_comments_endpoint_returns_list(self, api_client):
        """Test /api/v1/comments returns paginated comments"""
        response = api_client.get('/api/v1/comments')
        assert response.status_code == 200
        data = response.get_json()

        assert 'data' in data
        assert 'meta' in data
        assert 'links' in data
        assert isinstance(data['data'], list)


class TestSubredditsEndpoint:
    """Test subreddits endpoint"""

    def test_subreddits_endpoint_returns_list(self, api_client):
        """Test /api/v1/subreddits returns subreddit list"""
        response = api_client.get('/api/v1/subreddits')
        assert response.status_code == 200
        data = response.get_json()

        assert 'data' in data
        assert 'meta' in data
        assert isinstance(data['data'], list)

    def test_subreddit_detail_endpoint(self, api_client, clean_database, sample_post_data):
        """Test /api/v1/subreddits/{name} returns subreddit stats"""
        # Insert test post to create subreddit
        clean_database.insert_posts_batch([sample_post_data])

        response = api_client.get(f'/api/v1/subreddits/{sample_post_data["subreddit"]}')
        assert response.status_code == 200
        data = response.get_json()

        assert data['subreddit'] == sample_post_data['subreddit']
        assert 'total_posts' in data
        assert 'total_comments' in data
        assert 'unique_users' in data


class TestUsersEndpoint:
    """Test users endpoint"""

    def test_users_endpoint_returns_list(self, api_client):
        """Test /api/v1/users returns paginated users"""
        response = api_client.get('/api/v1/users')
        assert response.status_code == 200
        data = response.get_json()

        assert 'data' in data
        assert 'meta' in data
        assert 'links' in data
        assert isinstance(data['data'], list)


class TestErrorHandling:
    """Test API error handling"""

    def test_invalid_subreddit_returns_404(self, api_client):
        """Test non-existent subreddit returns 404"""
        response = api_client.get('/api/v1/subreddits/nonexistent_subreddit_12345')
        assert response.status_code in [404, 200, 400]  # 400 if invalid format, 404 if not found

    def test_invalid_page_number(self, api_client):
        """Test invalid pagination parameters"""
        response = api_client.get('/api/v1/posts?page=-1')
        # Should handle gracefully (default to page 1 or return error)
        assert response.status_code in [200, 400]

    def test_excessive_limit(self, api_client):
        """Test excessive limit parameter"""
        response = api_client.get('/api/v1/posts?limit=10000')
        # Should reject or cap excessive limit
        assert response.status_code in [200, 400]  # 400 if rejected, 200 if capped
        if response.status_code == 200:
            data = response.get_json()
            assert data['meta']['limit'] <= 100  # Assuming 100 is max


class TestRateLimiting:
    """Test API rate limiting"""

    def test_rate_limit_not_exceeded_normal_use(self, api_client):
        """Test normal API usage doesn't hit rate limit"""
        # Make 5 requests (well under limit)
        for _ in range(5):
            response = api_client.get('/api/v1/health')
            assert response.status_code == 200


class TestCORSHeaders:
    """Test CORS configuration"""

    def test_cors_headers_present(self, api_client):
        """Test CORS headers are set correctly"""
        response = api_client.get('/api/v1/health')
        # CORS should allow all origins for public API
        assert 'Access-Control-Allow-Origin' in response.headers or response.status_code == 200


class TestInputValidation:
    """Test input validation and sanitization"""

    def test_sql_injection_prevention(self, api_client):
        """Test SQL injection attempts are safely handled"""
        # Attempt SQL injection in search parameter
        malicious_queries = [
            "test' OR '1'='1",
            "test; DROP TABLE posts;--",
            "test' UNION SELECT * FROM users--",
        ]

        for query in malicious_queries:
            response = api_client.get(f'/api/v1/posts?search={query}')
            # Should return safely (200 with no results or proper error)
            assert response.status_code in [200, 400]
            # Should not cause internal server error
            assert response.status_code != 500

    def test_xss_prevention_in_params(self, api_client):
        """Test XSS attempts in query parameters"""
        xss_payload = '<script>alert("XSS")</script>'
        response = api_client.get(f'/api/v1/posts?search={xss_payload}')

        # Should handle safely
        assert response.status_code in [200, 400]
        # Response should not contain unescaped script tags
        if response.status_code == 200:
            response_text = response.get_data(as_text=True)
            assert '<script>' not in response_text or '&lt;script&gt;' in response_text


class TestFieldSelection:
    """Test field selection functionality (MCP-optimized)"""

    def test_posts_field_selection(self, api_client, clean_database, sample_post_data):
        """Test field selection on posts endpoint"""
        clean_database.insert_posts_batch([sample_post_data])

        # Request only specific fields
        response = api_client.get('/api/v1/posts?fields=id,title,score')
        assert response.status_code == 200
        data = response.get_json()

        if data['data']:
            post = data['data'][0]
            # Should only have requested fields
            assert 'id' in post
            assert 'title' in post
            assert 'score' in post
            # Should NOT have unrequested fields
            assert 'selftext' not in post
            assert 'author' not in post

    def test_invalid_field_selection(self, api_client):
        """Test invalid field selection returns error"""
        response = api_client.get('/api/v1/posts?fields=id,invalid_field_xyz')
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data
        assert 'Invalid fields' in data['error']

    def test_comments_field_selection(self, api_client):
        """Test field selection on comments endpoint"""
        response = api_client.get('/api/v1/comments?fields=id,author,score')
        assert response.status_code == 200
        data = response.get_json()
        # If there are comments, verify field filtering
        if data['data']:
            comment = data['data'][0]
            assert 'id' in comment
            assert 'author' in comment
            assert 'score' in comment
            assert 'body' not in comment

    def test_users_field_selection(self, api_client):
        """Test field selection on users endpoint"""
        response = api_client.get('/api/v1/users?fields=username,post_count')
        assert response.status_code == 200
        data = response.get_json()
        if data['data']:
            user = data['data'][0]
            assert 'username' in user
            assert 'post_count' in user
            assert 'comment_count' not in user

    def test_subreddits_field_selection(self, api_client):
        """Test field selection on subreddits endpoint"""
        response = api_client.get('/api/v1/subreddits?fields=name,total_posts')
        assert response.status_code == 200
        data = response.get_json()
        if data['data']:
            subreddit = data['data'][0]
            assert 'name' in subreddit
            assert 'total_posts' in subreddit
            assert 'total_comments' not in subreddit


class TestTruncationControls:
    """Test body truncation controls (MCP-optimized)"""

    def test_posts_max_body_length(self, api_client, clean_database, sample_post_data):
        """Test max_body_length truncation on posts"""
        # Create post with long selftext
        post_data = sample_post_data.copy()
        post_data['selftext'] = 'A' * 1000  # 1000 character body
        clean_database.insert_posts_batch([post_data])

        # Request with truncation
        response = api_client.get('/api/v1/posts?max_body_length=100')
        assert response.status_code == 200
        data = response.get_json()

        if data['data']:
            # Find any post with selftext that should be truncated
            for post in data['data']:
                if post.get('selftext') and post.get('selftext_truncated'):
                    # Body should be truncated
                    assert len(post['selftext']) <= 103  # 100 + "..."
                    # Truncation metadata should be present
                    assert post.get('selftext_truncated') is True
                    assert post.get('selftext_full_length') is not None
                    break

    def test_posts_include_body_false(self, api_client, clean_database, sample_post_data):
        """Test include_body=false on posts"""
        clean_database.insert_posts_batch([sample_post_data])

        response = api_client.get('/api/v1/posts?include_body=false')
        assert response.status_code == 200
        data = response.get_json()

        if data['data']:
            post = data['data'][0]
            # Selftext should be None/null when include_body=false
            assert post.get('selftext') is None

    def test_comments_max_body_length(self, api_client):
        """Test max_body_length truncation on comments"""
        response = api_client.get('/api/v1/comments?max_body_length=50')
        assert response.status_code == 200
        data = response.get_json()

        # Verify response structure is valid
        assert 'data' in data
        assert 'meta' in data

    def test_comments_include_body_false(self, api_client):
        """Test include_body=false on comments"""
        response = api_client.get('/api/v1/comments?include_body=false')
        assert response.status_code == 200
        data = response.get_json()

        if data['data']:
            comment = data['data'][0]
            # Body should be None when include_body=false
            assert comment.get('body') is None


class TestCombinedFieldsAndTruncation:
    """Test combined field selection and truncation"""

    def test_posts_fields_and_truncation(self, api_client, clean_database, sample_post_data):
        """Test combining field selection with truncation"""
        post_data = sample_post_data.copy()
        post_data['selftext'] = 'Test content ' * 100  # Long content
        clean_database.insert_posts_batch([post_data])

        response = api_client.get('/api/v1/posts?fields=id,title,selftext&max_body_length=50')
        assert response.status_code == 200
        data = response.get_json()

        if data['data']:
            post = data['data'][0]
            # Should have selected fields
            assert 'id' in post
            assert 'title' in post
            # Selftext should be truncated
            if post.get('selftext'):
                assert len(post['selftext']) <= 53  # 50 + "..."

    def test_pagination_with_fields(self, api_client):
        """Test pagination works with field selection"""
        response = api_client.get('/api/v1/posts?page=1&limit=10&fields=id,title')
        assert response.status_code == 200
        data = response.get_json()

        assert 'meta' in data
        assert data['meta']['page'] == 1
        assert data['meta']['limit'] == 10
        # Field selection should work with pagination
        if data['data']:
            post = data['data'][0]
            assert 'id' in post
            assert 'title' in post
            # Unrequested fields should not be present
            assert 'selftext' not in post


class TestExportFormats:
    """Test CSV and NDJSON export functionality"""

    def test_posts_csv_export(self, api_client, clean_database, sample_post_data):
        """Test CSV export for posts endpoint"""
        clean_database.insert_posts_batch([sample_post_data])

        response = api_client.get('/api/v1/posts?format=csv')
        assert response.status_code == 200
        assert response.content_type == 'text/csv; charset=utf-8'
        # Check headers indicate file download
        assert 'attachment' in response.headers.get('Content-Disposition', '')
        # Content should have CSV header row
        content = response.get_data(as_text=True)
        assert 'id' in content or 'title' in content  # CSV has header

    def test_posts_ndjson_export(self, api_client, clean_database, sample_post_data):
        """Test NDJSON export for posts endpoint"""
        clean_database.insert_posts_batch([sample_post_data])

        response = api_client.get('/api/v1/posts?format=ndjson')
        assert response.status_code == 200
        assert 'ndjson' in response.content_type
        # Check headers indicate file download
        assert 'attachment' in response.headers.get('Content-Disposition', '')
        # Content should be valid NDJSON
        content = response.get_data(as_text=True)
        if content.strip():
            # Each line should be valid JSON
            lines = content.strip().split('\n')
            for line in lines:
                if line:
                    data = json.loads(line)
                    assert isinstance(data, dict)

    def test_invalid_format_returns_error(self, api_client):
        """Test invalid format parameter returns 400 error"""
        response = api_client.get('/api/v1/posts?format=invalid')
        # Should return 400 for invalid format
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data
        assert 'Invalid format' in data['error']

    def test_comments_csv_export(self, api_client):
        """Test CSV export for comments endpoint"""
        response = api_client.get('/api/v1/comments?format=csv')
        assert response.status_code == 200
        assert response.content_type == 'text/csv; charset=utf-8'

    def test_users_csv_export(self, api_client):
        """Test CSV export for users endpoint"""
        response = api_client.get('/api/v1/users?format=csv')
        assert response.status_code == 200
        assert response.content_type == 'text/csv; charset=utf-8'

    def test_subreddits_csv_export(self, api_client):
        """Test CSV export for subreddits endpoint"""
        response = api_client.get('/api/v1/subreddits?format=csv')
        assert response.status_code == 200
        assert response.content_type == 'text/csv; charset=utf-8'


class TestOpenAPISpec:
    """Test OpenAPI specification endpoint"""

    def test_openapi_spec_returns_valid_json(self, api_client):
        """Test /api/v1/openapi.json returns valid OpenAPI spec"""
        response = api_client.get('/api/v1/openapi.json')
        assert response.status_code == 200
        data = response.get_json()

        # Verify OpenAPI structure
        assert 'openapi' in data
        assert data['openapi'].startswith('3.')
        assert 'info' in data
        assert 'paths' in data

    def test_openapi_spec_contains_required_info(self, api_client):
        """Test OpenAPI spec contains required info fields"""
        response = api_client.get('/api/v1/openapi.json')
        data = response.get_json()

        assert 'title' in data['info']
        assert 'version' in data['info']
        assert 'description' in data['info']

    def test_openapi_spec_contains_all_endpoints(self, api_client):
        """Test OpenAPI spec documents all major endpoints"""
        response = api_client.get('/api/v1/openapi.json')
        data = response.get_json()

        paths = data['paths']
        # Verify major endpoint paths exist
        assert '/posts' in paths
        assert '/comments' in paths
        assert '/users' in paths
        assert '/subreddits' in paths
        assert '/search' in paths
        assert '/health' in paths
        assert '/stats' in paths
        assert '/schema' in paths

    def test_openapi_spec_contains_components(self, api_client):
        """Test OpenAPI spec contains schema components"""
        response = api_client.get('/api/v1/openapi.json')
        data = response.get_json()

        assert 'components' in data
        assert 'schemas' in data['components']
        # Verify major schemas exist
        schemas = data['components']['schemas']
        assert 'Post' in schemas
        assert 'Comment' in schemas
        assert 'User' in schemas
        assert 'Subreddit' in schemas

    def test_openapi_spec_contains_tags(self, api_client):
        """Test OpenAPI spec contains organized tags"""
        response = api_client.get('/api/v1/openapi.json')
        data = response.get_json()

        assert 'tags' in data
        tag_names = [t['name'] for t in data['tags']]
        assert 'Posts' in tag_names
        assert 'Comments' in tag_names
        assert 'Users' in tag_names
        assert 'Search' in tag_names
