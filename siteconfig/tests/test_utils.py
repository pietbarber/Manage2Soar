import pytest

from duty_roster.models import DutyRoleDefinition
from siteconfig.models import SiteConfiguration
from siteconfig.utils import get_role_title


@pytest.mark.django_db
def test_get_role_title_commercial_pilot_without_config():
    assert get_role_title("commercial_pilot") == "Commercial Pilot"


@pytest.mark.django_db
def test_get_role_title_commercial_pilot_with_config():
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        commercial_pilot_title="Ride Pilot",
    )

    assert get_role_title("commercial_pilot") == "Ride Pilot"


@pytest.mark.django_db
def test_get_role_title_dynamic_role_uses_display_name_when_enabled():
    config = SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        enable_dynamic_duty_roles=True,
    )
    DutyRoleDefinition.objects.create(
        site_configuration=config,
        key="am_tow",
        display_name="AM Tow",
        is_active=True,
    )

    assert get_role_title("am_tow") == "AM Tow"


@pytest.mark.django_db
def test_get_role_title_dynamic_role_prefers_legacy_terminology_mapping():
    config = SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        enable_dynamic_duty_roles=True,
        towpilot_title="Tug Driver",
    )
    DutyRoleDefinition.objects.create(
        site_configuration=config,
        key="pm_tow",
        display_name="PM Tow",
        is_active=True,
        legacy_role_key="towpilot",
    )

    assert get_role_title("pm_tow") == "Tug Driver"
