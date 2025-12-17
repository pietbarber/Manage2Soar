"""
Security utility functions for the Manage2Soar application.

This module provides helper functions for common security operations
like URL validation, input sanitization, and safe redirects.
"""

from django.utils.http import url_has_allowed_host_and_scheme


def is_safe_redirect_url(url: str | None, request=None) -> bool:
    """
    Check if a URL is safe to redirect to.

    A safe URL is one that:
    1. Is a relative path (no scheme or host)
    2. Points to the same host as the request (if provided)

    Args:
        url: The URL to check
        request: Optional Django request object to get allowed hosts from

    Returns:
        True if the URL is safe to redirect to, False otherwise
    """
    if not url:
        return False

    # Get allowed hosts from request or use None (same host only)
    allowed_hosts = None
    if request and hasattr(request, "get_host"):
        try:
            allowed_hosts = {request.get_host()}
        except Exception:
            # Silently handle any errors getting host (request may be mocked or incomplete)
            pass

    return url_has_allowed_host_and_scheme(url, allowed_hosts=allowed_hosts)


def get_safe_redirect_url(url: str | None, default: str = "/", request=None) -> str:
    """
    Get a safe redirect URL, falling back to a default if the URL is unsafe.

    Args:
        url: The URL to check
        default: The default URL to use if the provided URL is unsafe
        request: Optional Django request object for host validation

    Returns:
        The original URL if safe, otherwise the default URL
    """
    if is_safe_redirect_url(url, request):
        return url  # type: ignore[return-value]
    return default


def sanitize_exception_message(exception: Exception) -> str:
    """
    Sanitize an exception message for safe display to users.

    This prevents exposing sensitive internal information like file paths,
    database queries, or stack traces in error responses.

    Args:
        exception: The exception to sanitize

    Returns:
        A generic error message safe for user display
    """
    # Map of known safe exception types to their user-facing messages
    safe_exceptions = {
        "ValidationError": "Validation failed. Please check your input.",
        "PermissionDenied": "You don't have permission to perform this action.",
        "ObjectDoesNotExist": "The requested resource was not found.",
        "IntegrityError": "A database constraint was violated.",
    }

    exception_type = type(exception).__name__

    if exception_type in safe_exceptions:
        return safe_exceptions[exception_type]

    # For all other exceptions, return a generic message
    # The actual exception is already logged, so we don't lose information
    return "An unexpected error occurred. Please try again."
