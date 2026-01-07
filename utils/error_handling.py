#!/usr/bin/env python
"""
ABOUTME: Safe error handling module for production - prevents information disclosure
ABOUTME: Logs detailed errors internally while showing generic messages to users
"""
import os
import logging
from typing import Optional

# Configure logging
logger = logging.getLogger(__name__)

class SafeErrorHandler:
    """Handles errors safely by showing generic messages in production."""

    def __init__(self):
        """Initialize error handler with environment detection."""
        self.is_production = os.getenv('FLASK_ENV', 'production') == 'production'

    def format_user_error(self, exception: Exception, context: str = '') -> str:
        """
        Format error message safe for user display.

        In production mode, returns generic error messages to prevent information
        disclosure. In development mode, returns detailed error messages for debugging.

        Args:
            exception: The exception that occurred
            context: Context about where error occurred (e.g., "search", "query")

        Returns:
            Safe error message for user display
        """
        # Log full exception details internally (with stack trace)
        logger.error(
            f"Error in {context}: {type(exception).__name__}: {str(exception)}",
            exc_info=True,
            extra={
                'context': context,
                'exception_type': type(exception).__name__,
                'exception_message': str(exception)
            }
        )

        if self.is_production:
            # Generic messages for production (no internal details)
            return self._get_generic_message(exception, context)
        else:
            # Detailed messages for development
            return f"{context.title()} error: {str(exception)}"

    def _get_generic_message(self, exception: Exception, context: str) -> str:
        """
        Get generic error message based on exception type.

        Args:
            exception: The exception that occurred
            context: Error context

        Returns:
            User-friendly generic error message
        """
        # Import here to avoid circular dependencies
        import psycopg

        # Map exception types to generic messages
        if isinstance(exception, psycopg.OperationalError):
            return 'The search service is temporarily unavailable. Please try again in a few moments.'

        elif isinstance(exception, psycopg.Error):
            return 'A database error occurred. Please try a different search query.'

        elif isinstance(exception, (ValueError, TypeError)):
            return 'Invalid search parameters. Please check your search query and try again.'

        elif isinstance(exception, TimeoutError):
            return 'Your search request timed out. Please try a simpler query.'

        else:
            # Fallback generic message for unknown errors
            error_messages = {
                'search': 'Your search could not be completed. Please try again.',
                'query': 'Invalid search query. Please check your search terms.',
                'database': 'A service error occurred. Please try again later.',
                'connection': 'Connection error. Please try again.',
            }
            return error_messages.get(context, 'An error occurred. Please try again.')

    def is_safe_to_display(self, message: str) -> bool:
        """
        Check if an error message is safe to display to users.

        Detects messages that might contain sensitive information like:
        - File paths
        - Database connection strings
        - Stack traces
        - Internal implementation details

        Args:
            message: Error message to check

        Returns:
            True if message is safe to display, False otherwise
        """
        # Patterns that indicate sensitive information
        sensitive_patterns = [
            '/var/', '/usr/', '/home/',  # File paths
            'postgresql://', 'password=', 'host=',  # Connection strings
            'Traceback', 'File "', 'line ',  # Stack traces
            'psycopg', 'sqlalchemy',  # Database internals
            'at 0x',  # Memory addresses
        ]

        message_lower = message.lower()
        for pattern in sensitive_patterns:
            if pattern.lower() in message_lower:
                return False

        return True

    def sanitize_error_message(self, message: str) -> str:
        """
        Sanitize an error message by removing sensitive information.

        Args:
            message: Raw error message

        Returns:
            Sanitized error message
        """
        if not self.is_safe_to_display(message):
            return "An error occurred. Please contact support if this persists."

        # Truncate very long messages
        max_length = 200
        if len(message) > max_length:
            message = message[:max_length] + '...'

        return message


# Global instance for easy import
error_handler = SafeErrorHandler()


# Convenience functions
def format_user_error(exception: Exception, context: str = '') -> str:
    """
    Format exception for user display (convenience function).

    Args:
        exception: The exception that occurred
        context: Context about where error occurred

    Returns:
        Safe error message
    """
    return error_handler.format_user_error(exception, context)


def is_production() -> bool:
    """Check if running in production mode."""
    return error_handler.is_production


def sanitize_message(message: str) -> str:
    """
    Sanitize error message (convenience function).

    Args:
        message: Raw error message

    Returns:
        Sanitized message
    """
    return error_handler.sanitize_error_message(message)


if __name__ == '__main__':
    """Test error handling with various exception types."""
    import psycopg

    print("Error Handling Module Test")
    print("=" * 80)
    print(f"Production mode: {is_production()}")
    print()

    # Test cases
    test_exceptions = [
        (psycopg.OperationalError("connection failed"), "database"),
        (ValueError("invalid query format"), "query"),
        (TimeoutError("query timeout"), "search"),
        (Exception("unknown error"), "general"),
    ]

    for exc, ctx in test_exceptions:
        formatted = format_user_error(exc, ctx)
        print(f"Exception: {type(exc).__name__}")
        print(f"Context: {ctx}")
        print(f"User Message: {formatted}")
        print()

    # Test message sanitization
    print("Message Sanitization Tests:")
    print("-" * 80)

    test_messages = [
        "Simple error message",
        "Error in /var/lib/postgresql/data",
        "postgresql://user:pass@localhost:5432/db",
        "Traceback (most recent call last):",
    ]

    for msg in test_messages:
        safe = is_safe_to_display(msg)
        sanitized = sanitize_message(msg)
        print(f"Original: {msg[:50]}...")
        print(f"Safe: {safe}")
        print(f"Sanitized: {sanitized}")
        print()

    print("=" * 80)
    print("All tests completed!")
