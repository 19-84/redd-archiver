#!/usr/bin/env python
"""
ABOUTME: Tests for the theme palette system (Feature 4 Phases 3-4)
ABOUTME: Covers palette derivation, CSS token injection, accent override, and CSS<->Python anti-drift
"""

import re
from pathlib import Path

import pytest

from html_modules.theme_data import BASE_PALETTE, DEFAULT_DARK, DEFAULT_LIGHT
from html_modules.themes import (
    THEME_NAMES,
    THEMES,
    apply_theme_to_css,
    build_palette,
    render_inline_theme_css,
    validate_accent_color,
)

CSS_PATH = Path(__file__).parent.parent / "static" / "css" / "redd-archiver-universal.css"

TOGGLE_HEADER = r"#dark-theme-toggle:checked\s*~\s*body,\s*\n#dark-theme-toggle:checked\s*~\s*\.site-content"


@pytest.fixture(scope="module")
def css():
    return CSS_PATH.read_text(encoding="utf-8")


def _block_tokens(css, header_re):
    m = re.search(header_re + r"\s*\{([^}]*)\}", css, re.S)
    assert m, f"block not found: {header_re}"
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", m.group(1)))


@pytest.mark.unit
class TestPalettes:
    def test_theme_names(self):
        assert set(THEME_NAMES) == {
            "default",
            "sepia",
            "high-contrast",
            "nord",
            "solarized",
            "dracula",
            "gruvbox",
            "cyberpunk",
            "midnight",
            "old-reddit",
            "phosphor",
        }

    def test_palette_structure(self):
        """Every theme covers the full default token set; extras only re-skin BASE_PALETTE vars."""
        for name, palette in THEMES.items():
            assert set(palette) == {"dark", "light"}, name
            assert set(DEFAULT_DARK) <= set(palette["dark"]), name
            assert set(DEFAULT_LIGHT) <= set(palette["light"]), name
            assert set(palette["dark"]) - set(DEFAULT_DARK) <= set(BASE_PALETTE), name
            assert set(palette["light"]) - set(DEFAULT_LIGHT) <= set(BASE_PALETTE), name

    def test_default_is_verbatim(self):
        assert THEMES["default"]["dark"] == DEFAULT_DARK
        assert THEMES["default"]["light"] == DEFAULT_LIGHT

    def test_css_python_anti_drift(self, css):
        """theme_data.py must stay in sync with the stylesheet's three token sources."""
        assert _block_tokens(css, r":root") == BASE_PALETTE
        assert _block_tokens(css[css.index("DESIGN TOKENS") :], r":root") == DEFAULT_DARK
        assert _block_tokens(css, TOGGLE_HEADER) == DEFAULT_LIGHT

    def test_spec_anchor_colors(self):
        """Anchor values from roadmap/04-visual-themes.md's palette matrix."""
        sepia = THEMES["sepia"]
        assert sepia["dark"]["--body-text"] == "#e8dcc8"
        assert "#2c2416" in sepia["dark"]["--body-bg"]
        assert sepia["light"]["--body-text"] == "#3d3425"
        assert "#f5f0e8" in sepia["light"]["--body-bg"]
        hc = THEMES["high-contrast"]
        assert hc["dark"]["--body-bg"] == "#000000"
        assert hc["dark"]["--body-text"] == "#ffffff"
        assert hc["light"]["--body-bg"] == "#ffffff"
        assert hc["light"]["--body-text"] == "#000000"

    def test_sepia_rehues_accent_family_only(self):
        sepia = THEMES["sepia"]["dark"]
        # blue accent family is re-hued
        assert sepia["--alert-heading-text"] != DEFAULT_DARK["--alert-heading-text"]
        assert sepia["--gradient-primary"] != BASE_PALETTE["--gradient-primary"]
        # semantic greens/reds/ambers pass through untouched
        for token in ("--mod-badge-text", "--admin-badge-text", "--locked-icon-text", "--gilded-icon-text"):
            assert sepia[token] == DEFAULT_DARK[token], token

    def test_high_contrast_accent_snaps(self):
        hc = THEMES["high-contrast"]
        assert hc["dark"]["--alert-heading-text"] == "#ffff00"
        assert hc["light"]["--card-title-a-text"] == "#0000cc"

    def test_alpha_preserved_through_transform(self):
        # rgba(59, 130, 246, 0.1) re-hued for sepia keeps its alpha channel
        assert THEMES["sepia"]["dark"]["--deep-marker-bg"].endswith(", 0.1)")

    def test_unknown_theme_raises(self):
        with pytest.raises(ValueError, match="unknown theme"):
            build_palette("vaporwave")

    def test_new_theme_reference_anchors(self):
        """Each palette pins its reference colors (nordtheme.com, solarized, etc.)."""
        anchors = {
            "nord": {"dark": {"--body-text": "#d8dee9"}, "light": {"--body-text": "#2e3440"}},
            "solarized": {"dark": {"--body-text": "#93a1a1"}, "light": {"--body-text": "#657b83"}},
            "dracula": {"dark": {"--body-text": "#f8f8f2"}, "light": {"--body-text": "#282a36"}},
            "gruvbox": {"dark": {"--body-text": "#ebdbb2"}, "light": {"--body-text": "#3c3836"}},
            "cyberpunk": {"dark": {"--body-text": "#d6f6ff"}, "light": {"--body-text": "#1a1025"}},
            "midnight": {"dark": {"--body-bg": "#000000", "--body-text": "#d4d4d8"}, "light": {}},
            "old-reddit": {
                "dark": {"--body-bg": "#1a1a1b", "--body-text": "#d7dadc"},
                "light": {"--body-bg": "#ffffff", "--body-text": "#1a1a1b"},
            },
            "phosphor": {"dark": {"--body-bg": "#000000", "--body-text": "#33ff33"}, "light": {}},
        }
        for theme, modes in anchors.items():
            palette = THEMES[theme]
            for mode, tokens in modes.items():
                for key, value in tokens.items():
                    assert palette[mode][key] == value, f"{theme}/{mode} {key}"

    def test_new_themes_preserve_semantic_colors(self):
        """Greens/reds/ambers (badges, vote colors) survive every theme transform."""
        for theme in ("nord", "solarized", "dracula", "gruvbox", "cyberpunk", "midnight", "old-reddit", "phosphor"):
            palette = THEMES[theme]
            for mode in ("dark", "light"):
                for key in ("--mod-badge-text", "--admin-badge-text", "--gilded-icon-text"):
                    assert palette[mode][key] == THEMES["default"][mode][key], f"{theme}/{mode} {key}"

    def test_midnight_light_mode_is_default(self):
        """OLED midnight only changes dark mode; light stays stock."""
        assert THEMES["midnight"]["light"] == THEMES["default"]["light"]

    def test_midnight_crushes_dark_surfaces(self):
        """Surface ladder approaches true black; accents are untouched."""
        midnight_dark = THEMES["midnight"]["dark"]
        # the comment-depth surface ramp (BASE_PALETTE) rides along darker
        assert midnight_dark["--comment-depth-0"] != BASE_PALETTE["--comment-depth-0"]
        # bright accents stay stock
        assert midnight_dark["--links-title-hover-text"] == DEFAULT_DARK["--links-title-hover-text"]


@pytest.mark.unit
class TestAccentColor:
    def test_validate_normalizes(self):
        assert validate_accent_color("#AbCdEf") == "#abcdef"
        assert validate_accent_color("8b6914") == "#8b6914"
        assert validate_accent_color("#f00") == "#ff0000"

    @pytest.mark.parametrize("bad", ["", "#12345", "#gggggg", "red", "#1234567"])
    def test_validate_rejects(self, bad):
        with pytest.raises(ValueError):
            validate_accent_color(bad)

    def test_accent_rotates_accent_family_only(self):
        palette = build_palette("default", "#ff0000")
        assert palette["dark"]["--alert-heading-text"] != DEFAULT_DARK["--alert-heading-text"]
        assert palette["dark"]["--mod-badge-text"] == DEFAULT_DARK["--mod-badge-text"]
        # lightness/saturation ladders are preserved: only the hue moves
        assert palette["dark"]["--alert-heading-text"] == "#fa6060"  # from #60a5fa

    def test_accent_applies_to_theme_pins(self):
        # sepia's pinned body text sits in the sepia accent band, so it follows the override
        palette = build_palette("sepia", "#ff0000")
        assert palette["dark"]["--body-text"] != THEMES["sepia"]["dark"]["--body-text"]


@pytest.mark.unit
class TestCssInjection:
    def test_default_injection_is_idempotent(self, css):
        out = apply_theme_to_css(css, "default")
        assert apply_theme_to_css(out, "default") == out
        # token content identical to source (comments inside blocks are dropped)
        assert _block_tokens(out[out.index("DESIGN TOKENS") :], r":root") == DEFAULT_DARK
        assert _block_tokens(out, TOGGLE_HEADER) == DEFAULT_LIGHT

    def test_sepia_injection(self, css):
        out = apply_theme_to_css(css, "sepia")
        sepia = THEMES["sepia"]
        assert _block_tokens(out[out.index("DESIGN TOKENS") :], r":root") == sepia["dark"]
        assert _block_tokens(out, TOGGLE_HEADER) == sepia["light"]
        assert _block_tokens(out[out.index("SYSTEM COLOR-SCHEME SUPPORT") :], r":root") == sepia["light"]
        # original :root palette and structural rules are untouched
        assert _block_tokens(out, r":root") == BASE_PALETTE
        assert "Light-structural rules" in out

    def test_injection_keeps_css_balanced(self, css):
        for theme in THEME_NAMES:
            out = apply_theme_to_css(css, theme)
            stripped = re.sub(r"/\*.*?\*/", "", out, flags=re.S)
            assert stripped.count("{") == stripped.count("}"), theme

    def test_inline_css_empty_for_default(self):
        assert render_inline_theme_css() == ""
        assert render_inline_theme_css("default", None) == ""

    def test_inline_css_structure(self):
        inline = render_inline_theme_css("sepia")
        assert inline.startswith(":root {")
        assert "@media (prefers-color-scheme: light)" in inline
        assert "#dark-theme-toggle:checked ~ body" in inline
        assert "--body-text: #e8dcc8;" in inline

    def test_inline_css_for_accent_only(self):
        inline = render_inline_theme_css("default", "#ff0000")
        assert "--alert-heading-text: #fa6060;" in inline
