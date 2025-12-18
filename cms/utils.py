"""
Utility functions for fixing YouTube embed iframes to prevent Error 153.

This module provides a shared function for fixing YouTube iframe embeds
by adding the proper referrerpolicy="strict-origin-when-cross-origin"
attribute to prevent YouTube Error 153 playback issues.
"""

import re

# YouTube allow attribute required for proper embedding
YOUTUBE_ALLOW_ATTR = 'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"'


def fix_youtube_embeds(content):
    """
    Fix YouTube iframe embeds by adding proper referrer policy and allow attribute.

    Adds referrerpolicy="strict-origin-when-cross-origin" and the full allow attribute
    to YouTube iframes to ensure proper domain verification and prevent Error 153.

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

        needs_update = False

        # Check if referrerpolicy is already set correctly
        if 'referrerpolicy="strict-origin-when-cross-origin"' not in iframe_attrs:
            needs_update = True
            # Remove any existing referrerpolicy (handles both single and double quotes)
            iframe_attrs = re.sub(
                r'\s*referrerpolicy=["\'][^"\']*["\']',
                "",
                iframe_attrs,
                flags=re.IGNORECASE,
            )
            iframe_attrs = (
                f'{iframe_attrs} referrerpolicy="strict-origin-when-cross-origin"'
            )

        # Check if allow attribute is present with the right content
        if 'allow="' not in iframe_attrs.lower():
            needs_update = True
            iframe_attrs = f"{iframe_attrs} {YOUTUBE_ALLOW_ATTR}"

        if not needs_update:
            return match.group(0)  # Already correct

        return f"{iframe_attrs}{closing}"

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
