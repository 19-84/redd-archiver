#!/usr/bin/env python3
# ABOUTME: Comprehensive API validation script using Python requests
# ABOUTME: Tests all 30+ endpoints with extensive parameter combinations

import requests
import json
import sys
from typing import Dict, List, Tuple

BASE_URL = "http://localhost/api/v1"

class APITester:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        self.session = requests.Session()

    def test_endpoint(self, name: str, path: str, method: str = "GET",
                     data: Dict = None, expected_code: int = 200,
                     check_json: bool = True) -> bool:
        """Test a single endpoint"""
        url = f"{BASE_URL}{path}"
        print(f"  ├─ {name}...", end=" ", flush=True)

        try:
            if method == "POST":
                response = self.session.post(url, json=data, timeout=30)
            else:
                response = self.session.get(url, timeout=30)

            # Check status code
            if response.status_code != expected_code:
                print(f"✗ FAIL (HTTP {response.status_code}, expected {expected_code})")
                if response.text:
                    print(f"    Response: {response.text[:200]}")
                self.failed += 1
                return False

            # Check JSON structure (skip for CSV/NDJSON)
            if check_json and 'json' in response.headers.get('Content-Type', ''):
                try:
                    response.json()
                except json.JSONDecodeError:
                    print(f"⚠ WARN (Invalid JSON)")
                    self.warnings += 1
                    return False

            print("✓ PASS")
            self.passed += 1
            return True

        except requests.exceptions.Timeout:
            print(f"✗ FAIL (Timeout)")
            self.failed += 1
            return False
        except Exception as e:
            print(f"✗ FAIL ({type(e).__name__}: {str(e)[:100]})")
            self.failed += 1
            return False

    def test_response_structure(self, name: str, path: str, required_fields: List[str]) -> bool:
        """Test that response contains required fields"""
        url = f"{BASE_URL}{path}"
        print(f"  ├─ {name}...", end=" ", flush=True)

        try:
            response = self.session.get(url, timeout=30)
            if response.status_code != 200:
                print(f"✗ FAIL (HTTP {response.status_code})")
                self.failed += 1
                return False

            data = response.json()
            for field in required_fields:
                if field not in json.dumps(data):
                    print(f"✗ FAIL (Missing field: {field})")
                    self.failed += 1
                    return False

            print("✓ PASS")
            self.passed += 1
            return True
        except Exception as e:
            print(f"✗ FAIL ({str(e)[:100]})")
            self.failed += 1
            return False

    def section(self, title: str):
        """Print section header"""
        print(f"\n{'='*60}")
        print(f"{title}")
        print('='*60)

    def run_all_tests(self):
        """Run comprehensive test suite"""
        print("="*60)
        print("COMPREHENSIVE API VALIDATION TEST SUITE")
        print(f"Target: {BASE_URL}")
        print("="*60)

        # System Endpoints
        self.section("1. SYSTEM ENDPOINTS")
        self.test_endpoint("GET /health", "/health")
        self.test_response_structure("Health fields", "/health", ["status", "database", "timestamp"])
        self.test_endpoint("GET /stats", "/stats")
        self.test_endpoint("GET /schema", "/schema")
        self.test_endpoint("GET /openapi.json", "/openapi.json")

        # Posts - Basic
        self.section("2. POSTS ENDPOINTS - Basic")
        self.test_endpoint("GET /posts (basic)", "/posts?limit=10")
        self.test_endpoint("GET /posts (page 2)", "/posts?page=2&limit=10")
        self.test_endpoint("GET /posts (limit 100)", "/posts?limit=100")
        self.test_endpoint("GET /posts (sort by score)", "/posts?sort=score&limit=10")
        self.test_endpoint("GET /posts (sort by date)", "/posts?sort=created_utc&limit=10")
        self.test_endpoint("GET /posts (sort by comments)", "/posts?sort=num_comments&limit=10")

        # Posts - Filtering
        self.test_endpoint("Filter by subreddit", "/posts?subreddit=RedditCensors&limit=10")
        self.test_endpoint("Filter by author", "/posts?author=G_Petronius&limit=10")
        self.test_endpoint("Filter by min_score", "/posts?min_score=100&limit=10")
        self.test_endpoint("Combined filters", "/posts?subreddit=RedditCensors&min_score=50&limit=10")

        # Posts - Field Selection
        self.section("3. POSTS - Field Selection")
        self.test_endpoint("Fields: id,title", "/posts?fields=id,title&limit=10")
        self.test_endpoint("Fields: id,title,score", "/posts?fields=id,title,score&limit=10")
        self.test_endpoint("Invalid field", "/posts?fields=invalid_field&limit=10", expected_code=400)

        # Posts - Truncation
        self.section("4. POSTS - Truncation")
        self.test_endpoint("max_body_length=100", "/posts?max_body_length=100&limit=10")
        self.test_endpoint("max_body_length=500", "/posts?max_body_length=500&limit=10")
        self.test_endpoint("include_body=false", "/posts?include_body=false&limit=10")

        # Posts - Export
        self.section("5. POSTS - Export Formats")
        self.test_endpoint("CSV export", "/posts?format=csv&limit=10", check_json=False)
        self.test_endpoint("NDJSON export", "/posts?format=ndjson&limit=10", check_json=False)
        self.test_endpoint("Invalid format", "/posts?format=xml&limit=10", expected_code=400)

        # Posts - Single & Related
        self.section("6. POSTS - Single & Related")
        self.test_endpoint("GET /posts/{id}", "/posts/6a6igz")
        self.test_endpoint("GET /posts/{id}/comments", "/posts/6a6igz/comments?limit=10")
        self.test_endpoint("Invalid post ID", "/posts/zzzzzzz", expected_code=404)

        # Posts - Advanced
        self.section("7. POSTS - Advanced Features")
        self.test_endpoint("Context endpoint", "/posts/6a6igz/context?top_comments=5")
        self.test_endpoint("Context with params", "/posts/6a6igz/context?top_comments=3&max_depth=2&max_body_length=200")
        self.test_endpoint("Comment tree", "/posts/6a6igz/comments/tree?max_depth=2&limit=10")
        self.test_endpoint("Related posts", "/posts/6a6igz/related?limit=5")
        self.test_endpoint("Random posts", "/posts/random?n=10&subreddit=RedditCensors")
        self.test_endpoint("Random with seed", "/posts/random?n=10&seed=42")

        # Posts - Aggregation & Batch
        self.section("8. POSTS - Aggregation & Batch")
        self.test_endpoint("Aggregate by author", "/posts/aggregate?group_by=author&limit=10")
        self.test_endpoint("Aggregate by subreddit", "/posts/aggregate?group_by=subreddit&limit=10")
        self.test_endpoint("Aggregate by time", "/posts/aggregate?group_by=created_utc&frequency=month&limit=12")
        self.test_endpoint("Batch lookup", "/posts/batch", "POST", {"ids": ["6a6igz", "6c7t1b"]})
        self.test_endpoint("Batch with fields", "/posts/batch", "POST", {"ids": ["6a6igz"], "fields": ["id", "title"]})

        # Comments
        self.section("9. COMMENTS ENDPOINTS")
        self.test_endpoint("GET /comments", "/comments?limit=10")
        self.test_endpoint("Comments by subreddit", "/comments?subreddit=RedditCensors&limit=10")
        self.test_endpoint("Comments with truncation", "/comments?max_body_length=100&limit=10")
        self.test_endpoint("Comments CSV export", "/comments?format=csv&limit=10", check_json=False)
        self.test_endpoint("Random comments", "/comments/random?n=10")
        self.test_endpoint("Comments aggregate", "/comments/aggregate?group_by=author&limit=10")
        self.test_endpoint("Comments batch", "/comments/batch", "POST", {"ids": ["e4kq3zj", "h2tiwkj"]})

        # Users
        self.section("10. USERS ENDPOINTS")
        self.test_endpoint("GET /users", "/users?limit=10")
        self.test_endpoint("Users sort by karma", "/users?sort=karma&limit=10")
        self.test_endpoint("Users sort by activity", "/users?sort=activity&limit=10")
        self.test_endpoint("Users with fields", "/users?fields=username,total_karma&limit=10")
        self.test_endpoint("Users CSV export", "/users?format=csv&limit=10", check_json=False)
        self.test_endpoint("GET /users/{username}", "/users/G_Petronius")
        self.test_endpoint("User summary", "/users/G_Petronius/summary")
        self.test_endpoint("User posts", "/users/G_Petronius/posts?limit=10")
        self.test_endpoint("User comments", "/users/G_Petronius/comments?limit=10")
        self.test_endpoint("Users aggregate", "/users/aggregate?limit=10")
        self.test_endpoint("Users batch", "/users/batch", "POST", {"usernames": ["G_Petronius", "NorseGodLoki0411"]})

        # Subreddits
        self.section("11. SUBREDDITS ENDPOINTS")
        self.test_endpoint("GET /subreddits", "/subreddits")
        self.test_endpoint("Subreddits CSV export", "/subreddits?format=csv", check_json=False)
        self.test_endpoint("GET /subreddits/{name}", "/subreddits/RedditCensors")
        self.test_endpoint("Subreddit summary", "/subreddits/RedditCensors/summary")

        # Search
        self.section("12. SEARCH ENDPOINTS")
        self.test_endpoint("Basic search", "/search?q=censorship&limit=10")
        self.test_endpoint("Search posts only", "/search?q=banned&type=posts&limit=10")
        self.test_endpoint("Search comments only", "/search?q=moderator&type=comments&limit=10")
        self.test_endpoint("Search with filters", "/search?q=reddit&subreddit=RedditCensors&limit=10")
        self.test_endpoint("Search sort by score", "/search?q=post&sort=score&limit=10")
        self.test_endpoint("Search explain", "/search/explain?q=censorship")
        self.test_endpoint("Empty search query", "/search?q=&limit=10", expected_code=400)

        # Error Cases
        self.section("13. ERROR HANDLING")
        self.test_endpoint("Limit too low", "/posts?limit=5", expected_code=400)
        self.test_endpoint("Limit too high", "/posts?limit=200", expected_code=400)
        self.test_endpoint("Negative page", "/posts?page=-1&limit=10", expected_code=400)
        self.test_endpoint("Invalid sort", "/posts?sort=invalid&limit=10", expected_code=400)
        self.test_endpoint("Nonexistent post", "/posts/zzzzzzz", expected_code=404)
        self.test_endpoint("Nonexistent user", "/users/nonexistentuser123", expected_code=404)
        self.test_endpoint("Nonexistent subreddit", "/subreddits/nonexistent123", expected_code=404)

        # Summary
        self.section("TEST RESULTS SUMMARY")
        total = self.passed + self.failed + self.warnings
        print(f"\nPassed:   {self.passed}")
        print(f"Failed:   {self.failed}")
        print(f"Warnings: {self.warnings}")
        print(f"Total:    {total}")
        print("="*60)

        if self.failed == 0:
            print("\n✓✓✓ ALL TESTS PASSED! ✓✓✓\n")
            return 0
        else:
            print(f"\n✗✗✗ {self.failed} TESTS FAILED ✗✗✗\n")
            return 1

if __name__ == "__main__":
    tester = APITester()
    sys.exit(tester.run_all_tests())
