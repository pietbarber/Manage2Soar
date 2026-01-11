"""Tests for validation helper functions in logsheet.views."""

from django.core.exceptions import ValidationError

from logsheet.views import get_validation_message


class TestGetValidationMessage:
    """Tests for the get_validation_message helper function.

    This function is security-critical as it ensures only user-facing
    messages are exposed, not stack traces or internal exception details.
    """

    def test_single_message(self):
        """Test extraction of a single validation message."""
        error = ValidationError("This glider is already scheduled.")
        result = get_validation_message(error)
        assert result == "This glider is already scheduled."

    def test_multiple_messages(self):
        """Test extraction of multiple validation messages."""
        error = ValidationError(["Error one", "Error two"])
        result = get_validation_message(error)
        assert result == "Error one; Error two"

    def test_message_dict(self):
        """Test extraction from ValidationError with message_dict."""
        error = ValidationError({"field1": ["Error A"], "field2": ["Error B"]})
        result = get_validation_message(error)
        # messages property flattens the dict values
        assert "Error A" in result
        assert "Error B" in result

    def test_empty_messages_returns_fallback(self):
        """Test that empty messages list returns generic fallback."""
        error = ValidationError([])
        result = get_validation_message(error)
        assert result == "Validation failed"

    def test_no_messages_attribute_returns_fallback(self):
        """Test fallback when messages attribute is missing/empty.

        This ensures we never accidentally expose internal exception details.
        """

        # Create a mock error-like object without proper messages
        class FakeError:
            pass

        fake_error = FakeError()
        result = get_validation_message(fake_error)
        assert result == "Validation failed"

    def test_does_not_expose_traceback_info(self):
        """Verify that stack trace info is never in the result.

        The function should only return user-facing message text,
        not any traceback or exception class info.
        """
        error = ValidationError("User message here")
        result = get_validation_message(error)

        # Should not contain exception class names or traceback markers
        assert "Traceback" not in result
        assert "ValidationError" not in result
        assert "File" not in result
        assert "line" not in result.lower() or "User message" in result

    def test_unicode_messages(self):
        """Test handling of unicode characters in messages."""
        error = ValidationError("Glider René's flight is ≥ 2 hours")
        result = get_validation_message(error)
        assert result == "Glider René's flight is ≥ 2 hours"

    def test_html_in_message_preserved(self):
        """Test that HTML in messages is preserved (escaping is caller's job)."""
        error = ValidationError("<script>alert('xss')</script>")
        result = get_validation_message(error)
        # The helper just extracts, doesn't escape - that's JsonResponse's job
        assert "<script>" in result
