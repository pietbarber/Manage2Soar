"""
Tests for security utility functions.
"""

import pytest
from django.http import HttpRequest
from django.test import RequestFactory

from utils.security import (
    get_safe_redirect_url,
    is_safe_redirect_url,
    sanitize_exception_message,
)


@pytest.fixture
def request_factory():
    return RequestFactory()


@pytest.fixture
def mock_request(request_factory):
    """Create a mock request with testserver as host."""
    request = request_factory.get("/")
    request.META["HTTP_HOST"] = "testserver"
    return request


class TestIsSafeRedirectUrl:
    """Tests for is_safe_redirect_url function."""

    def test_none_url_returns_false(self):
        """None URL should return False."""
        assert is_safe_redirect_url(None) is False

    def test_empty_string_returns_false(self):
        """Empty string URL should return False."""
        assert is_safe_redirect_url("") is False

    def test_relative_path_is_safe(self):
        """Relative paths should be safe."""
        assert is_safe_redirect_url("/dashboard") is True
        assert is_safe_redirect_url("/members/profile") is True
        assert is_safe_redirect_url("/") is True

    def test_absolute_url_same_host_is_safe(self, mock_request):
        """Absolute URL with same host should be safe."""
        assert is_safe_redirect_url("http://testserver/dashboard", mock_request) is True
        assert (
            is_safe_redirect_url("https://testserver/dashboard", mock_request) is True
        )

    def test_absolute_url_different_host_is_unsafe(self, mock_request):
        """Absolute URL with different host should be unsafe."""
        assert is_safe_redirect_url("http://evil.com/phishing", mock_request) is False
        assert is_safe_redirect_url("https://evil.com/phishing", mock_request) is False

    def test_javascript_protocol_is_unsafe(self):
        """JavaScript protocol should be unsafe."""
        assert is_safe_redirect_url("javascript:alert(1)") is False

    def test_data_protocol_is_unsafe(self):
        """Data protocol should be unsafe."""
        assert is_safe_redirect_url("data:text/html,<script>alert(1)</script>") is False

    def test_protocol_relative_url_without_request(self):
        """Protocol-relative URL without request should be handled safely."""
        # Without request, these should be rejected as we can't verify the host
        assert is_safe_redirect_url("//evil.com/phishing") is False

    def test_url_with_double_slash_attack(self):
        """URL with double slash (protocol bypass) should be handled."""
        # These are potential XSS vectors
        assert is_safe_redirect_url("//evil.com") is False
        assert is_safe_redirect_url("///evil.com") is False

    def test_no_request_object_rejects_absolute_urls(self):
        """Without request object, absolute URLs should be rejected."""
        assert is_safe_redirect_url("http://testserver/dashboard") is False
        assert is_safe_redirect_url("https://testserver/dashboard") is False

    def test_request_without_get_host_method(self):
        """Request without get_host method should handle gracefully."""
        request = object()  # Object without get_host
        assert is_safe_redirect_url("/dashboard", request) is True
        assert is_safe_redirect_url("http://evil.com", request) is False


class TestGetSafeRedirectUrl:
    """Tests for get_safe_redirect_url function."""

    def test_safe_url_returns_original(self):
        """Safe URL should return the original URL."""
        assert get_safe_redirect_url("/dashboard") == "/dashboard"
        assert get_safe_redirect_url("/members/profile") == "/members/profile"

    def test_unsafe_url_returns_default(self):
        """Unsafe URL should return the default."""
        assert get_safe_redirect_url("http://evil.com/phishing") == "/"
        assert get_safe_redirect_url("javascript:alert(1)") == "/"

    def test_custom_default_is_used(self):
        """Custom default should be used for unsafe URLs."""
        assert get_safe_redirect_url("http://evil.com", default="/login") == "/login"
        assert get_safe_redirect_url("javascript:alert(1)", default="/home") == "/home"

    def test_none_url_returns_default(self):
        """None URL should return default."""
        assert get_safe_redirect_url(None) == "/"
        assert get_safe_redirect_url(None, default="/home") == "/home"

    def test_empty_string_returns_default(self):
        """Empty string should return default."""
        assert get_safe_redirect_url("") == "/"
        assert get_safe_redirect_url("", default="/home") == "/home"

    def test_safe_url_with_request_object(self, mock_request):
        """Safe URL with request should work correctly."""
        assert (
            get_safe_redirect_url("http://testserver/dashboard", request=mock_request)
            == "http://testserver/dashboard"
        )
        assert get_safe_redirect_url("/dashboard", request=mock_request) == "/dashboard"

    def test_unsafe_url_with_request_object(self, mock_request):
        """Unsafe URL with request should return default."""
        assert get_safe_redirect_url("http://evil.com", request=mock_request) == "/"


class TestSanitizeExceptionMessage:
    """Tests for sanitize_exception_message function."""

    def test_validation_error_message(self):
        """ValidationError should return user-friendly message."""
        from django.core.exceptions import ValidationError

        exc = ValidationError("Invalid input")
        assert (
            sanitize_exception_message(exc)
            == "Validation failed. Please check your input."
        )

    def test_permission_denied_message(self):
        """PermissionDenied should return user-friendly message."""
        from django.core.exceptions import PermissionDenied

        exc = PermissionDenied("You don't have access")
        assert (
            sanitize_exception_message(exc)
            == "You don't have permission to perform this action."
        )

    def test_object_does_not_exist_message(self):
        """ObjectDoesNotExist should return user-friendly message."""
        from django.core.exceptions import ObjectDoesNotExist

        exc = ObjectDoesNotExist("Flight not found")
        assert (
            sanitize_exception_message(exc) == "The requested resource was not found."
        )

    def test_integrity_error_message(self):
        """IntegrityError should return user-friendly message."""
        from django.db import IntegrityError

        exc = IntegrityError("UNIQUE constraint failed")
        assert sanitize_exception_message(exc) == "A database constraint was violated."

    def test_unknown_exception_returns_generic_message(self):
        """Unknown exception types should return generic message."""
        exc = RuntimeError("Detailed error with /path/to/file.py line 42")
        assert (
            sanitize_exception_message(exc)
            == "An unexpected error occurred. Please try again."
        )

    def test_custom_exception_returns_generic_message(self):
        """Custom exception types should return generic message."""

        class CustomException(Exception):
            pass

        exc = CustomException("Custom error details")
        assert (
            sanitize_exception_message(exc)
            == "An unexpected error occurred. Please try again."
        )

    def test_sanitize_prevents_information_leakage(self):
        """Verify that detailed error info doesn't leak through."""
        exc = Exception(
            "Database connection failed: host=db.internal.com, "
            "database=manage2soar_prod, user=admin"
        )
        result = sanitize_exception_message(exc)
        # Should not contain any internal details
        assert "db.internal.com" not in result
        assert "manage2soar_prod" not in result
        assert "admin" not in result
        assert result == "An unexpected error occurred. Please try again."


class TestSecurityEdgeCases:
    """Edge case tests for security functions."""

    def test_url_with_special_characters(self):
        """URLs with special characters should be handled correctly."""
        # URL-encoded characters
        assert is_safe_redirect_url("/dashboard?next=%2Fhome") is True
        assert is_safe_redirect_url("/search?q=test%20query") is True

    def test_url_with_fragments(self):
        """URLs with fragments should be handled correctly."""
        assert is_safe_redirect_url("/page#section") is True
        assert is_safe_redirect_url("/dashboard#top") is True

    def test_url_with_query_params(self):
        """URLs with query parameters should be handled correctly."""
        assert is_safe_redirect_url("/search?q=test&page=2") is True
        assert is_safe_redirect_url("/filter?status=active") is True

    def test_very_long_url(self):
        """Very long URLs should be handled without errors."""
        long_path = "/dashboard/" + "a" * 2000
        assert is_safe_redirect_url(long_path) is True

    def test_unicode_in_url(self):
        """URLs with Unicode characters should be handled."""
        assert is_safe_redirect_url("/member/Müller") is True
        assert is_safe_redirect_url("/search?q=测试") is True
