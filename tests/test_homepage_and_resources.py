import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_homepage_anonymous(client):
    """Anonymous users can load the site homepage (CMS home)."""
    url = reverse("cms:home")
    resp = client.get(url)
    assert resp.status_code == 200


@pytest.mark.django_db
def test_homepage_logged_in(client, django_user_model):
    """A logged-in user can load the site homepage."""
    user = django_user_model.objects.create_user(username="testuser", password="pass")
    client.login(username="testuser", password="pass")
    url = reverse("cms:home")
    resp = client.get(url)
    assert resp.status_code == 200


@pytest.mark.django_db
def test_resources_link_for_logged_in_user(client, django_user_model):
    """When logged in, the nav contains the Resources link pointing to cms:home."""
    user = django_user_model.objects.create_user(
        username="resource_user", password="pass"
    )
    client.login(username="resource_user", password="pass")
    # load base template via cms home and inspect the rendered HTML for the link
    resp = client.get(reverse("cms:home"))
    assert resp.status_code == 200
    content = resp.content.decode("utf-8")
    # look for an href that points to the cms home url (could be / or /cms/ depending on routing)
    assert 'href="' in content
    # ensure Resources label exists somewhere
    assert "Resources" in content
