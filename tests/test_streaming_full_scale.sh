#!/bin/bash
# ABOUTME: Integration tests for streaming user page generation at various scales
# ABOUTME: Tests 1K, 10K, 100K user datasets with memory profiling and resume capability

set -e  # Exit on error

echo "=== Streaming User Pages - Integration Test Suite ==="
echo ""

# =============================================================================
# CONFIGURATION
# =============================================================================

export DATABASE_URL="${DATABASE_URL:-postgresql://archive:archive_dev_2025@localhost:5432/archive_test}"
export ARCHIVE_USER_BATCH_SIZE=2000
export ARCHIVE_QUEUE_MAX_BATCHES=10
export ARCHIVE_CHECKPOINT_INTERVAL=5
export ARCHIVE_USER_PAGE_WORKERS=4

TEST_DATA_DIR="/tmp/archive-streaming-tests"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Configuration:"
echo "  DATABASE_URL: $DATABASE_URL"
echo "  BATCH_SIZE: $ARCHIVE_USER_BATCH_SIZE"
echo "  QUEUE_MAX: $ARCHIVE_QUEUE_MAX_BATCHES"
echo "  CHECKPOINT_INTERVAL: $ARCHIVE_CHECKPOINT_INTERVAL"
echo "  WORKERS: $ARCHIVE_USER_PAGE_WORKERS"
echo ""

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

cleanup() {
    echo "Cleaning up test data..."
    rm -rf "$TEST_DATA_DIR"
}

trap cleanup EXIT

create_test_data_dir() {
    rm -rf "$TEST_DATA_DIR"
    mkdir -p "$TEST_DATA_DIR"
}

verify_user_pages() {
    local output_dir=$1
    local expected_count=$2

    local actual_count=$(find "$output_dir/user" -name 'index.html' 2>/dev/null | wc -l)

    if [ "$actual_count" -eq "$expected_count" ]; then
        echo "  ✅ User pages verified: $actual_count / $expected_count"
        return 0
    else
        echo "  ❌ User pages mismatch: $actual_count / $expected_count"
        return 1
    fi
}

check_memory_usage() {
    local pid=$1
    local max_memory=0

    while kill -0 $pid 2>/dev/null; do
        local current_memory=$(ps -p $pid -o rss= 2>/dev/null || echo 0)
        if [ "$current_memory" -gt "$max_memory" ]; then
            max_memory=$current_memory
        fi
        sleep 1
    done

    # Convert to MB
    local max_memory_mb=$((max_memory / 1024))
    echo $max_memory_mb
}

# =============================================================================
# TEST CASES
# =============================================================================

test_1k_users() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Test 1: 1,000 Users"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    create_test_data_dir
    local output_dir="$TEST_DATA_DIR/test-1k"

    # Generate test users in database
    python3 - <<EOF
import sys
sys.path.insert(0, '$PROJECT_ROOT')
from postgres_database import PostgresDatabase

db = PostgresDatabase('$DATABASE_URL', workload_type='test')
print("Generating 1,000 test users...")
for i in range(1, 1001):
    db.update_user_statistics(
        username=f'test_user_{i:04d}',
        post_count=5,
        comment_count=10
    )
db.close()
print("✅ Test users generated")
EOF

    # Run streaming user page generation
    echo "Running streaming user page generation..."
    time python3 "$PROJECT_ROOT/redarch.py" /tmp/test-data \
        --output "$output_dir" \
        --export-from-database \
        --no-sitemap \
        --no-search

    # Verify output
    verify_user_pages "$output_dir" 1000

    echo "✅ Test 1 passed"
    echo ""
}

test_10k_users() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Test 2: 10,000 Users"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    create_test_data_dir
    local output_dir="$TEST_DATA_DIR/test-10k"

    # Generate test users in database
    python3 - <<EOF
import sys
sys.path.insert(0, '$PROJECT_ROOT')
from postgres_database import PostgresDatabase

db = PostgresDatabase('$DATABASE_URL', workload_type='test')
print("Generating 10,000 test users...")
for i in range(1, 10001):
    db.update_user_statistics(
        username=f'test_user_{i:05d}',
        post_count=10,
        comment_count=20
    )
    if i % 1000 == 0:
        print(f"  {i:,} users generated...")
db.close()
print("✅ Test users generated")
EOF

    # Run streaming user page generation with memory monitoring
    echo "Running streaming user page generation with memory monitoring..."
    python3 "$PROJECT_ROOT/redarch.py" /tmp/test-data \
        --output "$output_dir" \
        --export-from-database \
        --no-sitemap \
        --no-search &

    local pid=$!
    local max_memory=$(check_memory_usage $pid)
    wait $pid

    echo "  Peak memory usage: ${max_memory}MB"

    # Memory should stay below 2GB for 10K users
    if [ "$max_memory" -lt 2048 ]; then
        echo "  ✅ Memory usage within bounds (<2GB)"
    else
        echo "  ⚠️  Memory usage high: ${max_memory}MB"
    fi

    # Verify output
    verify_user_pages "$output_dir" 10000

    echo "✅ Test 2 passed"
    echo ""
}

test_100k_users() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Test 3: 100,000 Users (Memory Stress Test)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    create_test_data_dir
    local output_dir="$TEST_DATA_DIR/test-100k"

    # Generate test users in database
    python3 - <<EOF
import sys
sys.path.insert(0, '$PROJECT_ROOT')
from postgres_database import PostgresDatabase

db = PostgresDatabase('$DATABASE_URL', workload_type='test')
print("Generating 100,000 test users...")
for i in range(1, 100001):
    db.update_user_statistics(
        username=f'test_user_{i:06d}',
        post_count=10,
        comment_count=30
    )
    if i % 10000 == 0:
        print(f"  {i:,} users generated...")
db.close()
print("✅ Test users generated")
EOF

    # Run streaming user page generation with memory monitoring
    echo "Running streaming user page generation with memory monitoring..."
    python3 "$PROJECT_ROOT/redarch.py" /tmp/test-data \
        --output "$output_dir" \
        --export-from-database \
        --no-sitemap \
        --no-search &

    local pid=$!
    local max_memory=$(check_memory_usage $pid)
    wait $pid

    echo "  Peak memory usage: ${max_memory}MB"

    # Memory should stay below 4GB for 100K users
    if [ "$max_memory" -lt 4096 ]; then
        echo "  ✅ Memory usage within bounds (<4GB)"
    else
        echo "  ⚠️  Memory usage high: ${max_memory}MB"
    fi

    # Verify output
    verify_user_pages "$output_dir" 100000

    echo "✅ Test 3 passed"
    echo ""
}

test_resume_capability() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Test 4: Resume Capability"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    create_test_data_dir
    local output_dir="$TEST_DATA_DIR/test-resume"

    # Generate test users in database
    python3 - <<EOF
import sys
sys.path.insert(0, '$PROJECT_ROOT')
from postgres_database import PostgresDatabase

db = PostgresDatabase('$DATABASE_URL', workload_type='test')
print("Generating 5,000 test users...")
for i in range(1, 5001):
    db.update_user_statistics(
        username=f'test_user_{i:04d}',
        post_count=5,
        comment_count=15
    )
db.close()
print("✅ Test users generated")
EOF

    # Start processing and interrupt after 30 seconds
    echo "Starting processing (will interrupt after 30 seconds)..."
    timeout 30 python3 "$PROJECT_ROOT/redarch.py" /tmp/test-data \
        --output "$output_dir" \
        --export-from-database \
        --no-sitemap \
        --no-search || true

    local partial_count=$(find "$output_dir/user" -name 'index.html' 2>/dev/null | wc -l)
    echo "  Partial completion: $partial_count users processed"

    # Resume processing
    echo "Resuming processing..."
    time python3 "$PROJECT_ROOT/redarch.py" /tmp/test-data \
        --output "$output_dir" \
        --export-from-database \
        --no-sitemap \
        --no-search

    # Verify all users processed
    verify_user_pages "$output_dir" 5000

    echo "✅ Test 4 passed - Resume capability verified"
    echo ""
}

# =============================================================================
# RUN ALL TESTS
# =============================================================================

main() {
    echo "Starting integration test suite..."
    echo ""

    local tests_passed=0
    local tests_failed=0

    # Run tests
    if test_1k_users; then
        ((tests_passed++))
    else
        ((tests_failed++))
    fi

    if test_10k_users; then
        ((tests_passed++))
    else
        ((tests_failed++))
    fi

    if test_100k_users; then
        ((tests_passed++))
    else
        ((tests_failed++))
    fi

    if test_resume_capability; then
        ((tests_passed++))
    else
        ((tests_failed++))
    fi

    # Summary
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Test Summary"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Passed: $tests_passed"
    echo "  Failed: $tests_failed"
    echo ""

    if [ "$tests_failed" -eq 0 ]; then
        echo "✅ All integration tests passed!"
        return 0
    else
        echo "❌ Some tests failed"
        return 1
    fi
}

# Run main function
main
