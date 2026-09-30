#!/usr/bin/env python
"""
ABOUTME: Naive-UTC replacements for the deprecated datetime.utcnow() / utcfromtimestamp()
ABOUTME: Same values as before, so comparisons with other naive datetimes keep working
"""

from datetime import datetime, timezone


def utc_from_timestamp(timestamp: float) -> datetime:
    """Naive UTC datetime for a Unix timestamp (drop-in for ``datetime.utcfromtimestamp``)."""
    return datetime.fromtimestamp(timestamp, timezone.utc).replace(tzinfo=None)


def utc_now() -> datetime:
    """Current naive UTC datetime (drop-in for ``datetime.utcnow``)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
