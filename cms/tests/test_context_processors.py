"""
Tests for cms.context_processors — specifically the google_oauth_configured flag
and its effect on the login page template.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import override_settings
from django.test.client import RequestFactory
from django.urls import reverse

from cms.context_processors import footer_content
from cms.models import HomePageContent, Page
from siteconfig.models import SiteConfiguration

User = get_user_model()


@pytest.mark.django_db
def test_google_oauth_configured_true_when_key_set(client):
    """google_oauth_configured is True when SOCIAL_AUTH_GOOGLE_OAUTH2_KEY is set."""
    with override_settings(SOCIAL_AUTH_GOOGLE_OAUTH2_KEY="fake-key"):
        response = client.get(reverse("login"))
    assert response.context["google_oauth_configured"] is True


@pytest.mark.django_db
def test_google_oauth_configured_false_when_key_missing(client):
    """google_oauth_configured is False when SOCIAL_AUTH_GOOGLE_OAUTH2_KEY is None."""
    with override_settings(SOCIAL_AUTH_GOOGLE_OAUTH2_KEY=None):
        response = client.get(reverse("login"))
    assert response.context["google_oauth_configured"] is False


@pytest.mark.django_db
def test_login_page_shows_google_button_when_configured(client):
    """The login page renders the Sign in with Google button when OAuth is configured."""
    with override_settings(SOCIAL_AUTH_GOOGLE_OAUTH2_KEY="fake-key"):
        response = client.get(reverse("login"))
    assert b"Sign in with Google" in response.content


@pytest.mark.django_db
def test_login_page_hides_google_button_when_not_configured(client):
    """The login page omits the Sign in with Google button when OAuth is not configured."""
    with override_settings(SOCIAL_AUTH_GOOGLE_OAUTH2_KEY=None):
        response = client.get(reverse("login"))
    assert b"Sign in with Google" not in response.content


@pytest.mark.django_db
def test_resources_nav_includes_document_root_for_anonymous():
    request = RequestFactory().get("/")
    request.user = AnonymousUser()

    context = footer_content(request)
    titles = [item["title"] for item in context["resources_nav_items"]]

    assert "Document Root" in titles


@pytest.mark.django_db
def test_resources_nav_includes_promoted_public_page_for_anonymous():
    Page.objects.create(
        title="Weather",
        slug="weather",
        is_public=True,
        promote_to_navbar=True,
        navbar_rank=5,
        navbar_title="Weather Links",
    )

    request = RequestFactory().get("/")
    request.user = AnonymousUser()
    context = footer_content(request)

    titles = [item["title"] for item in context["resources_nav_items"]]
    assert "Weather Links" in titles


@pytest.mark.django_db
def test_resources_nav_excludes_private_promoted_page_for_anonymous():
    Page.objects.create(
        title="Board Docs",
        slug="board-docs",
        is_public=False,
        promote_to_navbar=True,
        navbar_rank=6,
    )

    request = RequestFactory().get("/")
    request.user = AnonymousUser()
    context = footer_content(request)

    titles = [item["title"] for item in context["resources_nav_items"]]
    assert "Board Docs" not in titles


@pytest.mark.django_db
def test_resources_nav_excludes_member_utility_links_for_anonymous():
    request = RequestFactory().get("/")
    request.user = AnonymousUser()
    context = footer_content(request)

    titles = [item["title"] for item in context["resources_nav_items"]]
    assert "Gliders and Towplanes" not in titles
    assert "Report Website Issue" not in titles
    assert "Safety Suggestion Box" not in titles
    assert "Safety Dashboard" not in titles
    assert "Suggestion Box Reports" not in titles
    assert "Webcam" not in titles


@pytest.mark.django_db
def test_resources_nav_includes_member_only_links_for_active_member():
    member = User.objects.create_user(
        username="member_nav",
        password="testpass123",
        membership_status="Full Member",
    )
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.example.com",
        club_abbreviation="TC",
        webcam_snapshot_url="https://example.com/webcam.jpg",
    )

    request = RequestFactory().get("/")
    request.user = member
    context = footer_content(request)

    titles = [item["title"] for item in context["resources_nav_items"]]
    assert "Report Website Issue" in titles
    assert "Safety Suggestion Box" in titles
    assert "Webcam" in titles


@pytest.mark.django_db
def test_resources_nav_includes_member_footer_links_for_active_member():
    member = User.objects.create_user(
        username="member_footer_links",
        password="testpass123",
        membership_status="Full Member",
    )
    HomePageContent.objects.create(
        title="Footer",
        slug="footer",
        audience="member",
        content=(
            '<p><a href="https://example.com/weather">Weather</a> '
            '<a href="https://www.weglide.org">WeGlide</a></p>'
        ),
    )

    request = RequestFactory().get("/")
    request.user = member
    context = footer_content(request)

    titles = [item["title"] for item in context["resources_nav_items"]]
    assert "Weather" in titles
    assert "WeGlide" in titles


@pytest.mark.django_db
def test_resources_nav_dedupes_report_issue_link_from_footer():
    member = User.objects.create_user(
        username="member_footer_dedupe",
        password="testpass123",
        membership_status="Full Member",
    )
    HomePageContent.objects.create(
        title="Footer",
        slug="footer",
        audience="member",
        content='<p><a href="/cms/feedback/">Report Website Issue</a></p>',
    )

    request = RequestFactory().get("/")
    request.user = member
    context = footer_content(request)

    report_issue_items = [
        item
        for item in context["resources_nav_items"]
        if item["url"] == "/cms/feedback/"
    ]
    assert len(report_issue_items) == 1


@pytest.mark.django_db
def test_resources_nav_includes_safety_team_links_for_safety_officer():
    safety_officer = User.objects.create_user(
        username="safety_nav",
        password="testpass123",
        membership_status="Full Member",
    )
    safety_officer.safety_officer = True
    safety_officer.save()

    request = RequestFactory().get("/")
    request.user = safety_officer
    context = footer_content(request)

    titles = [item["title"] for item in context["resources_nav_items"]]
    assert "Safety Dashboard" in titles
    assert "Suggestion Box Reports" in titles


@pytest.mark.django_db
def test_resources_nav_filters_unsafe_footer_link_schemes():
    member = User.objects.create_user(
        username="member_footer_schemes",
        password="testpass123",
        membership_status="Full Member",
    )
    HomePageContent.objects.create(
        title="Footer",
        slug="footer",
        audience="member",
        content=(
            '<p><a href="javascript:alert(1)">Bad JS</a> '
            '<a href="data:text/plain,boom">Bad Data</a> '
            '<a href="/cms/feedback/">Good Relative</a> '
            '<a href="https://example.com/weather">Good HTTPS</a></p>'
        ),
    )

    request = RequestFactory().get("/")
    request.user = member
    context = footer_content(request)

    titles = [item["title"] for item in context["resources_nav_items"]]
    urls = [item["url"] for item in context["resources_nav_items"]]
    assert "Bad JS" not in titles
    assert "Bad Data" not in titles
    assert "Good HTTPS" in titles
    assert "/cms/feedback/" in urls


@pytest.mark.django_db
def test_resources_nav_ignores_promoted_pages_with_null_rank():
    page = Page.objects.create(
        title="Ranked Page",
        slug="ranked-page",
        is_public=True,
        promote_to_navbar=True,
        navbar_rank=10,
    )
    Page.objects.filter(pk=page.pk).update(navbar_rank=None)

    request = RequestFactory().get("/")
    request.user = AnonymousUser()
    context = footer_content(request)

    titles = [item["title"] for item in context["resources_nav_items"]]
    assert "Ranked Page" not in titles
