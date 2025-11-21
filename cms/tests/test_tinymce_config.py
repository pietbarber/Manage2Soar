"""
Tests for TinyMCE configuration to ensure URLs remain relative.
Addresses issue #207: CMS Pages editing, unwelcome FQDN in URLs
"""

from django.conf import settings
from django.test import TestCase


class TinyMCEConfigurationTest(TestCase):
    """Test TinyMCE configuration for relative URL handling."""

    def test_global_tinymce_config_preserves_user_urls(self):
        """Test that global TinyMCE config preserves user input URLs without conversion."""
        config = settings.TINYMCE_DEFAULT_CONFIG

        # These settings should prevent automatic URL conversion
        self.assertFalse(
            config.get("relative_urls"),
            "relative_urls should be False to prevent ugly ../../../ paths",
        )

        self.assertTrue(
            config.get("remove_script_host"),
            "remove_script_host should be True to strip protocol+host from URLs",
        )

        # convert_urls should be False to preserve user input exactly as typed
        self.assertFalse(
            config.get("convert_urls"),
            "convert_urls should be False to preserve user input like '/contact/'",
        )

    def test_tinymce_js_url_configured(self):
        """Test that TinyMCE JS is configured to use local static files."""
        tinymce_js_url = getattr(settings, "TINYMCE_JS_URL", None)
        self.assertIsNotNone(tinymce_js_url, "TINYMCE_JS_URL should be configured")
        if tinymce_js_url:
            # Check that it uses the configured STATIC_URL (which may be /static/ or /ssc/static/ etc)
            self.assertTrue(
                tinymce_js_url.startswith(settings.STATIC_URL),
                f"TinyMCE JS should be served from local static files (expected to start with {settings.STATIC_URL}, got {tinymce_js_url})",
            )
