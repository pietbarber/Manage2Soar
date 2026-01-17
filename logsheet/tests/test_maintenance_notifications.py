from datetime import date
from unittest.mock import patch

import pytest
from django.urls import reverse

from logsheet.models import AircraftMeister, Glider, MaintenanceIssue
from members.models import Member
from notifications.models import Notification


@pytest.mark.django_db
def test_maintenance_issue_create_notifies_meisters_immediately():
    """Issue #463: Notifications should be sent immediately on issue creation,
    not waiting for logsheet finalization.
    """
    from logsheet.models import Airfield, Logsheet

    meister = Member.objects.create(username="meister1", email="m1@example.com")
    glider = Glider.objects.create(make="Schleicher", model="ASW", n_number="G-TEST1")
    AircraftMeister.objects.create(glider=glider, member=meister)

    # Create a logsheet (required for maintenance issues)
    airfield = Airfield.objects.create(name="Test Field", identifier="TEST")
    logsheet = Logsheet.objects.create(
        log_date=date(2025, 10, 22),
        airfield=airfield,
        created_by=meister,
        finalized=False,
    )

    # Mock send_mail to avoid actual email sending
    with patch("logsheet.signals.send_mail"):
        # Create an issue - should notify IMMEDIATELY (Issue #463)
        MaintenanceIssue.objects.create(
            glider=glider,
            reported_by=meister,
            logsheet=logsheet,
            description="wingtip damage",
            grounded=False,
        )

    # Issue #463: Should have notification immediately, even before finalization
    notes = Notification.objects.filter(user=meister, dismissed=False)
    assert notes.exists(), "Notification should be sent immediately on issue creation"
    n = notes.first()
    assert n is not None
    assert "wingtip damage" in n.message
    # URL should point to the maintenance list per spec
    assert reverse("logsheet:maintenance_issues") in (n.url or "")


@pytest.mark.django_db
def test_maintenance_issue_sends_email_immediately():
    """Issue #463: Email should be sent immediately when maintenance issue is created."""
    from logsheet.models import Airfield, Logsheet

    meister = Member.objects.create(
        username="meister_email", email="meister@example.com"
    )
    glider = Glider.objects.create(
        make="Schempp-Hirth", model="Discus", n_number="N123AB"
    )
    AircraftMeister.objects.create(glider=glider, member=meister)

    airfield = Airfield.objects.create(name="Test Field Email", identifier="TSTE")
    logsheet = Logsheet.objects.create(
        log_date=date(2025, 10, 22),
        airfield=airfield,
        created_by=meister,
        finalized=False,
    )

    with patch("logsheet.signals.send_mail") as mock_send_mail:
        # Create an issue - should send email immediately
        MaintenanceIssue.objects.create(
            glider=glider,
            reported_by=meister,
            logsheet=logsheet,
            description="landing gear issue",
            grounded=True,
        )

        # Verify email was sent
        mock_send_mail.assert_called_once()
        call_kwargs = mock_send_mail.call_args[1]

        # Check email subject contains grounded warning and full aircraft string
        assert "GROUNDED" in call_kwargs["subject"]
        assert str(glider) in call_kwargs["subject"]

        # Check recipient
        assert "meister@example.com" in call_kwargs["recipient_list"]

        # Check email content
        assert "landing gear issue" in call_kwargs["message"]
        assert "landing gear issue" in call_kwargs["html_message"]


@pytest.mark.django_db
def test_maintenance_issue_email_squawk_no_grounded_prefix():
    """Verify squawk (non-grounded) issues send emails without GROUNDED prefix."""
    from logsheet.models import Airfield, Logsheet

    meister = Member.objects.create(username="meister_squawk", email="sq@example.com")
    glider = Glider.objects.create(make="Rolladen", model="LS4", n_number="N456CD")
    AircraftMeister.objects.create(glider=glider, member=meister)

    airfield = Airfield.objects.create(name="Test Field Squawk", identifier="TSQU")
    logsheet = Logsheet.objects.create(
        log_date=date(2025, 10, 22),
        airfield=airfield,
        created_by=meister,
        finalized=False,
    )

    with patch("logsheet.signals.send_mail") as mock_send_mail:
        MaintenanceIssue.objects.create(
            glider=glider,
            reported_by=meister,
            logsheet=logsheet,
            description="minor scratch",
            grounded=False,  # Not grounded
        )

        mock_send_mail.assert_called_once()
        call_kwargs = mock_send_mail.call_args[1]

        # Should NOT have GROUNDED in subject for squawks
        assert "GROUNDED" not in call_kwargs["subject"]


@pytest.mark.django_db
def test_maintenance_issue_resolve_notifies_meisters():
    from logsheet.models import Airfield, Logsheet

    meister = Member.objects.create(username="meister2", email="m2@example.com")
    resolver = Member.objects.create(username="resolver", email="r@example.com")
    glider = Glider.objects.create(make="Schleicher", model="ASW", n_number="G-TEST2")
    AircraftMeister.objects.create(glider=glider, member=meister)

    # Create a logsheet
    airfield = Airfield.objects.create(name="Test Field 2", identifier="TST2")
    logsheet = Logsheet.objects.create(
        log_date=date(2025, 10, 22),
        airfield=airfield,
        created_by=meister,
        finalized=True,
    )

    # Create issue - will immediately create notification and send email (Issue #463)
    with patch("logsheet.signals.send_mail"):  # Mock to avoid actual email
        issue = MaintenanceIssue.objects.create(
            glider=glider,
            reported_by=resolver,
            logsheet=logsheet,
            description="brake check",
            grounded=False,
        )

    # Clear initial notification from creation
    Notification.objects.all().delete()

    # Resolve it - this should send a resolution notification
    issue.resolved = True
    issue.resolved_by = resolver
    issue.save()

    notes = Notification.objects.filter(user=meister, dismissed=False)
    assert notes.exists()
    n = notes.order_by("-created_at").first()
    assert n is not None
    assert "resolved" in n.message.lower()
    assert reverse("logsheet:maintenance_issues") in (n.url or "")


@pytest.mark.django_db
def test_maintenance_notification_dedupe():
    """Test that duplicate notifications are not created for identical issues."""
    from logsheet.models import Airfield, Logsheet

    meister = Member.objects.create(username="meister3", email="m3@example.com")
    glider = Glider.objects.create(make="Schleicher", model="ASW", n_number="G-TEST3")
    AircraftMeister.objects.create(glider=glider, member=meister)

    # Create a logsheet
    airfield = Airfield.objects.create(name="Test Field 3", identifier="TST3")
    logsheet = Logsheet.objects.create(
        log_date=date(2025, 10, 22),
        airfield=airfield,
        created_by=meister,
        finalized=False,
    )

    with patch("logsheet.signals.send_mail"):  # Mock to avoid actual email
        # Create two separate issues with identical descriptions
        # Issue #463: Both creations will trigger immediate notifications
        MaintenanceIssue.objects.create(
            glider=glider,
            reported_by=meister,
            logsheet=logsheet,
            description="battery low",
            grounded=False,
        )
        MaintenanceIssue.objects.create(
            glider=glider,
            reported_by=meister,
            logsheet=logsheet,
            description="battery low",
            grounded=False,
        )

    notes = Notification.objects.filter(
        user=meister, dismissed=False, message__contains="battery low"
    )
    # Dedupe should create exactly one notification despite two issues with identical descriptions
    # The deduplication check in signals.py prevents duplicate notifications
    assert (
        notes.count() == 1
    ), f"Expected 1 notification due to deduplication, got {notes.count()}"


@pytest.mark.django_db
def test_maintenance_issue_no_email_when_no_meisters():
    """Verify no email is sent when there are no meisters assigned to the aircraft."""
    from logsheet.models import Airfield, Logsheet

    reporter = Member.objects.create(username="reporter", email="rep@example.com")
    glider = Glider.objects.create(make="DG", model="DG-300", n_number="N789EF")
    # No meister assigned to this glider

    airfield = Airfield.objects.create(name="Test Field No Meister", identifier="TSNM")
    logsheet = Logsheet.objects.create(
        log_date=date(2025, 10, 22),
        airfield=airfield,
        created_by=reporter,
        finalized=False,
    )

    with patch("logsheet.signals.send_mail") as mock_send_mail:
        MaintenanceIssue.objects.create(
            glider=glider,
            reported_by=reporter,
            logsheet=logsheet,
            description="canopy latch issue",
            grounded=False,
        )

        # Email should NOT be sent when no meisters
        mock_send_mail.assert_not_called()
