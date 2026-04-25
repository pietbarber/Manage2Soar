from datetime import date
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.messages import get_messages
from django.urls import reverse

from duty_roster.models import DutyAssignment, DutyAssignmentRole, DutyRoleDefinition
from logsheet.models import Airfield
from members.models import Member
from siteconfig.models import SiteConfiguration


@pytest.fixture
def rostermeister():
    user = Member.objects.create_user(
        username="rm_dynamic",
        email="rm_dynamic@test.com",
        password="testpass123",
        first_name="Roster",
        last_name="Meister",
        is_active=True,
        membership_status="Full Member",
        joined_club=date.today(),
    )
    user.rostermeister = True
    user.save()
    return user


@pytest.fixture
def helper_member():
    return Member.objects.create_user(
        username="helper_dynamic",
        email="helper_dynamic@test.com",
        password="testpass123",
        first_name="Helper",
        last_name="Member",
        is_active=True,
        membership_status="Full Member",
        joined_club=date.today(),
        instructor=True,
    )


@pytest.mark.django_db
def test_propose_roster_uses_dynamic_role_keys_when_feature_enabled(
    client, rostermeister
):
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
        sort_order=10,
    )

    client.login(username="rm_dynamic", password="testpass123")
    url = reverse("duty_roster:propose_roster")

    with patch("duty_roster.views.generate_roster", return_value=[]) as mock_generate:
        response = client.get(url, {"year": 2026, "month": 3})

    assert response.status_code == 200
    assert response.context["enabled_roles"] == ["am_tow"]
    assert mock_generate.called
    assert mock_generate.call_args.kwargs["roles"] == ["am_tow"]


@pytest.mark.django_db
def test_propose_roster_uses_dynamic_display_names_for_dynamic_keys(
    client, rostermeister
):
    config = SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        enable_dynamic_duty_roles=True,
        towpilot_title="Tow Pilot",
    )
    DutyRoleDefinition.objects.create(
        site_configuration=config,
        key="am_tow",
        display_name="AM Tow",
        legacy_role_key="towpilot",
        is_active=True,
        sort_order=10,
    )
    DutyRoleDefinition.objects.create(
        site_configuration=config,
        key="pm_tow",
        display_name="PM Tow",
        legacy_role_key="towpilot",
        is_active=True,
        sort_order=20,
    )

    client.login(username="rm_dynamic", password="testpass123")
    url = reverse("duty_roster:propose_roster")

    with patch("duty_roster.views.generate_roster", return_value=[]):
        response = client.get(url, {"year": 2026, "month": 3})

    assert response.status_code == 200
    assert response.context["role_labels"]["am_tow"] == "AM Tow"
    assert response.context["role_labels"]["pm_tow"] == "PM Tow"


@pytest.mark.django_db
def test_propose_roster_legacy_role_discovery_unchanged_when_dynamic_disabled(
    client, rostermeister
):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        enable_dynamic_duty_roles=False,
        schedule_instructors=True,
        schedule_tow_pilots=False,
        schedule_duty_officers=False,
        schedule_assistant_duty_officers=False,
        schedule_commercial_pilots=False,
    )

    client.login(username="rm_dynamic", password="testpass123")
    url = reverse("duty_roster:propose_roster")

    with patch("duty_roster.views.generate_roster", return_value=[]) as mock_generate:
        response = client.get(url, {"year": 2026, "month": 3})

    assert response.status_code == 200
    assert response.context["enabled_roles"] == ["instructor"]
    assert mock_generate.called
    assert mock_generate.call_args.kwargs["roles"] == ["instructor"]


@pytest.mark.django_db
def test_publish_warns_and_skips_unmappable_dynamic_roles(
    client, rostermeister, helper_member
):
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
        sort_order=10,
    )

    Airfield.objects.create(
        id=settings.DEFAULT_AIRFIELD_ID,
        name="Test Field",
        identifier="TEST",
    )

    client.login(username="rm_dynamic", password="testpass123")
    url = reverse("duty_roster:propose_roster")

    session = client.session
    session["proposed_roster"] = [
        {
            "date": "2026-03-07",
            "slots": {"am_tow": str(helper_member.id)},
            "diagnostics": {},
        }
    ]
    session["proposed_roster_range"] = {
        "start_date": "2026-03-01",
        "end_date": "2026-03-31",
    }
    session.save()

    with patch(
        "duty_roster.utils.email.send_roster_published_notifications",
        return_value={"sent_count": 0, "errors": []},
    ):
        response = client.post(
            url,
            {
                "year": 2026,
                "month": 3,
                "action": "publish",
            },
            follow=True,
        )

    assert response.status_code == 200
    messages = [str(m) for m in get_messages(response.wsgi_request)]
    assert any("normalized assignment rows only" in message for message in messages)

    assignment = DutyAssignment.objects.get(date=date(2026, 3, 7))
    assert assignment.instructor is None
    assert assignment.tow_pilot is None
    assert assignment.duty_officer is None
    assert assignment.assistant_duty_officer is None
    assert assignment.commercial_pilot is None

    role_row = DutyAssignmentRole.objects.get(assignment=assignment, role_key="am_tow")
    assert role_row.member == helper_member
    assert role_row.role_definition is not None


@pytest.mark.django_db
def test_publish_dual_writes_legacy_and_normalized_rows(
    client, rostermeister, helper_member
):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        enable_dynamic_duty_roles=False,
        schedule_instructors=True,
    )

    Airfield.objects.create(
        id=settings.DEFAULT_AIRFIELD_ID,
        name="Test Field",
        identifier="TEST",
    )

    client.login(username="rm_dynamic", password="testpass123")
    url = reverse("duty_roster:propose_roster")

    session = client.session
    session["proposed_roster"] = [
        {
            "date": "2026-03-14",
            "slots": {"instructor": str(helper_member.id)},
            "diagnostics": {},
        }
    ]
    session["proposed_roster_range"] = {
        "start_date": "2026-03-01",
        "end_date": "2026-03-31",
    }
    session.save()

    with patch(
        "duty_roster.utils.email.send_roster_published_notifications",
        return_value={"sent_count": 0, "errors": []},
    ):
        response = client.post(
            url,
            {
                "year": 2026,
                "month": 3,
                "action": "publish",
            },
            follow=True,
        )

    assert response.status_code == 200

    assignment = DutyAssignment.objects.get(date=date(2026, 3, 14))
    assert assignment.instructor == helper_member

    role_row = DutyAssignmentRole.objects.get(
        assignment=assignment,
        role_key="instructor",
    )
    assert role_row.member == helper_member
    assert role_row.legacy_role_key == "instructor"


@pytest.mark.django_db
def test_publish_dynamic_role_with_legacy_mapping_writes_both_paths(
    client, rostermeister, helper_member
):
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
        legacy_role_key="towpilot",
        is_active=True,
        sort_order=10,
    )

    Airfield.objects.create(
        id=settings.DEFAULT_AIRFIELD_ID,
        name="Test Field",
        identifier="TEST",
    )

    client.login(username="rm_dynamic", password="testpass123")
    url = reverse("duty_roster:propose_roster")

    session = client.session
    session["proposed_roster"] = [
        {
            "date": "2026-03-21",
            "slots": {"am_tow": str(helper_member.id)},
            "diagnostics": {},
        }
    ]
    session["proposed_roster_range"] = {
        "start_date": "2026-03-01",
        "end_date": "2026-03-31",
    }
    session.save()

    with patch(
        "duty_roster.utils.email.send_roster_published_notifications",
        return_value={"sent_count": 0, "errors": []},
    ):
        response = client.post(
            url,
            {
                "year": 2026,
                "month": 3,
                "action": "publish",
            },
            follow=True,
        )

    assert response.status_code == 200

    assignment = DutyAssignment.objects.get(date=date(2026, 3, 21))
    assert assignment.tow_pilot == helper_member

    dynamic_row = DutyAssignmentRole.objects.get(
        assignment=assignment, role_key="am_tow"
    )
    assert dynamic_row.member == helper_member
    assert dynamic_row.legacy_role_key == "towpilot"
