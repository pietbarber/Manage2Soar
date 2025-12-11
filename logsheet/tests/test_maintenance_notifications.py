import pytest
from django.urls import reverse

from logsheet.models import AircraftMeister, Glider, MaintenanceIssue
from members.models import Member
from notifications.models import Notification


@pytest.mark.django_db
def test_maintenance_issue_create_notifies_meisters():
    # create a member and assign as meister for a glider
    from logsheet.models import Airfield, Logsheet

    meister = Member.objects.create(username="meister1", email="m1@example.com")
    glider = Glider.objects.create(make="Schleicher", model="ASW", n_number="G-TEST1")
    AircraftMeister.objects.create(glider=glider, member=meister)

    # Create a logsheet (required for maintenance issues)
    airfield = Airfield.objects.create(name="Test Field", identifier="TEST")
    logsheet = Logsheet.objects.create(
        log_date="2025-10-22", airfield=airfield, created_by=meister, finalized=False
    )

    # Create an issue (should NOT notify yet since logsheet is not finalized)
    MaintenanceIssue.objects.create(
        glider=glider,
        reported_by=meister,
        logsheet=logsheet,
        description="wingtip damage",
        grounded=False,
    )

    # Should NOT have notification yet (logsheet not finalized)
    notes = Notification.objects.filter(user=meister, dismissed=False)
    assert not notes.exists()

    # Now finalize the logsheet - this should trigger notifications
    logsheet.finalized = True
    logsheet.save()

    # Now expect a notification for the meister
    notes = Notification.objects.filter(user=meister, dismissed=False)
    assert notes.exists()
    n = notes.first()
    assert n is not None
    assert "wingtip damage" in n.message
    # URL should point to the maintenance list per spec
    assert reverse("logsheet:maintenance_issues") in (n.url or "")


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
        log_date="2025-10-22", airfield=airfield, created_by=meister, finalized=True
    )

    # Create and immediately finalize creates the issue with notification
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
    from logsheet.models import Airfield, Logsheet

    meister = Member.objects.create(username="meister3", email="m3@example.com")
    glider = Glider.objects.create(make="Schleicher", model="ASW", n_number="G-TEST3")
    AircraftMeister.objects.create(glider=glider, member=meister)

    # Create a logsheet
    airfield = Airfield.objects.create(name="Test Field 3", identifier="TST3")
    logsheet = Logsheet.objects.create(
        log_date="2025-10-22", airfield=airfield, created_by=meister, finalized=False
    )

    # Create the same issue twice (simulate duplicate saves) before finalization
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

    # Finalize to trigger notifications
    logsheet.finalized = True
    logsheet.save()

    notes = Notification.objects.filter(
        user=meister, dismissed=False, message__contains="battery low"
    )
    # Dedupe should create exactly one notification despite two issues with identical descriptions
    # The deduplication check in models.py (line 778-780) prevents duplicate notifications
    assert (
        notes.count() == 1
    ), f"Expected 1 notification due to deduplication, got {notes.count()}"
