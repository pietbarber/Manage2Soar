import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import RequestFactory

from cms.admin import PageAdmin
from cms.models import Page

User = get_user_model()


@pytest.mark.django_db
def test_promoted_page_requires_navbar_rank():
    page = Page(
        title="Operations",
        slug="operations",
        is_public=True,
        promote_to_navbar=True,
        navbar_rank=None,
    )

    with pytest.raises(ValidationError) as exc:
        page.full_clean()

    assert "navbar_rank" in str(exc.value)


@pytest.mark.django_db
def test_effective_navbar_title_falls_back_to_page_title():
    page = Page.objects.create(
        title="Club Procedures",
        slug="club-procedures",
        is_public=True,
        promote_to_navbar=True,
        navbar_rank=10,
        navbar_title="",
    )

    assert page.effective_navbar_title() == "Club Procedures"


@pytest.mark.django_db
def test_effective_navbar_title_prefers_override_title():
    page = Page.objects.create(
        title="Club Procedures",
        slug="club-procedures-2",
        is_public=True,
        promote_to_navbar=True,
        navbar_rank=10,
        navbar_title="  Quick Links  ",
    )

    assert page.effective_navbar_title() == "Quick Links"


@pytest.mark.django_db
def test_effective_navbar_title_handles_none():
    page = Page(
        title="Fallback Title",
        slug="fallback-title",
        is_public=True,
        navbar_title=None,
    )

    assert page.effective_navbar_title() == "Fallback Title"


@pytest.mark.django_db
def test_page_admin_readonly_promotion_fields_for_non_webmaster():
    factory = RequestFactory()
    request = factory.get("/admin/cms/page/1/change/")

    director = User.objects.create_user(
        username="director_admin",
        password="testpass123",
        membership_status="Full Member",
    )
    director.director = True
    director.save()
    request.user = director

    readonly_fields = PageAdmin(Page, AdminSite()).get_readonly_fields(request)

    assert "promote_to_navbar" in readonly_fields
    assert "navbar_title" in readonly_fields
    assert "navbar_rank" in readonly_fields


@pytest.mark.django_db
def test_page_admin_promotion_fields_editable_for_webmaster():
    factory = RequestFactory()
    request = factory.get("/admin/cms/page/1/change/")

    webmaster = User.objects.create_user(
        username="webmaster_admin",
        password="testpass123",
        membership_status="Full Member",
    )
    webmaster.webmaster = True
    webmaster.save()
    request.user = webmaster

    readonly_fields = PageAdmin(Page, AdminSite()).get_readonly_fields(request)

    assert "promote_to_navbar" not in readonly_fields
    assert "navbar_title" not in readonly_fields
    assert "navbar_rank" not in readonly_fields


@pytest.mark.django_db
def test_page_admin_navbar_fieldset_description_mentions_superusers():
    description = PageAdmin(Page, AdminSite()).fieldsets[3][1]["description"]
    assert "webmasters and superusers" in description


@pytest.mark.django_db
def test_promote_to_navbar_help_text_mentions_superusers():
    help_text = Page._meta.get_field("promote_to_navbar").help_text
    assert "webmasters and superusers" in help_text


@pytest.mark.django_db
def test_create_promoted_page_without_rank_fails_on_save():
    with pytest.raises(ValidationError):
        Page.objects.create(
            title="Broken Promotion",
            slug="broken-promotion",
            is_public=True,
            promote_to_navbar=True,
            navbar_rank=None,
        )


@pytest.mark.django_db
def test_create_promoted_page_with_invalid_rank_fails_on_save():
    with pytest.raises(ValidationError):
        Page.objects.create(
            title="Bad Rank",
            slug="bad-rank",
            is_public=True,
            promote_to_navbar=True,
            navbar_rank=0,
        )
