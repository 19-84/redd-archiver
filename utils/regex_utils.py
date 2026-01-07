#!/usr/bin/env python
"""
ABOUTME: Safe regex execution module with timeout protection against ReDoS attacks
ABOUTME: Wraps regex operations with timeout to prevent catastrophic backtracking
"""
import re
import signal
from typing import Optional, Pattern, Match
from contextlib import contextmanager

from .console_output import print_warning


class RegexTimeout(Exception):
    """Raised when regex execution exceeds timeout."""
    pass


class SafeRegex:
    """Wrapper for regex operations with timeout protection against ReDoS attacks."""

    def __init__(self, timeout_seconds: float = 0.1):
        """
        Initialize safe regex wrapper.

        Args:
            timeout_seconds: Maximum time allowed for regex execution (default: 0.1s)
        """
        self.timeout = timeout_seconds
        self._timeout_count = 0

    @contextmanager
    def _timeout_context(self):
        """
        Context manager for setting timeout alarm.

        Uses SIGALRM to interrupt long-running regex operations.
        """
        def timeout_handler(signum, frame):
            raise RegexTimeout("Regex execution timed out")

        # Set alarm signal
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.setitimer(signal.ITIMER_REAL, self.timeout)

        try:
            yield
        finally:
            # Reset alarm
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_handler)

    def search(self, pattern: str, text: str, flags: int = 0) -> Optional[Match]:
        """
        Execute regex search with timeout protection.

        Args:
            pattern: Regex pattern
            text: Text to search
            flags: Regex flags (e.g., re.IGNORECASE)

        Returns:
            Match object or None if no match or timeout
        """
        try:
            with self._timeout_context():
                return re.search(pattern, text, flags)
        except RegexTimeout:
            # Log timeout but don't crash - return None for no match
            self._timeout_count += 1
            print_warning(f"Regex timeout #{self._timeout_count} on pattern: {pattern[:50]}...")
            return None

    def sub(self, pattern: str, repl: str, text: str, flags: int = 0) -> str:
        """
        Execute regex substitution with timeout protection.

        Args:
            pattern: Regex pattern
            repl: Replacement string
            text: Text to process
            flags: Regex flags

        Returns:
            Modified text, or original if timeout
        """
        try:
            with self._timeout_context():
                return re.sub(pattern, repl, text, flags)
        except RegexTimeout:
            # Log timeout but don't crash - return original text
            self._timeout_count += 1
            print_warning(f"Regex timeout #{self._timeout_count} on substitution: {pattern[:50]}...")
            return text  # Return original text on timeout

    def findall(self, pattern: str, text: str, flags: int = 0) -> list:
        """
        Execute regex findall with timeout protection.

        Args:
            pattern: Regex pattern
            text: Text to search
            flags: Regex flags

        Returns:
            List of matches, or empty list if timeout
        """
        try:
            with self._timeout_context():
                return re.findall(pattern, text, flags)
        except RegexTimeout:
            # Log timeout but don't crash - return empty list
            self._timeout_count += 1
            print_warning(f"Regex timeout #{self._timeout_count} on findall: {pattern[:50]}...")
            return []

    def match(self, pattern: str, text: str, flags: int = 0) -> Optional[Match]:
        """
        Execute regex match with timeout protection.

        Args:
            pattern: Regex pattern
            text: Text to match from beginning
            flags: Regex flags

        Returns:
            Match object or None if no match or timeout
        """
        try:
            with self._timeout_context():
                return re.match(pattern, text, flags)
        except RegexTimeout:
            # Log timeout but don't crash - return None
            self._timeout_count += 1
            print_warning(f"Regex timeout #{self._timeout_count} on match: {pattern[:50]}...")
            return None

    def get_timeout_count(self) -> int:
        """
        Get number of regex timeouts that have occurred.

        Returns:
            Number of timeouts
        """
        return self._timeout_count

    def reset_timeout_count(self):
        """Reset timeout counter."""
        self._timeout_count = 0


# Global instance with sensible defaults (0.1 second timeout)
safe_regex = SafeRegex(timeout_seconds=0.1)


# Convenience functions for easy import
def search(pattern: str, text: str, flags: int = 0) -> Optional[Match]:
    """
    Safe regex search with timeout protection.

    Args:
        pattern: Regex pattern
        text: Text to search
        flags: Regex flags

    Returns:
        Match object or None
    """
    return safe_regex.search(pattern, text, flags)


def sub(pattern: str, repl: str, text: str, flags: int = 0) -> str:
    """
    Safe regex substitution with timeout protection.

    Args:
        pattern: Regex pattern
        repl: Replacement string
        text: Text to process
        flags: Regex flags

    Returns:
        Modified text
    """
    return safe_regex.sub(pattern, repl, text, flags)


def findall(pattern: str, text: str, flags: int = 0) -> list:
    """
    Safe regex findall with timeout protection.

    Args:
        pattern: Regex pattern
        text: Text to search
        flags: Regex flags

    Returns:
        List of matches
    """
    return safe_regex.findall(pattern, text, flags)


# Test module functionality
if __name__ == '__main__':
    """Test regex timeout protection with various patterns."""
    print("Safe Regex Module Test")
    print("=" * 80)
    print(f"Timeout configured: {safe_regex.timeout}s")
    print()

    # Test 1: Normal regex (should succeed)
    print("Test 1: Normal regex search")
    result = safe_regex.search(r'\bsub:(\w+)', 'hello sub:technology world', re.IGNORECASE)
    print(f"Pattern: \\bsub:(\\w+)")
    print(f"Text: 'hello sub:technology world'")
    print(f"Match: {result.group(0) if result else 'None'}")
    print()

    # Test 2: Normal substitution (should succeed)
    print("Test 2: Normal regex substitution")
    result = safe_regex.sub(r'\bsub:\w+', '', 'test sub:tech query', re.IGNORECASE)
    print(f"Pattern: \\bsub:\\w+")
    print(f"Text: 'test sub:tech query'")
    print(f"Result: '{result}'")
    print()

    # Test 3: Potentially slow regex (should timeout)
    print("Test 3: Potentially slow regex (catastrophic backtracking)")
    long_text = "sub:" + "a" * 10000 + "!"
    result = safe_regex.search(r'\b(?:sub|subreddit):(\w+)', long_text, re.IGNORECASE)
    print(f"Pattern: \\b(?:sub|subreddit):(\\w+)")
    print(f"Text: 'sub:' + 'a' * 10000 + '!'")
    print(f"Match: {result.group(0) if result else 'None (timeout)'}")
    print()

    # Test 4: Check timeout count
    print(f"Total timeouts encountered: {safe_regex.get_timeout_count()}")
    print()

    print("=" * 80)
    print("All tests completed!")
