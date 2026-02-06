"""
Unit tests for utils.url_helpers module.

Tests Issue #612 canonical URL helper functions:
- get_canonical_url(): Fallback priority (DB → SITE_URL → localhost)
- build_absolute_url(): Path normalization and canonical parameter usage
"""

from unittest.mock import patch

import pytest
from django.conf import settings
from django.db.utils import OperationalError

from siteconfig.models import SiteConfiguration
from utils.url_helpers import build_absolute_url, get_canonical_url


@pytest.mark.django_db
class TestGetCanonicalURL:
    """Test get_canonical_url() fallback priority and error handling."""

    def test_returns_db_canonical_url_when_set(self):
        """Should return canonical_url from database when available."""
        config = SiteConfiguration.objects.first()
        if not config:
            config = SiteConfiguration.objects.create(
                club_name="Test Club",
                club_abbreviation="TCC",
                domain_name="example.org",
            )
        config.canonical_url = "https://www.skylinesoaring.org"
        config.save()

        result = get_canonical_url()
        assert result == "https://www.skylinesoaring.org"

    def test_strips_trailing_slash_from_db_value(self):
        """Should normalize DB canonical_url by removing trailing slash."""
        config = SiteConfiguration.objects.first()
        if not config:
            config = SiteConfiguration.objects.create(
                club_name="Test Club",
                club_abbreviation="TCC",
                domain_name="example.org",
            )
        config.canonical_url = "https://www.skylinesoaring.org/"
        config.save()

        result = get_canonical_url()
        assert result == "https://www.skylinesoaring.org"
        assert not result.endswith("/")

    def test_falls_back_to_site_url_when_db_empty(self):
        """Should fall back to settings.SITE_URL when DB canonical_url is blank."""
        config = SiteConfiguration.objects.first()
        if not config:
            config = SiteConfiguration.objects.create(
                club_name="Test Club",
                club_abbreviation="TCC",
                domain_name="example.org",
            )
        config.canonical_url = ""
        config.save()

        with patch.object(settings, "SITE_URL", "https://fallback.example.com"):
            result = get_canonical_url()
            assert result == "https://fallback.example.com"

    def test_strips_trailing_slash_from_site_url(self):
        """Should normalize settings.SITE_URL by removing trailing slash."""
        config = SiteConfiguration.objects.first()
        if not config:
            config = SiteConfiguration.objects.create(
                club_name="Test Club",
                club_abbreviation="TCC",
                domain_name="example.org",
            )
        config.canonical_url = ""
        config.save()

        with patch.object(settings, "SITE_URL", "https://fallback.example.com/"):
            result = get_canonical_url()
            assert result == "https://fallback.example.com"

    def test_falls_back_to_localhost_when_all_empty(self):
        """Should fall back to localhost:8001 when DB and SITE_URL are both blank."""
        config = SiteConfiguration.objects.first()
        if not config:
            config = SiteConfiguration.objects.create(
                club_name="Test Club",
                club_abbreviation="TCC",
                domain_name="example.org",
            )
        config.canonical_url = ""
        config.save()

        with patch.object(settings, "SITE_URL", ""):
            result = get_canonical_url()
            assert result == "http://localhost:8001"

    def test_handles_db_not_ready_operational_error(self):
        """Should gracefully handle OperationalError during migrations/startup."""
        with patch(
            "siteconfig.models.SiteConfiguration.objects.first",
            side_effect=OperationalError("no such table"),
        ):
            with patch.object(settings, "SITE_URL", "https://recovered.example.com"):
                result = get_canonical_url()
                assert result == "https://recovered.example.com"

    def test_handles_db_not_ready_program_error(self):
        """Should gracefully handle ProgrammingError during migrations/startup."""
        from django.db.utils import ProgrammingError

        with patch(
            "siteconfig.models.SiteConfiguration.objects.first",
            side_effect=ProgrammingError("relation does not exist"),
        ):
            with patch.object(settings, "SITE_URL", ""):
                result = get_canonical_url()
                assert result == "http://localhost:8001"


@pytest.mark.django_db
class TestBuildAbsoluteURL:
    """Test build_absolute_url() path normalization and canonical parameter."""

    def test_builds_url_from_path(self):
        """Should build absolute URL by combining canonical base with path."""
        config = SiteConfiguration.objects.first()
        if not config:
            config = SiteConfiguration.objects.create(
                club_name="Test Club",
                club_abbreviation="TCC",
                domain_name="example.org",
            )
        config.canonical_url = "https://www.skylinesoaring.org"
        config.save()

        result = build_absolute_url("/members/")
        assert result == "https://www.skylinesoaring.org/members/"

    def test_strips_leading_slash_from_path(self):
        """Should normalize path by removing leading slash."""
        config = SiteConfiguration.objects.first()
        if not config:
            config = SiteConfiguration.objects.create(
                club_name="Test Club",
                club_abbreviation="TCC",
                domain_name="example.org",
            )
        config.canonical_url = "https://www.skylinesoaring.org"
        config.save()

        result = build_absolute_url("members/")
        assert result == "https://www.skylinesoaring.org/members/"

    def test_handles_path_with_leading_slash(self):
        """Should handle paths with leading slash correctly."""
        config = SiteConfiguration.objects.first()
        if not config:
            config = SiteConfiguration.objects.create(
                club_name="Test Club",
                club_abbreviation="TCC",
                domain_name="example.org",
            )
        config.canonical_url = "https://www.skylinesoaring.org"
        config.save()

        result = build_absolute_url("/duty_roster/calendar/")
        assert result == "https://www.skylinesoaring.org/duty_roster/calendar/"

    def test_prevents_double_slashes_with_trailing_canonical(self):
        """Should prevent // when canonical has trailing slash."""
        result = build_absolute_url(
            "/members/", canonical="https://www.skylinesoaring.org/"
        )
        assert result == "https://www.skylinesoaring.org/members/"
        assert "//" not in result.replace("https://", "")

    def test_prevents_double_slashes_with_both_trailing(self):
        """Should prevent // when both canonical and path have slashes."""
        result = build_absolute_url(
            "/members/", canonical="https://www.skylinesoaring.org/"
        )
        assert result == "https://www.skylinesoaring.org/members/"

    def test_uses_canonical_parameter_when_provided(self):
        """Should use provided canonical parameter instead of querying DB."""
        config = SiteConfiguration.objects.first()
        if not config:
            config = SiteConfiguration.objects.create(
                club_name="Test Club",
                club_abbreviation="TCC",
                domain_name="example.org",
            )
        config.canonical_url = "https://wrong.example.com"
        config.save()

        result = build_absolute_url(
            "/members/", canonical="https://correct.example.com"
        )
        assert result == "https://correct.example.com/members/"

    def test_queries_db_when_canonical_parameter_none(self):
        """Should query DB via get_canonical_url() when canonical=None."""
        config = SiteConfiguration.objects.first()
        if not config:
            config = SiteConfiguration.objects.create(
                club_name="Test Club",
                club_abbreviation="TCC",
                domain_name="example.org",
            )
        config.canonical_url = "https://www.skylinesoaring.org"
        config.save()

        result = build_absolute_url("/members/", canonical=None)
        assert result == "https://www.skylinesoaring.org/members/"

    def test_reuses_canonical_for_multiple_paths(self):
        """Should allow reusing a precomputed canonical base for efficiency."""
        config = SiteConfiguration.objects.first()
        if not config:
            config = SiteConfiguration.objects.create(
                club_name="Test Club",
                club_abbreviation="TCC",
                domain_name="example.org",
            )
        config.canonical_url = "https://www.skylinesoaring.org"
        config.save()

        base = get_canonical_url()
        url1 = build_absolute_url("/path1/", canonical=base)
        url2 = build_absolute_url("/path2/", canonical=base)

        assert url1 == "https://www.skylinesoaring.org/path1/"
        assert url2 == "https://www.skylinesoaring.org/path2/"

    def test_handles_complex_paths(self):
        """Should handle complex paths with query strings and fragments."""
        result = build_absolute_url(
            "/admin/members/member/?status=active",
            canonical="https://www.skylinesoaring.org",
        )
        assert (
            result
            == "https://www.skylinesoaring.org/admin/members/member/?status=active"
        )


@pytest.mark.django_db
class TestCanonicalURLIntegration:
    """Integration tests for canonical URL system in email notifications."""

    def test_consistent_urls_across_multiple_calls(self):
        """Should produce consistent URLs when reusing canonical base."""
        config = SiteConfiguration.objects.first()
        if not config:
            config = SiteConfiguration.objects.create(
                club_name="Test Club",
                club_abbreviation="TCC",
                domain_name="example.org",
            )
        config.canonical_url = "https://www.skylinesoaring.org"
        config.save()

        # Simulate email building with multiple URLs
        base = get_canonical_url()
        urls = [
            build_absolute_url("/members/", canonical=base),
            build_absolute_url("/duty_roster/", canonical=base),
            build_absolute_url("/instructors/", canonical=base),
        ]

        # All URLs should use same base
        assert all(url.startswith("https://www.skylinesoaring.org/") for url in urls)

    def test_fallback_chain_produces_valid_urls(self):
        """Should produce valid absolute URLs through entire fallback chain."""
        # Test all fallback scenarios produce valid URLs
        scenarios = [
            ("https://www.skylinesoaring.org", "/members/"),
            ("", "/members/"),  # Falls back to SITE_URL or localhost
        ]

        for canonical_value, path in scenarios:
            config = SiteConfiguration.objects.first()
            if not config:
                config = SiteConfiguration.objects.create(
                    club_name="Test Club",
                    club_abbreviation="TCC",
                    domain_name="example.org",
                )
            config.canonical_url = canonical_value
            config.save()

            result = build_absolute_url(path)
            # Should always produce a valid absolute URL
            assert result.startswith("http://") or result.startswith("https://")
            assert path.strip("/") in result
