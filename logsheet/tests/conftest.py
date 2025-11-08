from datetime import date

import pytest
from django.contrib.auth import get_user_model

from logsheet.models import (
    AircraftMeister,
    Airfield,
    Glider,
    Logsheet,
    MaintenanceIssue,
    Towplane,
)

from .test_fixtures_finances import *

User = get_user_model()


@pytest.fixture
def active_member(db):
    user = User.objects.create_user(
        username="active_user",
        password="testpass123",
        is_active=True,
        first_name="Active",
        last_name="Member",
        membership_status="Full Member",
    )
    return user


User = get_user_model()


@pytest.fixture
def glider_for_meister(db):
    return Glider.objects.create(n_number="N123AB", club_owned=True, is_active=True)


@pytest.fixture
def meister_member(db, glider_for_meister):
    user = User.objects.create_user(
        username="meister_user",
        password="testpass123",
        is_active=True,
        first_name="Meister",
        last_name="User",
        membership_status="Full Member",  # assuming A = Active
    )
    AircraftMeister.objects.create(glider=glider_for_meister, member=user)
    return user


@pytest.fixture
def glider(db):
    return Glider.objects.create(n_number="N456CD", club_owned=True, is_active=True)


@pytest.fixture
def towplane(db):
    return Towplane.objects.create(n_number="N789EF", club_owned=True, is_active=True)


@pytest.fixture
def maintenance_issue(db, glider_for_meister):
    return MaintenanceIssue.objects.create(
        description="Brake inspection needed", glider=glider_for_meister, resolved=False
    )


@pytest.fixture
def airfield(db):
    return Airfield.objects.create(identifier="KFRR", name="Front Royal Airport")


@pytest.fixture
def logsheet(db, airfield, active_member):
    return Logsheet.objects.create(
        log_date=date.today(), airfield=airfield, created_by=active_member
    )


@pytest.fixture
def member_instructor(db):
    """Creates a member who is an instructor"""
    user = User.objects.create_user(
        username="instructor_user",
        password="testpass123",
        is_active=True,
        first_name="Instructor",
        last_name="Smith",
        membership_status="Full Member",
        instructor=True,
    )
    return user


@pytest.fixture
def member_instructor2(db):
    """Creates a second member who is an instructor"""
    user = User.objects.create_user(
        username="instructor_user2",
        password="testpass123",
        is_active=True,
        first_name="Second",
        last_name="Instructor",
        membership_status="Full Member",
        instructor=True,
    )
    return user


@pytest.fixture
def member_towpilot(db):
    """Creates a member who is a tow pilot"""
    user = User.objects.create_user(
        username="towpilot_user",
        password="testpass123",
        is_active=True,
        first_name="Towpilot",
        last_name="Jones",
        membership_status="Full Member",
        towpilot=True,
    )
    return user


@pytest.fixture
def member_towpilot2(db):
    """Creates a second member who is a tow pilot"""
    user = User.objects.create_user(
        username="towpilot_user2",
        password="testpass123",
        is_active=True,
        first_name="Second",
        last_name="Towpilot",
        membership_status="Full Member",
        towpilot=True,
    )
    return user


@pytest.fixture
def member_instructor_towpilot(db):
    """Creates a member who is both an instructor and tow pilot"""
    user = User.objects.create_user(
        username="instructor_towpilot_user",
        password="testpass123",
        is_active=True,
        first_name="Multi",
        last_name="Role",
        membership_status="Full Member",
        instructor=True,
        towpilot=True,
    )
    return user


@pytest.fixture
def member_duty_officer(db):
    """Creates a member who is a duty officer and assistant duty officer"""
    user = User.objects.create_user(
        username="duty_officer_user",
        password="testpass123",
        is_active=True,
        first_name="Duty",
        last_name="Officer",
        membership_status="Full Member",
        duty_officer=True,
        assistant_duty_officer=True,
    )
    return user


@pytest.fixture
def member_duty_officer_instructor(db):
    """Creates a member who is both duty officer and instructor"""
    user = User.objects.create_user(
        username="duty_officer_instructor_user",
        password="testpass123",
        is_active=True,
        first_name="DutyOfficer",
        last_name="Instructor",
        membership_status="Full Member",
        duty_officer=True,
        instructor=True,
    )
    return user


@pytest.fixture
def member_duty_officer_towpilot(db):
    """Creates a member who is both duty officer and tow pilot"""
    user = User.objects.create_user(
        username="duty_officer_towpilot_user",
        password="testpass123",
        is_active=True,
        first_name="DutyOfficer",
        last_name="Towpilot",
        membership_status="Full Member",
        duty_officer=True,
        towpilot=True,
    )
    return user
