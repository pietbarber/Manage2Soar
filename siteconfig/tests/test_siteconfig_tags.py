"""
Unit tests for siteconfig template tags (Issue #625 follow-up).

Verifies get_siteconfig() and webcam_enabled() caching behaviour and
that webcam_snapshot_url is never stored in the cache backend.
"""

import pytest
from django.core.cache import cache

from siteconfig.models import SiteConfiguration
from siteconfig.templatetags.siteconfig_tags import get_siteconfig, webcam_enabled

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WEBCAM_URL = "http://cam.example.com/snapshot.jpg"


def _make_config(webcam_snapshot_url=WEBCAM_URL, **kwargs):
    defaults = dict(
        club_name="Tag Test Club",
        domain_name="tagtest.org",
        club_abbreviation="TT",
        webcam_snapshot_url=webcam_snapshot_url,
    )
    defaults.update(kwargs)
    existing = SiteConfiguration.objects.first()
    if existing:
        for k, v in defaults.items():
            setattr(existing, k, v)
        existing.save()
        return existing
    return SiteConfiguration.objects.create(**defaults)


# ---------------------------------------------------------------------------
# webcam_enabled tag
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_webcam_enabled_true_when_url_configured():
    """Returns True when webcam_snapshot_url is non-empty."""
    cache.clear()
    _make_config(webcam_snapshot_url=WEBCAM_URL)
    assert webcam_enabled() is True


@pytest.mark.django_db
def test_webcam_enabled_false_when_url_blank():
    """Returns False when webcam_snapshot_url is blank."""
    cache.clear()
    _make_config(webcam_snapshot_url="")
    assert webcam_enabled() is False


@pytest.mark.django_db
def test_webcam_enabled_false_when_no_siteconfig():
    """Returns False when no SiteConfiguration row exists."""
    cache.clear()
    SiteConfiguration.objects.all().delete()
    assert webcam_enabled() is False


@pytest.mark.django_db
def test_webcam_enabled_caches_result():
    """Result is cached; second call hits cache, not DB."""
    cache.clear()
    _make_config(webcam_snapshot_url=WEBCAM_URL)

    first = webcam_enabled()
    assert first is True
    assert cache.get("siteconfig_webcam_enabled") is True

    # Delete the DB row; cached value should still be returned.
    SiteConfiguration.objects.all().delete()
    assert webcam_enabled() is True  # still from cache


@pytest.mark.django_db
def test_webcam_enabled_does_not_store_url_in_cache():
    """The cache key must hold only a boolean, never the credential URL."""
    cache.clear()
    _make_config(webcam_snapshot_url=WEBCAM_URL)
    webcam_enabled()

    cached = cache.get("siteconfig_webcam_enabled")
    assert isinstance(cached, bool), f"Expected bool in cache, got {type(cached)}"
    # Verify no string containing the URL leaked into this key
    assert WEBCAM_URL not in str(cached)


# ---------------------------------------------------------------------------
# get_siteconfig tag
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_siteconfig_returns_instance():
    """Returns the SiteConfiguration instance."""
    cache.clear()
    _make_config()
    cfg = get_siteconfig()
    assert cfg is not None
    assert cfg.club_name == "Tag Test Club"


@pytest.mark.django_db
def test_get_siteconfig_returns_none_when_missing():
    """Returns None when no SiteConfiguration row exists."""
    cache.clear()
    SiteConfiguration.objects.all().delete()
    assert get_siteconfig() is None


@pytest.mark.django_db
def test_get_siteconfig_caches_instance():
    """Result is stored under siteconfig_deferred and reused."""
    cache.clear()
    _make_config()

    cfg = get_siteconfig()
    assert cfg is not None

    # Cache should be populated now.
    cached = cache.get("siteconfig_deferred")
    assert cached is not None
    assert cached.pk == cfg.pk

    # Second call returns the cached object (deserialized; same pk).
    cfg2 = get_siteconfig()
    assert cfg2 is not None
    assert cfg2.pk == cached.pk


@pytest.mark.django_db
def test_get_siteconfig_defers_webcam_snapshot_url():
    """webcam_snapshot_url must not be present in the cached object's
    __dict__ so it is never serialised into the cache backend."""
    cache.clear()
    _make_config(webcam_snapshot_url=WEBCAM_URL)

    get_siteconfig()

    cached = cache.get("siteconfig_deferred")
    assert cached is not None
    # Deferred fields are absent from __dict__; accessing them triggers a
    # fresh DB query.  Verify the key is NOT in the instance's field cache.
    assert "webcam_snapshot_url" not in cached.__dict__, (
        "webcam_snapshot_url should be deferred and absent from the "
        "cached object's __dict__ to prevent credential leakage."
    )
