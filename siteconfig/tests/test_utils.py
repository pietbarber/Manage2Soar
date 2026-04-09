import pytest

from siteconfig.models import SiteConfiguration
from siteconfig.utils import get_role_title


@pytest.mark.django_db
def test_get_role_title_commercial_pilot_without_config():
    assert get_role_title("commercial_pilot") == "Commercial Pilot"


@pytest.mark.django_db
def test_get_role_title_commercial_pilot_with_config():
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        commercial_pilot_title="Ride Pilot",
    )

    assert get_role_title("commercial_pilot") == "Ride Pilot"
