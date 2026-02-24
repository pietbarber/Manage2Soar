"""
Tests for the webcam proxy view (Issue #625).

The Django server fetches a snapshot from the configured webcam URL and
streams the image bytes back to authenticated members.  Credentials in the
URL never reach the browser.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse

from siteconfig.models import SiteConfiguration

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WEBCAM_URL = "http://camera.example.com:9137/cgi-bin/CGIProxy.fcgi?cmd=snapPicture2&usr=test&pwd=secret"


def _make_config(webcam_snapshot_url=WEBCAM_URL, **kwargs):
    defaults = dict(
        club_name="Test Club",
        domain_name="test.org",
        club_abbreviation="TC",
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


def _make_member(django_user_model, username="member"):
    return django_user_model.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="password",
        membership_status="Full Member",
    )


# ---------------------------------------------------------------------------
# webcam_page view
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_webcam_page_requires_login(client):
    """Unauthenticated request is redirected to login."""
    _make_config()
    url = reverse("siteconfig:webcam")
    response = client.get(url)
    assert response.status_code in (302, 301)
    assert (
        "login" in response["Location"].lower() or "/accounts/" in response["Location"]
    )


@pytest.mark.django_db
def test_webcam_page_returns_200_for_active_member(client, django_user_model):
    """Active member can access the webcam page."""
    _make_config()
    user = _make_member(django_user_model)
    client.force_login(user)
    url = reverse("siteconfig:webcam")
    response = client.get(url)
    assert response.status_code == 200
    assert "webcam-img" in response.content.decode()


@pytest.mark.django_db
def test_webcam_page_404_when_not_configured(client, django_user_model):
    """Returns 404 when webcam_snapshot_url is blank."""
    _make_config(webcam_snapshot_url="")
    user = _make_member(django_user_model)
    client.force_login(user)
    url = reverse("siteconfig:webcam")
    response = client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_webcam_page_404_when_no_siteconfig(client, django_user_model):
    """Returns 404 when SiteConfiguration does not exist at all."""
    SiteConfiguration.objects.all().delete()
    user = django_user_model.objects.create_user(
        username="orphan",
        email="orphan@example.com",
        password="pw",
        membership_status="Full Member",
    )
    client.force_login(user)
    url = reverse("siteconfig:webcam")
    response = client.get(url)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# webcam_snapshot proxy view
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_snapshot_requires_login(client):
    """Unauthenticated request to snapshot URL is redirected."""
    _make_config()
    url = reverse("siteconfig:webcam_snapshot")
    response = client.get(url)
    assert response.status_code in (302, 301)


@pytest.mark.django_db
def test_snapshot_proxies_image_bytes(client, django_user_model):
    """Snapshot view fetches camera URL server-side and returns raw bytes."""
    _make_config()
    user = _make_member(django_user_model)
    client.force_login(user)

    fake_image = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # minimal JPEG header
    mock_resp = MagicMock()
    mock_resp.content = fake_image
    mock_resp.headers = {"Content-Type": "image/jpeg"}
    mock_resp.raise_for_status = MagicMock()

    with patch("siteconfig.views.requests.get", return_value=mock_resp) as mock_get:
        response = client.get(reverse("siteconfig:webcam_snapshot"))

    assert response.status_code == 200
    assert response["Content-Type"] == "image/jpeg"
    assert response.content == fake_image
    # Confirm the camera URL was fetched (with credentials) on the server
    mock_get.assert_called_once()
    call_url = mock_get.call_args[0][0]
    assert call_url == WEBCAM_URL
    # Credentials must NOT leak to the browser
    assert "secret" not in response.content.decode("latin-1", errors="ignore")[:500]


@pytest.mark.django_db
def test_snapshot_no_cache_headers(client, django_user_model):
    """Response carries no-store Cache-Control so browsers always re-fetch."""
    _make_config()
    user = _make_member(django_user_model)
    client.force_login(user)

    mock_resp = MagicMock()
    mock_resp.content = b"\xff\xd8"
    mock_resp.headers = {"Content-Type": "image/jpeg"}
    mock_resp.raise_for_status = MagicMock()

    with patch("siteconfig.views.requests.get", return_value=mock_resp):
        response = client.get(reverse("siteconfig:webcam_snapshot"))

    assert "no-store" in response["Cache-Control"]


@pytest.mark.django_db
def test_snapshot_returns_503_when_camera_down(client, django_user_model):
    """Returns 503 when the upstream camera is unreachable."""
    import requests as req_lib

    _make_config()
    user = _make_member(django_user_model)
    client.force_login(user)

    with patch(
        "siteconfig.views.requests.get", side_effect=req_lib.ConnectionError("down")
    ):
        response = client.get(reverse("siteconfig:webcam_snapshot"))

    assert response.status_code == 503


@pytest.mark.django_db
def test_snapshot_404_when_not_configured(client, django_user_model):
    """Returns 404 when webcam_snapshot_url is blank."""
    _make_config(webcam_snapshot_url="")
    user = _make_member(django_user_model)
    client.force_login(user)
    url = reverse("siteconfig:webcam_snapshot")
    response = client.get(url)
    assert response.status_code == 404
