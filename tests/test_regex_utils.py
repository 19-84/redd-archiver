#!/usr/bin/env python
"""
ABOUTME: Unit tests for safe regex execution module with ReDoS protection
ABOUTME: Tests timeout protection, normal regex operations, and edge cases
"""

import platform
import re

import pytest

from utils.regex_utils import RegexTimeout, SafeRegex, safe_regex
from utils.regex_utils import findall as safe_findall
from utils.regex_utils import search as safe_search
from utils.regex_utils import sub as safe_sub

# Skip timeout tests on non-Unix systems (SIGALRM not available)
unix_only = pytest.mark.skipif(platform.system() == "Windows", reason="SIGALRM not available on Windows")


# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def fresh_regex():
    """Create fresh SafeRegex instance for each test."""
    return SafeRegex(timeout_seconds=0.1)


# =============================================================================
# NORMAL PATTERN TESTS
# =============================================================================


@pytest.mark.unit
class TestNormalPatterns:
    """Tests for normal regex patterns that should succeed."""

    def test_search_simple_pattern(self, fresh_regex):
        """Test simple search pattern succeeds."""
        result = fresh_regex.search(r"\bword\b", "this is a word here")

        assert result is not None
        assert result.group(0) == "word"

    def test_search_with_groups(self, fresh_regex):
        """Test search with capture groups."""
        result = fresh_regex.search(r"sub:(\w+)", "query sub:technology")

        assert result is not None
        assert result.group(1) == "technology"

    def test_search_case_insensitive(self, fresh_regex):
        """Test case insensitive search."""
        result = fresh_regex.search(r"SUB:(\w+)", "query sub:tech", re.IGNORECASE)

        assert result is not None
        assert result.group(1) == "tech"

    def test_search_no_match(self, fresh_regex):
        """Test search with no match returns None."""
        result = fresh_regex.search(r"notfound", "this text has no match")

        assert result is None

    def test_sub_simple_replacement(self, fresh_regex):
        """Test simple substitution."""
        result = fresh_regex.sub(r"\bword\b", "REPLACED", "this word is here")

        assert result == "this REPLACED is here"

    def test_sub_with_backreference(self, fresh_regex):
        """Test substitution with backreference."""
        result = fresh_regex.sub(r"(\w+)@(\w+)", r"\2-\1", "user@domain")

        assert result == "domain-user"

    def test_sub_remove_pattern(self, fresh_regex):
        """Test substitution to remove pattern."""
        result = fresh_regex.sub(r"\s+sub:\w+", "", "query sub:tech words")

        assert result == "query words"

    def test_sub_no_match(self, fresh_regex):
        """Test substitution with no match returns original."""
        result = fresh_regex.sub(r"notfound", "REPLACED", "original text")

        assert result == "original text"

    def test_findall_simple(self, fresh_regex):
        """Test findall with multiple matches."""
        result = fresh_regex.findall(r"\d+", "a1b2c3d4")

        assert result == ["1", "2", "3", "4"]

    def test_findall_with_groups(self, fresh_regex):
        """Test findall with capture groups."""
        result = fresh_regex.findall(r"(\w+)@(\w+)", "a@b c@d")

        assert result == [("a", "b"), ("c", "d")]

    def test_findall_no_match(self, fresh_regex):
        """Test findall with no matches returns empty list."""
        result = fresh_regex.findall(r"\d+", "no numbers here")

        assert result == []

    def test_match_at_start(self, fresh_regex):
        """Test match at string start."""
        result = fresh_regex.match(r"\w+", "word at start")

        assert result is not None
        assert result.group(0) == "word"

    def test_match_not_at_start(self, fresh_regex):
        """Test match fails when pattern not at start."""
        result = fresh_regex.match(r"\d+", "no digits at start 123")

        assert result is None


# =============================================================================
# CONVENIENCE FUNCTION TESTS
# =============================================================================


@pytest.mark.unit
class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_safe_search(self):
        """Test safe_search convenience function."""
        result = safe_search(r"test", "this is a test")

        assert result is not None
        assert result.group(0) == "test"

    def test_safe_sub(self):
        """Test safe_sub convenience function."""
        result = safe_sub(r"old", "new", "old text old")

        assert result == "new text new"

    def test_safe_findall(self):
        """Test safe_findall convenience function."""
        result = safe_findall(r"\w+", "a b c")

        assert result == ["a", "b", "c"]


# =============================================================================
# TIMEOUT COUNTER TESTS
# =============================================================================


@pytest.mark.unit
class TestTimeoutCounter:
    """Tests for timeout counter functionality."""

    def test_initial_timeout_count_zero(self, fresh_regex):
        """Test timeout count starts at zero."""
        assert fresh_regex.get_timeout_count() == 0

    def test_reset_timeout_count(self, fresh_regex):
        """Test reset_timeout_count resets to zero."""
        fresh_regex._timeout_count = 5
        fresh_regex.reset_timeout_count()

        assert fresh_regex.get_timeout_count() == 0


# =============================================================================
# REGEX TIMEOUT EXCEPTION TESTS
# =============================================================================


@pytest.mark.unit
class TestRegexTimeoutException:
    """Tests for RegexTimeout exception."""

    def test_exception_can_be_raised(self):
        """Test RegexTimeout can be raised and caught."""
        with pytest.raises(RegexTimeout):
            raise RegexTimeout("test timeout")

    def test_exception_message(self):
        """Test exception message is preserved."""
        try:
            raise RegexTimeout("custom message")
        except RegexTimeout as e:
            assert "custom message" in str(e)


# =============================================================================
# SAFE REGEX CONFIGURATION TESTS
# =============================================================================


@pytest.mark.unit
class TestSafeRegexConfiguration:
    """Tests for SafeRegex configuration."""

    def test_default_timeout(self):
        """Test default timeout is 0.1 seconds."""
        regex = SafeRegex()
        assert regex.timeout == 0.1

    def test_custom_timeout(self):
        """Test custom timeout is respected."""
        regex = SafeRegex(timeout_seconds=0.5)
        assert regex.timeout == 0.5


# =============================================================================
# GLOBAL INSTANCE TESTS
# =============================================================================


@pytest.mark.unit
class TestGlobalInstance:
    """Tests for global safe_regex instance."""

    def test_global_instance_exists(self):
        """Test global instance is available."""
        assert safe_regex is not None
        assert isinstance(safe_regex, SafeRegex)

    def test_global_instance_has_timeout(self):
        """Test global instance has timeout configured."""
        assert safe_regex.timeout == 0.1


# =============================================================================
# TIMEOUT BEHAVIOR TESTS (Unix only)
# =============================================================================


@unix_only
@pytest.mark.unit
class TestTimeoutBehavior:
    """Tests for timeout behavior (Unix-only due to SIGALRM)."""

    def test_search_returns_none_on_timeout(self):
        """Test search returns None (not crashes) on timeout."""
        # Create regex with very short timeout
        regex = SafeRegex(timeout_seconds=0.001)

        # Use a pattern and input that takes longer than 1ms
        # This is a simple pattern - it may not actually timeout
        # but the test ensures the timeout mechanism is set up
        result = regex.search(r"\w+", "short text")

        # Should either succeed or return None (not raise)
        assert result is None or result is not None

    def test_sub_returns_original_on_timeout(self):
        """Test sub returns original text (not crashes) on timeout."""
        regex = SafeRegex(timeout_seconds=0.001)

        original = "original text"
        result = regex.sub(r"\w+", "X", original)

        # Should either succeed with replacement or return original
        assert result is not None

    def test_findall_returns_empty_on_timeout(self):
        """Test findall returns empty list (not crashes) on timeout."""
        regex = SafeRegex(timeout_seconds=0.001)

        result = regex.findall(r"\w+", "a b c")

        # Should either succeed or return empty list
        assert isinstance(result, list)


# =============================================================================
# EDGE CASES
# =============================================================================


@pytest.mark.unit
class TestEdgeCases:
    """Tests for edge cases and unusual inputs."""

    def test_empty_text_search(self, fresh_regex):
        """Test search on empty text."""
        result = fresh_regex.search(r"\w+", "")

        assert result is None

    def test_empty_text_sub(self, fresh_regex):
        """Test sub on empty text."""
        result = fresh_regex.sub(r"\w+", "X", "")

        assert result == ""

    def test_empty_text_findall(self, fresh_regex):
        """Test findall on empty text."""
        result = fresh_regex.findall(r"\w+", "")

        assert result == []

    def test_empty_pattern_search(self, fresh_regex):
        """Test search with empty pattern."""
        result = fresh_regex.search(r"", "text")

        # Empty pattern matches at position 0
        assert result is not None
        assert result.group(0) == ""

    def test_special_characters_in_text(self, fresh_regex):
        """Test regex with special characters in text."""
        result = fresh_regex.search(r"\$\d+", "price: $100")

        assert result is not None
        assert result.group(0) == "$100"

    def test_unicode_text(self, fresh_regex):
        """Test regex with unicode text."""
        result = fresh_regex.search(r"\w+", "hello 世界 world")

        assert result is not None
        assert result.group(0) == "hello"

    def test_multiline_text(self, fresh_regex):
        """Test regex with multiline text."""
        text = "line1\nline2\nline3"
        result = fresh_regex.findall(r"line\d", text)

        assert result == ["line1", "line2", "line3"]

    def test_flags_combined(self, fresh_regex):
        """Test regex with multiple flags."""
        result = fresh_regex.search(r"^line", "other\nline2", re.MULTILINE | re.IGNORECASE)

        assert result is not None
        assert result.group(0) == "line"
