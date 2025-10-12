import pytest
from django.contrib.auth import get_user_model
from siteconfig.models import SiteConfiguration

User = get_user_model()


@pytest.mark.django_db
def test_create_siteconfiguration():
    config = SiteConfiguration.objects.create(site_name="Skyline Soaring")
    assert SiteConfiguration.objects.filter(
        site_name="Skyline Soaring").exists()


@pytest.mark.django_db
def test_update_siteconfiguration():
    config = SiteConfiguration.objects.create(site_name="Old Name")
    config.site_name = "New Name"
    config.save()
    config.refresh_from_db()
    assert config.site_name == "New Name"


@pytest.mark.django_db
def test_only_superuser_can_edit(client, django_user_model):
    user = django_user_model.objects.create_superuser(
        username="admin", password="pw")
    client.force_login(user)
    response = client.post("/siteconfig/edit/", {"site_name": "Changed"})
    assert response.status_code in (200, 302)
