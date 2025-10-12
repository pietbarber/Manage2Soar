import pytest
from django.urls import reverse
from cms.models import HomePageContent
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
def test_create_homepage_content():
    page = HomePageContent.objects.create(
        title="Test Page", slug="test-page", content="<p>Hello</p>")
    assert HomePageContent.objects.filter(slug="test-page").exists()


@pytest.mark.django_db
def test_homepagecontent_slug_unique():
    HomePageContent.objects.create(
        title="Page1", slug="unique-slug", content="A")
    with pytest.raises(Exception):
        HomePageContent.objects.create(
            title="Page2", slug="unique-slug", content="B")


@pytest.mark.django_db
@pytest.mark.django_db
def test_homepagecontent_view_visitor(client):
    HomePageContent.objects.create(
        title="Test", slug="test", content="<p>Hi Visitor</p>")
    response = client.get("/")
    assert response.status_code == 200
    assert b"Hi Visitor" in response.content


@pytest.mark.django_db
def test_homepagecontent_view_logged_in(client, django_user_model):
    user = django_user_model.objects.create_user(
        username="user", password="pass")
    client.login(username="user", password="pass")
    HomePageContent.objects.create(
        title="Test", slug="test", content="<p>Hi User</p>")
    response = client.get("/")
    assert response.status_code == 200
    assert b"Hi User" in response.content


@pytest.mark.django_db
def test_homepagecontent_404(client):
    # Since there is no detail view, just check a non-existent path returns 404
    response = client.get("/nonexistent-path/")
    assert response.status_code == 404
