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
def test_homepagecontent_view(client):
    page = HomePageContent.objects.create(
        title="Test", slug="test", content="<p>Hi</p>")
    url = reverse("cms:page", args=[page.slug])
    response = client.get(url)
    assert response.status_code == 200
    assert b"Hi" in response.content


@pytest.mark.django_db
def test_homepagecontent_404(client):
    url = reverse("cms:page", args=["does-not-exist"])
    response = client.get(url)
    assert response.status_code == 404
