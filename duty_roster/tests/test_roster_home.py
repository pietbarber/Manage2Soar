"""
Tests for the ``roster_home`` view (Issue #1120).

``roster_home`` is the public app index ("Fill a Roster Hole").  It lists
open duty-role slots in the current + next calendar month that the requesting
member is qualified to fill.

Key behaviors under test:
* Anonymous users get a 200 response with an inviting empty state.
* Authenticated qualified members see holes for each role they hold.
* Authenticated members without the qualification do NOT see that hole.
* The flag-off (``schedule_instructors=False``) case still lists the hole
  for a qualified member (Issue #1120 core fix).
* Each opportunity's ``volunteer_url`` points at ``volunteer_fill_role``.
"""

from datetime import date, timedelta

import pytest
from django.urls import reverse

from duty_roster.models import DutyAssignment
from siteconfig.models import SiteConfiguration

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**kwargs):
    defaults = dict(
        club_name="Test Club",
        domain_name="test.org",
        club_abbreviation="TC",
        schedule_instructors=False,
        schedule_tow_pilots=False,
        schedule_duty_officers=False,
        schedule_assistant_duty_officers=False,
        schedule_commercial_pilots=False,
    )
    defaults.update(kwargs)
    existing = SiteConfiguration.objects.first()
    if existing:
        for k, v in defaults.items():
            setattr(existing, k, v)
        existing.save()
        return existing
    return SiteConfiguration.objects.create(**defaults)


def _make_user(django_user_model, username="member", **kwargs):
    defaults = dict(
        email=f"{username}@example.com",
        password="password",
        membership_status="Full Member",
    )
    defaults.update(kwargs)
    return django_user_model.objects.create_user(username=username, **defaults)


def _future_assignment():
    future = date.today() + timedelta(days=7)
    assignment, _ = DutyAssignment.objects.get_or_create(date=future)
    return assignment


def _home_url():
    return reverse("duty_roster:roster_home")


# ---------------------------------------------------------------------------
# Anonymous behavior
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_roster_home_anonymous_200(client):
    """Anonymous visitor gets 200 and the inviting empty state."""
    _make_config()
    assignment = _future_assignment()
    # Ensure there is an open hole (no instructor assigned)
    assignment.instructor = None
    assignment.tow_pilot = None
    assignment.save(update_fields=["instructor", "tow_pilot"])

    response = client.get(_home_url())
    assert response.status_code == 200
    # Anonymous context: no opportunities listed.
    assert response.context["volunteer_opportunities"] == []
    assert response.context["is_authenticated"] is False


@pytest.mark.django_db
def test_roster_home_anonymous_shows_sign_in(client):
    """Anonymous visitor sees the sign-in call-to-action."""
    _make_config()
    _future_assignment()

    response = client.get(_home_url())
    assert response.status_code == 200
    assert b"Sign in" in response.content
    # And no volunteer table rows.
    assert (
        b"Volunteer" not in response.content
        or b"Sign in to volunteer" in response.content
    )


# ---------------------------------------------------------------------------
# Authenticated member behavior
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_roster_home_lists_qualified_instructor(client, django_user_model):
    """Qualified instructor sees the open instructor slot."""
    _make_config(schedule_instructors=True)
    user = _make_user(django_user_model, instructor=True)
    assignment = _future_assignment()

    client.force_login(user)
    response = client.get(_home_url())

    assert response.status_code == 200
    opportunities = response.context["volunteer_opportunities"]
    assert len(opportunities) >= 1
    # Find the instructor opportunity.
    instr_opp = next(
        (o for o in opportunities if o["role_label"] in ("Instructor",)),
        None,
    )
    # Fallback: role_label may be the config title.
    if instr_opp is None:
        instr_opp = next(
            (
                o
                for o in opportunities
                if "instructor" in str(o.get("role_label", "")).lower()
            ),
            None,
        )
    assert instr_opp is not None
    # The volunteer_url points at volunteer_fill_role.
    assert "/volunteer-fill/" in instr_opp["volunteer_url"]
    assert f"/{assignment.id}/instructor/" in instr_opp["volunteer_url"]


@pytest.mark.django_db
def test_roster_home_lists_qualified_tow_pilot(client, django_user_model):
    """Qualified tow pilot sees the open tow-pilot slot."""
    _make_config(schedule_tow_pilots=True)
    user = _make_user(django_user_model, towpilot=True)
    assignment = _future_assignment()

    client.force_login(user)
    response = client.get(_home_url())

    assert response.status_code == 200
    opportunities = response.context["volunteer_opportunities"]
    assert len(opportunities) >= 1
    tow_opp = next(
        (o for o in opportunities if "tow" in str(o.get("role_label", "")).lower()),
        None,
    )
    assert tow_opp is not None
    assert f"/{assignment.id}/tow_pilot/" in tow_opp["volunteer_url"]


@pytest.mark.django_db
def test_roster_home_hides_unqualified_role(client, django_user_model):
    """Member without instructor qualification does not see the instructor hole."""
    _make_config(schedule_instructors=True)
    user = _make_user(django_user_model, instructor=False, towpilot=False)
    _future_assignment()

    client.force_login(user)
    response = client.get(_home_url())

    assert response.status_code == 200
    opportunities = response.context["volunteer_opportunities"]
    # No instructor or tow_pilot hole should be listed for this user.
    for opp in opportunities:
        label = str(opp.get("role_label", "")).lower()
        assert "instructor" not in label
        assert "tow" not in label


@pytest.mark.django_db
def test_roster_home_lists_holes_when_flag_off(client, django_user_model):
    """
    Issue #1120 core fix: a qualified instructor still sees the open instructor
    hole on roster_home when schedule_instructors is OFF.
    """
    _make_config(schedule_instructors=False)
    user = _make_user(django_user_model, instructor=True)
    assignment = _future_assignment()

    client.force_login(user)
    response = client.get(_home_url())

    assert response.status_code == 200
    opportunities = response.context["volunteer_opportunities"]
    # The instructor hole should still be listed (flag is off, but the member
    # is qualified and the slot is empty).
    instr_opp = next(
        (
            o
            for o in opportunities
            if "instructor" in str(o.get("role_label", "")).lower()
        ),
        None,
    )
    assert instr_opp is not None
    assert f"/{assignment.id}/instructor/" in instr_opp["volunteer_url"]


@pytest.mark.django_db
def test_roster_home_hides_filled_role(client, django_user_model):
    """A filled slot does not appear as an opportunity."""
    _make_config(schedule_instructors=True)
    filler = _make_user(django_user_model, username="filler", instructor=True)
    assignment = _future_assignment()
    assignment.instructor = filler
    assignment.save(update_fields=["instructor"])

    # Volunteer is a different qualified instructor
    volunteer = _make_user(django_user_model, username="volunteer", instructor=True)
    client.force_login(volunteer)
    response = client.get(_home_url())

    assert response.status_code == 200
    opportunities = response.context["volunteer_opportunities"]
    for opp in opportunities:
        if "instructor" in str(opp.get("role_label", "")).lower():
            # The volunteer cannot fill a slot that is already filled.
            pytest.fail("Filled instructor slot should not be listed")
