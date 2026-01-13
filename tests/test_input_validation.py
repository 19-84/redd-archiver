#!/usr/bin/env python
"""
ABOUTME: Unit tests for input validation module
ABOUTME: Tests query, subreddit, author, score, limit, offset, and page validation
"""

import pytest

from utils.input_validation import (
    MAX_AUTHOR_LENGTH,
    MAX_LIMIT,
    MAX_OFFSET,
    MAX_PAGE_NUMBER,
    MAX_QUERY_LENGTH,
    MAX_SCORE_VALUE,
    MAX_SUBREDDIT_LENGTH,
    MIN_LIMIT,
    MIN_SCORE_VALUE,
    SearchInputValidator,
    ValidationError,
    ValidationResult,
    is_valid_author,
    is_valid_subreddit,
    sanitize_query,
    validate_search_params,
    validator,
)

# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def input_validator():
    """Fresh validator instance for each test."""
    return SearchInputValidator()


# =============================================================================
# QUERY VALIDATION TESTS
# =============================================================================


@pytest.mark.unit
class TestValidateQuery:
    """Tests for query text validation."""

    def test_valid_query_simple(self, input_validator):
        """Test simple valid query."""
        valid, sanitized, error = input_validator.validate_query("test query")
        assert valid is True
        assert sanitized == "test query"
        assert error is None

    def test_valid_query_with_special_chars(self, input_validator):
        """Test query with allowed special characters."""
        valid, sanitized, error = input_validator.validate_query('"quoted phrase" -exclude OR alternative')
        assert valid is True
        assert sanitized == '"quoted phrase" -exclude OR alternative'
        assert error is None

    def test_valid_query_max_length(self, input_validator):
        """Test query at maximum length boundary."""
        query = "a" * MAX_QUERY_LENGTH
        valid, sanitized, error = input_validator.validate_query(query)
        assert valid is True
        assert len(sanitized) == MAX_QUERY_LENGTH
        assert error is None

    def test_empty_query_allowed(self, input_validator):
        """Test that empty query is allowed (converted to wildcard later)."""
        valid, sanitized, error = input_validator.validate_query("")
        assert valid is True
        assert sanitized == ""
        assert error is None

    def test_whitespace_only_query_allowed(self, input_validator):
        """Test that whitespace-only query is allowed."""
        valid, sanitized, error = input_validator.validate_query("   ")
        assert valid is True
        assert sanitized == ""
        assert error is None

    def test_query_too_long_rejected(self, input_validator):
        """Test query exceeding max length is rejected."""
        query = "a" * (MAX_QUERY_LENGTH + 1)
        valid, sanitized, error = input_validator.validate_query(query)
        assert valid is False
        assert "too long" in error.lower()

    def test_null_byte_rejected(self, input_validator):
        """Test query with null byte is rejected (security)."""
        valid, sanitized, error = input_validator.validate_query("test\x00query")
        assert valid is False
        assert "invalid" in error.lower()

    def test_control_characters_rejected(self, input_validator):
        """Test query with control characters is rejected."""
        # Test with bell character (ASCII 7)
        valid, sanitized, error = input_validator.validate_query("test\x07query")
        assert valid is False
        assert "control" in error.lower()

    def test_tab_and_newline_allowed(self, input_validator):
        """Test that tab and newline are allowed in queries."""
        valid, sanitized, error = input_validator.validate_query("line1\nline2\ttab")
        assert valid is True
        assert sanitized == "line1\nline2\ttab"

    def test_query_stripped(self, input_validator):
        """Test query whitespace is stripped."""
        valid, sanitized, error = input_validator.validate_query("  test query  ")
        assert valid is True
        assert sanitized == "test query"


# =============================================================================
# SUBREDDIT VALIDATION TESTS
# =============================================================================


@pytest.mark.unit
class TestValidateSubreddit:
    """Tests for subreddit name validation."""

    def test_valid_subreddit_lowercase(self, input_validator):
        """Test valid lowercase subreddit name."""
        valid, sanitized, error = input_validator.validate_subreddit("technology")
        assert valid is True
        assert sanitized == "technology"
        assert error is None

    def test_valid_subreddit_mixed_case(self, input_validator):
        """Test valid mixed case subreddit name."""
        valid, sanitized, error = input_validator.validate_subreddit("AskReddit")
        assert valid is True
        assert sanitized == "AskReddit"
        assert error is None

    def test_valid_subreddit_with_numbers(self, input_validator):
        """Test valid subreddit name with numbers."""
        valid, sanitized, error = input_validator.validate_subreddit("tech123")
        assert valid is True
        assert sanitized == "tech123"

    def test_valid_subreddit_with_underscore(self, input_validator):
        """Test valid subreddit name with underscore."""
        valid, sanitized, error = input_validator.validate_subreddit("ask_reddit")
        assert valid is True
        assert sanitized == "ask_reddit"

    def test_valid_subreddit_min_length(self, input_validator):
        """Test subreddit at minimum length (2 chars)."""
        valid, sanitized, error = input_validator.validate_subreddit("ab")
        assert valid is True
        assert sanitized == "ab"

    def test_valid_subreddit_max_length(self, input_validator):
        """Test subreddit at maximum length (21 chars)."""
        subreddit = "a" * MAX_SUBREDDIT_LENGTH
        valid, sanitized, error = input_validator.validate_subreddit(subreddit)
        assert valid is True
        assert len(sanitized) == MAX_SUBREDDIT_LENGTH

    def test_empty_subreddit_allowed(self, input_validator):
        """Test empty subreddit is allowed (optional field)."""
        valid, sanitized, error = input_validator.validate_subreddit("")
        assert valid is True
        assert sanitized is None
        assert error is None

    def test_none_subreddit_allowed(self, input_validator):
        """Test None subreddit is allowed (optional field)."""
        valid, sanitized, error = input_validator.validate_subreddit(None)
        assert valid is True
        assert sanitized is None

    def test_subreddit_too_short_rejected(self, input_validator):
        """Test subreddit below minimum length is rejected."""
        valid, sanitized, error = input_validator.validate_subreddit("a")
        assert valid is False
        assert "too short" in error.lower()

    def test_subreddit_too_long_rejected(self, input_validator):
        """Test subreddit exceeding max length is rejected."""
        subreddit = "a" * (MAX_SUBREDDIT_LENGTH + 1)
        valid, sanitized, error = input_validator.validate_subreddit(subreddit)
        assert valid is False
        assert "too long" in error.lower()

    def test_subreddit_with_hyphen_rejected(self, input_validator):
        """Test subreddit with hyphen is rejected (not allowed by Reddit)."""
        valid, sanitized, error = input_validator.validate_subreddit("test-sub")
        assert valid is False
        assert "invalid" in error.lower()

    def test_subreddit_with_space_rejected(self, input_validator):
        """Test subreddit with space is rejected."""
        valid, sanitized, error = input_validator.validate_subreddit("test sub")
        assert valid is False
        assert "invalid" in error.lower()

    def test_subreddit_with_special_chars_rejected(self, input_validator):
        """Test subreddit with special characters is rejected."""
        valid, sanitized, error = input_validator.validate_subreddit("test@sub")
        assert valid is False
        assert "invalid" in error.lower()


# =============================================================================
# AUTHOR VALIDATION TESTS
# =============================================================================


@pytest.mark.unit
class TestValidateAuthor:
    """Tests for author username validation."""

    def test_valid_author_lowercase(self, input_validator):
        """Test valid lowercase username."""
        valid, sanitized, error = input_validator.validate_author("testuser")
        assert valid is True
        assert sanitized == "testuser"
        assert error is None

    def test_valid_author_with_underscore(self, input_validator):
        """Test valid username with underscore."""
        valid, sanitized, error = input_validator.validate_author("test_user")
        assert valid is True
        assert sanitized == "test_user"

    def test_valid_author_with_hyphen(self, input_validator):
        """Test valid username with hyphen."""
        valid, sanitized, error = input_validator.validate_author("test-user")
        assert valid is True
        assert sanitized == "test-user"

    def test_valid_author_with_numbers(self, input_validator):
        """Test valid username with numbers."""
        valid, sanitized, error = input_validator.validate_author("user123")
        assert valid is True
        assert sanitized == "user123"

    def test_valid_author_min_length(self, input_validator):
        """Test username at minimum length (3 chars)."""
        valid, sanitized, error = input_validator.validate_author("abc")
        assert valid is True
        assert sanitized == "abc"

    def test_valid_author_max_length(self, input_validator):
        """Test username at maximum length (20 chars)."""
        author = "a" * MAX_AUTHOR_LENGTH
        valid, sanitized, error = input_validator.validate_author(author)
        assert valid is True
        assert len(sanitized) == MAX_AUTHOR_LENGTH

    def test_empty_author_allowed(self, input_validator):
        """Test empty author is allowed (optional field)."""
        valid, sanitized, error = input_validator.validate_author("")
        assert valid is True
        assert sanitized is None

    def test_none_author_allowed(self, input_validator):
        """Test None author is allowed (optional field)."""
        valid, sanitized, error = input_validator.validate_author(None)
        assert valid is True
        assert sanitized is None

    def test_author_too_short_rejected(self, input_validator):
        """Test username below minimum length is rejected."""
        valid, sanitized, error = input_validator.validate_author("ab")
        assert valid is False
        assert "too short" in error.lower()

    def test_author_too_long_rejected(self, input_validator):
        """Test username exceeding max length is rejected."""
        author = "a" * (MAX_AUTHOR_LENGTH + 1)
        valid, sanitized, error = input_validator.validate_author(author)
        assert valid is False
        assert "too long" in error.lower()

    def test_author_with_at_symbol_rejected(self, input_validator):
        """Test username with @ symbol is rejected."""
        valid, sanitized, error = input_validator.validate_author("user@domain")
        assert valid is False
        assert "invalid" in error.lower()

    def test_author_with_space_rejected(self, input_validator):
        """Test username with space is rejected."""
        valid, sanitized, error = input_validator.validate_author("test user")
        assert valid is False
        assert "invalid" in error.lower()


# =============================================================================
# SCORE VALIDATION TESTS
# =============================================================================


@pytest.mark.unit
class TestValidateScore:
    """Tests for score value validation."""

    def test_valid_score_zero(self, input_validator):
        """Test zero score is valid."""
        valid, sanitized, error = input_validator.validate_score(0)
        assert valid is True
        assert sanitized == 0

    def test_valid_score_positive(self, input_validator):
        """Test positive score is valid."""
        valid, sanitized, error = input_validator.validate_score(100)
        assert valid is True
        assert sanitized == 100

    def test_valid_score_negative(self, input_validator):
        """Test negative score is valid."""
        valid, sanitized, error = input_validator.validate_score(-100)
        assert valid is True
        assert sanitized == -100

    def test_valid_score_max_value(self, input_validator):
        """Test score at maximum value boundary."""
        valid, sanitized, error = input_validator.validate_score(MAX_SCORE_VALUE)
        assert valid is True
        assert sanitized == MAX_SCORE_VALUE

    def test_valid_score_min_value(self, input_validator):
        """Test score at minimum value boundary."""
        valid, sanitized, error = input_validator.validate_score(MIN_SCORE_VALUE)
        assert valid is True
        assert sanitized == MIN_SCORE_VALUE

    def test_none_score_defaults_to_zero(self, input_validator):
        """Test None score defaults to 0."""
        valid, sanitized, error = input_validator.validate_score(None)
        assert valid is True
        assert sanitized == 0

    def test_score_overflow_rejected(self, input_validator):
        """Test score exceeding max value is rejected."""
        valid, sanitized, error = input_validator.validate_score(MAX_SCORE_VALUE + 1)
        assert valid is False
        assert "out of range" in error.lower()

    def test_score_string_coerced(self, input_validator):
        """Test string score is coerced to integer."""
        valid, sanitized, error = input_validator.validate_score("100")
        assert valid is True
        assert sanitized == 100

    def test_score_invalid_string_rejected(self, input_validator):
        """Test invalid string score is rejected."""
        valid, sanitized, error = input_validator.validate_score("not_a_number")
        assert valid is False
        assert "integer" in error.lower()


# =============================================================================
# LIMIT VALIDATION TESTS
# =============================================================================


@pytest.mark.unit
class TestValidateLimit:
    """Tests for limit (results per page) validation."""

    def test_valid_limit_default(self, input_validator):
        """Test limit at typical default value."""
        valid, sanitized, error = input_validator.validate_limit(25)
        assert valid is True
        assert sanitized == 25

    def test_valid_limit_min(self, input_validator):
        """Test limit at minimum value."""
        valid, sanitized, error = input_validator.validate_limit(MIN_LIMIT)
        assert valid is True
        assert sanitized == MIN_LIMIT

    def test_valid_limit_max(self, input_validator):
        """Test limit at maximum value."""
        valid, sanitized, error = input_validator.validate_limit(MAX_LIMIT)
        assert valid is True
        assert sanitized == MAX_LIMIT

    def test_none_limit_defaults(self, input_validator):
        """Test None limit defaults to 25."""
        valid, sanitized, error = input_validator.validate_limit(None)
        assert valid is True
        assert sanitized == 25

    def test_limit_too_low_rejected(self, input_validator):
        """Test limit below minimum is rejected."""
        valid, sanitized, error = input_validator.validate_limit(MIN_LIMIT - 1)
        assert valid is False
        assert "out of range" in error.lower()

    def test_limit_too_high_rejected(self, input_validator):
        """Test limit above maximum is rejected."""
        valid, sanitized, error = input_validator.validate_limit(MAX_LIMIT + 1)
        assert valid is False
        assert "out of range" in error.lower()

    def test_limit_string_coerced(self, input_validator):
        """Test string limit is coerced to integer."""
        valid, sanitized, error = input_validator.validate_limit("50")
        assert valid is True
        assert sanitized == 50


# =============================================================================
# OFFSET VALIDATION TESTS
# =============================================================================


@pytest.mark.unit
class TestValidateOffset:
    """Tests for offset (pagination) validation."""

    def test_valid_offset_zero(self, input_validator):
        """Test zero offset is valid."""
        valid, sanitized, error = input_validator.validate_offset(0)
        assert valid is True
        assert sanitized == 0

    def test_valid_offset_mid_range(self, input_validator):
        """Test mid-range offset is valid."""
        valid, sanitized, error = input_validator.validate_offset(5000)
        assert valid is True
        assert sanitized == 5000

    def test_valid_offset_max(self, input_validator):
        """Test offset at maximum value."""
        valid, sanitized, error = input_validator.validate_offset(MAX_OFFSET)
        assert valid is True
        assert sanitized == MAX_OFFSET

    def test_none_offset_defaults(self, input_validator):
        """Test None offset defaults to 0."""
        valid, sanitized, error = input_validator.validate_offset(None)
        assert valid is True
        assert sanitized == 0

    def test_negative_offset_rejected(self, input_validator):
        """Test negative offset is rejected."""
        valid, sanitized, error = input_validator.validate_offset(-1)
        assert valid is False
        assert "out of range" in error.lower()

    def test_offset_too_high_rejected(self, input_validator):
        """Test offset exceeding max is rejected (prevent deep pagination abuse)."""
        valid, sanitized, error = input_validator.validate_offset(MAX_OFFSET + 1)
        assert valid is False
        assert "out of range" in error.lower()


# =============================================================================
# PAGE VALIDATION TESTS
# =============================================================================


@pytest.mark.unit
class TestValidatePage:
    """Tests for page number validation and offset calculation."""

    def test_valid_page_one(self, input_validator):
        """Test page 1 returns offset 0."""
        valid, offset, error = input_validator.validate_page(1)
        assert valid is True
        assert offset == 0

    def test_valid_page_two(self, input_validator):
        """Test page 2 with default limit (25) returns offset 25."""
        valid, offset, error = input_validator.validate_page(2, limit=25)
        assert valid is True
        assert offset == 25

    def test_valid_page_with_custom_limit(self, input_validator):
        """Test page calculation with custom limit."""
        valid, offset, error = input_validator.validate_page(3, limit=50)
        assert valid is True
        assert offset == 100  # (3-1) * 50

    def test_none_page_defaults(self, input_validator):
        """Test None page defaults to page 1 (offset 0)."""
        valid, offset, error = input_validator.validate_page(None)
        assert valid is True
        assert offset == 0

    def test_page_zero_rejected(self, input_validator):
        """Test page 0 is rejected (pages are 1-indexed)."""
        valid, offset, error = input_validator.validate_page(0)
        assert valid is False
        assert "at least 1" in error.lower()

    def test_negative_page_rejected(self, input_validator):
        """Test negative page is rejected."""
        valid, offset, error = input_validator.validate_page(-1)
        assert valid is False
        assert "at least 1" in error.lower()

    def test_page_too_high_rejected(self, input_validator):
        """Test page exceeding max is rejected."""
        valid, offset, error = input_validator.validate_page(MAX_PAGE_NUMBER + 1)
        assert valid is False
        assert "too high" in error.lower()

    def test_page_offset_exceeds_max_rejected(self, input_validator):
        """Test page that would result in offset > MAX_OFFSET is rejected."""
        # With limit=100, page 102 would give offset 10100 > MAX_OFFSET (10000)
        valid, offset, error = input_validator.validate_page(102, limit=100)
        assert valid is False
        assert "exceeds maximum offset" in error.lower()


# =============================================================================
# RESULT TYPE VALIDATION TESTS
# =============================================================================


@pytest.mark.unit
class TestValidateResultType:
    """Tests for result type (post/comment) validation."""

    def test_valid_type_post(self, input_validator):
        """Test 'post' type is valid."""
        valid, sanitized, error = input_validator.validate_result_type("post")
        assert valid is True
        assert sanitized == "post"

    def test_valid_type_comment(self, input_validator):
        """Test 'comment' type is valid."""
        valid, sanitized, error = input_validator.validate_result_type("comment")
        assert valid is True
        assert sanitized == "comment"

    def test_type_case_insensitive(self, input_validator):
        """Test result type is case insensitive."""
        valid, sanitized, error = input_validator.validate_result_type("POST")
        assert valid is True
        assert sanitized == "post"

    def test_empty_type_allowed(self, input_validator):
        """Test empty type is allowed (search both)."""
        valid, sanitized, error = input_validator.validate_result_type("")
        assert valid is True
        assert sanitized is None

    def test_none_type_allowed(self, input_validator):
        """Test None type is allowed (search both)."""
        valid, sanitized, error = input_validator.validate_result_type(None)
        assert valid is True
        assert sanitized is None

    def test_invalid_type_rejected(self, input_validator):
        """Test invalid type is rejected."""
        valid, sanitized, error = input_validator.validate_result_type("invalid")
        assert valid is False
        assert "invalid result type" in error.lower()


# =============================================================================
# SORT BY VALIDATION TESTS
# =============================================================================


@pytest.mark.unit
class TestValidateSortBy:
    """Tests for sort order validation."""

    def test_valid_sort_rank(self, input_validator):
        """Test 'rank' sort is valid."""
        valid, sanitized, error = input_validator.validate_sort_by("rank")
        assert valid is True
        assert sanitized == "rank"

    def test_valid_sort_score(self, input_validator):
        """Test 'score' sort is valid."""
        valid, sanitized, error = input_validator.validate_sort_by("score")
        assert valid is True
        assert sanitized == "score"

    def test_valid_sort_date(self, input_validator):
        """Test 'date' sort is valid."""
        valid, sanitized, error = input_validator.validate_sort_by("date")
        assert valid is True
        assert sanitized == "date"

    def test_valid_sort_new(self, input_validator):
        """Test 'new' sort is valid."""
        valid, sanitized, error = input_validator.validate_sort_by("new")
        assert valid is True
        assert sanitized == "new"

    def test_valid_sort_old(self, input_validator):
        """Test 'old' sort is valid."""
        valid, sanitized, error = input_validator.validate_sort_by("old")
        assert valid is True
        assert sanitized == "old"

    def test_sort_case_insensitive(self, input_validator):
        """Test sort is case insensitive."""
        valid, sanitized, error = input_validator.validate_sort_by("SCORE")
        assert valid is True
        assert sanitized == "score"

    def test_empty_sort_defaults(self, input_validator):
        """Test empty sort defaults to rank."""
        valid, sanitized, error = input_validator.validate_sort_by("")
        assert valid is True
        assert sanitized == "rank"

    def test_none_sort_defaults(self, input_validator):
        """Test None sort defaults to rank."""
        valid, sanitized, error = input_validator.validate_sort_by(None)
        assert valid is True
        assert sanitized == "rank"

    def test_invalid_sort_rejected(self, input_validator):
        """Test invalid sort is rejected."""
        valid, sanitized, error = input_validator.validate_sort_by("invalid")
        assert valid is False
        assert "invalid sort" in error.lower()


# =============================================================================
# COMPREHENSIVE VALIDATION TESTS
# =============================================================================


@pytest.mark.unit
class TestValidateAll:
    """Tests for comprehensive validation (validate_all method)."""

    def test_valid_complete_query(self, input_validator):
        """Test completely valid query parameters."""
        result = input_validator.validate_all(
            query="test search", subreddit="technology", author="testuser", min_score=10, limit=50, page=1
        )

        assert result.is_valid is True
        assert len(result.errors) == 0
        assert result.sanitized_values["query"] == "test search"
        assert result.sanitized_values["subreddit"] == "technology"
        assert result.sanitized_values["author"] == "testuser"
        assert result.sanitized_values["min_score"] == 10
        assert result.sanitized_values["limit"] == 50
        assert result.sanitized_values["offset"] == 0  # page 1

    def test_multiple_validation_errors(self, input_validator):
        """Test multiple errors are collected."""
        result = input_validator.validate_all(
            query="test",
            subreddit="a",
            author="ab",
            limit=200,  # too short  # too short  # too high
        )

        assert result.is_valid is False
        assert len(result.errors) >= 3

        error_fields = [err.field for err in result.errors]
        assert "subreddit" in error_fields
        assert "author" in error_fields
        assert "limit" in error_fields

    def test_sanitized_values_returned_on_success(self, input_validator):
        """Test sanitized values are properly returned."""
        result = input_validator.validate_all(
            query="  test  ", subreddit="TechNology", limit=50, result_type="POST", sort_by="SCORE"
        )

        assert result.is_valid is True
        assert result.sanitized_values["query"] == "test"
        assert result.sanitized_values["subreddit"] == "TechNology"
        assert result.sanitized_values["limit"] == 50
        assert result.sanitized_values["result_type"] == "post"
        assert result.sanitized_values["sort_by"] == "score"

    def test_page_and_offset_mutual_exclusion(self, input_validator):
        """Test page takes precedence over offset."""
        result = input_validator.validate_all(query="test", page=2, offset=100, limit=25)

        assert result.is_valid is True
        # Page should win, offset should be calculated from page
        assert result.sanitized_values["offset"] == 25  # (page 2 - 1) * 25
        assert result.sanitized_values["page"] == 2


# =============================================================================
# VALIDATION RESULT CLASS TESTS
# =============================================================================


@pytest.mark.unit
class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_get_error_messages(self):
        """Test error message retrieval."""
        errors = [
            ValidationError("field1", "Error message 1"),
            ValidationError("field2", "Error message 2"),
        ]
        result = ValidationResult(is_valid=False, errors=errors, sanitized_values={})

        messages = result.get_error_messages()
        assert len(messages) == 2
        assert "field1: Error message 1" in messages
        assert "field2: Error message 2" in messages

    def test_get_first_error(self):
        """Test first error retrieval."""
        errors = [
            ValidationError("field1", "First error"),
            ValidationError("field2", "Second error"),
        ]
        result = ValidationResult(is_valid=False, errors=errors, sanitized_values={})

        first = result.get_first_error()
        assert first == "field1: First error"

    def test_get_first_error_empty(self):
        """Test first error on valid result."""
        result = ValidationResult(is_valid=True, errors=[], sanitized_values={})
        assert result.get_first_error() is None


# =============================================================================
# CONVENIENCE FUNCTION TESTS
# =============================================================================


@pytest.mark.unit
class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_validate_search_params(self):
        """Test validate_search_params convenience function."""
        result = validate_search_params("test query", subreddit="tech", limit=50)

        assert result.is_valid is True
        assert result.sanitized_values["subreddit"] == "tech"

    def test_is_valid_subreddit_true(self):
        """Test is_valid_subreddit returns True for valid names."""
        assert is_valid_subreddit("technology") is True
        assert is_valid_subreddit("AskReddit") is True
        assert is_valid_subreddit("test_sub") is True

    def test_is_valid_subreddit_false(self):
        """Test is_valid_subreddit returns False for invalid names."""
        assert is_valid_subreddit("a") is False
        assert is_valid_subreddit("test-sub") is False
        assert is_valid_subreddit("a" * 25) is False

    def test_is_valid_author_true(self):
        """Test is_valid_author returns True for valid usernames."""
        assert is_valid_author("testuser") is True
        assert is_valid_author("test-user") is True
        assert is_valid_author("test_user") is True

    def test_is_valid_author_false(self):
        """Test is_valid_author returns False for invalid usernames."""
        assert is_valid_author("ab") is False
        assert is_valid_author("user@domain") is False
        assert is_valid_author("a" * 25) is False

    def test_sanitize_query_valid(self):
        """Test sanitize_query with valid input."""
        assert sanitize_query("  test query  ") == "test query"

    def test_sanitize_query_invalid(self):
        """Test sanitize_query with invalid input returns empty string."""
        assert sanitize_query("test\x00query") == ""


# =============================================================================
# GLOBAL VALIDATOR INSTANCE TESTS
# =============================================================================


@pytest.mark.unit
class TestGlobalValidator:
    """Tests for global validator instance."""

    def test_global_validator_exists(self):
        """Test global validator is available."""
        assert validator is not None
        assert isinstance(validator, SearchInputValidator)

    def test_global_validator_works(self):
        """Test global validator functions correctly."""
        valid, sanitized, error = validator.validate_query("test")
        assert valid is True
        assert sanitized == "test"
