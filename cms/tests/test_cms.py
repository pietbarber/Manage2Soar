import pytest
from django.urls import reverse
from cms.models import Page
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
def test_create_cms_page():
    page = Page.objects.create(
        title="Test Page", slug="test-page", content="<p>Hello</p>")
    assert Page.objects.filter(slug="test-page").exists()


@pytest.mark.django_db
def test_cms_page_slug_unique():
    Page.objects.create(title="Page1", slug="unique-slug", content="A")
    with pytest.raises(Exception):
        Page.objects.create(title="Page2", slug="unique-slug", content="B")


@pytest.mark.django_db
def test_cms_page_view(client):
    page = Page.objects.create(title="Test", slug="test", content="<p>Hi</p>")
    url = reverse("cms:page", args=[page.slug])
    response = client.get(url)
    assert response.status_code == 200
    assert b"Hi" in response.content


@pytest.mark.django_db
def test_cms_page_404(client):
    url = reverse("cms:page", args=["does-not-exist"])
    response = client.get(url)
    assert response.status_code == 404
