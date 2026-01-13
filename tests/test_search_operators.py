#!/usr/bin/env python
"""
ABOUTME: Unit tests for Google-style search operator parsing
ABOUTME: Tests query parsing, XSS prevention, and ReDoS protection
"""

import pytest

from utils.search_operators import (
    ParsedSearchQuery,
    format_search_breadcrumb,
    get_search_tips,
    parse_search_operators,
)

# =============================================================================
# BASIC QUERY PARSING TESTS
# =============================================================================


@pytest.mark.unit
class TestParseSearchOperatorsBasic:
    """Tests for basic query parsing without operators."""

    def test_plain_query_no_operators(self):
        """Test plain query with no operators."""
        result = parse_search_operators("simple search query")

        assert result.query_text == "simple search query"
        assert result.subreddit is None
        assert result.author is None
        assert result.min_score == 0
        assert result.result_type is None
        assert result.sort_by is None

    def test_empty_query(self):
        """Test empty query returns empty result."""
        result = parse_search_operators("")

        assert result.query_text == ""
        assert result.subreddit is None

    def test_whitespace_only_query(self):
        """Test whitespace-only query returns empty result."""
        result = parse_search_operators("   ")

        assert result.query_text == ""

    def test_quoted_phrase_preserved(self):
        """Test quoted phrases are preserved."""
        result = parse_search_operators('"exact phrase" other words')

        assert '"exact phrase"' in result.query_text
        assert "other words" in result.query_text

    def test_boolean_or_preserved(self):
        """Test OR boolean operator is preserved."""
        result = parse_search_operators("word1 OR word2")

        assert result.query_text == "word1 OR word2"

    def test_exclude_operator_preserved(self):
        """Test exclusion operator is preserved."""
        result = parse_search_operators("include -exclude")

        assert result.query_text == "include -exclude"


# =============================================================================
# SUBREDDIT OPERATOR TESTS
# =============================================================================


@pytest.mark.unit
class TestSubredditOperator:
    """Tests for sub: and subreddit: operators."""

    def test_sub_operator_lowercase(self):
        """Test sub: operator with lowercase."""
        result = parse_search_operators("query sub:technology")

        assert result.query_text == "query"
        assert result.subreddit == "technology"

    def test_subreddit_operator_full(self):
        """Test subreddit: operator (full form)."""
        result = parse_search_operators("query subreddit:privacy")

        assert result.query_text == "query"
        assert result.subreddit == "privacy"

    def test_sub_operator_case_insensitive(self):
        """Test SUB: operator works (case insensitive)."""
        result = parse_search_operators("query SUB:AskReddit")

        assert result.subreddit == "AskReddit"

    def test_sub_operator_mixed_case_value(self):
        """Test subreddit value preserves case."""
        result = parse_search_operators("query sub:AskReddit")

        assert result.subreddit == "AskReddit"

    def test_sub_operator_at_start(self):
        """Test sub: operator at start of query."""
        result = parse_search_operators("sub:technology query words")

        assert result.query_text == "query words"
        assert result.subreddit == "technology"

    def test_sub_operator_with_underscore(self):
        """Test sub: with underscore in name."""
        result = parse_search_operators("query sub:ask_reddit")

        assert result.subreddit == "ask_reddit"

    def test_sub_operator_with_numbers(self):
        """Test sub: with numbers in name."""
        result = parse_search_operators("query sub:tech123")

        assert result.subreddit == "tech123"


# =============================================================================
# AUTHOR OPERATOR TESTS
# =============================================================================


@pytest.mark.unit
class TestAuthorOperator:
    """Tests for author: and user: operators."""

    def test_author_operator(self):
        """Test author: operator."""
        result = parse_search_operators("query author:testuser")

        assert result.query_text == "query"
        assert result.author == "testuser"

    def test_user_operator(self):
        """Test user: operator (alias)."""
        result = parse_search_operators("query user:testuser")

        assert result.author == "testuser"

    def test_author_operator_case_insensitive(self):
        """Test AUTHOR: operator works (case insensitive)."""
        result = parse_search_operators("query AUTHOR:TestUser")

        assert result.author == "TestUser"

    def test_author_with_underscore(self):
        """Test author: with underscore in name."""
        result = parse_search_operators("query author:test_user")

        assert result.author == "test_user"

    def test_author_with_numbers(self):
        """Test author: with numbers in name."""
        result = parse_search_operators("query author:user123")

        assert result.author == "user123"


# =============================================================================
# SCORE OPERATOR TESTS
# =============================================================================


@pytest.mark.unit
class TestScoreOperator:
    """Tests for score: operator."""

    def test_score_operator_basic(self):
        """Test score:10 operator."""
        result = parse_search_operators("query score:10")

        assert result.query_text == "query"
        assert result.min_score == 10

    def test_score_operator_plus_suffix(self):
        """Test score:10+ operator."""
        result = parse_search_operators("query score:10+")

        assert result.min_score == 10

    def test_score_operator_greater_than(self):
        """Test score:>10 operator."""
        result = parse_search_operators("query score:>10")

        assert result.min_score == 10

    def test_score_operator_case_insensitive(self):
        """Test SCORE: operator works."""
        result = parse_search_operators("query SCORE:50+")

        assert result.min_score == 50

    def test_score_operator_large_value(self):
        """Test score: with large value."""
        result = parse_search_operators("query score:1000")

        assert result.min_score == 1000


# =============================================================================
# TYPE OPERATOR TESTS
# =============================================================================


@pytest.mark.unit
class TestTypeOperator:
    """Tests for type: operator."""

    def test_type_operator_post(self):
        """Test type:post operator."""
        result = parse_search_operators("query type:post")

        assert result.query_text == "query"
        assert result.result_type == "post"

    def test_type_operator_comment(self):
        """Test type:comment operator."""
        result = parse_search_operators("query type:comment")

        assert result.result_type == "comment"

    def test_type_operator_case_insensitive(self):
        """Test TYPE:POST operator works."""
        result = parse_search_operators("query TYPE:POST")

        assert result.result_type == "post"


# =============================================================================
# SORT OPERATOR TESTS
# =============================================================================


@pytest.mark.unit
class TestSortOperator:
    """Tests for sort: operator."""

    def test_sort_operator_rank(self):
        """Test sort:rank operator."""
        result = parse_search_operators("query sort:rank")

        assert result.query_text == "query"
        assert result.sort_by == "rank"

    def test_sort_operator_relevance(self):
        """Test sort:relevance operator (maps to rank)."""
        result = parse_search_operators("query sort:relevance")

        assert result.sort_by == "rank"

    def test_sort_operator_score(self):
        """Test sort:score operator."""
        result = parse_search_operators("query sort:score")

        assert result.sort_by == "score"

    def test_sort_operator_date(self):
        """Test sort:date operator."""
        result = parse_search_operators("query sort:date")

        assert result.sort_by == "created_utc"

    def test_sort_operator_new(self):
        """Test sort:new operator."""
        result = parse_search_operators("query sort:new")

        assert result.sort_by == "created_utc"

    def test_sort_operator_newest(self):
        """Test sort:newest operator."""
        result = parse_search_operators("query sort:newest")

        assert result.sort_by == "created_utc"

    def test_sort_operator_old(self):
        """Test sort:old operator."""
        result = parse_search_operators("query sort:old")

        assert result.sort_by == "created_utc_asc"

    def test_sort_operator_oldest(self):
        """Test sort:oldest operator."""
        result = parse_search_operators("query sort:oldest")

        assert result.sort_by == "created_utc_asc"

    def test_sort_operator_case_insensitive(self):
        """Test SORT:SCORE operator works."""
        result = parse_search_operators("query SORT:SCORE")

        assert result.sort_by == "score"


# =============================================================================
# COMBINED OPERATORS TESTS
# =============================================================================


@pytest.mark.unit
class TestCombinedOperators:
    """Tests for multiple operators combined."""

    def test_all_operators_combined(self):
        """Test all operators used together."""
        result = parse_search_operators("search term sub:technology author:user123 score:50+ type:post sort:score")

        assert result.query_text == "search term"
        assert result.subreddit == "technology"
        assert result.author == "user123"
        assert result.min_score == 50
        assert result.result_type == "post"
        assert result.sort_by == "score"

    def test_operators_with_quoted_phrase(self):
        """Test operators with quoted phrase in query."""
        result = parse_search_operators('"security update" OR patch sub:technology score:10+')

        assert '"security update" OR patch' in result.query_text
        assert result.subreddit == "technology"
        assert result.min_score == 10

    def test_operators_in_any_order(self):
        """Test operators can appear in any order."""
        result = parse_search_operators("score:100 author:test sub:tech query words type:post")

        assert "query words" in result.query_text
        assert result.subreddit == "tech"
        assert result.author == "test"
        assert result.min_score == 100
        assert result.result_type == "post"

    def test_extra_whitespace_cleaned(self):
        """Test extra whitespace is cleaned after operator removal."""
        result = parse_search_operators("query   sub:tech   author:user   words")

        assert result.query_text == "query words"


# =============================================================================
# REDOS PROTECTION TESTS
# =============================================================================


@pytest.mark.unit
class TestReDoSProtection:
    """Tests for ReDoS protection (query length limits)."""

    def test_query_length_limit_enforced(self):
        """Test very long queries are truncated."""
        long_query = "a" * 1000
        result = parse_search_operators(long_query)

        # Query should be truncated to 500 chars
        assert len(result.query_text) <= 500

    def test_long_query_with_operators(self):
        """Test long query with operators still parses correctly."""
        long_query = "a" * 450 + " sub:technology"
        result = parse_search_operators(long_query)

        # Should still extract subreddit even after truncation
        # (operator is near the end, within 500 char limit)
        assert result.subreddit == "technology"


# =============================================================================
# BREADCRUMB FORMATTING TESTS
# =============================================================================


@pytest.mark.unit
class TestFormatSearchBreadcrumb:
    """Tests for breadcrumb formatting with XSS prevention."""

    def test_basic_breadcrumb(self):
        """Test basic breadcrumb formatting."""
        parsed = ParsedSearchQuery(query_text="test query")
        breadcrumb = format_search_breadcrumb(parsed)

        assert "Searching for test query" in breadcrumb
        assert "in all communities" in breadcrumb

    def test_breadcrumb_with_subreddit(self):
        """Test breadcrumb with subreddit filter."""
        parsed = ParsedSearchQuery(query_text="test", subreddit="technology")
        breadcrumb = format_search_breadcrumb(parsed)

        assert "in technology" in breadcrumb

    def test_breadcrumb_with_author(self):
        """Test breadcrumb with author filter."""
        parsed = ParsedSearchQuery(query_text="test", author="testuser")
        breadcrumb = format_search_breadcrumb(parsed)

        assert "by u/testuser" in breadcrumb

    def test_breadcrumb_with_type(self):
        """Test breadcrumb with result type filter."""
        parsed = ParsedSearchQuery(query_text="test", result_type="post")
        breadcrumb = format_search_breadcrumb(parsed)

        assert "(posts only)" in breadcrumb

    def test_breadcrumb_with_score(self):
        """Test breadcrumb with score filter."""
        parsed = ParsedSearchQuery(query_text="test", min_score=100)
        breadcrumb = format_search_breadcrumb(parsed)

        assert "(score 100+)" in breadcrumb

    def test_breadcrumb_with_sort(self):
        """Test breadcrumb with sort order."""
        parsed = ParsedSearchQuery(query_text="test", sort_by="score")
        breadcrumb = format_search_breadcrumb(parsed)

        assert "sorted by score" in breadcrumb

    def test_xss_prevention_query(self):
        """Test XSS is prevented in query text."""
        parsed = ParsedSearchQuery(query_text="<script>alert('xss')</script>")
        breadcrumb = format_search_breadcrumb(parsed)

        assert "<script>" not in breadcrumb
        assert "&lt;script&gt;" in breadcrumb

    def test_xss_prevention_subreddit(self):
        """Test XSS is prevented in subreddit name."""
        parsed = ParsedSearchQuery(query_text="test", subreddit="<img onerror='xss'>")
        breadcrumb = format_search_breadcrumb(parsed)

        assert "<img" not in breadcrumb
        assert "&lt;img" in breadcrumb

    def test_xss_prevention_author(self):
        """Test XSS is prevented in author name."""
        parsed = ParsedSearchQuery(query_text="test", author="<script>")
        breadcrumb = format_search_breadcrumb(parsed)

        assert "<script>" not in breadcrumb
        assert "&lt;script&gt;" in breadcrumb

    def test_empty_query_breadcrumb(self):
        """Test breadcrumb with empty query."""
        parsed = ParsedSearchQuery(query_text="")
        breadcrumb = format_search_breadcrumb(parsed)

        assert "Searching" in breadcrumb


# =============================================================================
# PARSED SEARCH QUERY TESTS
# =============================================================================


@pytest.mark.unit
class TestParsedSearchQuery:
    """Tests for ParsedSearchQuery dataclass."""

    def test_str_representation(self):
        """Test string representation."""
        parsed = ParsedSearchQuery(
            query_text="test", subreddit="tech", author="user", min_score=10, result_type="post", sort_by="score"
        )

        str_repr = str(parsed)
        assert 'query="test"' in str_repr
        assert "sub:tech" in str_repr
        assert "author:user" in str_repr
        assert "score:10+" in str_repr
        assert "type:post" in str_repr
        assert "sort:score" in str_repr

    def test_default_values(self):
        """Test default values."""
        parsed = ParsedSearchQuery(query_text="test")

        assert parsed.subreddit is None
        assert parsed.author is None
        assert parsed.min_score == 0
        assert parsed.result_type is None
        assert parsed.sort_by is None


# =============================================================================
# SEARCH TIPS TESTS
# =============================================================================


@pytest.mark.unit
class TestGetSearchTips:
    """Tests for search tips HTML generation."""

    def test_search_tips_returns_html(self):
        """Test search tips returns HTML string."""
        tips = get_search_tips()

        assert isinstance(tips, str)
        assert '<div class="search-tips">' in tips

    def test_search_tips_contains_operators(self):
        """Test search tips documents all operators."""
        tips = get_search_tips()

        assert "sub:" in tips
        assert "author:" in tips
        assert "score:" in tips
        assert "type:" in tips
        assert "sort:" in tips

    def test_search_tips_contains_boolean_logic(self):
        """Test search tips documents boolean logic."""
        tips = get_search_tips()

        assert "OR" in tips
        assert "-exclude" in tips or "-" in tips
        assert "quoted" in tips.lower()


# =============================================================================
# EDGE CASES
# =============================================================================


@pytest.mark.unit
class TestEdgeCases:
    """Tests for edge cases and unusual inputs."""

    def test_operator_at_end(self):
        """Test operator at very end of query."""
        result = parse_search_operators("query words sub:tech")

        assert result.query_text == "query words"
        assert result.subreddit == "tech"

    def test_only_operator_no_query(self):
        """Test query with only operator, no search text."""
        result = parse_search_operators("sub:technology")

        assert result.query_text == ""
        assert result.subreddit == "technology"

    def test_multiple_same_operators(self):
        """Test multiple same operators (first wins)."""
        result = parse_search_operators("query sub:first sub:second")

        # First match should be extracted
        assert result.subreddit == "first"

    def test_operator_like_text_without_colon(self):
        """Test operator-like text without colon is preserved."""
        result = parse_search_operators("subscribe to technology")

        assert "subscribe" in result.query_text
        assert result.subreddit is None

    def test_colon_in_query_not_operator(self):
        """Test colon in query that's not an operator."""
        result = parse_search_operators("time: 10:30")

        # Should preserve non-operator colons
        assert "10:30" in result.query_text or "time" in result.query_text
