from datetime import date, timedelta

import pytest
from django.core import mail
from django.test import override_settings
from django.urls import reverse

from duty_roster.models import DutyAssignment, InstructionSlot, OpsIntent


def _create_member(django_user_model, username, email, **extra):
    defaults = {
        "first_name": username.capitalize(),
        "last_name": "Member",
        "membership_status": "Full Member",
    }
    defaults.update(extra)
    return django_user_model.objects.create_user(
        username=username,
        email=email,
        password="testpass123",
        **defaults,
    )


@pytest.mark.django_db
@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@testclub.com",
    EMAIL_DEV_MODE=False,
)
def test_ops_intent_toggle_sends_member_flight_intent_email_for_club_single(
    client, django_user_model
):
    pilot = _create_member(
        django_user_model,
        username="pilot1",
        email="pilot1@example.com",
        first_name="Pat",
        last_name="Pilot",
    )
    instructor = _create_member(
        django_user_model,
        username="inst1",
        email="inst1@example.com",
        instructor=True,
        first_name="Ivy",
        last_name="Instructor",
    )

    ops_day = date.today() + timedelta(days=7)
    DutyAssignment.objects.create(date=ops_day, instructor=instructor)

    client.force_login(pilot)
    mail.outbox.clear()

    response = client.post(
        reverse(
            "duty_roster:ops_intent_toggle",
            kwargs={"year": ops_day.year, "month": ops_day.month, "day": ops_day.day},
        ),
        data={"available_as": ["club_single"]},
    )

    assert response.status_code == 200
    intent = OpsIntent.objects.get(member=pilot, date=ops_day)
    assert intent.available_as == ["club_single"]

    assert len(mail.outbox) == 1
    email = mail.outbox[0]
    assert "Member Flight Intent" in email.subject
    assert instructor.email in email.to
    assert "Fly Club Single-Seater" in email.body
    assert pilot.full_display_name in email.body


@pytest.mark.django_db
@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@testclub.com",
    EMAIL_DEV_MODE=False,
)
def test_ops_intent_toggle_does_not_notify_for_private_only_intent(
    client, django_user_model
):
    pilot = _create_member(
        django_user_model,
        username="pilot2",
        email="pilot2@example.com",
    )
    instructor = _create_member(
        django_user_model,
        username="inst2",
        email="inst2@example.com",
        instructor=True,
    )

    ops_day = date.today() + timedelta(days=8)
    DutyAssignment.objects.create(date=ops_day, instructor=instructor)

    client.force_login(pilot)
    mail.outbox.clear()

    response = client.post(
        reverse(
            "duty_roster:ops_intent_toggle",
            kwargs={"year": ops_day.year, "month": ops_day.month, "day": ops_day.day},
        ),
        data={"available_as": ["private"]},
    )

    assert response.status_code == 200
    intent = OpsIntent.objects.get(member=pilot, date=ops_day)
    assert intent.available_as == ["private"]
    assert len(mail.outbox) == 0


@pytest.mark.django_db
@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@testclub.com",
    EMAIL_DEV_MODE=False,
)
def test_ops_intent_toggle_blocks_new_intent_when_instruction_request_exists(
    client, django_user_model
):
    pilot = _create_member(
        django_user_model,
        username="pilot3",
        email="pilot3@example.com",
    )
    instructor = _create_member(
        django_user_model,
        username="inst3",
        email="inst3@example.com",
        instructor=True,
    )

    ops_day = date.today() + timedelta(days=9)
    assignment = DutyAssignment.objects.create(date=ops_day, instructor=instructor)
    InstructionSlot.objects.create(
        assignment=assignment,
        student=pilot,
        instruction_types=["general"],
        status="pending",
    )

    client.force_login(pilot)
    mail.outbox.clear()

    response = client.post(
        reverse(
            "duty_roster:ops_intent_toggle",
            kwargs={"year": ops_day.year, "month": ops_day.month, "day": ops_day.day},
        ),
        data={"available_as": ["club_single"]},
    )

    assert response.status_code == 200
    assert OpsIntent.objects.filter(member=pilot, date=ops_day).count() == 0
    assert "already requested instruction" in response.content.decode()
    assert len(mail.outbox) == 0
