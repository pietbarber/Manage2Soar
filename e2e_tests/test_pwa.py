"""Tests for PWA (Progressive Web App) views."""

import json
import os
from unittest.mock import patch

import pytest
from django.conf import settings


@pytest.mark.django_db
class TestManifestView:
    """Tests for the PWA manifest view."""

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

        # Verify values
        assert data["name"] == "Manage2Soar"
        assert data["short_name"] == "M2S"
        assert data["start_url"] == "/"
        assert data["display"] == "standalone"

    def test_manifest_icon_urls_use_static_url(self, client):
        """Test that icon URLs correctly use STATIC_URL setting."""
        response = client.get("/manifest.json")
        data = json.loads(response.content)

        icons = data["icons"]
        assert len(icons) == 2

        # Icons should use the STATIC_URL prefix
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
