#!/usr/bin/env python
"""
ABOUTME: Unit tests for Jinja2 custom filters
ABOUTME: Tests date formatting, number formatting, text truncation, and tooltip generation
"""

import pytest
from markupsafe import Markup

from html_modules.jinja_filters import (
    author_tooltip,
    date_tooltip,
    extract_domain,
    format_number,
    pluralize,
    reddit_date,
    register_filters,
    safe_int,
    score_tooltip,
    truncate_smart,
)

# =============================================================================
# REDDIT DATE FILTER TESTS
# =============================================================================


@pytest.mark.unit
class TestRedditDateFilter:
    """Tests for reddit_date filter."""

    def test_valid_timestamp(self):
        """Test formatting valid Unix timestamp."""
        # 2021-01-01 00:00:00 UTC
        result = reddit_date(1609459200)

        assert "01" in result  # Day
        assert "Jan" in result  # Month
        assert "2021" in result  # Year

    def test_custom_format(self):
        """Test custom format string."""
        result = reddit_date(1609459200, "%Y-%m-%d")

        assert result == "2021-01-01"

    def test_float_timestamp(self):
        """Test float timestamp is converted."""
        result = reddit_date(1609459200.5, "%Y-%m-%d")

        assert result == "2021-01-01"

    def test_string_timestamp(self):
        """Test string timestamp is converted."""
        result = reddit_date("1609459200", "%Y-%m-%d")

        assert result == "2021-01-01"

    def test_invalid_timestamp_returns_unknown(self):
        """Test invalid timestamp returns 'Unknown date'."""
        result = reddit_date("not_a_number")

        assert result == "Unknown date"

    def test_none_timestamp_returns_unknown(self):
        """Test None timestamp returns 'Unknown date'."""
        result = reddit_date(None)

        assert result == "Unknown date"

    def test_caching_same_result(self):
        """Test same timestamp returns cached result."""
        result1 = reddit_date(1609459200, "%Y-%m-%d")
        result2 = reddit_date(1609459200, "%Y-%m-%d")

        assert result1 == result2


# =============================================================================
# DATE TOOLTIP FILTER TESTS
# =============================================================================


@pytest.mark.unit
class TestDateTooltipFilter:
    """Tests for date_tooltip filter."""

    def test_valid_timestamp(self):
        """Test tooltip for valid timestamp."""
        result = date_tooltip(1609459200)

        assert "title=" in str(result)
        assert "Posted:" in str(result)
        assert "2021" in str(result)
        assert "UTC" in str(result)

    def test_returns_markup(self):
        """Test result is Markup (safe HTML)."""
        result = date_tooltip(1609459200)

        assert isinstance(result, Markup)

    def test_invalid_timestamp_returns_empty(self):
        """Test invalid timestamp returns empty string."""
        result = date_tooltip("invalid")

        assert result == ""

    def test_none_returns_empty(self):
        """Test None returns empty string."""
        result = date_tooltip(None)

        assert result == ""


# =============================================================================
# FORMAT NUMBER FILTER TESTS
# =============================================================================


@pytest.mark.unit
class TestFormatNumberFilter:
    """Tests for format_number filter."""

    def test_small_number(self):
        """Test formatting small number."""
        result = format_number(123)

        assert result == "123"

    def test_thousands_separator(self):
        """Test thousands separator is added."""
        result = format_number(1234)

        assert result == "1,234"

    def test_large_number(self):
        """Test large number formatting."""
        result = format_number(1234567890)

        assert result == "1,234,567,890"

    def test_float_truncated(self):
        """Test float is truncated to integer."""
        result = format_number(1234.56)

        assert result == "1,234"

    def test_string_number(self):
        """Test string number is converted."""
        result = format_number("1234567")

        assert result == "1,234,567"

    def test_invalid_returns_original(self):
        """Test invalid value returns original string."""
        result = format_number("not_a_number")

        assert result == "not_a_number"

    def test_zero(self):
        """Test zero formatting."""
        result = format_number(0)

        assert result == "0"

    def test_negative_number(self):
        """Test negative number formatting."""
        result = format_number(-1234)

        assert result == "-1,234"


# =============================================================================
# TRUNCATE SMART FILTER TESTS
# =============================================================================


@pytest.mark.unit
class TestTruncateSmartFilter:
    """Tests for truncate_smart filter."""

    def test_short_text_unchanged(self):
        """Test short text is returned unchanged."""
        result = truncate_smart("Short text", 100)

        assert result == "Short text"

    def test_long_text_truncated(self):
        """Test long text is truncated."""
        text = "This is a very long text that should be truncated at a word boundary"
        result = truncate_smart(text, 30)

        assert len(result) < len(text)
        assert result.endswith("...")

    def test_truncates_at_word_boundary(self):
        """Test truncation happens at word boundary."""
        text = "Word1 Word2 Word3 Word4 Word5"
        result = truncate_smart(text, 15)

        # Should not cut in the middle of a word
        assert not result.endswith("d...")  # Not "Word..." mid-word

    def test_custom_suffix(self):
        """Test custom suffix."""
        text = "This is a long text"
        result = truncate_smart(text, 10, ">>>")

        assert result.endswith(">>>")

    def test_empty_text(self):
        """Test empty text returns empty."""
        result = truncate_smart("", 100)

        assert result == ""

    def test_none_text(self):
        """Test None returns None."""
        result = truncate_smart(None, 100)

        assert result is None

    def test_exact_length(self):
        """Test text at exact length is not truncated."""
        text = "Exactly 20 chars!!"
        result = truncate_smart(text, len(text))

        assert result == text


# =============================================================================
# SAFE INT FILTER TESTS
# =============================================================================


@pytest.mark.unit
class TestSafeIntFilter:
    """Tests for safe_int filter."""

    def test_valid_int(self):
        """Test valid integer is returned."""
        result = safe_int(42)

        assert result == 42

    def test_float_converted(self):
        """Test float is converted to int."""
        result = safe_int(42.7)

        assert result == 42

    def test_string_converted(self):
        """Test string number is converted."""
        result = safe_int("42")

        assert result == 42

    def test_invalid_returns_default(self):
        """Test invalid value returns default."""
        result = safe_int("not_a_number")

        assert result == 0

    def test_custom_default(self):
        """Test custom default value."""
        result = safe_int("invalid", default=-1)

        assert result == -1

    def test_none_returns_default(self):
        """Test None returns default."""
        result = safe_int(None)

        assert result == 0


# =============================================================================
# PLURALIZE FILTER TESTS
# =============================================================================


@pytest.mark.unit
class TestPluralizeFilter:
    """Tests for pluralize filter."""

    def test_singular(self):
        """Test singular (count = 1)."""
        result = pluralize(1)

        assert result == ""

    def test_plural(self):
        """Test plural (count > 1)."""
        result = pluralize(5)

        assert result == "s"

    def test_zero_is_plural(self):
        """Test zero is treated as plural."""
        result = pluralize(0)

        assert result == "s"

    def test_custom_singular(self):
        """Test custom singular suffix."""
        result = pluralize(1, singular="y", plural="ies")

        assert result == "y"

    def test_custom_plural(self):
        """Test custom plural suffix."""
        result = pluralize(5, singular="y", plural="ies")

        assert result == "ies"

    def test_invalid_value_returns_plural(self):
        """Test invalid value returns plural suffix."""
        result = pluralize("invalid")

        assert result == "s"


# =============================================================================
# EXTRACT DOMAIN FILTER TESTS
# =============================================================================


@pytest.mark.unit
class TestExtractDomainFilter:
    """Tests for extract_domain filter."""

    def test_simple_url(self):
        """Test simple URL domain extraction."""
        result = extract_domain("https://example.com/path")

        assert result == "example.com"

    def test_url_with_www(self):
        """Test www prefix is removed."""
        result = extract_domain("https://www.example.com/path")

        assert result == "example.com"

    def test_url_with_port(self):
        """Test URL with port."""
        result = extract_domain("https://example.com:8080/path")

        assert "example.com" in result

    def test_url_with_subdomain(self):
        """Test subdomain is preserved."""
        result = extract_domain("https://blog.example.com/path")

        assert result == "blog.example.com"

    def test_invalid_url_returns_original(self):
        """Test invalid URL returns original."""
        result = extract_domain("not_a_url")

        assert result == "not_a_url"


# =============================================================================
# SCORE TOOLTIP FILTER TESTS
# =============================================================================


@pytest.mark.unit
class TestScoreTooltipFilter:
    """Tests for score_tooltip filter."""

    def test_basic_score(self):
        """Test basic score tooltip."""
        post = {"score": 1234}
        result = score_tooltip(post)

        assert "title=" in str(result)
        assert "Score:" in str(result)
        assert "1,234" in str(result)

    def test_score_with_upvote_ratio(self):
        """Test score with upvote ratio."""
        post = {"score": 100, "upvote_ratio": 0.85}
        result = score_tooltip(post)

        assert "85% upvoted" in str(result)

    def test_returns_markup(self):
        """Test returns safe Markup."""
        post = {"score": 100}
        result = score_tooltip(post)

        assert isinstance(result, Markup)

    def test_missing_score(self):
        """Test missing score defaults to 0."""
        post = {}
        result = score_tooltip(post)

        assert "Score: 0" in str(result)


# =============================================================================
# AUTHOR TOOLTIP FILTER TESTS
# =============================================================================


@pytest.mark.unit
class TestAuthorTooltipFilter:
    """Tests for author_tooltip filter."""

    def test_with_account_age(self):
        """Test author tooltip with account age."""
        post = {"author": "testuser", "author_created_utc": 1577836800}  # 2020-01-01
        result = author_tooltip(post)

        assert "title=" in str(result)
        assert "Redditor since" in str(result)
        assert "2020-01-01" in str(result)

    def test_without_account_age(self):
        """Test author tooltip without account age."""
        post = {"author": "testuser"}
        result = author_tooltip(post)

        assert result == Markup("")

    def test_returns_markup(self):
        """Test returns safe Markup."""
        post = {"author": "testuser", "author_created_utc": 1577836800}
        result = author_tooltip(post)

        assert isinstance(result, Markup)


# =============================================================================
# REGISTER FILTERS TESTS
# =============================================================================


@pytest.mark.unit
class TestRegisterFilters:
    """Tests for register_filters function."""

    def test_registers_all_filters(self):
        """Test all filters are registered."""
        from unittest.mock import MagicMock

        mock_env = MagicMock()
        mock_env.filters = {}

        register_filters(mock_env)

        expected_filters = [
            "reddit_date",
            "date_tooltip",
            "format_number",
            "truncate_smart",
            "score_class",
            "score_class_global",
            "safe_int",
            "score_tooltip",
            "author_tooltip",
            "pluralize",
            "extract_domain",
        ]

        for filter_name in expected_filters:
            assert filter_name in mock_env.filters


# =============================================================================
# CACHING TESTS
# =============================================================================


@pytest.mark.unit
class TestCaching:
    """Tests for filter caching behavior."""

    def test_reddit_date_cache_hit(self):
        """Test reddit_date cache hit."""
        from html_modules.jinja_filters import _reddit_date_cached

        # Clear cache for fresh test
        _reddit_date_cached.cache_clear()

        # First call
        result1 = reddit_date(1609459200, "%Y-%m-%d")
        info_after_first = _reddit_date_cached.cache_info()

        # Second call (should hit cache)
        result2 = reddit_date(1609459200, "%Y-%m-%d")
        info_after_second = _reddit_date_cached.cache_info()

        assert result1 == result2
        assert info_after_second.hits > info_after_first.hits

    def test_date_tooltip_cache_hit(self):
        """Test date_tooltip cache hit."""
        from html_modules.jinja_filters import _date_tooltip_cached

        _date_tooltip_cached.cache_clear()

        result1 = date_tooltip(1609459200)
        info_after_first = _date_tooltip_cached.cache_info()

        result2 = date_tooltip(1609459200)
        info_after_second = _date_tooltip_cached.cache_info()

        assert str(result1) == str(result2)
        assert info_after_second.hits > info_after_first.hits
