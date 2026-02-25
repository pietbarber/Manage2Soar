"""
Tests for student allocation between primary and surge instructor (Issue #664).

Covers:
- assign_student_to_instructor view (move to primary, move to surge, guards)
- _notify_student_instructor_assigned helper (success / failure paths)
- instructor_requests view allocation context (allocation_by_date / accepted_by_date split)
- template rendering (allocation section shown / hidden)
"""

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.urls import reverse

from duty_roster.models import DutyAssignment, InstructionSlot
from duty_roster.views import _notify_student_instructor_assigned
from siteconfig.models import SiteConfiguration

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_member(django_user_model, username, instructor=False, **extra):
    extra.setdefault("email", f"{username}@example.com")
    return django_user_model.objects.create_user(
        username=username,
        password="password",
        membership_status="Full Member",
        instructor=instructor,
        **extra,
    )


def _make_site_config():
    return SiteConfiguration.objects.create(
        club_name="Sky Club",
        domain_name="sky.org",
        club_abbreviation="SC",
        instructors_email="instructors@sky.org",
    )


def _make_assignment(primary, date_offset=60, surge=None):
    test_date = date.today() + timedelta(days=date_offset)
    a = DutyAssignment.objects.create(date=test_date, instructor=primary)
    if surge:
        a.surge_instructor = surge
        a.save(update_fields=["surge_instructor"])
    return a


def _make_accepted_slot(assignment, student, instructor):
    """Create an already-accepted InstructionSlot."""
    return InstructionSlot.objects.create(
        assignment=assignment,
        student=student,
        instructor=instructor,
        instructor_response="accepted",
        status="confirmed",
    )


# ---------------------------------------------------------------------------
# assign_student_to_instructor — happy paths
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_move_student_to_surge_instructor(client, django_user_model):
    """POST action=surge moves a student whose instructor is primary → surge."""
    _make_site_config()
    primary = _make_member(django_user_model, "al_primary1", instructor=True)
    surge = _make_member(django_user_model, "al_surge1", instructor=True)
    student = _make_member(django_user_model, "al_student1")
    assignment = _make_assignment(primary, date_offset=60, surge=surge)

    slot = _make_accepted_slot(assignment, student, primary)

    client.force_login(primary)
    url = reverse(
        "duty_roster:assign_student_to_instructor", kwargs={"slot_id": slot.id}
    )
    with patch("duty_roster.views.send_mail") as mock_send:
        mock_send.return_value = 1
        response = client.post(url, {"action": "surge"})

    assert response.status_code == 302
    slot.refresh_from_db()
    assert slot.instructor == surge


@pytest.mark.django_db
def test_move_student_to_primary_instructor(client, django_user_model):
    """POST action=primary moves a student whose instructor is surge → primary."""
    _make_site_config()
    primary = _make_member(django_user_model, "al_primary2", instructor=True)
    surge = _make_member(django_user_model, "al_surge2", instructor=True)
    student = _make_member(django_user_model, "al_student2")
    assignment = _make_assignment(primary, date_offset=61, surge=surge)

    slot = _make_accepted_slot(assignment, student, surge)

    client.force_login(surge)
    url = reverse(
        "duty_roster:assign_student_to_instructor", kwargs={"slot_id": slot.id}
    )
    with patch("duty_roster.views.send_mail") as mock_send:
        mock_send.return_value = 1
        response = client.post(url, {"action": "primary"})

    assert response.status_code == 302
    slot.refresh_from_db()
    assert slot.instructor == primary


@pytest.mark.django_db
def test_surge_instructor_can_also_move_students(client, django_user_model):
    """The surge instructor (not just primary) can move students between queues."""
    _make_site_config()
    primary = _make_member(django_user_model, "al_primary3", instructor=True)
    surge = _make_member(django_user_model, "al_surge3", instructor=True)
    student = _make_member(django_user_model, "al_student3")
    assignment = _make_assignment(primary, date_offset=62, surge=surge)

    slot = _make_accepted_slot(assignment, student, primary)

    # Log in as SURGE and move the student
    client.force_login(surge)
    url = reverse(
        "duty_roster:assign_student_to_instructor", kwargs={"slot_id": slot.id}
    )
    with patch("duty_roster.views.send_mail") as mock_send:
        mock_send.return_value = 1
        response = client.post(url, {"action": "surge"})

    assert response.status_code == 302
    slot.refresh_from_db()
    assert slot.instructor == surge


@pytest.mark.django_db
def test_move_redirects_to_instructor_requests(client, django_user_model):
    """Successful move redirects to instructor_requests."""
    _make_site_config()
    primary = _make_member(django_user_model, "al_primary4", instructor=True)
    surge = _make_member(django_user_model, "al_surge4", instructor=True)
    student = _make_member(django_user_model, "al_student4")
    assignment = _make_assignment(primary, date_offset=63, surge=surge)
    slot = _make_accepted_slot(assignment, student, primary)

    client.force_login(primary)
    url = reverse(
        "duty_roster:assign_student_to_instructor", kwargs={"slot_id": slot.id}
    )
    with patch("duty_roster.views.send_mail") as mock_send:
        mock_send.return_value = 1
        response = client.post(url, {"action": "surge"})

    assert response.status_code == 302
    assert response["Location"].endswith(reverse("duty_roster:instructor_requests"))


@pytest.mark.django_db
def test_move_sends_html_email_to_student(client, django_user_model):
    """Moving a student triggers an HTML notification email sent to the student."""
    _make_site_config()
    primary = _make_member(django_user_model, "al_primary5", instructor=True)
    surge = _make_member(django_user_model, "al_surge5", instructor=True)
    student = _make_member(
        django_user_model, "al_student5", email="student5@example.com"
    )
    assignment = _make_assignment(primary, date_offset=64, surge=surge)
    slot = _make_accepted_slot(assignment, student, primary)

    client.force_login(primary)
    url = reverse(
        "duty_roster:assign_student_to_instructor", kwargs={"slot_id": slot.id}
    )
    with patch("duty_roster.views.send_mail") as mock_send:
        mock_send.return_value = 1
        client.post(url, {"action": "surge"})

    mock_send.assert_called_once()
    call = mock_send.call_args
    recipients = (
        call.args[3] if len(call.args) > 3 else call.kwargs.get("recipient_list", [])
    )
    assert "student5@example.com" in recipients
    html_content = call.kwargs.get("html_message", "")
    assert "<html" in html_content.lower()


# ---------------------------------------------------------------------------
# assign_student_to_instructor — guard / error paths
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_unrelated_member_gets_403(client, django_user_model):
    """A member who is not an instructor for this day gets 403 Forbidden."""
    primary = _make_member(django_user_model, "al_primary6", instructor=True)
    surge = _make_member(django_user_model, "al_surge6", instructor=True)
    outsider = _make_member(django_user_model, "al_outsider6", instructor=True)
    student = _make_member(django_user_model, "al_student6")
    assignment = _make_assignment(primary, date_offset=65, surge=surge)
    slot = _make_accepted_slot(assignment, student, primary)

    client.force_login(outsider)
    url = reverse(
        "duty_roster:assign_student_to_instructor", kwargs={"slot_id": slot.id}
    )
    with patch("duty_roster.views.send_mail") as mock_send:
        response = client.post(url, {"action": "surge"})
        mock_send.assert_not_called()

    assert response.status_code == 403
    slot.refresh_from_db()
    assert slot.instructor == primary  # unchanged


@pytest.mark.django_db
def test_action_surge_without_surge_instructor_shows_error(client, django_user_model):
    """If no surge instructor is assigned, action=surge is rejected with an error message."""
    _make_site_config()
    primary = _make_member(django_user_model, "al_primary7", instructor=True)
    student = _make_member(django_user_model, "al_student7")
    # No surge instructor on this assignment
    assignment = _make_assignment(primary, date_offset=66)
    slot = _make_accepted_slot(assignment, student, primary)

    client.force_login(primary)
    url = reverse(
        "duty_roster:assign_student_to_instructor", kwargs={"slot_id": slot.id}
    )
    with patch("duty_roster.views.send_mail") as mock_send:
        response = client.post(url, {"action": "surge"})
        mock_send.assert_not_called()

    assert response.status_code == 302
    slot.refresh_from_db()
    assert slot.instructor == primary  # unchanged


@pytest.mark.django_db
def test_pending_slot_cannot_be_moved(client, django_user_model):
    """Only accepted (confirmed) slots can be moved; pending slots are rejected."""
    _make_site_config()
    primary = _make_member(django_user_model, "al_primary8", instructor=True)
    surge = _make_member(django_user_model, "al_surge8", instructor=True)
    student = _make_member(django_user_model, "al_student8")
    assignment = _make_assignment(primary, date_offset=67, surge=surge)

    # Pending slot (not yet accepted)
    slot = InstructionSlot.objects.create(
        assignment=assignment,
        student=student,
        instructor=None,
        instructor_response="pending",
        status="pending",
    )

    client.force_login(primary)
    url = reverse(
        "duty_roster:assign_student_to_instructor", kwargs={"slot_id": slot.id}
    )
    with patch("duty_roster.views.send_mail") as mock_send:
        response = client.post(url, {"action": "surge"})
        mock_send.assert_not_called()

    assert response.status_code == 302
    slot.refresh_from_db()
    assert slot.instructor is None  # unchanged


@pytest.mark.django_db
def test_invalid_action_shows_error(client, django_user_model):
    """An unrecognised action string is rejected without changing the slot."""
    primary = _make_member(django_user_model, "al_primary9", instructor=True)
    surge = _make_member(django_user_model, "al_surge9", instructor=True)
    student = _make_member(django_user_model, "al_student9")
    assignment = _make_assignment(primary, date_offset=68, surge=surge)
    slot = _make_accepted_slot(assignment, student, primary)

    client.force_login(primary)
    url = reverse(
        "duty_roster:assign_student_to_instructor", kwargs={"slot_id": slot.id}
    )
    with patch("duty_roster.views.send_mail") as mock_send:
        response = client.post(url, {"action": "magic"})
        mock_send.assert_not_called()

    assert response.status_code == 302
    slot.refresh_from_db()
    assert slot.instructor == primary  # unchanged


@pytest.mark.django_db
def test_noop_when_already_on_target_instructor(client, django_user_model):
    """Moving a student to the instructor they're already assigned to is a no-op."""
    _make_site_config()
    primary = _make_member(django_user_model, "al_primary10", instructor=True)
    surge = _make_member(django_user_model, "al_surge10", instructor=True)
    student = _make_member(django_user_model, "al_student10")
    assignment = _make_assignment(primary, date_offset=69, surge=surge)
    # Student is already with primary
    slot = _make_accepted_slot(assignment, student, primary)

    client.force_login(primary)
    url = reverse(
        "duty_roster:assign_student_to_instructor", kwargs={"slot_id": slot.id}
    )
    with patch("duty_roster.views.send_mail") as mock_send:
        response = client.post(url, {"action": "primary"})
        mock_send.assert_not_called()  # no email sent for no-op

    assert response.status_code == 302
    slot.refresh_from_db()
    assert slot.instructor == primary  # still primary, no change


@pytest.mark.django_db
def test_surge_instructor_cannot_be_assigned_as_own_student_to_surge(
    client, django_user_model
):
    """Issue #685: when the student IS the surge instructor, action=surge is blocked."""
    _make_site_config()
    primary = _make_member(django_user_model, "al_self1_primary", instructor=True)
    surge = _make_member(django_user_model, "al_self1_surge", instructor=True)
    assignment = _make_assignment(primary, date_offset=80, surge=surge)

    # A student request exists where the student IS the surge instructor
    slot = InstructionSlot.objects.create(
        assignment=assignment,
        student=surge,
        instructor=primary,
        instructor_response="accepted",
        status="confirmed",
    )

    client.force_login(primary)
    url = reverse(
        "duty_roster:assign_student_to_instructor", kwargs={"slot_id": slot.id}
    )
    with patch("duty_roster.views.send_mail") as mock_send:
        response = client.post(url, {"action": "surge"})
        mock_send.assert_not_called()

    assert response.status_code == 302
    slot.refresh_from_db()
    # Slot must not have been moved to surge instructor
    assert slot.instructor == primary


@pytest.mark.django_db
def test_primary_instructor_cannot_be_assigned_as_own_student(
    client, django_user_model
):
    """Issue #685: block applies when student IS the primary instructor and action=primary."""
    _make_site_config()
    primary = _make_member(django_user_model, "al_self2_primary", instructor=True)
    surge = _make_member(django_user_model, "al_self2_surge", instructor=True)
    assignment = _make_assignment(primary, date_offset=81, surge=surge)

    # Slot where student IS the primary instructor (moving to primary is self-referential)
    slot = InstructionSlot.objects.create(
        assignment=assignment,
        student=primary,
        instructor=surge,
        instructor_response="accepted",
        status="confirmed",
    )

    client.force_login(surge)
    url = reverse(
        "duty_roster:assign_student_to_instructor", kwargs={"slot_id": slot.id}
    )
    with patch("duty_roster.views.send_mail") as mock_send:
        response = client.post(url, {"action": "primary"})
        mock_send.assert_not_called()

    assert response.status_code == 302
    slot.refresh_from_db()
    assert slot.instructor == surge  # unchanged — guard blocked the move


@pytest.mark.django_db
def test_self_student_guard_error_message_contains_name(client, django_user_model):
    """Issue #685: the error flash message mentions the instructor's name."""
    _make_site_config()
    primary = _make_member(
        django_user_model,
        "al_self3_primary",
        instructor=True,
        first_name="Alice",
        last_name="Smith",
    )
    surge = _make_member(
        django_user_model,
        "al_self3_surge",
        instructor=True,
        first_name="Bob",
        last_name="Jones",
    )
    assignment = _make_assignment(primary, date_offset=82, surge=surge)

    slot = InstructionSlot.objects.create(
        assignment=assignment,
        student=surge,
        instructor=primary,
        instructor_response="accepted",
        status="confirmed",
    )

    client.force_login(primary)
    url = reverse(
        "duty_roster:assign_student_to_instructor", kwargs={"slot_id": slot.id}
    )
    with patch("duty_roster.views.send_mail"):
        response = client.post(url, {"action": "surge"}, follow=True)

    content = response.content.decode()
    # Error message should contain "cannot be assigned as their own student"
    assert "cannot be assigned as their own student" in content


@pytest.mark.django_db
def test_unauthenticated_post_redirects_to_login(client, django_user_model):
    """Unauthenticated POST is caught by @active_member_required and redirected."""
    primary = _make_member(django_user_model, "al_anon_p", instructor=True)
    student = _make_member(django_user_model, "al_anon_s")
    assignment = _make_assignment(primary, date_offset=70)
    slot = _make_accepted_slot(assignment, student, primary)

    url = reverse(
        "duty_roster:assign_student_to_instructor", kwargs={"slot_id": slot.id}
    )
    response = client.post(url, {"action": "primary"})

    assert response.status_code == 302
    assert "/login/" in response["Location"]


@pytest.mark.django_db
def test_invalid_slot_id_returns_404(client, django_user_model):
    """A nonexistent slot_id returns 404."""
    primary = _make_member(django_user_model, "al_404", instructor=True)
    client.force_login(primary)

    url = reverse(
        "duty_roster:assign_student_to_instructor", kwargs={"slot_id": 999999}
    )
    response = client.post(url, {"action": "primary"})

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# _notify_student_instructor_assigned helper
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_notify_student_returns_true_on_success(django_user_model):
    """Helper returns True and sends HTML email to student on success."""
    _make_site_config()
    primary = _make_member(django_user_model, "ns_primary", instructor=True)
    surge = _make_member(django_user_model, "ns_surge", instructor=True)
    student = _make_member(
        django_user_model, "ns_student", email="student_notify@sky.org"
    )
    assignment = _make_assignment(primary, date_offset=80, surge=surge)
    slot = _make_accepted_slot(assignment, student, surge)

    with patch("duty_roster.views.send_mail") as mock_send:
        mock_send.return_value = 1
        result = _notify_student_instructor_assigned(slot)

    assert result is True
    mock_send.assert_called_once()
    call = mock_send.call_args
    recipients = (
        call.args[3] if len(call.args) > 3 else call.kwargs.get("recipient_list", [])
    )
    assert "student_notify@sky.org" in recipients
    html_content = call.kwargs.get("html_message", "")
    assert "<html" in html_content.lower()


@pytest.mark.django_db
def test_notify_student_returns_false_when_no_email(django_user_model):
    """Helper returns False without crashing when student has no email address."""
    _make_site_config()
    primary = _make_member(django_user_model, "ns_noemail_p", instructor=True)
    student = django_user_model.objects.create_user(
        username="ns_noemail_s",
        email="",
        password="password",
        membership_status="Full Member",
    )
    assignment = _make_assignment(primary, date_offset=81)
    slot = _make_accepted_slot(assignment, student, primary)

    with patch("duty_roster.views.send_mail") as mock_send:
        result = _notify_student_instructor_assigned(slot)
        mock_send.assert_not_called()

    assert result is False


@pytest.mark.django_db
def test_notify_student_returns_false_on_smtp_error(django_user_model):
    """Helper catches SMTP exceptions and returns False."""
    _make_site_config()
    primary = _make_member(django_user_model, "ns_smtp_p", instructor=True)
    student = _make_member(django_user_model, "ns_smtp_s", email="smtp@sky.org")
    assignment = _make_assignment(primary, date_offset=82)
    slot = _make_accepted_slot(assignment, student, primary)

    with patch("duty_roster.views.send_mail", side_effect=Exception("SMTP error")):
        result = _notify_student_instructor_assigned(slot)

    assert result is False


@pytest.mark.django_db
def test_notify_student_returns_false_when_no_assigned_instructor(django_user_model):
    """Helper returns False when slot.instructor is null."""
    _make_site_config()
    primary = _make_member(django_user_model, "ns_null_p", instructor=True)
    student = _make_member(django_user_model, "ns_null_s")
    assignment = _make_assignment(primary, date_offset=83)
    slot = InstructionSlot.objects.create(
        assignment=assignment,
        student=student,
        instructor=None,
        instructor_response="accepted",
        status="confirmed",
    )

    with patch("duty_roster.views.send_mail") as mock_send:
        result = _notify_student_instructor_assigned(slot)
        mock_send.assert_not_called()

    assert result is False


# ---------------------------------------------------------------------------
# instructor_requests view — allocation context split
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_view_splits_surge_day_into_allocation_context(client, django_user_model):
    """For a day with a surge instructor, the view puts slots into
    allocation_by_date rather than accepted_by_date."""
    _make_site_config()
    primary = _make_member(django_user_model, "ctx_primary", instructor=True)
    surge = _make_member(django_user_model, "ctx_surge", instructor=True)
    student = _make_member(django_user_model, "ctx_student")
    assignment = _make_assignment(primary, date_offset=90, surge=surge)
    _make_accepted_slot(assignment, student, primary)

    client.force_login(primary)
    response = client.get(reverse("duty_roster:instructor_requests"))

    assert response.status_code == 200
    allocation_by_date = response.context["allocation_by_date"]
    accepted_by_date = response.context["accepted_by_date"]

    # The surged day must appear in allocation_by_date
    assert assignment.date in allocation_by_date
    # The surged day must NOT appear in the flat accepted_by_date
    assert assignment.date not in accepted_by_date


@pytest.mark.django_db
def test_view_keeps_non_surge_day_in_accepted_by_date(client, django_user_model):
    """For a day WITHOUT a surge instructor, slots appear in accepted_by_date
    as before (unaffected by allocation logic)."""
    _make_site_config()
    primary = _make_member(django_user_model, "ctx_ns_primary", instructor=True)
    student = _make_member(django_user_model, "ctx_ns_student")
    assignment = _make_assignment(primary, date_offset=91)  # no surge
    _make_accepted_slot(assignment, student, primary)

    client.force_login(primary)
    response = client.get(reverse("duty_roster:instructor_requests"))

    assert response.status_code == 200
    allocation_by_date = response.context["allocation_by_date"]
    accepted_by_date = response.context["accepted_by_date"]

    assert assignment.date not in allocation_by_date
    assert assignment.date in accepted_by_date


@pytest.mark.django_db
def test_allocation_context_has_correct_slot_split(client, django_user_model):
    """The allocation context correctly splits students between primary and surge."""
    _make_site_config()
    primary = _make_member(django_user_model, "ctx_split_p", instructor=True)
    surge = _make_member(django_user_model, "ctx_split_s", instructor=True)
    student_a = _make_member(django_user_model, "ctx_split_sa")
    student_b = _make_member(django_user_model, "ctx_split_sb")
    assignment = _make_assignment(primary, date_offset=92, surge=surge)

    _make_accepted_slot(assignment, student_a, primary)
    _make_accepted_slot(assignment, student_b, surge)

    client.force_login(primary)
    response = client.get(reverse("duty_roster:instructor_requests"))

    alloc = response.context["allocation_by_date"][assignment.date]
    assert len(alloc["primary_slots"]) == 1
    assert len(alloc["surge_slots"]) == 1
    assert alloc["primary_slots"][0].student == student_a
    assert alloc["surge_slots"][0].student == student_b


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_template_shows_allocation_section_for_surge_day(client, django_user_model):
    """The 'Student Allocation' section is rendered when a surge instructor is assigned."""
    _make_site_config()
    primary = _make_member(django_user_model, "tmpl_al_p", instructor=True)
    surge = _make_member(
        django_user_model,
        "tmpl_al_s",
        instructor=True,
        first_name="Surge",
        last_name="Flyer",
    )
    student = _make_member(django_user_model, "tmpl_al_st")
    assignment = _make_assignment(primary, date_offset=95, surge=surge)
    _make_accepted_slot(assignment, student, primary)

    client.force_login(primary)
    response = client.get(reverse("duty_roster:instructor_requests"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Student Allocation" in content
    # Surge instructor name should appear in the allocation section
    assert "Surge Flyer" in content
    # Student count badge should show correctly
    assert "1 student" in content


@pytest.mark.django_db
def test_template_hides_allocation_section_when_no_surge(client, django_user_model):
    """The 'Student Allocation' section is NOT rendered when there is no surge instructor."""
    _make_site_config()
    primary = _make_member(django_user_model, "tmpl_no_al_p", instructor=True)
    student = _make_member(django_user_model, "tmpl_no_al_st")
    assignment = _make_assignment(primary, date_offset=96)  # no surge
    _make_accepted_slot(assignment, student, primary)

    client.force_login(primary)
    response = client.get(reverse("duty_roster:instructor_requests"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Student Allocation" not in content


@pytest.mark.django_db
def test_template_shows_move_buttons_for_surge_day(client, django_user_model):
    """Move buttons linking to assign_student_to_instructor appear for surge days."""
    _make_site_config()
    primary = _make_member(django_user_model, "tmpl_mv_p", instructor=True)
    surge = _make_member(django_user_model, "tmpl_mv_s", instructor=True)
    student = _make_member(django_user_model, "tmpl_mv_st")
    assignment = _make_assignment(primary, date_offset=97, surge=surge)
    _make_accepted_slot(assignment, student, primary)

    client.force_login(primary)
    response = client.get(reverse("duty_roster:instructor_requests"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "assign-student" in content


@pytest.mark.django_db
def test_unassigned_slots_appear_in_context_and_render_warning(
    client, django_user_model
):
    """
    Accepted slots where instructor=None (or not the primary/surge instructor)
    should appear in alloc['unassigned_slots'] in the view context, and the
    template should render the amber 'alert-warning' section for them.
    """
    _make_site_config()
    primary = _make_member(django_user_model, "tmpl_ua_p", instructor=True)
    surge = _make_member(django_user_model, "tmpl_ua_s", instructor=True)
    student = _make_member(django_user_model, "tmpl_ua_st")
    assignment = _make_assignment(primary, date_offset=99, surge=surge)

    # Slot with no instructor assigned yet
    unassigned_slot = _make_accepted_slot(assignment, student, None)

    client.force_login(primary)
    response = client.get(reverse("duty_roster:instructor_requests"))

    assert response.status_code == 200

    # Verify the slot lands in unassigned_slots in the allocation context
    allocation_by_date = response.context["allocation_by_date"]
    assert allocation_by_date, "Expected allocation context for surged day"
    alloc = list(allocation_by_date.values())[0]
    assert unassigned_slot in alloc["unassigned_slots"]

    # Verify the amber warning section is rendered in the template
    content = response.content.decode()
    assert "alert-warning" in content
