from datetime import date, time, timedelta

import pytest
from django.core import mail
from django.core.management import call_command
from django.test import override_settings

from instructors.models import InstructionReport
from instructors.utils import get_pending_sprs_for_date
from logsheet.models import Airfield, Flight, Logsheet
from members.models import Member
from notifications.models import Notification
from siteconfig.models import SiteConfiguration


@pytest.fixture
def site_config(db):
    return SiteConfiguration.objects.create(
        club_name="Test Soaring Club",
        club_nickname="Test Club",
        domain_name="test.manage2soar.com",
        club_abbreviation="TSC",
        duty_officer_title="Duty Officer",
        assistant_duty_officer_title="Assistant DO",
        towpilot_title="Tow Pilot",
        instructor_title="Instructor",
    )


@pytest.fixture
def airfield(db):
    return Airfield.objects.create(identifier="TST", name="Test Field")


@pytest.fixture
def instructor(db):
    return Member.objects.create(
        username="inst",
        first_name="Chris",
        last_name="Instructor",
        email="chris@example.com",
        membership_status="Full Member",
    )


@pytest.fixture
def student_one(db):
    return Member.objects.create(
        username="student1",
        first_name="Alice",
        last_name="Student",
        email="alice@example.com",
        membership_status="Student",
    )


@pytest.fixture
def student_two(db):
    return Member.objects.create(
        username="student2",
        first_name="Bob",
        last_name="Student",
        email="bob@example.com",
        membership_status="Student",
    )


def create_flight(logsheet, pilot, instructor, launch_hour):
    return Flight.objects.create(
        logsheet=logsheet,
        pilot=pilot,
        instructor=instructor,
        launch_time=time(launch_hour, 0),
        landing_time=time(launch_hour, 30),
        flight_type="dual",
    )


@pytest.mark.django_db
def test_get_pending_sprs_for_date_groups_students_and_excludes_existing_reports(
    airfield, instructor, student_one, student_two
):
    target_date = date(2026, 4, 25)
    logsheet = Logsheet.objects.create(
        log_date=target_date,
        airfield=airfield,
        created_by=instructor,
        finalized=True,
    )
    create_flight(logsheet, student_one, instructor, 10)
    create_flight(logsheet, student_two, instructor, 11)
    InstructionReport.objects.create(
        student=student_two,
        instructor=instructor,
        report_date=target_date,
        report_text="Completed already",
    )

    pending = get_pending_sprs_for_date(target_date)

    assert list(pending.keys()) == [instructor]
    assert len(pending[instructor]) == 1
    assert pending[instructor][0]["student"] == student_one


@pytest.mark.django_db
def test_get_pending_sprs_for_date_deduplicates_multiple_flights_for_same_student(
    airfield, instructor, student_one
):
    """Multiple flights on the same day for the same instructor/student pair
    should produce exactly one pending SPR entry, not one per flight."""
    target_date = date(2026, 4, 25)
    logsheet = Logsheet.objects.create(
        log_date=target_date,
        airfield=airfield,
        created_by=instructor,
        finalized=True,
    )
    # Same student flew twice with the same instructor on the same day.
    create_flight(logsheet, student_one, instructor, 10)
    create_flight(logsheet, student_one, instructor, 14)

    pending = get_pending_sprs_for_date(target_date)

    assert list(pending.keys()) == [instructor]
    assert (
        len(pending[instructor]) == 1
    ), "Expected exactly one pending entry for a student who flew twice on the same day"
    assert pending[instructor][0]["student"] == student_one


@pytest.mark.django_db
@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_DEV_MODE=False,
    DEFAULT_FROM_EMAIL="noreply@test.com",
    SITE_URL="https://test.manage2soar.com",
)
def test_notify_pending_sprs_sends_one_email_per_instructor_and_dedupes_reruns(
    site_config, airfield, instructor, student_one, student_two
):
    target_date = date(2026, 4, 25)
    logsheet = Logsheet.objects.create(
        log_date=target_date,
        airfield=airfield,
        created_by=instructor,
        finalized=True,
    )
    create_flight(logsheet, student_one, instructor, 10)
    create_flight(logsheet, student_two, instructor, 11)

    mail.outbox.clear()
    Notification.objects.all().delete()

    call_command("notify_pending_sprs", f"--flight-date={target_date.isoformat()}")

    assert len(mail.outbox) == 1
    email = mail.outbox[0]
    assert email.to == ["chris@example.com"]
    assert "2 Pending Report(s)" in email.subject
    assert "Alice Student" in email.body
    assert "Bob Student" in email.body
    assert Notification.objects.filter(user=instructor).count() == 1

    call_command("notify_pending_sprs", f"--flight-date={target_date.isoformat()}")

    assert len(mail.outbox) == 1
    assert Notification.objects.filter(user=instructor).count() == 1


@pytest.mark.django_db
@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_DEV_MODE=False,
    DEFAULT_FROM_EMAIL="noreply@test.com",
    SITE_URL="https://test.manage2soar.com",
)
def test_notify_pending_sprs_dedupes_even_after_notification_is_dismissed(
    site_config, airfield, instructor, student_one
):
    target_date = date(2026, 4, 25)
    logsheet = Logsheet.objects.create(
        log_date=target_date,
        airfield=airfield,
        created_by=instructor,
        finalized=True,
    )
    create_flight(logsheet, student_one, instructor, 10)

    mail.outbox.clear()
    Notification.objects.all().delete()

    call_command("notify_pending_sprs", f"--flight-date={target_date.isoformat()}")

    notification = Notification.objects.get(user=instructor)
    notification.dismissed = True
    notification.save(update_fields=["dismissed"])

    call_command("notify_pending_sprs", f"--flight-date={target_date.isoformat()}")

    assert len(mail.outbox) == 1
    assert Notification.objects.filter(user=instructor).count() == 1


@pytest.mark.django_db
@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_DEV_MODE=False,
    DEFAULT_FROM_EMAIL="noreply@test.com",
    SITE_URL="https://test.manage2soar.com",
)
def test_notify_pending_sprs_ignores_non_finalized_logsheets(
    site_config, airfield, instructor, student_one
):
    target_date = date(2026, 4, 25)
    logsheet = Logsheet.objects.create(
        log_date=target_date,
        airfield=airfield,
        created_by=instructor,
        finalized=False,
    )
    create_flight(logsheet, student_one, instructor, 10)

    mail.outbox.clear()
    Notification.objects.all().delete()

    call_command("notify_pending_sprs", f"--flight-date={target_date.isoformat()}")

    assert len(mail.outbox) == 0
    assert Notification.objects.count() == 0


@pytest.mark.django_db
@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_DEV_MODE=False,
    DEFAULT_FROM_EMAIL="noreply@test.com",
    SITE_URL="https://test.manage2soar.com",
)
def test_notify_pending_sprs_picks_up_late_finalized_logsheet(
    site_config, airfield, instructor, student_one
):
    """Without --flight-date, the command should find the most recent finalized
    flying day regardless of when the logsheet was finalized, so logsheets
    finalized 2+ days after the flights are still picked up."""
    # Logsheet dated 3 days ago but finalized late (today) — simulates a
    # real scenario where the DO closes out after a delay.
    from django.utils import timezone

    flight_date = timezone.now().date() - timedelta(days=3)
    logsheet = Logsheet.objects.create(
        log_date=flight_date,
        airfield=airfield,
        created_by=instructor,
        finalized=True,
    )
    create_flight(logsheet, student_one, instructor, 10)

    mail.outbox.clear()
    Notification.objects.all().delete()

    # Run without --flight-date; should auto-discover flight_date as the
    # most recent finalized instructional flying day.
    call_command("notify_pending_sprs")

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [instructor.email]
    assert flight_date.strftime("%B %d, %Y") in mail.outbox[0].subject
    assert Notification.objects.filter(user=instructor).count() == 1


@pytest.mark.django_db
@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_DEV_MODE=False,
    DEFAULT_FROM_EMAIL="noreply@test.com",
    SITE_URL="https://test.manage2soar.com",
)
def test_notify_pending_sprs_skips_fully_notified_date_and_falls_back_to_older(
    site_config, airfield, instructor, student_one, student_two
):
    """If the most recent finalized date with pending SPRs already has
    notifications for all its instructors, the command should skip that date
    and process the next older date that still has un-notified pending SPRs.

    Scenario:
      - newer_date (2 days ago): pending SPR, but notification ALREADY sent
      - older_date (4 days ago): pending SPR, NO notification sent yet
      → command should email for older_date, not newer_date
    """
    from django.utils import timezone

    from instructors.utils import PENDING_SPR_NOTIFICATION_FRAGMENT

    today = timezone.now().date()
    newer_date = today - timedelta(days=2)
    older_date = today - timedelta(days=4)

    # Set up newer_date logsheet with a pending SPR for instructor
    newer_logsheet = Logsheet.objects.create(
        log_date=newer_date,
        airfield=airfield,
        created_by=instructor,
        finalized=True,
    )
    create_flight(newer_logsheet, student_one, instructor, 10)

    # Set up older_date logsheet with a pending SPR for instructor
    older_logsheet = Logsheet.objects.create(
        log_date=older_date,
        airfield=airfield,
        created_by=instructor,
        finalized=True,
    )
    create_flight(older_logsheet, student_two, instructor, 10)

    # Pre-seed a notification for newer_date so the command treats it as
    # already handled for this instructor.
    Notification.objects.create(
        user=instructor,
        message=(
            f"You have 1 {PENDING_SPR_NOTIFICATION_FRAGMENT}(s) "
            f"from {newer_date.isoformat()}."
        ),
        url="/instructors/",
    )

    mail.outbox.clear()

    call_command("notify_pending_sprs")

    # Should have emailed for older_date (the first un-notified date)
    assert (
        len(mail.outbox) == 1
    ), "Expected one email for older_date; newer_date should have been skipped"
    assert older_date.strftime("%B %d, %Y") in mail.outbox[0].subject
    assert mail.outbox[0].to == [instructor.email]
    # Notification for older_date should now exist
    assert Notification.objects.filter(
        user=instructor,
        message__contains=older_date.isoformat(),
    ).exists()
