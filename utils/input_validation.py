#!/usr/bin/env python
"""
ABOUTME: Comprehensive input validation module for search parameters
ABOUTME: Enforces length limits, format validation, and sanitization to prevent abuse
"""
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

# ============================================================================
# VALIDATION CONSTANTS (based on Reddit's actual limits)
# ============================================================================

MAX_QUERY_LENGTH = 500
MAX_SUBREDDIT_LENGTH = 21  # Reddit max subreddit name length
MAX_AUTHOR_LENGTH = 20     # Reddit max username length
MAX_SCORE_VALUE = 2147483647  # INT32_MAX
MIN_SCORE_VALUE = -2147483648  # INT32_MIN
MAX_LIMIT = 100  # Maximum results per page
MIN_LIMIT = 10   # Minimum results per page
MAX_OFFSET = 10000  # Maximum pagination offset (prevent abuse)
MAX_PAGE_NUMBER = 1000  # Maximum page number (prevent deep pagination abuse)

# Valid patterns (Reddit's actual format rules)
SUBREDDIT_PATTERN = re.compile(r'^[a-zA-Z0-9_]{2,21}$')
AUTHOR_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{3,20}$')

# ============================================================================
# VALIDATION RESULT CLASSES
# ============================================================================

@dataclass
class ValidationError:
    """Validation error with field and message."""
    field: str
    message: str

    def __str__(self):
        return f"{self.field}: {self.message}"


@dataclass
class ValidationResult:
    """Result of input validation."""
    is_valid: bool
    errors: List[ValidationError]
    sanitized_values: dict

    def get_error_messages(self) -> List[str]:
        """Get list of error messages."""
        return [str(err) for err in self.errors]

    def get_first_error(self) -> Optional[str]:
        """Get first error message (for simple error display)."""
        return str(self.errors[0]) if self.errors else None


# ============================================================================
# VALIDATOR CLASS
# ============================================================================

class SearchInputValidator:
    """Validates and sanitizes search input parameters."""

    def validate_query(self, query: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validate search query text.

        Args:
            query: Raw query string

        Returns:
            Tuple of (is_valid, sanitized_query, error_message)
        """
        if not query:
            # Empty query is allowed - will be converted to wildcard in search_server.py
            return True, '', None

        # Strip whitespace
        query = query.strip()

        if not query:
            # Empty query after stripping is allowed - will be converted to wildcard
            return True, '', None

        # Check length
        if len(query) > MAX_QUERY_LENGTH:
            return False, query[:MAX_QUERY_LENGTH], f"Query too long (max {MAX_QUERY_LENGTH} characters)"

        # Check for null bytes (security - can cause issues in C libraries)
        if '\x00' in query:
            return False, None, "Query contains invalid characters"

        # Check for control characters (except newline/tab which might be in quotes)
        control_chars = [chr(i) for i in range(32) if i not in (9, 10, 13)]
        for char in control_chars:
            if char in query:
                return False, None, "Query contains invalid control characters"

        return True, query, None

    def validate_subreddit(self, subreddit: Optional[str]) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validate subreddit name.

        Args:
            subreddit: Subreddit name (without r/ prefix)

        Returns:
            Tuple of (is_valid, sanitized_subreddit, error_message)
        """
        if not subreddit:
            return True, None, None  # Optional field

        subreddit = subreddit.strip()

        # Check length
        if len(subreddit) > MAX_SUBREDDIT_LENGTH:
            return False, None, f"Subreddit name too long (max {MAX_SUBREDDIT_LENGTH} characters)"

        if len(subreddit) < 2:
            return False, None, "Subreddit name too short (min 2 characters)"

        # Check format (alphanumeric + underscore only, per Reddit rules)
        if not SUBREDDIT_PATTERN.match(subreddit):
            return False, None, "Invalid subreddit name (only letters, numbers, underscore allowed)"

        return True, subreddit, None

    def validate_author(self, author: Optional[str]) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validate author username.

        Args:
            author: Reddit username

        Returns:
            Tuple of (is_valid, sanitized_author, error_message)
        """
        if not author:
            return True, None, None  # Optional field

        author = author.strip()

        # Check length
        if len(author) > MAX_AUTHOR_LENGTH:
            return False, None, f"Username too long (max {MAX_AUTHOR_LENGTH} characters)"

        if len(author) < 3:
            return False, None, "Username too short (min 3 characters)"

        # Check format (alphanumeric + underscore + hyphen, per Reddit rules)
        if not AUTHOR_PATTERN.match(author):
            return False, None, "Invalid username (only letters, numbers, underscore, hyphen allowed)"

        return True, author, None

    def validate_score(self, score: Optional[int]) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        Validate minimum score filter.

        Args:
            score: Minimum score value

        Returns:
            Tuple of (is_valid, sanitized_score, error_message)
        """
        if score is None:
            return True, 0, None  # Default to 0

        # Type check
        if not isinstance(score, int):
            try:
                score = int(score)
            except (ValueError, TypeError):
                return False, None, "Score must be an integer"

        # Check range
        if score < MIN_SCORE_VALUE or score > MAX_SCORE_VALUE:
            return False, None, f"Score out of range ({MIN_SCORE_VALUE} to {MAX_SCORE_VALUE})"

        return True, score, None

    def validate_limit(self, limit: Optional[int]) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        Validate results limit (results per page).

        Args:
            limit: Number of results per page

        Returns:
            Tuple of (is_valid, sanitized_limit, error_message)
        """
        if limit is None:
            return True, 25, None  # Default to 25

        # Type check
        if not isinstance(limit, int):
            try:
                limit = int(limit)
            except (ValueError, TypeError):
                return False, None, "Limit must be an integer"

        # Check range
        if limit < MIN_LIMIT or limit > MAX_LIMIT:
            return False, None, f"Limit out of range ({MIN_LIMIT} to {MAX_LIMIT} results per page)"

        return True, limit, None

    def validate_offset(self, offset: Optional[int]) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        Validate pagination offset.

        Args:
            offset: Number of results to skip

        Returns:
            Tuple of (is_valid, sanitized_offset, error_message)
        """
        if offset is None:
            return True, 0, None  # Default to 0

        # Type check
        if not isinstance(offset, int):
            try:
                offset = int(offset)
            except (ValueError, TypeError):
                return False, None, "Offset must be an integer"

        # Check range (prevent deep pagination abuse)
        if offset < 0 or offset > MAX_OFFSET:
            return False, None, f"Offset out of range (0 to {MAX_OFFSET})"

        return True, offset, None

    def validate_page(self, page: Optional[int], limit: int = 25) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        Validate page number and convert to offset.

        Args:
            page: Page number (1-indexed)
            limit: Results per page

        Returns:
            Tuple of (is_valid, offset, error_message)
        """
        if page is None:
            return True, 0, None  # Default to page 1 (offset 0)

        # Type check
        if not isinstance(page, int):
            try:
                page = int(page)
            except (ValueError, TypeError):
                return False, None, "Page must be an integer"

        # Check range
        if page < 1:
            return False, None, "Page must be at least 1"

        if page > MAX_PAGE_NUMBER:
            return False, None, f"Page number too high (max {MAX_PAGE_NUMBER})"

        # Calculate offset
        offset = (page - 1) * limit

        # Check if resulting offset is within bounds
        if offset > MAX_OFFSET:
            return False, None, f"Page {page} exceeds maximum offset (try fewer results per page)"

        return True, offset, None

    def validate_result_type(self, result_type: Optional[str]) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validate result type filter.

        Args:
            result_type: Content type ('post', 'comment', or None)

        Returns:
            Tuple of (is_valid, sanitized_type, error_message)
        """
        if not result_type:
            return True, None, None  # Optional field

        result_type = result_type.strip().lower()

        # Check against whitelist
        valid_types = {'post', 'comment'}
        if result_type not in valid_types:
            return False, None, f"Invalid result type (must be 'post' or 'comment')"

        return True, result_type, None

    def validate_sort_by(self, sort_by: Optional[str]) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validate sort order.

        Args:
            sort_by: Sort field name

        Returns:
            Tuple of (is_valid, sanitized_sort, error_message)
        """
        if not sort_by:
            return True, 'rank', None  # Default to relevance

        sort_by = sort_by.strip().lower()

        # Check against whitelist
        valid_sorts = {'rank', 'relevance', 'score', 'date', 'created_utc', 'created_utc_asc',
                      'new', 'newest', 'old', 'oldest'}
        if sort_by not in valid_sorts:
            return False, None, f"Invalid sort option (must be one of: {', '.join(sorted(valid_sorts))})"

        return True, sort_by, None

    def validate_all(self, query: Optional[str] = None, subreddit: Optional[str] = None,
                    author: Optional[str] = None, min_score: Optional[int] = None,
                    limit: Optional[int] = None, offset: Optional[int] = None,
                    page: Optional[int] = None, result_type: Optional[str] = None,
                    sort_by: Optional[str] = None) -> ValidationResult:
        """
        Validate all search parameters comprehensively.

        Args:
            query: Optional search query text (required for search endpoints)
            subreddit: Optional subreddit filter
            author: Optional author filter
            min_score: Optional minimum score
            limit: Results per page
            offset: Pagination offset
            page: Page number (alternative to offset)
            result_type: Content type filter
            sort_by: Sort order

        Returns:
            ValidationResult with validation status and sanitized values
        """
        errors = []
        sanitized = {}

        # Validate query (optional for API list endpoints, required for search)
        if query is not None:
            valid, sanitized_query, error = self.validate_query(query)
            if not valid:
                errors.append(ValidationError('query', error))
            else:
                sanitized['query'] = sanitized_query

        # Validate subreddit (optional)
        valid, sanitized_sub, error = self.validate_subreddit(subreddit)
        if not valid:
            errors.append(ValidationError('subreddit', error))
        else:
            sanitized['subreddit'] = sanitized_sub

        # Validate author (optional)
        valid, sanitized_auth, error = self.validate_author(author)
        if not valid:
            errors.append(ValidationError('author', error))
        else:
            sanitized['author'] = sanitized_auth

        # Validate score (optional)
        valid, sanitized_score, error = self.validate_score(min_score)
        if not valid:
            errors.append(ValidationError('min_score', error))
        else:
            sanitized['min_score'] = sanitized_score

        # Validate limit (optional)
        valid, sanitized_limit, error = self.validate_limit(limit)
        if not valid:
            errors.append(ValidationError('limit', error))
        else:
            sanitized['limit'] = sanitized_limit

        # Validate page or offset (mutually exclusive)
        if page is not None:
            # Use page number to calculate offset
            valid, calculated_offset, error = self.validate_page(page, sanitized.get('limit', 25))
            if not valid:
                errors.append(ValidationError('page', error))
            else:
                sanitized['offset'] = calculated_offset
                sanitized['page'] = page
        else:
            # Use offset directly
            valid, sanitized_offset, error = self.validate_offset(offset)
            if not valid:
                errors.append(ValidationError('offset', error))
            else:
                sanitized['offset'] = sanitized_offset

        # Validate result_type (optional)
        valid, sanitized_type, error = self.validate_result_type(result_type)
        if not valid:
            errors.append(ValidationError('result_type', error))
        else:
            sanitized['result_type'] = sanitized_type

        # Validate sort_by (optional)
        valid, sanitized_sort, error = self.validate_sort_by(sort_by)
        if not valid:
            errors.append(ValidationError('sort_by', error))
        else:
            sanitized['sort_by'] = sanitized_sort

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            sanitized_values=sanitized
        )


# ============================================================================
# GLOBAL VALIDATOR INSTANCE
# ============================================================================

# Create global instance for easy import
validator = SearchInputValidator()


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def validate_search_params(query: str, **kwargs) -> ValidationResult:
    """
    Validate search parameters (convenience function).

    Args:
        query: Search query text
        **kwargs: Additional search parameters

    Returns:
        ValidationResult
    """
    return validator.validate_all(query, **kwargs)


def is_valid_subreddit(subreddit: str) -> bool:
    """Check if subreddit name is valid."""
    valid, _, _ = validator.validate_subreddit(subreddit)
    return valid


def is_valid_author(author: str) -> bool:
    """Check if author username is valid."""
    valid, _, _ = validator.validate_author(author)
    return valid


def sanitize_query(query: str) -> str:
    """
    Sanitize query string (convenience function).

    Args:
        query: Raw query string

    Returns:
        Sanitized query (or empty string if invalid)
    """
    valid, sanitized, _ = validator.validate_query(query)
    return sanitized if valid and sanitized else ''


# ============================================================================
# TEST MODULE
# ============================================================================

if __name__ == '__main__':
    """Test input validation with various inputs."""
    print("Input Validation Module Test")
    print("=" * 80)
    print()

    # Test cases: (value, expected_valid, field_name)
    test_cases = [
        # Query validation
        ("example concerns", True, "query"),
        ("a" * 500, True, "query (max length)"),
        ("a" * 501, False, "query (too long)"),
        ("", False, "query (empty)"),
        ("test\x00null", False, "query (null byte)"),

        # Subreddit validation
        ("technology", True, "subreddit"),
        ("Example", True, "subreddit (mixed case)"),
        ("ab", True, "subreddit (2 chars - min)"),
        ("a" * 21, True, "subreddit (21 chars - max)"),
        ("a", False, "subreddit (too short)"),
        ("a" * 22, False, "subreddit (too long)"),
        ("test-sub", False, "subreddit (invalid hyphen)"),
        ("test sub", False, "subreddit (invalid space)"),

        # Author validation
        ("danielmicay", True, "author"),
        ("User_Name-123", True, "author (valid chars)"),
        ("abc", True, "author (3 chars - min)"),
        ("a" * 20, True, "author (20 chars - max)"),
        ("ab", False, "author (too short)"),
        ("a" * 21, False, "author (too long)"),
        ("user@domain", False, "author (invalid @ symbol)"),

        # Score validation
        (0, True, "score (zero)"),
        (100, True, "score (positive)"),
        (-100, True, "score (negative)"),
        (2147483647, True, "score (max)"),
        (-2147483648, True, "score (min)"),
        (2147483648, False, "score (too high)"),

        # Limit validation
        (25, True, "limit (default)"),
        (10, True, "limit (min)"),
        (100, True, "limit (max)"),
        (9, False, "limit (too low)"),
        (101, False, "limit (too high)"),

        # Offset validation
        (0, True, "offset (zero)"),
        (5000, True, "offset (mid-range)"),
        (10000, True, "offset (max)"),
        (-1, False, "offset (negative)"),
        (10001, False, "offset (too high)"),
    ]

    print("Individual Field Validation Tests:")
    print("-" * 80)

    for value, expected_valid, description in test_cases:
        # Determine which validator to use based on description
        if "query" in description:
            valid, sanitized, error = validator.validate_query(value) if isinstance(value, str) else (False, None, "Wrong type")
        elif "subreddit" in description:
            valid, sanitized, error = validator.validate_subreddit(value) if isinstance(value, str) else (False, None, "Wrong type")
        elif "author" in description:
            valid, sanitized, error = validator.validate_author(value) if isinstance(value, str) else (False, None, "Wrong type")
        elif "score" in description:
            valid, sanitized, error = validator.validate_score(value)
        elif "limit" in description:
            valid, sanitized, error = validator.validate_limit(value)
        elif "offset" in description:
            valid, sanitized, error = validator.validate_offset(value)
        else:
            valid, sanitized, error = False, None, "Unknown test type"

        # Check if result matches expectation
        status = "✅ PASS" if valid == expected_valid else "❌ FAIL"

        print(f"{status} | {description}")
        if not valid and error:
            print(f"       Error: {error}")
        if valid and sanitized is not None and sanitized != value:
            print(f"       Sanitized: {repr(sanitized)}")

    print()
    print("=" * 80)
    print()

    # Test comprehensive validation
    print("Comprehensive Validation Tests:")
    print("-" * 80)

    comprehensive_tests = [
        {
            'name': 'Valid search query',
            'params': {'query': 'example', 'subreddit': 'technology', 'limit': 50},
            'expected_valid': True
        },
        {
            'name': 'Invalid long query',
            'params': {'query': 'a' * 501, 'subreddit': 'tech'},
            'expected_valid': False
        },
        {
            'name': 'Invalid subreddit format',
            'params': {'query': 'test', 'subreddit': 'test-sub'},
            'expected_valid': False
        },
        {
            'name': 'Invalid author length',
            'params': {'query': 'test', 'author': 'ab'},
            'expected_valid': False
        },
        {
            'name': 'Invalid limit range',
            'params': {'query': 'test', 'limit': 150},
            'expected_valid': False
        },
        {
            'name': 'Multiple validation errors',
            'params': {'query': '', 'subreddit': 'a', 'author': 'ab', 'limit': 200},
            'expected_valid': False
        },
    ]

    for test in comprehensive_tests:
        result = validator.validate_all(**test['params'])
        status = "✅ PASS" if result.is_valid == test['expected_valid'] else "❌ FAIL"

        print(f"{status} | {test['name']}")
        if not result.is_valid:
            for error in result.errors:
                print(f"       {error}")
        if result.is_valid and result.sanitized_values:
            print(f"       Sanitized: {result.sanitized_values}")

    print()
    print("=" * 80)
    print("All validation tests completed!")
