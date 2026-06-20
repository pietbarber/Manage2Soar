import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_homepage_anonymous(client):
    """Anonymous users can load the site homepage at root URL."""
    url = reverse("home")
    resp = client.get(url)
    assert resp.status_code == 200


@pytest.mark.django_db
def test_homepage_logged_in(client, django_user_model):
    """A logged-in user can load the site homepage at root URL."""
    user = django_user_model.objects.create_user(username="testuser", password="pass")
    client.login(username="testuser", password="pass")
    url = reverse("home")
    resp = client.get(url)
    assert resp.status_code == 200


@pytest.mark.django_db
def test_cms_resources_page(client, django_user_model):
    """Test that CMS resources page loads correctly at /cms/."""
    django_user_model.objects.create_user(username="testuser", password="pass")
    client.login(username="testuser", password="pass")
    url = reverse("cms:resources")
    resp = client.get(url)
    assert resp.status_code == 200


@pytest.mark.django_db
def test_resources_link_for_logged_in_user(client, django_user_model):
    """When logged in, the nav contains the Resources link pointing to cms:resources."""
    user = django_user_model.objects.create_user(
        username="resource_user", password="pass"
    )
    client.login(username="resource_user", password="pass")
    # load homepage and inspect the rendered HTML for the resources link
    resp = client.get(reverse("home"))
    assert resp.status_code == 200
    content = resp.content.decode("utf-8")
    # look for an href that points to the cms resources url
    assert 'href="/cms/"' in content or "href=\"{% url 'cms:resources' %}\"" in content
    # ensure Resources label exists somewhere
    assert "Resources" in content


@pytest.mark.django_db
def test_equipment_link_visible_for_active_member(client, django_user_model):
    user = django_user_model.objects.create_user(
        username="active_member_equipment",
        password="pass",
        membership_status="Full Member",
    )
    client.force_login(user)

    resp = client.get(reverse("home"))
    assert resp.status_code == 200

    content = resp.content.decode("utf-8")
    assert "Gliders and Towplanes" in content


@pytest.mark.django_db
def test_equipment_link_hidden_for_non_active_non_superuser(client, django_user_model):
    user = django_user_model.objects.create_user(
        username="inactive_member_equipment",
        password="pass",
        membership_status="Prospective Member",
    )
    client.force_login(user)

    resp = client.get(reverse("home"))
    assert resp.status_code == 200

    content = resp.content.decode("utf-8")
    assert "Gliders and Towplanes" not in content


@pytest.mark.django_db
def test_equipment_link_visible_for_superuser_even_if_not_active_member(
    client, django_user_model
):
    user = django_user_model.objects.create_user(
        username="superuser_equipment",
        password="pass",
        membership_status="Prospective Member",
        is_superuser=True,
        is_staff=True,
    )
    client.force_login(user)

    resp = client.get(reverse("home"))
    assert resp.status_code == 200

    content = resp.content.decode("utf-8")
    assert "Gliders and Towplanes" in content
