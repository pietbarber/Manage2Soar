import pytest
from django.urls import reverse

from logsheet.models import MaintenanceIssue, Glider, AircraftMeister
from members.models import Member
from notifications.models import Notification


@pytest.mark.django_db
def test_maintenance_issue_create_notifies_meisters():
    # create a member and assign as meister for a glider
    meister = Member.objects.create(username="meister1", email="m1@example.com")
    glider = Glider.objects.create(make="Schleicher", model="ASW", n_number="G-TEST1")
    AircraftMeister.objects.create(glider=glider, member=meister)

    # Create an issue
    MaintenanceIssue.objects.create(
        glider=glider, reported_by=meister, report_date="2025-10-22", description="wingtip damage", grounded=False)

    # Expect a notification for the meister
    notes = Notification.objects.filter(user=meister, dismissed=False)
    assert notes.exists()
    n = notes.first()
    assert n is not None
    assert "wingtip damage" in n.message
    # URL should point to the maintenance list per spec
    assert reverse("logsheet:maintenance_issues") in (n.url or "")


@pytest.mark.django_db
def test_maintenance_issue_resolve_notifies_meisters():
    meister = Member.objects.create(username="meister2", email="m2@example.com")
    resolver = Member.objects.create(username="resolver", email="r@example.com")
    glider = Glider.objects.create(make="Schleicher", model="ASW", n_number="G-TEST2")
    AircraftMeister.objects.create(glider=glider, member=meister)

    issue = MaintenanceIssue.objects.create(
        glider=glider, reported_by=resolver, report_date="2025-10-22", description="brake check", grounded=False)

    # Resolve it
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
    meister = Member.objects.create(username="meister3", email="m3@example.com")
    glider = Glider.objects.create(make="Schleicher", model="ASW", n_number="G-TEST3")
    AircraftMeister.objects.create(glider=glider, member=meister)

    # Create the same issue twice (simulate duplicate saves)
    MaintenanceIssue.objects.create(
        glider=glider, reported_by=meister, report_date="2025-10-22", description="battery low", grounded=False)
    MaintenanceIssue.objects.create(
        glider=glider, reported_by=meister, report_date="2025-10-22", description="battery low", grounded=False)

    notes = Notification.objects.filter(
        user=meister, dismissed=False, message__contains="battery low")
    # Dedupe should create at most one undismissed notification with identical message
    assert notes.count() <= 1
