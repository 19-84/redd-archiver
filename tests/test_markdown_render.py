#!/usr/bin/env python
"""
ABOUTME: Unit tests for Reddit markdown rendering + sanitization (Feature 6)
ABOUTME: Covers link conversion, markdown formatting, and XSS sanitization
"""

from utils.markdown_render import render_reddit_markdown


class TestEmptyInput:
    def test_none_returns_empty(self):
        assert render_reddit_markdown(None) == ""

    def test_empty_string_returns_empty(self):
        assert render_reddit_markdown("") == ""

    def test_whitespace_only_returns_empty(self):
        assert render_reddit_markdown("   \n\t ") == ""


class TestMarkdownFormatting:
    def test_bold_and_italic(self):
        html = render_reddit_markdown("**bold** and *italic*")
        assert "<strong>bold</strong>" in html
        assert "<em>italic</em>" in html

    def test_lists(self):
        html = render_reddit_markdown("- one\n- two")
        assert "<ul>" in html
        assert "<li>one</li>" in html

    def test_explicit_link_preserved(self):
        html = render_reddit_markdown("[example](https://example.com)")
        assert '<a href="https://example.com">example</a>' in html


class TestRedditReferences:
    def test_subreddit_ref_becomes_link(self):
        html = render_reddit_markdown("see r/privacy for details")
        assert 'href="https://www.reddit.com/r/privacy"' in html
        assert ">r/privacy</a>" in html

    def test_leading_slash_subreddit_ref(self):
        html = render_reddit_markdown("check /r/linux out")
        assert 'href="https://www.reddit.com/r/linux"' in html

    def test_user_ref_becomes_link(self):
        html = render_reddit_markdown("ping u/spez please")
        assert 'href="https://www.reddit.com/user/spez"' in html
        assert ">u/spez</a>" in html

    def test_user_long_form_ref(self):
        html = render_reddit_markdown("see /user/example_user here")
        assert 'href="https://www.reddit.com/user/example_user"' in html

    def test_ref_inside_url_not_rewritten(self):
        # A path segment inside an existing URL must not be double-linked.
        html = render_reddit_markdown("[link](https://other.example/r/foo)")
        assert "www.reddit.com/r/foo" not in html
        assert 'href="https://other.example/r/foo"' in html


class TestSanitization:
    def test_script_tag_stripped(self):
        html = render_reddit_markdown("hello <script>alert('xss')</script> world")
        # The <script> element is removed entirely; any leftover inner text is
        # inert (escaped) and cannot execute. The security property is "no
        # script element", not "no occurrence of the string".
        assert "<script" not in html.lower()

    def test_event_handler_attribute_stripped(self):
        html = render_reddit_markdown('<img src="x" onerror="alert(1)">')
        assert "onerror" not in html

    def test_javascript_protocol_link_neutralized(self):
        html = render_reddit_markdown("[click](javascript:alert(1))")
        assert "javascript:" not in html

    def test_iframe_stripped(self):
        html = render_reddit_markdown('<iframe src="https://evil.example"></iframe>')
        assert "<iframe" not in html

    def test_style_tag_stripped(self):
        html = render_reddit_markdown("<style>body{display:none}</style>text")
        assert "<style>" not in html

    def test_safe_image_kept(self):
        html = render_reddit_markdown("![alt](https://i.redd.it/abc.png)")
        assert "<img" in html
        assert 'src="https://i.redd.it/abc.png"' in html
