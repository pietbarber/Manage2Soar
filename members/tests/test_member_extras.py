import pytest
from django.core.cache import cache

from members.templatetags import member_extras
from members.utils.roles import get_member_role_metadata
from siteconfig.cache_contract import SITECONFIG_DEFERRED_CACHE_KEY
from siteconfig.models import SiteConfiguration


class DummyMember:
    instructor = True


@pytest.mark.django_db
def test_get_member_role_metadata_uses_cached_site_configuration(
    django_assert_num_queries,
):
    cache.delete(SITECONFIG_DEFERRED_CACHE_KEY)
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.example.com",
        club_abbreviation="TC",
        instructor_title="Chief Instructor",
    )

    with django_assert_num_queries(1):
        first = get_member_role_metadata()
    with django_assert_num_queries(0):
        second = get_member_role_metadata()

    assert first[1]["label"] == "Chief Instructor"
    assert second[1]["label"] == "Chief Instructor"


@pytest.mark.django_db
def test_get_member_role_metadata_uses_deferred_siteconfig_cache_key():
    cache.delete(SITECONFIG_DEFERRED_CACHE_KEY)
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.example.com",
        club_abbreviation="TC",
        instructor_title="Chief Instructor",
        webcam_snapshot_url="https://user:pass@example.com/webcam.jpg",
    )

    get_member_role_metadata()

    assert cache.get(SITECONFIG_DEFERRED_CACHE_KEY) is not None


@pytest.mark.django_db
def test_get_member_role_metadata_caches_missing_configuration(
    django_assert_num_queries,
):
    SiteConfiguration.objects.all().delete()
    cache.delete(SITECONFIG_DEFERRED_CACHE_KEY)

    with django_assert_num_queries(1):
        first = get_member_role_metadata()
    with django_assert_num_queries(0):
        second = get_member_role_metadata()

    assert first[0]["label"] == "Tow Pilot"
    assert second[0]["label"] == "Tow Pilot"


@pytest.mark.django_db
def test_render_duties_escapes_configured_role_labels(monkeypatch):
    monkeypatch.setattr(
        member_extras,
        "get_member_role_metadata",
        lambda: [
            {
                "value": "instructor",
                "field": "instructor",
                "label": '<script>alert("x")</script>',
                "icon": "bi-mortarboard",
                "badge_class": "bg-primary",
                "show_in_duties": True,
            }
        ],
    )

    rendered = str(member_extras.render_duties(DummyMember()))

    assert "<script>" not in rendered
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in rendered
