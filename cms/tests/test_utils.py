"""
Unit tests for CMS utility functions.
"""

import pytest

from cms.utils import (
    REQUIRED_YOUTUBE_PERMISSIONS,
    YOUTUBE_ALLOW_ATTR,
    fix_youtube_embeds,
)


class TestFixYouTubeEmbeds:
    """Test the fix_youtube_embeds utility function."""

    def test_empty_content_returns_empty(self):
        """Test that empty content is returned unchanged."""
        assert fix_youtube_embeds(None) is None
        assert fix_youtube_embeds("") == ""

    def test_content_without_youtube_unchanged(self):
        """Test that content without YouTube iframes is unchanged."""
        content = "<p>Some text</p><div>More content</div>"
        assert fix_youtube_embeds(content) == content

    def test_adds_referrerpolicy_to_iframe_without_it(self):
        """Test that referrerpolicy is added to iframes that don't have it."""
        content = '<iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ"></iframe>'
        result = fix_youtube_embeds(content)

        assert 'referrerpolicy="strict-origin-when-cross-origin"' in result
        assert "youtube.com/embed/dQw4w9WgXcQ" in result

    def test_adds_allow_attribute_to_iframe_without_it(self):
        """Test that allow attribute is added to iframes that don't have it."""
        content = '<iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ"></iframe>'
        result = fix_youtube_embeds(content)

        assert YOUTUBE_ALLOW_ATTR in result
        # Verify all required permissions are present
        for perm in REQUIRED_YOUTUBE_PERMISSIONS:
            assert perm in result

    def test_replaces_incomplete_allow_attribute(self):
        """Test that incomplete allow attributes are replaced with full permissions."""
        content = '<iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ" allow="autoplay"></iframe>'
        result = fix_youtube_embeds(content)

        # Should replace partial allow with full canonical allow
        assert YOUTUBE_ALLOW_ATTR in result
        # Verify all required permissions are present
        for perm in REQUIRED_YOUTUBE_PERMISSIONS:
            assert perm in result

    def test_preserves_correct_attributes(self):
        """Test that iframes with correct attributes are left unchanged."""
        content = (
            '<iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ" '
            'referrerpolicy="strict-origin-when-cross-origin" '
            f"{YOUTUBE_ALLOW_ATTR}></iframe>"
        )
        result = fix_youtube_embeds(content)

        # Should be unchanged
        assert result == content

    def test_handles_single_quotes(self):
        """Test that iframes with single quotes are handled correctly."""
        content = "<iframe src='https://www.youtube.com/embed/dQw4w9WgXcQ'></iframe>"
        result = fix_youtube_embeds(content)

        assert 'referrerpolicy="strict-origin-when-cross-origin"' in result
        assert YOUTUBE_ALLOW_ATTR in result

    def test_handles_mixed_case_hostname(self):
        """Test that YouTube hostnames in various cases are recognized."""
        cases = [
            "https://www.youtube.com/embed/dQw4w9WgXcQ",
            "https://www.YOUTUBE.com/embed/dQw4w9WgXcQ",
            "https://www.YouTube.COM/embed/dQw4w9WgXcQ",
        ]

        for url in cases:
            content = f'<iframe src="{url}"></iframe>'
            result = fix_youtube_embeds(content)
            assert YOUTUBE_ALLOW_ATTR in result, f"Failed for URL: {url}"

    def test_handles_multiple_iframes(self):
        """Test that multiple iframes in content are all fixed."""
        content = """
        <p>First video:</p>
        <iframe src="https://www.youtube.com/embed/video1"></iframe>
        <p>Second video:</p>
        <iframe src="https://www.youtube.com/embed/video2"></iframe>
        """
        result = fix_youtube_embeds(content)

        # Count occurrences of the allow attribute
        allow_count = result.count(YOUTUBE_ALLOW_ATTR)
        assert allow_count == 2, "Should fix both iframes"

        # Count occurrences of referrerpolicy
        referrer_count = result.count(
            'referrerpolicy="strict-origin-when-cross-origin"'
        )
        assert referrer_count == 2, "Should add referrerpolicy to both iframes"

    def test_preserves_existing_iframe_attributes(self):
        """Test that other iframe attributes are preserved."""
        content = (
            '<iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ" '
            'width="560" height="315" frameborder="0" allowfullscreen></iframe>'
        )
        result = fix_youtube_embeds(content)

        # Should preserve width, height, frameborder, allowfullscreen
        assert 'width="560"' in result
        assert 'height="315"' in result
        assert 'frameborder="0"' in result
        assert "allowfullscreen" in result

        # Should add missing attributes
        assert 'referrerpolicy="strict-origin-when-cross-origin"' in result
        assert YOUTUBE_ALLOW_ATTR in result

    def test_handles_malformed_html_gracefully(self):
        """Test that malformed HTML doesn't break the function."""
        # Missing closing bracket - should not match and return unchanged
        content = '<iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ"'
        result = fix_youtube_embeds(content)
        assert result == content

    def test_replaces_incorrect_referrerpolicy(self):
        """Test that incorrect referrerpolicy values are replaced."""
        content = (
            '<iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ" '
            'referrerpolicy="no-referrer"></iframe>'
        )
        result = fix_youtube_embeds(content)

        # Should replace with correct value
        assert 'referrerpolicy="strict-origin-when-cross-origin"' in result
        # Should not contain old value
        assert 'referrerpolicy="no-referrer"' not in result

    def test_handles_allow_attribute_with_extra_permissions(self):
        """Test that allow attributes with all required + extra permissions are preserved."""
        # All required permissions + an extra one
        extra_allow = (
            'allow="accelerometer; autoplay; clipboard-write; encrypted-media; '
            'gyroscope; picture-in-picture; web-share; fullscreen"'
        )
        content = (
            f'<iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ" '
            f'referrerpolicy="strict-origin-when-cross-origin" {extra_allow}></iframe>'
        )
        result = fix_youtube_embeds(content)

        # Since all required permissions are present, it should be preserved
        # (the function checks if all required are present, not if it's exactly canonical)
        assert "fullscreen" in result
        for perm in REQUIRED_YOUTUBE_PERMISSIONS:
            assert perm in result

    def test_case_insensitive_attribute_matching(self):
        """Test that attribute matching is case-insensitive."""
        content = (
            '<iframe SRC="https://www.youtube.com/embed/dQw4w9WgXcQ" '
            'ALLOW="autoplay"></iframe>'
        )
        result = fix_youtube_embeds(content)

        # Should recognize and update the ALLOW attribute
        assert YOUTUBE_ALLOW_ATTR in result


class TestYouTubeEmbedConstants:
    """Test that the YouTube embed constants are correctly defined."""

    def test_required_permissions_list(self):
        """Test that all required permissions are defined."""
        expected_permissions = [
            "accelerometer",
            "autoplay",
            "clipboard-write",
            "encrypted-media",
            "gyroscope",
            "picture-in-picture",
            "web-share",
        ]

        assert REQUIRED_YOUTUBE_PERMISSIONS == expected_permissions

    def test_allow_attr_contains_all_permissions(self):
        """Test that YOUTUBE_ALLOW_ATTR contains all required permissions."""
        for perm in REQUIRED_YOUTUBE_PERMISSIONS:
            assert (
                perm in YOUTUBE_ALLOW_ATTR
            ), f"Permission '{perm}' missing from YOUTUBE_ALLOW_ATTR"
