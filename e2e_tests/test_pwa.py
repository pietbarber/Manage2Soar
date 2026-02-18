"""Tests for PWA (Progressive Web App) views."""

import io
import json
import os
from unittest.mock import patch

import pytest
from django.conf import settings
from PIL import Image

from siteconfig.models import SiteConfiguration
from utils.favicon import generate_pwa_icon_from_logo


@pytest.mark.django_db
class TestManifestView:
    """Tests for the PWA manifest view."""

    def setup_method(self):
        """Clear cached icon URL before each test to prevent cross-test pollution."""
        from django.core.cache import cache

        cache.delete("pwa_club_icon_url")

    def test_manifest_returns_json(self, client):
        """Test that manifest returns valid JSON with correct content type."""
        response = client.get("/manifest.json")

        assert response.status_code == 200
        assert response["Content-Type"] == "application/json"

        # Verify it's valid JSON
        data = json.loads(response.content)
        assert isinstance(data, dict)

    def test_manifest_contains_required_fields(self, client):
        """Test that manifest contains all required PWA fields."""
        response = client.get("/manifest.json")
        data = json.loads(response.content)

        # Required fields for PWA
        assert "name" in data
        assert "short_name" in data
        assert "start_url" in data
        assert "display" in data
        assert "icons" in data

        # Verify structural values (name comes from SiteConfiguration)
        assert data["start_url"] == "/"
        assert data["display"] == "standalone"

    def test_manifest_name_uses_site_configuration(self, client):
        """Test that manifest name uses the club name from SiteConfiguration."""
        siteconfig = SiteConfiguration.objects.first()
        response = client.get("/manifest.json")
        data = json.loads(response.content)

        if siteconfig and siteconfig.club_name and siteconfig.club_name.split():
            assert data["name"] == siteconfig.club_name
            assert data["short_name"] == siteconfig.club_name.split()[0][:12]
        elif siteconfig and siteconfig.club_name and not siteconfig.club_name.split():
            # Whitespace-only club_name: manifest uses the raw whitespace as name,
            # and "M2S" as short_name (split() returns [], triggering the "M2S" fallback)
            assert data["short_name"] == "M2S"
        else:
            # No SiteConfiguration or empty/None club_name: both fall back to defaults
            assert data["name"] == "Manage2Soar"
            assert data["short_name"] == "Manage2Soar"

    def test_manifest_icon_urls_use_static_url(self, client):
        """Test that icon URLs correctly use STATIC_URL setting when no club icon exists."""
        with patch(
            "django.core.files.storage.default_storage.exists", return_value=False
        ):
            response = client.get("/manifest.json")
        data = json.loads(response.content)

        icons = data["icons"]
        assert len(icons) == 2  # 192x192 club/fallback + 512x512 static default

        # When no club icon is in storage, all icons should use the STATIC_URL prefix
        static_url = settings.STATIC_URL.rstrip("/")
        for icon in icons:
            assert icon["src"].startswith(static_url)
            assert "pwa-icon" in icon["src"]
            assert icon["type"] == "image/png"

    def test_manifest_has_theme_colors(self, client):
        """Test that manifest includes theme and background colors."""
        response = client.get("/manifest.json")
        data = json.loads(response.content)

        assert "theme_color" in data
        assert "background_color" in data
        assert data["theme_color"] == "#212529"
        assert data["background_color"] == "#ffffff"


@pytest.mark.django_db
class TestServiceWorkerView:
    """Tests for the service worker view."""

    def test_service_worker_returns_javascript(self, client):
        """Test that service worker returns JavaScript content type."""
        response = client.get("/service-worker.js")

        assert response.status_code == 200
        assert response["Content-Type"] == "application/javascript"
        assert response["Service-Worker-Allowed"] == "/"

    def test_service_worker_contains_cache_name(self, client):
        """Test that service worker contains a cache name."""
        response = client.get("/service-worker.js")
        content = response.content.decode()

        assert "CACHE_NAME" in content
        assert "manage2soar-" in content

    def test_service_worker_cache_name_from_build_hash_env(self, client):
        """Test that BUILD_HASH env var is used for cache name."""
        with patch.dict(os.environ, {"BUILD_HASH": "abc12345"}):
            response = client.get("/service-worker.js")
            content = response.content.decode()

            assert "manage2soar-abc12345" in content

    def test_service_worker_cache_name_fallback_to_mtime(self, client):
        """Test that file mtime is used when BUILD_HASH not set."""
        # Ensure BUILD_HASH is not set by setting it to empty string
        with patch.dict(os.environ, {"BUILD_HASH": ""}, clear=False):
            response = client.get("/service-worker.js")
            content = response.content.decode()

            # Should contain a hash (8 hex chars after manage2soar-)
            import re

            match = re.search(r"manage2soar-([a-f0-9]{8})", content)
            assert match is not None

    def test_service_worker_cache_name_fallback_to_date(self, client):
        """Test that fallback content is returned when service worker file doesn't exist."""
        import builtins

        # Mock os.path.exists to return False for service worker file
        original_exists = os.path.exists

        def mock_exists(path):
            if "service-worker.js" in str(path):
                return False
            return original_exists(path)

        # Mock open to raise OSError when service worker is opened
        original_open = builtins.open

        def mock_open(path, *args, **kwargs):
            if "service-worker.js" in str(path):
                raise OSError("Mocked: file not found")
            return original_open(path, *args, **kwargs)

        with patch("os.path.exists", side_effect=mock_exists):
            with patch("builtins.open", side_effect=mock_open):
                with patch.dict(os.environ, {"BUILD_HASH": ""}, clear=False):
                    response = client.get("/service-worker.js")
                    content = response.content.decode()

                    # When file doesn't exist, open() raises OSError
                    # and the view returns minimal fallback content
                    assert response.status_code == 200
                    assert "// Service worker file not found" in content

    def test_service_worker_includes_offline_url(self, client):
        """Test that service worker references the offline URL."""
        response = client.get("/service-worker.js")
        content = response.content.decode()

        assert "/offline/" in content

    def test_service_worker_includes_core_pages(self, client):
        """Test that service worker caches core pages."""
        response = client.get("/service-worker.js")
        content = response.content.decode()

        # Core pages that should be cached
        assert "'/'" in content or '"/"' in content
        assert "'/offline/'" in content or '"/offline/"' in content


@pytest.mark.django_db
class TestOfflineView:
    """Tests for the offline page view."""

    def test_offline_page_returns_html(self, client):
        """Test that offline page returns HTML."""
        response = client.get("/offline/")

        assert response.status_code == 200
        assert "text/html" in response["Content-Type"]

    def test_offline_page_contains_retry_button(self, client):
        """Test that offline page has a retry button."""
        response = client.get("/offline/")
        content = response.content.decode()

        assert "Try Again" in content or "retry" in content.lower()

    def test_offline_page_contains_offline_message(self, client):
        """Test that offline page shows offline message."""
        response = client.get("/offline/")
        content = response.content.decode()

        assert "offline" in content.lower()


@pytest.mark.django_db
class TestAppleTouchIconView:
    """Tests for the Apple touch icon redirect view."""

    def setup_method(self):
        """Clear cached icon URL before each test to prevent cross-test pollution."""
        from django.core.cache import cache

        cache.delete("pwa_club_icon_url")

    def test_apple_touch_icon_redirects(self, client):
        """Test that /apple-touch-icon.png returns a temporary redirect to the PWA icon."""
        with patch(
            "django.core.files.storage.default_storage.exists", return_value=False
        ):
            response = client.get("/apple-touch-icon.png")

        assert response.status_code == 302
        assert "pwa-icon" in response["Location"]

    def test_apple_touch_icon_precomposed_redirects(self, client):
        """Test that /apple-touch-icon-precomposed.png returns a temporary redirect."""
        with patch(
            "django.core.files.storage.default_storage.exists", return_value=False
        ):
            response = client.get("/apple-touch-icon-precomposed.png")

        assert response.status_code == 302
        assert "pwa-icon" in response["Location"]

    def test_apple_touch_icon_redirect_target_uses_static_url(self, client):
        """When no club icon exists the redirect target should be the static fallback."""
        with patch(
            "django.core.files.storage.default_storage.exists", return_value=False
        ):
            response = client.get("/apple-touch-icon.png")

        static_url = settings.STATIC_URL.rstrip("/")
        assert response["Location"].startswith(static_url)


@pytest.mark.django_db
class TestClubBrandedPwaIcon:
    """Tests for club-branded PWA / Apple touch icon generation and serving."""

    def setup_method(self):
        """Clear cached icon URL before each test to prevent cross-test pollution."""
        from django.core.cache import cache

        cache.delete("pwa_club_icon_url")

    def _make_tiny_png(self):
        """Return a BytesIO containing a minimal 10x10 RGBA PNG."""
        buf = io.BytesIO()
        Image.new("RGBA", (10, 10), color=(30, 100, 200, 255)).save(buf, format="PNG")
        buf.seek(0)
        return buf

    def test_generate_pwa_icon_produces_correct_size(self):
        """generate_pwa_icon_from_logo should output a 192x192 PNG."""
        out = io.BytesIO()
        generate_pwa_icon_from_logo(self._make_tiny_png(), out)
        out.seek(0)
        img = Image.open(out)
        assert img.size == (192, 192)
        assert img.format == "PNG"

    def test_generate_pwa_icon_respects_custom_size(self):
        """generate_pwa_icon_from_logo should honour the size parameter."""
        out = io.BytesIO()
        generate_pwa_icon_from_logo(self._make_tiny_png(), out, size=180)
        out.seek(0)
        img = Image.open(out)
        assert img.size == (180, 180)

    def test_manifest_icon_uses_club_icon_when_available(self, client):
        """When pwa-icon-club.png exists in storage the manifest should reference it."""
        club_icon_url = "/media/pwa-icon-club.png"

        with patch(
            "django.core.files.storage.default_storage.exists", return_value=True
        ), patch(
            "django.core.files.storage.default_storage.url",
            return_value=club_icon_url,
        ):
            response = client.get("/manifest.json")
            data = json.loads(response.content)

        icon_srcs = [icon["src"] for icon in data["icons"]]
        # The 192x192 entry should point to the club icon
        assert any(src == club_icon_url for src in icon_srcs)
        # The 512x512 fallback should still be the static default
        static_url = settings.STATIC_URL.rstrip("/")
        assert any(
            "pwa-icon-512" in src and src.startswith(static_url) for src in icon_srcs
        )

    def test_apple_touch_icon_uses_club_icon_when_available(self, client):
        """When pwa-icon-club.png exists in storage the Apple touch icon should redirect to it."""
        club_icon_url = "/media/pwa-icon-club.png"

        with patch(
            "django.core.files.storage.default_storage.exists", return_value=True
        ), patch(
            "django.core.files.storage.default_storage.url",
            return_value=club_icon_url,
        ):
            response = client.get("/apple-touch-icon.png")

        assert response.status_code == 302
        assert response["Location"] == club_icon_url
