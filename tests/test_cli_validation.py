#!/usr/bin/env python
"""
ABOUTME: Unit tests for reddarc CLI argument validation helpers
ABOUTME: Covers which run modes require --comments-file/--submissions-file
"""

import argparse

import pytest

from reddarc import _import_needs_source_files


def _args(**overrides) -> argparse.Namespace:
    """Build an args namespace with all mode flags off, then apply overrides."""
    base = {
        "export_from_database": False,
        "enrich": None,
        "enrich_metadata": None,
        "enrich_rules": None,
        "enrich_wikis": None,
        "enrich_voat": None,
        "voat_thumbnails": None,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


@pytest.mark.unit
class TestImportNeedsSourceFiles:
    """A community filter only requires source files for a real import."""

    def test_plain_import_requires_files(self):
        # No export/enrich flag set: a normal import reads the source files.
        assert _import_needs_source_files(_args()) is True

    def test_export_from_database_does_not_require_files(self):
        # Regression: `--export-from-database --subverse x` used to demand
        # --comments-file/--submissions-file even though it renders from the DB.
        assert _import_needs_source_files(_args(export_from_database=True)) is False

    @pytest.mark.parametrize(
        "flag",
        ["enrich", "enrich_metadata", "enrich_rules", "enrich_wikis", "enrich_voat", "voat_thumbnails"],
    )
    def test_enrich_modes_do_not_require_files(self, flag):
        # Enrichment reads metadata dumps / the DB, not the comments/submissions files.
        assert _import_needs_source_files(_args(**{flag: "/some/path"})) is False

    def test_enrich_chained_with_export_still_does_not_require_files(self):
        assert _import_needs_source_files(_args(enrich_voat="/p", export_from_database=True)) is False
