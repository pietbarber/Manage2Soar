from datetime import date, time

import pytest
from django.contrib.auth import get_user_model

from logsheet.models import Flight, Logsheet

User = get_user_model()


@pytest.fixture
def another_member(db):
    user = User.objects.create_user(
        username="another_member",
        password="testpass123",
        is_active=True,
        first_name="Another",
        last_name="Member",
        membership_status="Full Member",
    )
    return user


@pytest.fixture
def logsheet_with_flights(
    db, airfield, active_member, another_member, glider, towplane
):
    logsheet = Logsheet.objects.create(
        log_date=date.today(), airfield=airfield, created_by=active_member
    )
    # Create at least one flight
    Flight.objects.create(
        logsheet=logsheet,
        pilot=active_member,
        glider=glider,
        towplane=towplane,
        launch_time=time(10, 0),
        landing_time=time(11, 0),
        split_with=another_member,
        split_type="even",
    )
    return logsheet
