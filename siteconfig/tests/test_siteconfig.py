import pytest
from django.contrib.auth import get_user_model

from siteconfig.models import SiteConfiguration

User = get_user_model()


@pytest.mark.django_db
def test_create_siteconfiguration():
    SiteConfiguration.objects.create(
        club_name="Skyline Soaring", domain_name="example.org", club_abbreviation="SSS"
    )
    assert SiteConfiguration.objects.filter(club_name="Skyline Soaring").exists()


@pytest.mark.django_db
def test_update_siteconfiguration():
    c = SiteConfiguration.objects.create(
        club_name="Old Name", domain_name="example.org", club_abbreviation="SSS"
    )
    c.club_name = "New Name"
    c.save()
    c.refresh_from_db()
    assert c.club_name == "New Name"
