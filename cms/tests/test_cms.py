import pytest
from django.contrib.auth import get_user_model

from cms.models import HomePageContent

User = get_user_model()


@pytest.mark.django_db
def test_create_homepage_content():
    HomePageContent.objects.create(
        title="Test Page", slug="test-page", content="<p>Hello</p>"
    )
    assert HomePageContent.objects.filter(slug="test-page").exists()


@pytest.mark.django_db
def test_homepagecontent_slug_unique():
    HomePageContent.objects.create(title="Page1", slug="unique-slug", content="A")
    with pytest.raises(Exception):
        HomePageContent.objects.create(title="Page2", slug="unique-slug", content="B")


@pytest.mark.django_db
def test_homepagecontent_view_visitor(client):
    HomePageContent.objects.create(
        title="Test", slug="home", content="<p>Hi Visitor</p>"
    )
    response = client.get("/")
    assert response.status_code == 200
    assert b"Hi Visitor" in response.content


@pytest.mark.django_db
def test_homepagecontent_view_logged_in(client, django_user_model):
    django_user_model.objects.create_user(
        username="user", password="pass", membership_status="Full Member"
    )
    client.login(username="user", password="pass")
    HomePageContent.objects.create(
        title="Test", slug="member-home", audience="member", content="<p>Hi User</p>"
    )
    response = client.get("/")
    assert response.status_code == 200
    assert b"Hi User" in response.content


@pytest.mark.django_db
def test_homepagecontent_public_override_for_logged_in_member(
    client, django_user_model
):
    django_user_model.objects.create_user(
        username="member", password="pass", membership_status="Full Member"
    )
    client.login(username="member", password="pass")
    HomePageContent.objects.create(
        title="Public Home",
        slug="home",
        audience="public",
        content="<p>Public Content</p>",
    )
    HomePageContent.objects.create(
        title="Member Home",
        slug="member-home",
        audience="member",
        content="<p>Member Content</p>",
    )

    response = client.get("/?view=public")
    assert response.status_code == 200
    assert b"Public Content" in response.content
    assert b"Member Content" not in response.content


@pytest.mark.django_db
def test_homepage_template_does_not_render_hardcoded_h1(client):
    HomePageContent.objects.create(
        title="Skyline Soaring Club",
        slug="home",
        audience="public",
        content="<p>Homepage body content</p>",
    )

    response = client.get("/")
    assert response.status_code == 200
    assert b'<h1 style="margin:0">Skyline Soaring Club</h1>' not in response.content


@pytest.mark.django_db
def test_homepagecontent_404(client):
    # Since there is no detail view, just check a non-existent path returns 404
    response = client.get("/nonexistent-path/")
    assert response.status_code == 404
