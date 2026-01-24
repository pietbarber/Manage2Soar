"""
Tests for maintenance deadline update functionality (Issue #541).

Tests that maintenance officers (Aircraft Meisters) and webmasters can update
maintenance deadlines via the web interface.
"""

from datetime import date

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from logsheet.models import AircraftMeister, Glider, MaintenanceDeadline, Towplane
from members.models import Member


@pytest.fixture
def webmaster_group():
    """Create Webmasters group."""
    return Group.objects.get_or_create(name="Webmasters")[0]


@pytest.fixture
def glider():
    """Create a test glider."""
    return Glider.objects.create(
        make="Schleicher",
        model="ASW 28",
        n_number="N123AB",
        competition_number="AB",
    )


@pytest.fixture
def towplane():
    """Create a test towplane."""
    return Towplane.objects.create(
        name="Pawnee", make="Piper", model="PA-25", n_number="N456CD"
    )


@pytest.fixture
def maintenance_officer(glider):
    """Create a maintenance officer (Aircraft Meister) for the glider."""
    officer = Member.objects.create(
        username="maintenance_officer",
        email="officer@example.com",
        membership_status="Full Member",
    )
    AircraftMeister.objects.create(glider=glider, member=officer)
    return officer


@pytest.fixture
def webmaster(webmaster_group):
    """Create a webmaster."""
    webmaster = Member.objects.create(
        username="webmaster",
        email="webmaster@example.com",
        membership_status="Full Member",
    )
    webmaster.groups.add(webmaster_group)
    return webmaster


@pytest.fixture
def regular_member():
    """Create a regular member with no special permissions."""
    return Member.objects.create(
        username="regular_member",
        email="regular@example.com",
        membership_status="Full Member",
    )


@pytest.fixture
def glider_deadline(glider):
    """Create a maintenance deadline for the glider."""
    return MaintenanceDeadline.objects.create(
        glider=glider, description="annual", due_date=date(2026, 6, 30)
    )


@pytest.fixture
def towplane_deadline(towplane):
    """Create a maintenance deadline for the towplane."""
    return MaintenanceDeadline.objects.create(
        towplane=towplane, description="annual", due_date=date(2026, 7, 15)
    )


@pytest.mark.django_db
class TestMaintenanceDeadlinePermissions:
    """Test permission checks for updating maintenance deadlines."""

    def test_maintenance_officer_can_update_their_aircraft_deadline(
        self, client, maintenance_officer, glider_deadline
    ):
        """Maintenance officer can update deadline for their assigned aircraft."""
        client.force_login(maintenance_officer)

        response = client.post(
            reverse(
                "logsheet:update_maintenance_deadline",
                kwargs={"deadline_id": glider_deadline.id},
            ),
            data={"due_date": "2027-01-31"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["new_due_date"] == "2027-01-31"

        # Verify deadline was actually updated
        glider_deadline.refresh_from_db()
        assert glider_deadline.due_date == date(2027, 1, 31)

    def test_maintenance_officer_cannot_update_other_aircraft_deadline(
        self, client, maintenance_officer, towplane_deadline
    ):
        """Maintenance officer cannot update deadline for aircraft they don't maintain."""
        client.force_login(maintenance_officer)

        response = client.post(
            reverse(
                "logsheet:update_maintenance_deadline",
                kwargs={"deadline_id": towplane_deadline.id},
            ),
            data={"due_date": "2027-02-28"},
        )

        assert response.status_code == 403
        data = response.json()
        assert data["success"] is False
        assert "not authorized" in data["error"]

        # Verify deadline was NOT updated
        towplane_deadline.refresh_from_db()
        assert towplane_deadline.due_date == date(2026, 7, 15)

    def test_webmaster_can_update_any_deadline(
        self, client, webmaster, glider_deadline, towplane_deadline
    ):
        """Webmasters can update deadlines for any aircraft."""
        client.force_login(webmaster)

        # Update glider deadline
        response1 = client.post(
            reverse(
                "logsheet:update_maintenance_deadline",
                kwargs={"deadline_id": glider_deadline.id},
            ),
            data={"due_date": "2027-03-15"},
        )
        assert response1.status_code == 200
        assert response1.json()["success"] is True

        # Update towplane deadline
        response2 = client.post(
            reverse(
                "logsheet:update_maintenance_deadline",
                kwargs={"deadline_id": towplane_deadline.id},
            ),
            data={"due_date": "2027-04-20"},
        )
        assert response2.status_code == 200
        assert response2.json()["success"] is True

        # Verify both were updated
        glider_deadline.refresh_from_db()
        towplane_deadline.refresh_from_db()
        assert glider_deadline.due_date == date(2027, 3, 15)
        assert towplane_deadline.due_date == date(2027, 4, 20)

    def test_superuser_can_update_any_deadline(
        self, client, glider_deadline, towplane_deadline
    ):
        """Superusers can update deadlines for any aircraft."""
        superuser = Member.objects.create(
            username="superuser",
            email="super@example.com",
            membership_status="Full Member",
            is_superuser=True,
        )
        client.force_login(superuser)

        response = client.post(
            reverse(
                "logsheet:update_maintenance_deadline",
                kwargs={"deadline_id": glider_deadline.id},
            ),
            data={"due_date": "2027-05-10"},
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

        glider_deadline.refresh_from_db()
        assert glider_deadline.due_date == date(2027, 5, 10)

    def test_regular_member_cannot_update_any_deadline(
        self, client, regular_member, glider_deadline
    ):
        """Regular members cannot update maintenance deadlines."""
        client.force_login(regular_member)

        response = client.post(
            reverse(
                "logsheet:update_maintenance_deadline",
                kwargs={"deadline_id": glider_deadline.id},
            ),
            data={"due_date": "2027-06-01"},
        )

        assert response.status_code == 403
        data = response.json()
        assert data["success"] is False
        assert "not authorized" in data["error"]

    def test_anonymous_user_cannot_update_deadline(self, client, glider_deadline):
        """Anonymous users cannot update maintenance deadlines."""
        response = client.post(
            reverse(
                "logsheet:update_maintenance_deadline",
                kwargs={"deadline_id": glider_deadline.id},
            ),
            data={"due_date": "2027-07-01"},
        )

        # Should redirect to login (active_member_required decorator)
        assert response.status_code == 302


@pytest.mark.django_db
class TestMaintenanceDeadlineValidation:
    """Test input validation for deadline updates."""

    def test_missing_due_date_returns_error(self, client, webmaster, glider_deadline):
        """Missing due_date parameter returns 400 error."""
        client.force_login(webmaster)

        response = client.post(
            reverse(
                "logsheet:update_maintenance_deadline",
                kwargs={"deadline_id": glider_deadline.id},
            ),
            data={},  # Missing due_date
        )

        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert "required" in data["error"].lower()

    def test_invalid_date_format_returns_error(
        self, client, webmaster, glider_deadline
    ):
        """Invalid date format returns 400 error."""
        client.force_login(webmaster)

        response = client.post(
            reverse(
                "logsheet:update_maintenance_deadline",
                kwargs={"deadline_id": glider_deadline.id},
            ),
            data={"due_date": "31/12/2027"},  # Wrong format
        )

        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert "Invalid date format" in data["error"]

    def test_non_post_request_rejected(self, client, webmaster, glider_deadline):
        """GET requests are rejected (require_POST decorator)."""
        client.force_login(webmaster)

        response = client.get(
            reverse(
                "logsheet:update_maintenance_deadline",
                kwargs={"deadline_id": glider_deadline.id},
            )
        )

        assert response.status_code == 405  # Method Not Allowed

    def test_nonexistent_deadline_returns_404(self, client, webmaster):
        """Requesting non-existent deadline returns 404."""
        client.force_login(webmaster)

        response = client.post(
            reverse(
                "logsheet:update_maintenance_deadline",
                kwargs={"deadline_id": 99999},
            ),
            data={"due_date": "2027-08-01"},
        )

        assert response.status_code == 404


@pytest.mark.django_db
class TestMaintenanceDeadlineDisplay:
    """Test the maintenance_deadlines view displays correct permissions."""

    def test_maintenance_officer_sees_update_button_for_their_aircraft(
        self, client, maintenance_officer, glider_deadline
    ):
        """Maintenance officer sees Update button for their assigned aircraft."""
        client.force_login(maintenance_officer)

        response = client.get(reverse("logsheet:maintenance_deadlines"))

        assert response.status_code == 200
        assert b"update-deadline-btn" in response.content
        assert "meister_gliders" in response.context
        assert glider_deadline.glider.id in response.context["meister_gliders"]

    def test_webmaster_sees_update_button_for_all_aircraft(
        self, client, webmaster, glider_deadline, towplane_deadline
    ):
        """Webmasters see Update button for all aircraft."""
        client.force_login(webmaster)

        response = client.get(reverse("logsheet:maintenance_deadlines"))

        assert response.status_code == 200
        assert response.context["is_webmaster"] is True
        # Should see two Update buttons (one for glider, one for towplane)
        assert response.content.count(b"update-deadline-btn") >= 2

    def test_regular_member_does_not_see_update_buttons(
        self, client, regular_member, glider_deadline
    ):
        """Regular members do not see Update buttons."""
        client.force_login(regular_member)

        response = client.get(reverse("logsheet:maintenance_deadlines"))

        assert response.status_code == 200
        # No Actions column
        assert b"update-deadline-btn" not in response.content
        assert response.context["is_webmaster"] is False
        assert not response.context["meister_gliders"]
        assert not response.context["meister_towplanes"]
        assert response.context["can_update_deadlines"] is False

    def test_superuser_sees_update_button_for_all_aircraft(
        self, client, glider_deadline, towplane_deadline
    ):
        """Superusers see Update button for all aircraft even without webmaster group."""
        superuser = Member.objects.create(
            username="superuser",
            email="super@example.com",
            membership_status="Full Member",
            is_superuser=True,
        )
        client.force_login(superuser)

        response = client.get(reverse("logsheet:maintenance_deadlines"))

        assert response.status_code == 200
        assert (
            response.context["is_webmaster"] is True
        )  # Superusers treated as webmasters
        assert response.context["can_update_deadlines"] is True
        # Should see two Update buttons (one for glider, one for towplane)
        assert response.content.count(b"update-deadline-btn") >= 2


@pytest.mark.django_db
class TestMultipleMaintenanceOfficers:
    """Test scenarios with multiple maintenance officers."""

    def test_multiple_officers_for_same_aircraft(self, glider):
        """Multiple officers can be assigned to the same aircraft."""
        officer1 = Member.objects.create(
            username="officer1", email="o1@example.com", membership_status="Full Member"
        )
        officer2 = Member.objects.create(
            username="officer2", email="o2@example.com", membership_status="Full Member"
        )

        AircraftMeister.objects.create(glider=glider, member=officer1)
        AircraftMeister.objects.create(glider=glider, member=officer2)

        deadline = MaintenanceDeadline.objects.create(
            glider=glider, description="annual", due_date=date(2026, 8, 1)
        )

        # Both officers should be able to update
        from django.test import Client

        client = Client()

        # Officer 1
        client.force_login(officer1)
        response1 = client.post(
            reverse(
                "logsheet:update_maintenance_deadline",
                kwargs={"deadline_id": deadline.id},
            ),
            data={"due_date": "2027-09-01"},
        )
        assert response1.json()["success"] is True

        # Officer 2
        client.force_login(officer2)
        response2 = client.post(
            reverse(
                "logsheet:update_maintenance_deadline",
                kwargs={"deadline_id": deadline.id},
            ),
            data={"due_date": "2027-10-01"},
        )
        assert response2.json()["success"] is True

    def test_officer_with_multiple_aircraft_assignments(self, client, glider, towplane):
        """Officer assigned to multiple aircraft can update all their deadlines."""
        multi_officer = Member.objects.create(
            username="multi_officer",
            email="multi@example.com",
            membership_status="Full Member",
        )
        AircraftMeister.objects.create(glider=glider, member=multi_officer)
        AircraftMeister.objects.create(towplane=towplane, member=multi_officer)

        glider_deadline = MaintenanceDeadline.objects.create(
            glider=glider, description="annual", due_date=date(2026, 9, 1)
        )
        towplane_deadline = MaintenanceDeadline.objects.create(
            towplane=towplane, description="100hr", due_date=date(2026, 10, 1)
        )

        client.force_login(multi_officer)

        # Should be able to update both
        response1 = client.post(
            reverse(
                "logsheet:update_maintenance_deadline",
                kwargs={"deadline_id": glider_deadline.id},
            ),
            data={"due_date": "2027-11-01"},
        )
        response2 = client.post(
            reverse(
                "logsheet:update_maintenance_deadline",
                kwargs={"deadline_id": towplane_deadline.id},
            ),
            data={"due_date": "2027-12-01"},
        )

        assert response1.json()["success"] is True
        assert response2.json()["success"] is True


@pytest.mark.django_db
def test_maintenance_deadline_constraint_requires_aircraft():
    """Test that database constraint prevents creating deadlines without aircraft."""
    from django.db import IntegrityError

    with pytest.raises(IntegrityError) as exc_info:
        MaintenanceDeadline.objects.create(
            glider=None, towplane=None, description="annual", due_date=date(2026, 12, 1)
        )

    # Verify the error is from our constraint
    assert "maintenance_deadline_must_have_aircraft" in str(exc_info.value)
