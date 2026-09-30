#!/usr/bin/env python
"""
ABOUTME: Tests for naive-UTC datetime helpers replacing deprecated utcnow/utcfromtimestamp
ABOUTME: Pins exact equivalence so rendered dates and naive comparisons are unchanged
"""

import warnings
from datetime import datetime, timedelta

import pytest

from utils.time_utils import utc_from_timestamp, utc_now


@pytest.mark.unit
class TestUtcFromTimestamp:
    @pytest.mark.parametrize("ts", [0, 1, 1_134_028_003, 1_700_000_000, 1_700_000_000.75, -86_400])
    def test_matches_deprecated_utcfromtimestamp(self, ts):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            expected = datetime.utcfromtimestamp(ts)

        assert utc_from_timestamp(ts) == expected

    def test_is_naive(self):
        assert utc_from_timestamp(1_700_000_000).tzinfo is None

    def test_comparable_with_naive_datetimes(self):
        """html_statistics mixes these with naive datetime(1970, 1, 1) in min/max."""
        assert max(datetime(1970, 1, 1), utc_from_timestamp(1_700_000_000)).year == 2023

    def test_emits_no_deprecation_warning(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            utc_from_timestamp(1_700_000_000)


@pytest.mark.unit
class TestUtcNow:
    def test_is_naive_and_close_to_deprecated_utcnow(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            expected = datetime.utcnow()

        now = utc_now()
        assert now.tzinfo is None
        assert abs(now - expected) < timedelta(seconds=5)

    def test_isoformat_has_no_offset(self):
        """API timestamps append 'Z' to isoformat(); an offset would yield '+00:00Z'."""
        assert "+" not in utc_now().isoformat()
