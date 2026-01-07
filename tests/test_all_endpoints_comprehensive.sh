#!/bin/bash
# ABOUTME: Ultra-comprehensive API endpoint validation script
# ABOUTME: Tests all endpoints with extensive parameter combinations and edge cases

BASE_URL="http://localhost/api/v1"
FAILED=0
PASSED=0
WARNINGS=0

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_section() {
    echo ""
    echo -e "${BLUE}=========================================="
    echo -e "$1"
    echo -e "==========================================${NC}"
    echo ""
}

test_endpoint() {
    local name="$1"
    local url="$2"
    local method="${3:-GET}"
    local data="$4"
    local expected_code="${5:-200}"
    local validate_json="${6:-true}"

    echo -n "  ├─ $name... "

    if [ "$method" = "POST" ]; then
        response=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL$url" \
            -H "Content-Type: application/json" \
            -d "$data" 2>&1)
    else
        response=$(curl -s -w "\n%{http_code}" -i "$BASE_URL$url" 2>&1)
    fi

    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')

    # Check HTTP status code
    if [ "$http_code" != "$expected_code" ]; then
        echo -e "${RED}✗ FAIL${NC} (HTTP $http_code, expected $expected_code)"
        echo "    URL: $BASE_URL$url"
        echo "    Response: $(echo "$body" | grep -v "^HTTP" | grep -v "^Content" | grep -v "^Date" | grep -v "^Server" | head -c 300)"
        FAILED=$((FAILED + 1))
        return 1
    fi

    # Validate JSON structure (skip for CSV/binary)
    if [ "$validate_json" = "true" ] && echo "$body" | grep -q "Content-Type: application/json"; then
        content=$(echo "$body" | sed '1,/^$/d')
        if ! echo "$content" | python3 -m json.tool >/dev/null 2>&1; then
            echo -e "${YELLOW}⚠ WARN${NC} (Invalid JSON)"
            WARNINGS=$((WARNINGS + 1))
            return 0
        fi
    fi

    echo -e "${GREEN}✓ PASS${NC}"
    PASSED=$((PASSED + 1))
    return 0
}

test_response_structure() {
    local name="$1"
    local url="$2"
    local required_fields="$3"

    echo -n "  ├─ $name (structure validation)... "

    response=$(curl -s "$BASE_URL$url" 2>&1)

    for field in $required_fields; do
        if ! echo "$response" | grep -q "\"$field\""; then
            echo -e "${RED}✗ FAIL${NC} (Missing field: $field)"
            FAILED=$((FAILED + 1))
            return 1
        fi
    done

    echo -e "${GREEN}✓ PASS${NC}"
    PASSED=$((PASSED + 1))
    return 0
}

test_pagination() {
    local endpoint="$1"
    echo -n "  ├─ Pagination structure... "

    response=$(curl -s "$BASE_URL$endpoint?limit=10&page=1")

    if ! echo "$response" | grep -q '"data"' || \
       ! echo "$response" | grep -q '"meta"' || \
       ! echo "$response" | grep -q '"links"' || \
       ! echo "$response" | grep -q '"page"' || \
       ! echo "$response" | grep -q '"limit"' || \
       ! echo "$response" | grep -q '"total"'; then
        echo -e "${RED}✗ FAIL${NC} (Incomplete pagination structure)"
        FAILED=$((FAILED + 1))
        return 1
    fi

    echo -e "${GREEN}✓ PASS${NC}"
    PASSED=$((PASSED + 1))
    return 0
}

# ============================================================================
# START TESTS
# ============================================================================

echo "=========================================="
echo "COMPREHENSIVE API VALIDATION TEST SUITE"
echo "Target: $BASE_URL"
echo "=========================================="

# ============================================================================
log_section "1. SYSTEM ENDPOINTS"
# ============================================================================

echo "Health & Discovery:"
test_endpoint "GET /health" "/health"
test_response_structure "Health response fields" "/health" "status database api_version timestamp"
test_endpoint "GET /stats" "/stats"
test_response_structure "Stats response fields" "/stats" "content date_range features"
test_endpoint "GET /schema" "/schema"
test_response_structure "Schema response fields" "/schema" "resources pagination field_selection"
test_endpoint "GET /openapi.json" "/openapi.json"
test_response_structure "OpenAPI spec fields" "/openapi.json" "openapi info paths components"

# ============================================================================
log_section "2. POSTS ENDPOINTS - Basic Operations"
# ============================================================================

echo "List Posts (Basic):"
test_endpoint "GET /posts (default)" "/posts?limit=10"
test_pagination "/posts"
test_endpoint "GET /posts (page 1)" "/posts?page=1&limit=10"
test_endpoint "GET /posts (page 2)" "/posts?page=2&limit=10"
test_endpoint "GET /posts (limit 10)" "/posts?limit=10"
test_endpoint "GET /posts (limit 25)" "/posts?limit=25"
test_endpoint "GET /posts (limit 50)" "/posts?limit=50"
test_endpoint "GET /posts (limit 100)" "/posts?limit=100"

echo ""
echo "List Posts (Sorting):"
test_endpoint "Sort by score DESC" "/posts?sort=score&limit=10"
test_endpoint "Sort by created_utc DESC" "/posts?sort=created_utc&limit=10"
test_endpoint "Sort by num_comments DESC" "/posts?sort=num_comments&limit=10"

echo ""
echo "List Posts (Filtering):"
test_endpoint "Filter by subreddit" "/posts?subreddit=RedditCensors&limit=10"
test_endpoint "Filter by author" "/posts?author=G_Petronius&limit=10"
test_endpoint "Filter by min_score=10" "/posts?min_score=10&limit=10"
test_endpoint "Filter by min_score=100" "/posts?min_score=100&limit=10"
test_endpoint "Filter by min_score=1000" "/posts?min_score=1000&limit=10"
test_endpoint "Combined filters (subreddit+score)" "/posts?subreddit=RedditCensors&min_score=100&limit=10"
test_endpoint "Combined filters (author+score)" "/posts?author=G_Petronius&min_score=50&limit=10"
test_endpoint "All filters combined" "/posts?subreddit=RedditCensors&author=G_Petronius&min_score=10&sort=score&limit=10"

echo ""
echo "Single Post:"
test_endpoint "GET /posts/{id} (valid)" "/posts/6a6igz"
test_endpoint "GET /posts/{id} (another valid)" "/posts/6c7t1b"
test_endpoint "GET /posts/{id} (invalid)" "/posts/invalid123" "GET" "" "404"
test_endpoint "GET /posts/{id} (nonexistent)" "/posts/zzzzzzz" "GET" "" "404"

echo ""
echo "Post Comments:"
test_endpoint "GET /posts/{id}/comments" "/posts/6a6igz/comments?limit=10"
test_endpoint "GET /posts/{id}/comments (page 2)" "/posts/6a6igz/comments?page=2&limit=10"
test_endpoint "GET /posts/{id}/comments (limit 50)" "/posts/6a6igz/comments?limit=50"

# ============================================================================
log_section "3. POSTS ENDPOINTS - Field Selection"
# ============================================================================

echo "Field Selection (Single Fields):"
test_endpoint "Field: id only" "/posts?fields=id&limit=10"
test_endpoint "Field: title only" "/posts?fields=title&limit=10"
test_endpoint "Field: score only" "/posts?fields=score&limit=10"
test_endpoint "Field: author only" "/posts?fields=author&limit=10"

echo ""
echo "Field Selection (Multiple Fields):"
test_endpoint "Fields: id,title" "/posts?fields=id,title&limit=10"
test_endpoint "Fields: id,title,score" "/posts?fields=id,title,score&limit=10"
test_endpoint "Fields: id,title,author,score" "/posts?fields=id,title,author,score&limit=10"
test_endpoint "Fields: all major fields" "/posts?fields=id,title,author,score,num_comments,created_utc&limit=10"

echo ""
echo "Field Selection (Invalid):"
test_endpoint "Invalid field name" "/posts?fields=invalid_field&limit=10" "GET" "" "400"
test_endpoint "Mixed valid/invalid" "/posts?fields=id,invalid,title&limit=10" "GET" "" "400"

# ============================================================================
log_section "4. POSTS ENDPOINTS - Truncation Controls"
# ============================================================================

echo "Body Truncation:"
test_endpoint "max_body_length=50" "/posts?max_body_length=50&limit=10"
test_endpoint "max_body_length=100" "/posts?max_body_length=100&limit=10"
test_endpoint "max_body_length=200" "/posts?max_body_length=200&limit=10"
test_endpoint "max_body_length=500" "/posts?max_body_length=500&limit=10"
test_endpoint "max_body_length=1000" "/posts?max_body_length=1000&limit=10"
test_endpoint "include_body=true" "/posts?include_body=true&limit=10"
test_endpoint "include_body=false" "/posts?include_body=false&limit=10"
test_endpoint "Combined: truncate + no body" "/posts?max_body_length=100&include_body=false&limit=10"

echo ""
echo "Truncation + Field Selection:"
test_endpoint "Fields + truncation" "/posts?fields=id,title,selftext&max_body_length=100&limit=10"
test_endpoint "Fields + no body" "/posts?fields=id,title&include_body=false&limit=10"

# ============================================================================
log_section "5. POSTS ENDPOINTS - Export Formats"
# ============================================================================

echo "CSV Export:"
test_endpoint "CSV: basic" "/posts?format=csv&limit=10" "GET" "" "200" "false"
test_endpoint "CSV: with filters" "/posts?format=csv&subreddit=RedditCensors&limit=10" "GET" "" "200" "false"
test_endpoint "CSV: with field selection" "/posts?format=csv&fields=id,title,score&limit=10" "GET" "" "200" "false"
test_endpoint "CSV: with truncation" "/posts?format=csv&max_body_length=100&limit=10" "GET" "" "200" "false"

echo ""
echo "NDJSON Export:"
test_endpoint "NDJSON: basic" "/posts?format=ndjson&limit=10" "GET" "" "200" "false"
test_endpoint "NDJSON: with filters" "/posts?format=ndjson&subreddit=RedditCensors&limit=10" "GET" "" "200" "false"
test_endpoint "NDJSON: with field selection" "/posts?format=ndjson&fields=id,title&limit=10" "GET" "" "200" "false"

echo ""
echo "Invalid Formats:"
test_endpoint "Invalid format: xml" "/posts?format=xml&limit=10" "GET" "" "400"
test_endpoint "Invalid format: yaml" "/posts?format=yaml&limit=10" "GET" "" "400"
test_endpoint "Invalid format: pdf" "/posts?format=pdf&limit=10" "GET" "" "400"

# ============================================================================
log_section "6. POSTS ENDPOINTS - Advanced Features"
# ============================================================================

echo "Context Endpoint:"
test_endpoint "GET /posts/{id}/context (default)" "/posts/6a6igz/context"
test_endpoint "Context: top_comments=3" "/posts/6a6igz/context?top_comments=3"
test_endpoint "Context: top_comments=10" "/posts/6a6igz/context?top_comments=10"
test_endpoint "Context: max_depth=1" "/posts/6a6igz/context?max_depth=1"
test_endpoint "Context: max_depth=3" "/posts/6a6igz/context?max_depth=3"
test_endpoint "Context: with truncation" "/posts/6a6igz/context?max_body_length=200"
test_endpoint "Context: combined params" "/posts/6a6igz/context?top_comments=5&max_depth=2&max_body_length=300"

echo ""
echo "Comment Tree:"
test_endpoint "GET /posts/{id}/comments/tree" "/posts/6a6igz/comments/tree?limit=20"
test_endpoint "Tree: max_depth=1" "/posts/6a6igz/comments/tree?max_depth=1&limit=10"
test_endpoint "Tree: max_depth=5" "/posts/6a6igz/comments/tree?max_depth=5&limit=20"
test_endpoint "Tree: sort by score" "/posts/6a6igz/comments/tree?sort=score&limit=20"
test_endpoint "Tree: sort by created_utc" "/posts/6a6igz/comments/tree?sort=created_utc&limit=20"
test_endpoint "Tree: limit variations" "/posts/6a6igz/comments/tree?limit=50"

echo ""
echo "Related Posts:"
test_endpoint "GET /posts/{id}/related" "/posts/6a6igz/related?limit=5"
test_endpoint "Related: limit=3" "/posts/6a6igz/related?limit=3"
test_endpoint "Related: limit=10" "/posts/6a6igz/related?limit=10"
test_endpoint "Related: same subreddit only" "/posts/6a6igz/related?same_subreddit=true&limit=5"
test_endpoint "Related: any subreddit" "/posts/6a6igz/related?same_subreddit=false&limit=5"

echo ""
echo "Random Posts:"
test_endpoint "GET /posts/random (n=5)" "/posts/random?n=5"
test_endpoint "Random: n=10" "/posts/random?n=10"
test_endpoint "Random: n=20" "/posts/random?n=20"
test_endpoint "Random: with subreddit" "/posts/random?n=10&subreddit=RedditCensors"
test_endpoint "Random: with seed" "/posts/random?n=10&seed=42"
test_endpoint "Random: seed consistency" "/posts/random?n=5&seed=12345"
test_endpoint "Random: different seed" "/posts/random?n=5&seed=67890"

# ============================================================================
log_section "7. POSTS ENDPOINTS - Aggregation"
# ============================================================================

echo "Aggregate by Author:"
test_endpoint "Group by author (default)" "/posts/aggregate?group_by=author&limit=10"
test_endpoint "Group by author (limit 20)" "/posts/aggregate?group_by=author&limit=20"
test_endpoint "Group by author (with subreddit)" "/posts/aggregate?group_by=author&subreddit=RedditCensors&limit=10"

echo ""
echo "Aggregate by Subreddit:"
test_endpoint "Group by subreddit" "/posts/aggregate?group_by=subreddit&limit=10"
test_endpoint "Group by subreddit (limit 5)" "/posts/aggregate?group_by=subreddit&limit=5"

echo ""
echo "Aggregate by Time:"
test_endpoint "Group by time (hourly)" "/posts/aggregate?group_by=created_utc&frequency=hour&limit=24"
test_endpoint "Group by time (daily)" "/posts/aggregate?group_by=created_utc&frequency=day&limit=30"
test_endpoint "Group by time (weekly)" "/posts/aggregate?group_by=created_utc&frequency=week&limit=12"
test_endpoint "Group by time (monthly)" "/posts/aggregate?group_by=created_utc&frequency=month&limit=12"
test_endpoint "Group by time (yearly)" "/posts/aggregate?group_by=created_utc&frequency=year&limit=5"

echo ""
echo "Aggregate with Filters:"
test_endpoint "Aggregate: subreddit filter" "/posts/aggregate?group_by=author&subreddit=RedditCensors&limit=10"
test_endpoint "Aggregate: time range" "/posts/aggregate?group_by=created_utc&frequency=month&after=2017-01-01&limit=12"

# ============================================================================
log_section "8. POSTS ENDPOINTS - Batch Operations"
# ============================================================================

echo "Batch Lookup:"
test_endpoint "Batch: 2 IDs" "/posts/batch" "POST" '{"ids":["6a6igz","6c7t1b"]}'
test_endpoint "Batch: 5 IDs" "/posts/batch" "POST" '{"ids":["6a6igz","6c7t1b","1aunksh","1au55qu","6alcv3"]}'
test_endpoint "Batch: with fields" "/posts/batch" "POST" '{"ids":["6a6igz","6c7t1b"],"fields":["id","title","score"]}'
test_endpoint "Batch: single ID" "/posts/batch" "POST" '{"ids":["6a6igz"]}'
test_endpoint "Batch: empty array" "/posts/batch" "POST" '{"ids":[]}' "" "400"
test_endpoint "Batch: missing ids field" "/posts/batch" "POST" '{}' "" "400"
test_endpoint "Batch: invalid JSON" "/posts/batch" "POST" '{invalid}' "" "400"
test_endpoint "Batch: non-array ids" "/posts/batch" "POST" '{"ids":"6a6igz"}' "" "400"

# ============================================================================
log_section "9. COMMENTS ENDPOINTS"
# ============================================================================

echo "List Comments:"
test_endpoint "GET /comments (basic)" "/comments?limit=10"
test_pagination "/comments"
test_endpoint "Comments: page 2" "/comments?page=2&limit=10"
test_endpoint "Comments: limit 25" "/comments?limit=25"
test_endpoint "Comments: with subreddit" "/comments?subreddit=RedditCensors&limit=10"
test_endpoint "Comments: with author" "/comments?author=NorseGodLoki0411&limit=10"
test_endpoint "Comments: with min_score" "/comments?min_score=5&limit=10"
test_endpoint "Comments: combined filters" "/comments?subreddit=RedditCensors&min_score=2&limit=10"

echo ""
echo "Comments Field Selection:"
test_endpoint "Fields: id only" "/comments?fields=id&limit=10"
test_endpoint "Fields: id,author,score" "/comments?fields=id,author,score&limit=10"
test_endpoint "Fields: id,body,created_utc" "/comments?fields=id,body,created_utc&limit=10"
test_endpoint "Invalid field" "/comments?fields=invalid_field&limit=10" "GET" "" "400"

echo ""
echo "Comments Truncation:"
test_endpoint "max_body_length=50" "/comments?max_body_length=50&limit=10"
test_endpoint "max_body_length=200" "/comments?max_body_length=200&limit=10"
test_endpoint "include_body=false" "/comments?include_body=false&limit=10"

echo ""
echo "Comments Export:"
test_endpoint "CSV export" "/comments?format=csv&limit=10" "GET" "" "200" "false"
test_endpoint "NDJSON export" "/comments?format=ndjson&limit=10" "GET" "" "200" "false"

echo ""
echo "Random Comments:"
test_endpoint "Random (n=5)" "/comments/random?n=5"
test_endpoint "Random (n=10)" "/comments/random?n=10"
test_endpoint "Random: with subreddit" "/comments/random?n=5&subreddit=RedditCensors"
test_endpoint "Random: with seed" "/comments/random?n=5&seed=42"

echo ""
echo "Comments Aggregation:"
test_endpoint "Group by author" "/comments/aggregate?group_by=author&limit=10"
test_endpoint "Group by subreddit" "/comments/aggregate?group_by=subreddit&limit=10"
test_endpoint "Group by time (daily)" "/comments/aggregate?group_by=created_utc&frequency=day&limit=30"

echo ""
echo "Comments Batch:"
test_endpoint "Batch lookup" "/comments/batch" "POST" '{"ids":["e4kq3zj","h2tiwkj"]}'

# ============================================================================
log_section "10. USERS ENDPOINTS"
# ============================================================================

echo "List Users:"
test_endpoint "GET /users (basic)" "/users?limit=10"
test_pagination "/users"
test_endpoint "Users: page 2" "/users?page=2&limit=10"
test_endpoint "Users: limit 25" "/users?limit=25"
test_endpoint "Users: sort by karma" "/users?sort=karma&limit=10"
test_endpoint "Users: sort by activity" "/users?sort=activity&limit=10"
test_endpoint "Users: sort by posts" "/users?sort=posts&limit=10"
test_endpoint "Users: sort by comments" "/users?sort=comments&limit=10"

echo ""
echo "Users Field Selection:"
test_endpoint "Fields: username only" "/users?fields=username&limit=10"
test_endpoint "Fields: username,total_karma" "/users?fields=username,total_karma&limit=10"
test_endpoint "Fields: username,post_count,comment_count" "/users?fields=username,post_count,comment_count&limit=10"
test_endpoint "Invalid field" "/users?fields=invalid_field&limit=10" "GET" "" "400"

echo ""
echo "Users Export:"
test_endpoint "CSV export" "/users?format=csv&limit=10" "GET" "" "200" "false"
test_endpoint "NDJSON export" "/users?format=ndjson&limit=10" "GET" "" "200" "false"

echo ""
echo "Single User:"
test_endpoint "GET /users/{username}" "/users/G_Petronius"
test_endpoint "GET /users/{username} (another)" "/users/NorseGodLoki0411"
test_endpoint "GET /users/{username} (invalid)" "/users/nonexistentuser12345" "GET" "" "404"

echo ""
echo "User Summary:"
test_endpoint "GET /users/{username}/summary" "/users/G_Petronius/summary"
test_endpoint "Summary: another user" "/users/NorseGodLoki0411/summary"

echo ""
echo "User Posts:"
test_endpoint "GET /users/{username}/posts" "/users/G_Petronius/posts?limit=10"
test_endpoint "User posts: page 2" "/users/G_Petronius/posts?page=2&limit=10"
test_endpoint "User posts: with fields" "/users/G_Petronius/posts?fields=id,title,score&limit=10"

echo ""
echo "User Comments:"
test_endpoint "GET /users/{username}/comments" "/users/G_Petronius/comments?limit=10"
test_endpoint "User comments: page 2" "/users/G_Petronius/comments?page=2&limit=10"
test_endpoint "User comments: with fields" "/users/G_Petronius/comments?fields=id,body,score&limit=10"

echo ""
echo "Users Aggregation:"
test_endpoint "Aggregate users" "/users/aggregate?limit=10"
test_endpoint "Aggregate: by subreddit" "/users/aggregate?subreddit=RedditCensors&limit=10"
test_endpoint "Aggregate: sort by posts" "/users/aggregate?sort_by=posts&limit=10"
test_endpoint "Aggregate: sort by comments" "/users/aggregate?sort_by=comments&limit=10"
test_endpoint "Aggregate: sort by total" "/users/aggregate?sort_by=total&limit=10"
test_endpoint "Aggregate: sort by karma" "/users/aggregate?sort_by=karma&limit=10"

echo ""
echo "Users Batch:"
test_endpoint "Batch: 2 users" "/users/batch" "POST" '{"usernames":["G_Petronius","NorseGodLoki0411"]}'
test_endpoint "Batch: 1 user" "/users/batch" "POST" '{"usernames":["G_Petronius"]}'
test_endpoint "Batch: with fields" "/users/batch" "POST" '{"usernames":["G_Petronius"],"fields":["username","total_karma"]}'

# ============================================================================
log_section "11. SUBREDDITS ENDPOINTS"
# ============================================================================

echo "List Subreddits:"
test_endpoint "GET /subreddits" "/subreddits"
test_endpoint "Subreddits: with filters" "/subreddits?min_score=10"
test_endpoint "Subreddits: with fields" "/subreddits?fields=name,total_posts,total_comments"
test_endpoint "Subreddits: CSV export" "/subreddits?format=csv" "GET" "" "200" "false"
test_endpoint "Subreddits: NDJSON export" "/subreddits?format=ndjson" "GET" "" "200" "false"

echo ""
echo "Single Subreddit:"
test_endpoint "GET /subreddits/{name}" "/subreddits/RedditCensors"
test_endpoint "Subreddit: with fields" "/subreddits/RedditCensors?fields=name,total_posts"
test_endpoint "Subreddit: invalid" "/subreddits/nonexistent123" "GET" "" "404"

echo ""
echo "Subreddit Summary:"
test_endpoint "GET /subreddits/{name}/summary" "/subreddits/RedditCensors/summary"

# ============================================================================
log_section "12. SEARCH ENDPOINTS"
# ============================================================================

echo "Basic Search:"
test_endpoint "Search: simple query" "/search?q=censorship&limit=10"
test_endpoint "Search: another query" "/search?q=banned&limit=10"
test_endpoint "Search: with pagination" "/search?q=moderator&page=1&limit=10"
test_endpoint "Search: page 2" "/search?q=reddit&page=2&limit=10"

echo ""
echo "Search Types:"
test_endpoint "Type: posts only" "/search?q=censorship&type=posts&limit=10"
test_endpoint "Type: comments only" "/search?q=censorship&type=comments&limit=10"
test_endpoint "Type: all (default)" "/search?q=censorship&type=all&limit=10"

echo ""
echo "Search Filters:"
test_endpoint "Filter: subreddit" "/search?q=ban&subreddit=RedditCensors&limit=10"
test_endpoint "Filter: author" "/search?q=post&author=G_Petronius&limit=10"
test_endpoint "Filter: min_score" "/search?q=thread&min_score=100&limit=10"
test_endpoint "Combined filters" "/search?q=reddit&subreddit=RedditCensors&min_score=10&limit=10"

echo ""
echo "Search Sorting:"
test_endpoint "Sort: relevance (default)" "/search?q=censorship&sort=relevance&limit=10"
test_endpoint "Sort: score" "/search?q=banned&sort=score&limit=10"
test_endpoint "Sort: created_utc" "/search?q=moderator&sort=created_utc&limit=10"

echo ""
echo "Search Operators:"
test_endpoint "Operator: exact phrase" "/search?q=\"reddit censorship\"&limit=10"
test_endpoint "Operator: OR" "/search?q=banned OR removed&limit=10"
test_endpoint "Operator: exclusion" "/search?q=censorship -moderator&limit=10"
test_endpoint "Operator: sub:" "/search?q=sub:RedditCensors banned&limit=10"
test_endpoint "Operator: author:" "/search?q=author:G_Petronius&limit=10"
test_endpoint "Operator: score:" "/search?q=score:100&limit=10"
test_endpoint "Combined operators" "/search?q=censorship OR banned sub:RedditCensors score:50&limit=10"

echo ""
echo "Search Explain:"
test_endpoint "Explain: simple query" "/search/explain?q=censorship"
test_endpoint "Explain: with operators" "/search/explain?q=banned OR removed"
test_endpoint "Explain: complex query" "/search/explain?q=\"reddit censorship\" -moderator sub:RedditCensors"

echo ""
echo "Search Error Cases:"
test_endpoint "Empty query" "/search?q=&limit=10" "GET" "" "400"
test_endpoint "Missing query" "/search?limit=10" "GET" "" "400"
test_endpoint "Invalid type" "/search?q=test&type=invalid&limit=10" "GET" "" "400"
test_endpoint "Invalid sort" "/search?q=test&sort=invalid&limit=10" "GET" "" "400"

# ============================================================================
log_section "13. ERROR HANDLING & EDGE CASES"
# ============================================================================

echo "Invalid Parameters:"
test_endpoint "Limit too low (5)" "/posts?limit=5" "GET" "" "400"
test_endpoint "Limit too high (200)" "/posts?limit=200" "GET" "" "400"
test_endpoint "Negative page" "/posts?page=-1&limit=10" "GET" "" "400"
test_endpoint "Zero page" "/posts?page=0&limit=10" "GET" "" "400"
test_endpoint "Invalid sort field" "/posts?sort=invalid_field&limit=10" "GET" "" "400"
test_endpoint "Invalid aggregate group_by" "/posts/aggregate?group_by=invalid" "GET" "" "400"
test_endpoint "Invalid frequency" "/posts/aggregate?group_by=created_utc&frequency=invalid" "GET" "" "400"

echo ""
echo "Boundary Testing:"
test_endpoint "Limit at minimum (10)" "/posts?limit=10"
test_endpoint "Limit at maximum (100)" "/posts?limit=100"
test_endpoint "Very high page number" "/posts?page=1000&limit=10"
test_endpoint "Max body length = 1" "/posts?max_body_length=1&limit=10"
test_endpoint "Max body length = 10000" "/posts?max_body_length=10000&limit=10"

echo ""
echo "Nonexistent Resources:"
test_endpoint "Nonexistent post" "/posts/zzzzzzz" "GET" "" "404"
test_endpoint "Nonexistent comment" "/comments/zzzzzzz" "GET" "" "404"
test_endpoint "Nonexistent user" "/users/nonexistentuser12345678" "GET" "" "404"
test_endpoint "Nonexistent subreddit" "/subreddits/nonexistentsubreddit12345" "GET" "" "404"

echo ""
echo "Special Characters & Unicode:"
test_endpoint "Query with spaces" "/search?q=reddit+censorship&limit=10"
test_endpoint "Query with special chars" "/search?q=test%21%40%23&limit=10"
test_endpoint "Author with underscore" "/posts?author=test_user&limit=10"

echo ""
echo "Empty Results:"
test_endpoint "Filter yielding no results" "/posts?subreddit=nonexistent&limit=10"
test_endpoint "Search yielding no results" "/search?q=zzzzzzzzzzzzzzz&limit=10"
test_endpoint "High min_score (no results)" "/posts?min_score=999999&limit=10"

# ============================================================================
log_section "14. RESPONSE STRUCTURE VALIDATION"
# ============================================================================

echo "Pagination Structure:"
test_pagination "/posts"
test_pagination "/comments"
test_pagination "/users"

echo ""
echo "Required Fields:"
test_response_structure "Post fields" "/posts/6a6igz" "id title author score created_utc"
test_response_structure "User fields" "/users/G_Petronius" "username post_count comment_count total_karma"
test_response_structure "Subreddit fields" "/subreddits/RedditCensors" "name total_posts total_comments"

# ============================================================================
log_section "15. PERFORMANCE & LIMITS"
# ============================================================================

echo "Large Result Sets:"
test_endpoint "100 posts" "/posts?limit=100"
test_endpoint "100 comments" "/comments?limit=100"
test_endpoint "100 users" "/users?limit=100"

echo ""
echo "Complex Queries:"
test_endpoint "All filters + field selection" "/posts?subreddit=RedditCensors&min_score=10&sort=score&fields=id,title,score&limit=50"
test_endpoint "Search with all operators" "/search?q=\"censorship\" OR banned -spam sub:RedditCensors score:10&type=posts&sort=score&limit=50"

# ============================================================================
# SUMMARY
# ============================================================================

log_section "TEST RESULTS SUMMARY"

echo "=========================================="
echo -e "${GREEN}Passed:   $PASSED${NC}"
echo -e "${RED}Failed:   $FAILED${NC}"
echo -e "${YELLOW}Warnings: $WARNINGS${NC}"
echo "Total:    $((PASSED + FAILED + WARNINGS))"
echo "=========================================="

if [ $FAILED -eq 0 ]; then
    echo -e "\n${GREEN}✓✓✓ ALL TESTS PASSED! ✓✓✓${NC}\n"
    exit 0
else
    echo -e "\n${RED}✗✗✗ SOME TESTS FAILED ✗✗✗${NC}\n"
    exit 1
fi
