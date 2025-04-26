import pytest
from django.contrib.auth import get_user_model
from datetime import date
from logsheet.models import Glider, Towplane, Logsheet, MaintenanceIssue, AircraftMeister, Airfield
from members.models import Member

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
        membership_status="Full Member"  # assuming A = Active
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
        description="Brake inspection needed",
        glider=glider_for_meister,
        resolved=False
    )


@pytest.fixture
def airfield(db):
    return Airfield.objects.create(identifier="KFRR", name="Front Royal Airport")

@pytest.fixture
def active_member(db):
    user = User.objects.create_user(username="active_user", password="testpass123", is_active=True)
    return user

@pytest.fixture
def logsheet(db, airfield, active_member):
    return Logsheet.objects.create(
        log_date=date.today(),
        airfield=airfield,
        created_by=active_member
    )

@pytest.fixture
def active_member(db):
    user = User.objects.create_user(
        username="active_user",
        password="testpass123",
        is_active=True,
        first_name="Active",
        last_name="Member",
        membership_status="Full Member"  # Assuming A = Active
    )
    return user
