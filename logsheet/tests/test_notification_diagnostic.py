import pytest
from datetime import time
from django.urls import reverse
from django.utils import timezone

from django.contrib.auth import get_user_model

from logsheet.models import Flight, Logsheet, Airfield
from notifications.models import Notification

User = get_user_model()


@pytest.mark.django_db
def test_notification_created_for_completed_flight(django_user_model):
    # Setup: create users and airfield
    instructor = django_user_model.objects.create_user(
        username="diag_inst", password="pw")
    pilot = django_user_model.objects.create_user(username="diag_pilot", password="pw")
    air = Airfield.objects.create(identifier="KDIAG", name="Diag Field")
    log = Logsheet.objects.create(
        log_date=timezone.now().date(), airfield=air, created_by=instructor)

    # Ensure no pre-existing notifications for this date
    Notification.objects.filter(
        user=instructor, message__contains=log.log_date.isoformat()).delete()

    # Create a completed flight (launch + landing)
    Flight.objects.create(
        logsheet=log,
        pilot=pilot,
        instructor=instructor,
        launch_time=time(9, 0),
        landing_time=time(9, 30),
    )

    # There should be a notification for this instructor containing the log_date
    qs = Notification.objects.filter(
        user=instructor, message__contains=log.log_date.isoformat())
    assert qs.exists(), "Expected a notification for the instructor after a completed flight"

    # The notification should point to the instructors dashboard URL
    expected_url = reverse("instructors:instructors-dashboard")
    assert any(
        n.url == expected_url for n in qs), f"Expected notification url to be {expected_url}"


@pytest.mark.django_db
def test_no_notification_on_landing_time_update_by_default(django_user_model):
    # Setup users and airfield
    instructor = django_user_model.objects.create_user(
        username="diag_inst2", password="pw")
    pilot = django_user_model.objects.create_user(username="diag_pilot2", password="pw")
    air = Airfield.objects.create(identifier="KDIAG2", name="Diag Field 2")
    log = Logsheet.objects.create(
        log_date=timezone.now().date(), airfield=air, created_by=instructor)

    # Clean up any notifications
    Notification.objects.filter(
        user=instructor, message__contains=log.log_date.isoformat()).delete()

    # Create flight with only launch_time (no landing yet)
    f = Flight.objects.create(
        logsheet=log,
        pilot=pilot,
        instructor=instructor,
        launch_time=time(10, 0),
        landing_time=None,
    )

    # No notification should exist yet
    assert not Notification.objects.filter(
        user=instructor, message__contains=log.log_date.isoformat()).exists()

    # Now simulate admin edit: add landing_time and save
    f.landing_time = time(10, 20)
    f.save()

    # With the updated behavior, updating an existing Flight to add landing_time
    # (transitioning to 'landed') SHOULD create a notification
    qs = Notification.objects.filter(
        user=instructor, message__contains=log.log_date.isoformat())
    assert qs.exists(), "Expected a notification after adding landing_time to an existing flight"
