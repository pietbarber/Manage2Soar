import pytest
from django.contrib.auth import get_user_model
from siteconfig.models import SiteConfiguration

User = get_user_model()


@pytest.mark.django_db
def test_create_siteconfiguration():
    config = SiteConfiguration.objects.create(
        club_name="Skyline Soaring", domain_name="example.org", club_abbreviation="SSS")
    assert SiteConfiguration.objects.filter(
        club_name="Skyline Soaring").exists()


@pytest.mark.django_db
def test_update_siteconfiguration():
    config = SiteConfiguration.objects.create(
        club_name="Old Name", domain_name="example.org", club_abbreviation="SSS")
    config.club_name = "New Name"
    config.save()
    config.refresh_from_db()
    assert config.club_name == "New Name"
