from unittest.mock import MagicMock

import pytest

from logsheet.models import Airfield, Glider, MaintenanceIssue, Towplane


@pytest.mark.django_db
def test_logsheet_str_representation(logsheet):
    assert str(logsheet) == f"{logsheet.log_date} @ {logsheet.airfield}"


@pytest.mark.django_db
def test_logsheet_default_finalized_false(logsheet):
    assert logsheet.finalized is False


@pytest.mark.django_db
def test_maintenance_issue_str_representation(glider):
    issue = MaintenanceIssue.objects.create(
        description="Flat tire", glider=glider, resolved=False
    )
    expected = f"{glider} - Open - Flat tire"
    assert str(issue) == expected


@pytest.mark.django_db
def test_maintenance_issue_default_resolved_false(glider):
    issue = MaintenanceIssue.objects.create(description="Battery issue", glider=glider)
    assert issue.resolved is False


@pytest.mark.django_db
def test_airfield_str_representation():
    airfield = Airfield.objects.create(identifier="W99", name="Winchester Airport")
    assert str(airfield) == "W99 – Winchester Airport"


# =============================================================================
# Equipment Photo URL Property Tests (Issue #286)
# =============================================================================


class TestGliderPhotoUrlProperties:
    """Tests for Glider photo_url_medium and photo_url_small properties."""

    def test_photo_url_medium_returns_medium_thumbnail(self):
        """Should return medium thumbnail URL when available."""
        glider = Glider(n_number="N12345", make="Schleicher", model="ASK-21")
        # Mock the photo_medium field
        mock_field = MagicMock()
        mock_field.url = "/media/glider_photos/medium/test.jpg"
        mock_field.__bool__ = lambda self: True
        glider.photo_medium = mock_field

        url = glider.photo_url_medium
        assert url == "/media/glider_photos/medium/test.jpg"

    def test_photo_url_medium_falls_back_to_full(self):
        """Should fall back to full photo when medium is not available."""
        glider = Glider(n_number="N12345", make="Schleicher", model="ASK-21")
        glider.photo_medium = ""
        mock_full = MagicMock()
        mock_full.url = "/media/glider_photos/test.jpg"
        mock_full.__bool__ = lambda self: True
        glider.photo = mock_full

        url = glider.photo_url_medium
        assert url == "/media/glider_photos/test.jpg"

    def test_photo_url_medium_returns_none_when_no_photos(self):
        """Should return None when no photos are available."""
        glider = Glider(n_number="N12345", make="Schleicher", model="ASK-21")
        glider.photo_medium = ""
        glider.photo = ""

        url = glider.photo_url_medium
        assert url is None

    def test_photo_url_small_returns_small_thumbnail(self):
        """Should return small thumbnail URL when available."""
        glider = Glider(n_number="N12345", make="Schleicher", model="ASK-21")
        mock_field = MagicMock()
        mock_field.url = "/media/glider_photos/small/test.jpg"
        mock_field.__bool__ = lambda self: True
        glider.photo_small = mock_field

        url = glider.photo_url_small
        assert url == "/media/glider_photos/small/test.jpg"

    def test_photo_url_small_falls_back_to_medium(self):
        """Should fall back to medium when small is not available."""
        glider = Glider(n_number="N12345", make="Schleicher", model="ASK-21")
        glider.photo_small = ""
        mock_medium = MagicMock()
        mock_medium.url = "/media/glider_photos/medium/test.jpg"
        mock_medium.__bool__ = lambda self: True
        glider.photo_medium = mock_medium

        url = glider.photo_url_small
        assert url == "/media/glider_photos/medium/test.jpg"

    def test_photo_url_small_falls_back_to_full(self):
        """Should fall back to full photo when small and medium not available."""
        glider = Glider(n_number="N12345", make="Schleicher", model="ASK-21")
        glider.photo_small = ""
        glider.photo_medium = ""
        mock_full = MagicMock()
        mock_full.url = "/media/glider_photos/test.jpg"
        mock_full.__bool__ = lambda self: True
        glider.photo = mock_full

        url = glider.photo_url_small
        assert url == "/media/glider_photos/test.jpg"


class TestTowplanePhotoUrlProperties:
    """Tests for Towplane photo_url_medium and photo_url_small properties."""

    def test_photo_url_medium_returns_medium_thumbnail(self):
        """Should return medium thumbnail URL when available."""
        towplane = Towplane(name="Pawnee", n_number="N67890")
        mock_field = MagicMock()
        mock_field.url = "/media/towplane_photos/medium/test.jpg"
        mock_field.__bool__ = lambda self: True
        towplane.photo_medium = mock_field

        url = towplane.photo_url_medium
        assert url == "/media/towplane_photos/medium/test.jpg"

    def test_photo_url_medium_falls_back_to_full(self):
        """Should fall back to full photo when medium is not available."""
        towplane = Towplane(name="Pawnee", n_number="N67890")
        towplane.photo_medium = ""
        mock_full = MagicMock()
        mock_full.url = "/media/towplane_photos/test.jpg"
        mock_full.__bool__ = lambda self: True
        towplane.photo = mock_full

        url = towplane.photo_url_medium
        assert url == "/media/towplane_photos/test.jpg"

    def test_photo_url_small_returns_small_thumbnail(self):
        """Should return small thumbnail URL when available."""
        towplane = Towplane(name="Pawnee", n_number="N67890")
        mock_field = MagicMock()
        mock_field.url = "/media/towplane_photos/small/test.jpg"
        mock_field.__bool__ = lambda self: True
        towplane.photo_small = mock_field

        url = towplane.photo_url_small
        assert url == "/media/towplane_photos/small/test.jpg"

    def test_photo_url_small_falls_back_chain(self):
        """Should fall back through medium to full when small not available."""
        towplane = Towplane(name="Pawnee", n_number="N67890")
        towplane.photo_small = ""
        towplane.photo_medium = ""
        mock_full = MagicMock()
        mock_full.url = "/media/towplane_photos/test.jpg"
        mock_full.__bool__ = lambda self: True
        towplane.photo = mock_full

        url = towplane.photo_url_small
        assert url == "/media/towplane_photos/test.jpg"

    def test_photo_url_returns_none_when_no_photos(self):
        """Should return None when no photos are available."""
        towplane = Towplane(name="Pawnee", n_number="N67890")
        towplane.photo_small = ""
        towplane.photo_medium = ""
        towplane.photo = ""

        url = towplane.photo_url_small
        assert url is None
