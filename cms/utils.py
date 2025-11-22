"""
Utility functions for fixing YouTube embed iframes to prevent Error 153.

This module provides a shared function for fixing YouTube iframe embeds
by adding the proper referrerpolicy="strict-origin-when-cross-origin"
attribute to prevent YouTube Error 153 playback issues.
"""

import re


def fix_youtube_embeds(content):
    """
    Fix YouTube iframe embeds by adding proper referrer policy.

    Adds referrerpolicy="strict-origin-when-cross-origin" to YouTube iframes
    to ensure proper domain verification and prevent playback errors.

    Args:
        content (str): HTML content that may contain YouTube iframe embeds

    Returns:
        str: Content with YouTube iframes fixed
    """
    if not content:
        return content

    # Pattern to match YouTube iframe embeds (handles both single and double quotes)
    youtube_pattern = re.compile(
        r'(<iframe[^>]*src=["\'][^"\']*youtube\.com/embed[^"\']*["\'][^>]*)(>)',
        re.IGNORECASE,
    )

    def fix_iframe(match):
        iframe_attrs = match.group(1)
        closing = match.group(2)

        # Check if referrerpolicy is already set correctly
        if 'referrerpolicy="strict-origin-when-cross-origin"' in iframe_attrs:
            return match.group(0)  # Already correct

        # Remove any existing referrerpolicy (handles both single and double quotes)
        iframe_attrs = re.sub(
            r'\s*referrerpolicy=["\'][^"\']*["\']',
            "",
            iframe_attrs,
            flags=re.IGNORECASE,
        )

        # Add the correct referrerpolicy
        return (
            f'{iframe_attrs} referrerpolicy="strict-origin-when-cross-origin"{closing}'
        )

    return youtube_pattern.sub(fix_iframe, content)


def needs_youtube_fix(content):
    """
    Check if content has YouTube iframes that need referrer policy fixing.

    Args:
        content (str): HTML content to check

    Returns:
        bool: True if content has YouTube embeds that need fixing
    """
    if not content:
        return False

    # Look for YouTube iframes without proper referrerpolicy
    youtube_pattern = re.compile(
        r'<iframe[^>]*src=["\'][^"\']*youtube\.com/embed[^"\']*["\'][^>]*>',
        re.IGNORECASE,
    )

    for match in youtube_pattern.finditer(content):
        iframe = match.group(0)
        # If it doesn't have the correct referrerpolicy, it needs fixing
        if 'referrerpolicy="strict-origin-when-cross-origin"' not in iframe:
            return True

    return False
