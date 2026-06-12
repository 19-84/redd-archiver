#!/usr/bin/env python
"""
ABOUTME: Tests for the design token system in redd-archiver-universal.css (Feature 4 Phase 1)
ABOUTME: Enforces dark/light token parity and structural sanity of the stylesheet
"""

import re
from pathlib import Path

import pytest

CSS_PATH = Path(__file__).parent.parent / "static" / "css" / "redd-archiver-universal.css"

# Referenced in the original stylesheet but never defined; the resulting
# "invalid at computed-value time -> unset" behavior is intentional-by-history.
KNOWN_UNDEFINED = {"--text-link"}


@pytest.fixture(scope="module")
def css():
    return CSS_PATH.read_text(encoding="utf-8")


def _block_tokens(css, header_re):
    """Custom-property declarations inside the first block whose selector matches."""
    m = re.search(header_re + r"\s*\{([^}]*)\}", css, re.S)
    assert m, f"block not found: {header_re}"
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", m.group(1)))


@pytest.mark.unit
class TestDesignTokens:
    def test_braces_balanced(self, css):
        stripped = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        assert stripped.count("{") == stripped.count("}")

    def test_dark_light_token_parity(self, css):
        """Every design token has both a dark (:root) and a light (toggle) value."""
        # the design-token :root block follows the Feature 4 Phase 1 banner
        banner = css.index("DESIGN TOKENS")
        dark = _block_tokens(css[banner:], r":root")
        light = _block_tokens(
            css, r"#dark-theme-toggle:checked\s*~\s*body,\s*\n#dark-theme-toggle:checked\s*~\s*\.site-content"
        )
        assert dark, "no design tokens found"
        # every dark token needs a light value; the light block may additionally
        # override variables defined in the ORIGINAL :root (e.g. --comment-depth-*)
        only_dark = set(dark) - set(light)
        assert not only_dark, f"tokens missing a light value: {sorted(only_dark)}"
        defined_anywhere = set(re.findall(r"(--[\w-]+)\s*:", css))
        unknown_light = {t for t in set(light) - set(dark) if t not in defined_anywhere}
        assert not unknown_light, f"light-only tokens never defined in :root: {sorted(unknown_light)}"

    def test_system_preference_block_matches_toggle(self, css):
        """The prefers-color-scheme light block must define the same tokens as the toggle (F4 Phase 2)."""
        toggle = _block_tokens(
            css, r"#dark-theme-toggle:checked\s*~\s*body,\s*\n#dark-theme-toggle:checked\s*~\s*\.site-content"
        )
        media_at = css.index("SYSTEM COLOR-SCHEME SUPPORT")
        media = _block_tokens(css[media_at:], r":root")
        assert media == toggle, (
            f"media-light tokens diverge from toggle: only-toggle={sorted(set(toggle) - set(media))}, "
            f"only-media={sorted(set(media) - set(toggle))}"
        )

    def test_all_var_references_defined(self, css):
        defined = set(re.findall(r"(--[\w-]+)\s*:", css))
        used = set(re.findall(r"var\((--[\w-]+)[,)]", css))
        undefined = used - defined - KNOWN_UNDEFINED
        assert not undefined, f"vars used but never defined: {sorted(undefined)}"

    def test_no_new_known_undefined(self, css):
        """KNOWN_UNDEFINED entries must stay genuinely undefined (else remove them here)."""
        defined = set(re.findall(r"(--[\w-]+)\s*:", css))
        assert not (KNOWN_UNDEFINED & defined)
