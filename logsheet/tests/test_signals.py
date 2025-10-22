import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import time

from logsheet.models import Flight, Logsheet
from notifications.models import Notification

User = get_user_model()


@pytest.mark.django_db
def test_instructor_notified_on_flight_creation(django_user_model):
    instructor = django_user_model.objects.create_user(username="inst", password="pw")
    pilot = django_user_model.objects.create_user(username="pilot", password="pw")
    log = Logsheet.objects.create(
        log_date=timezone.now().date(), airfield_id=1, created_by=instructor)
    # Create flight with both pilot and instructor and completed times
    f = Flight.objects.create(
        logsheet=log,
        pilot=pilot,
        instructor=instructor,
        launch_time=time(10, 0),
        landing_time=time(10, 30),
    )
    # A notification should be created for the instructor
    assert Notification.objects.filter(user=instructor).exists()


@pytest.mark.django_db
def test_no_duplicate_notifications_same_day(django_user_model):
    instructor = django_user_model.objects.create_user(username="inst2", password="pw")
    pilot1 = django_user_model.objects.create_user(username="p1", password="pw")
    pilot2 = django_user_model.objects.create_user(username="p2", password="pw")
    log = Logsheet.objects.create(
        log_date=timezone.now().date(), airfield_id=1, created_by=instructor)
    # First flight creates notification (completed)
    Flight.objects.create(
        logsheet=log,
        pilot=pilot1,
        instructor=instructor,
        launch_time=time(9, 0),
        landing_time=time(9, 30),
    )
    # Second flight same day should not create another notification
    Flight.objects.create(
        logsheet=log,
        pilot=pilot2,
        instructor=instructor,
        launch_time=time(11, 0),
        landing_time=time(11, 20),
    )
    assert Notification.objects.filter(user=instructor).count() == 1
