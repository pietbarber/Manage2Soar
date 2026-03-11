import pytest
from django.urls import reverse

from cms.models import HomePageContent, Page


@pytest.mark.django_db
def test_anonymous_navbar_shows_resources_drawer(client):
    HomePageContent.objects.create(title="Home", slug="home", content="<p>Public</p>")

    response = client.get(reverse("home"))

    assert response.status_code == 200
    assert b"Resources" in response.content
    assert b"Document Root" in response.content
    assert b"Report Website Issue" not in response.content


@pytest.mark.django_db
def test_member_navbar_shows_report_issue_and_no_welcome_prefix(
    client, django_user_model
):
    HomePageContent.objects.create(title="Home", slug="home", content="<p>Public</p>")
    HomePageContent.objects.create(
        title="Member Home",
        slug="member-home",
        audience="member",
        content="<p>Member</p>",
    )
    user = django_user_model.objects.create_user(
        username="navmember",
        password="testpass123",
        membership_status="Full Member",
        first_name="Nav",
        last_name="Member",
    )

    client.login(username="navmember", password="testpass123")
    response = client.get(reverse("home"))

    assert response.status_code == 200
    assert b"Resources" in response.content
    assert b"Report Website Issue" in response.content
    assert b"Welcome," not in response.content


@pytest.mark.django_db
def test_resources_drawer_lists_promoted_page(client):
    HomePageContent.objects.create(title="Home", slug="home", content="<p>Public</p>")
    Page.objects.create(
        title="Operations",
        slug="operations",
        is_public=True,
        promote_to_navbar=True,
        navbar_title="Operations Docs",
        navbar_rank=2,
    )

    response = client.get(reverse("home"))

    assert response.status_code == 200
    assert b"Operations Docs" in response.content


@pytest.mark.django_db
def test_member_navbar_resources_includes_footer_links(client, django_user_model):
    HomePageContent.objects.create(title="Home", slug="home", content="<p>Public</p>")
    HomePageContent.objects.create(
        title="Member Home",
        slug="member-home",
        audience="member",
        content="<p>Member</p>",
    )
    HomePageContent.objects.create(
        title="Footer",
        slug="footer",
        audience="member",
        content='<p><a href="https://example.com/weather">Weather</a></p>',
    )
    user = django_user_model.objects.create_user(
        username="memberfooter",
        password="testpass123",
        membership_status="Full Member",
    )

    client.login(username="memberfooter", password="testpass123")
    response = client.get(reverse("home"))

    assert response.status_code == 200
    assert b"Weather" in response.content
