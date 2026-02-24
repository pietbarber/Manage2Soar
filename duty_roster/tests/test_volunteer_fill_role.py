"""
Tests for the volunteer_fill_role view (Issue #679).

A qualified member can volunteer to fill an empty primary roster role on a
scheduled duty day.  The view accepts four role slugs:
  instructor, tow_pilot, duty_officer, assistant_duty_officer
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
        schedule_instructors=True,
        schedule_tow_pilots=True,
        schedule_duty_officers=True,
        schedule_assistant_duty_officers=True,
    )
    defaults.update(kwargs)
    existing = SiteConfiguration.objects.first()
    if existing:
        for k, v in defaults.items():
            setattr(existing, k, v)
        existing.save()
        return existing
    return SiteConfiguration.objects.create(**defaults)


def _make_user(django_user_model, username="volunteer", **kwargs):
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


def _url(assignment_id, role):
    return reverse(
        "duty_roster:volunteer_fill_role",
        kwargs={"assignment_id": assignment_id, "role": role},
    )


# ---------------------------------------------------------------------------
# GET – confirmation page
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_shows_confirmation_page(client, django_user_model):
    """Qualified member sees the confirmation page on GET."""
    _make_config()
    user = _make_user(django_user_model, instructor=True)
    assignment = _future_assignment()

    client.force_login(user)
    response = client.get(_url(assignment.id, "instructor"))

    assert response.status_code == 200
    assert b"Volunteer to Fill" in response.content


@pytest.mark.django_db
def test_get_redirects_if_role_already_filled(client, django_user_model):
    """If the role is already occupied the GET path redirects gracefully."""
    _make_config()
    filler = _make_user(django_user_model, username="filler", instructor=True)
    assignment = _future_assignment()
    assignment.instructor = filler
    assignment.save(update_fields=["instructor"])

    volunteer = _make_user(django_user_model, username="volunteer", instructor=True)
    client.force_login(volunteer)
    response = client.get(_url(assignment.id, "instructor"))

    assert response.status_code == 302  # redirect to calendar


@pytest.mark.django_db
def test_get_redirects_for_unknown_role(client, django_user_model):
    """An unrecognised role slug redirects without error."""
    _make_config()
    user = _make_user(django_user_model, instructor=True)
    assignment = _future_assignment()

    client.force_login(user)
    response = client.get(_url(assignment.id, "head_chef"))

    assert response.status_code == 302


@pytest.mark.django_db
def test_get_redirects_for_unqualified_member(client, django_user_model):
    """A member without the relevant qualification is redirected."""
    _make_config()
    user = _make_user(django_user_model, instructor=False)
    assignment = _future_assignment()

    client.force_login(user)
    response = client.get(_url(assignment.id, "instructor"))

    assert response.status_code == 302


@pytest.mark.django_db
def test_get_redirects_for_past_day(client, django_user_model):
    """Volunteering on a past day is rejected."""
    _make_config()
    user = _make_user(django_user_model, instructor=True)
    past_date = date.today() - timedelta(days=1)
    assignment, _ = DutyAssignment.objects.get_or_create(date=past_date)

    client.force_login(user)
    response = client.get(_url(assignment.id, "instructor"))

    assert response.status_code == 302


# ---------------------------------------------------------------------------
# POST – assigns the role
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role,qual_attr,assign_attr",
    [
        ("instructor", "instructor", "instructor"),
        ("tow_pilot", "towpilot", "tow_pilot"),
        ("duty_officer", "duty_officer", "duty_officer"),
        ("assistant_duty_officer", "assistant_duty_officer", "assistant_duty_officer"),
    ],
)
@pytest.mark.django_db
def test_post_assigns_role_for_all_four_roles(
    client, django_user_model, role, qual_attr, assign_attr
):
    """A qualified member is assigned to each fillable role via POST."""
    _make_config()
    kwargs = {qual_attr: True}
    user = _make_user(django_user_model, username=f"vol_{role}", **kwargs)
    assignment = _future_assignment()

    client.force_login(user)
    response = client.post(_url(assignment.id, role))

    assert response.status_code == 302
    assignment.refresh_from_db()
    assert getattr(assignment, assign_attr) == user


@pytest.mark.django_db
def test_post_race_condition_guard(client, django_user_model):
    """
    The POST path uses an atomic conditional UPDATE (filter + update where
    field__isnull=True) rather than refresh_from_db + save, so a concurrent
    volunteer cannot overwrite a slot that was claimed between the GET and POST.

    This test simulates the race by pre-filling the slot in the DB before the
    POST arrives.  The view fetches the assignment fresh (slot already taken),
    skips the pre-POST "already filled" fast-exit (which is GET-only), enters
    the POST branch, and runs the conditional update.  Since instructor is no
    longer NULL, the filtered queryset matches 0 rows; the view redirects with
    an informational message and leaves the original assignee untouched.
    """
    _make_config()
    first = _make_user(django_user_model, username="first", instructor=True)
    second = _make_user(django_user_model, username="second", instructor=True)
    assignment = _future_assignment()

    # Fill the slot in the DB before `second` submits their POST.
    assignment.instructor = first
    assignment.save(update_fields=["instructor"])

    client.force_login(second)
    response = client.post(_url(assignment.id, "instructor"))

    assert response.status_code == 302
    assignment.refresh_from_db()
    # second should NOT have overwritten first
    assert assignment.instructor == first


@pytest.mark.django_db
def test_post_rejected_for_unqualified_member(client, django_user_model):
    """POST is rejected for a member who lacks qualification."""
    _make_config()
    user = _make_user(django_user_model, instructor=False)
    assignment = _future_assignment()

    client.force_login(user)
    response = client.post(_url(assignment.id, "instructor"))

    assert response.status_code == 302
    assignment.refresh_from_db()
    assert assignment.instructor is None


@pytest.mark.django_db
def test_post_does_not_assign_when_role_scheduling_disabled(client, django_user_model):
    """
    Volunteering is rejected when the role's scheduling flag is disabled in
    SiteConfiguration, even if the user has the correct qualification.
    This prevents a direct URL bypass of the scheduling configuration.
    """
    _make_config(schedule_instructors=False)
    user = _make_user(django_user_model, instructor=True)
    assignment = _future_assignment()

    client.force_login(user)
    response = client.post(_url(assignment.id, "instructor"))

    assert response.status_code == 302
    assignment.refresh_from_db()
    assert assignment.instructor is None


# ---------------------------------------------------------------------------
# Authentication guard
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_unauthenticated_user_redirected(client):
    """Unauthenticated requests are redirected to login."""
    _make_config()
    assignment = _future_assignment()
    response = client.get(_url(assignment.id, "instructor"))

    assert response.status_code == 302
    assert "/login" in response["Location"] or "/accounts" in response["Location"]


# ---------------------------------------------------------------------------
# Context – volunteerable_holes in calendar day modal
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_scheduled_holes_visible_to_non_qualified_user(client, django_user_model):
    """
    scheduled_holes is included in the modal context regardless of the user's
    qualifications, so the 🕳️ Unfilled indicator is visible to everyone.
    Only volunteerable_holes (qualified subset) controls the volunteer button.
    """
    _make_config()
    # User has NO instructor qualification
    user = _make_user(django_user_model, username="non_qual", instructor=False)
    assignment = _future_assignment()

    client.force_login(user)
    url = reverse(
        "duty_roster:calendar_day_detail",
        kwargs={
            "year": assignment.date.year,
            "month": assignment.date.month,
            "day": assignment.date.day,
        },
    )
    response = client.get(url)

    assert response.status_code == 200
    # Unfilled indicator visible to everyone
    assert "instructor" in response.context["scheduled_holes"]
    # Volunteer button NOT available (user isn't an instructor)
    assert "instructor" not in response.context["volunteerable_holes"]

    """calendar_day_detail passes volunteerable_holes for qualified users."""
    _make_config()
    user = _make_user(django_user_model, instructor=True)
    assignment = _future_assignment()

    client.force_login(user)
    url = reverse(
        "duty_roster:calendar_day_detail",
        kwargs={
            "year": assignment.date.year,
            "month": assignment.date.month,
            "day": assignment.date.day,
        },
    )
    response = client.get(url)

    assert response.status_code == 200
    holes = response.context["volunteerable_holes"]
    assert "instructor" in holes


@pytest.mark.django_db
def test_no_volunteerable_holes_when_roles_filled(client, django_user_model):
    """volunteerable_holes is empty when all roles are already assigned."""
    _make_config()
    instructor = _make_user(django_user_model, username="instr", instructor=True)
    assignment = _future_assignment()
    assignment.instructor = instructor
    assignment.save(update_fields=["instructor"])

    client.force_login(instructor)
    url = reverse(
        "duty_roster:calendar_day_detail",
        kwargs={
            "year": assignment.date.year,
            "month": assignment.date.month,
            "day": assignment.date.day,
        },
    )
    response = client.get(url)

    assert response.status_code == 200
    holes = response.context["volunteerable_holes"]
    assert "instructor" not in holes
