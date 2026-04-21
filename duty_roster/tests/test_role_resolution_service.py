import pytest

from duty_roster.models import (
    DutyQualificationRequirement,
    DutyRoleDefinition,
    MemberDutyQualification,
)
from duty_roster.utils.role_resolution import RoleResolutionService
from members.models import Member
from siteconfig.models import SiteConfiguration


@pytest.fixture
def site_config():
    return SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
    )


@pytest.fixture
def full_member():
    return Member.objects.create_user(
        username="member1",
        email="member1@example.com",
        password="password",
        membership_status="Full Member",
        instructor=True,
        towpilot=True,
        duty_officer=True,
        assistant_duty_officer=True,
        glider_rating="commercial",
    )


@pytest.mark.django_db
def test_get_enabled_roles_falls_back_to_legacy_defaults_without_dynamic_mode(
    site_config,
):
    site_config.schedule_instructors = False
    site_config.schedule_tow_pilots = False
    site_config.schedule_duty_officers = False
    site_config.schedule_assistant_duty_officers = False
    site_config.schedule_commercial_pilots = False
    site_config.save()

    service = RoleResolutionService(site_configuration=site_config)

    assert service.get_enabled_roles() == [
        "instructor",
        "duty_officer",
        "assistant_duty_officer",
        "towpilot",
    ]


@pytest.mark.django_db
def test_dynamic_role_labels_use_site_terminology_for_legacy_mapping(site_config):
    site_config.enable_dynamic_duty_roles = True
    site_config.towpilot_title = "Tug Driver"
    site_config.save()

    DutyRoleDefinition.objects.create(
        site_configuration=site_config,
        key="am_tow",
        display_name="AM Tow",
        is_active=True,
        sort_order=1,
        legacy_role_key="towpilot",
        shift_code="am",
    )

    service = RoleResolutionService(site_configuration=site_config)

    assert service.get_role_label("am_tow") == "Tug Driver"


@pytest.mark.django_db
def test_dynamic_role_eligibility_from_member_duty_qualification(
    site_config, full_member
):
    site_config.enable_dynamic_duty_roles = True
    site_config.save()

    role = DutyRoleDefinition.objects.create(
        site_configuration=site_config,
        key="pm_check_pilot",
        display_name="PM Check Pilot",
        is_active=True,
        sort_order=1,
        shift_code="pm",
    )
    DutyQualificationRequirement.objects.create(
        role_definition=role,
        requirement_type=DutyQualificationRequirement.TYPE_MEMBER_DUTY_QUAL,
        requirement_value="check_pilot_pm",
    )

    service = RoleResolutionService(site_configuration=site_config)

    assert service.is_member_eligible(full_member, "pm_check_pilot") is False

    MemberDutyQualification.objects.create(
        member=full_member,
        qualification_code="check_pilot_pm",
        is_qualified=True,
    )

    assert service.is_member_eligible(full_member, "pm_check_pilot") is True


@pytest.mark.django_db
def test_dynamic_role_eligibility_from_legacy_role_requirement(
    site_config, full_member
):
    site_config.enable_dynamic_duty_roles = True
    site_config.save()

    role = DutyRoleDefinition.objects.create(
        site_configuration=site_config,
        key="am_instructor",
        display_name="AM Instructor",
        is_active=True,
        sort_order=1,
        shift_code="am",
    )
    DutyQualificationRequirement.objects.create(
        role_definition=role,
        requirement_type=DutyQualificationRequirement.TYPE_LEGACY_ROLE_FLAG,
        requirement_value="instructor",
    )

    service = RoleResolutionService(site_configuration=site_config)

    assert service.is_member_eligible(full_member, "am_instructor") is True

    full_member.instructor = False
    full_member.save(update_fields=["instructor"])

    assert service.is_member_eligible(full_member, "am_instructor") is False
