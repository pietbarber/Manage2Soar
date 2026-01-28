import pytest
from django.urls import reverse

from logsheet.models import MaintenanceIssue


@pytest.mark.django_db
def test_manage_logsheet_finances_view_accessible(client, active_member, logsheet):
    client.force_login(active_member)
    response = client.get(
        reverse("logsheet:manage_logsheet_finances", args=[logsheet.pk])
    )
    assert response.status_code == 200
    assert "flight_data" in response.context


@pytest.mark.django_db
def test_edit_logsheet_closeout_view(client, active_member, logsheet):
    client.force_login(active_member)
    response = client.get(
        reverse("logsheet:edit_logsheet_closeout", args=[logsheet.pk])
    )
    assert response.status_code == 200
    assert "form" in response.context
    # Issue #411: Verify tow_pilots_data is in context
    assert "tow_pilots_data" in response.context
    # Should be a dict (empty if no flights with tow pilots)
    assert isinstance(response.context["tow_pilots_data"], dict)


@pytest.mark.django_db
def test_edit_logsheet_closeout_tow_pilot_summary(
    client, active_member, logsheet, member_towpilot, towplane, glider
):
    """Issue #411: Test tow pilot summary data structure and aggregation"""
    from datetime import time

    from logsheet.models import Flight

    client.force_login(active_member)

    # Create flights with same pilot, same towplane - should aggregate
    Flight.objects.create(
        logsheet=logsheet,
        pilot=active_member,
        glider=glider,
        tow_pilot=member_towpilot,
        towplane=towplane,
        release_altitude=2000,
        launch_time=time(10, 0),
        landing_time=time(11, 0),
    )
    Flight.objects.create(
        logsheet=logsheet,
        pilot=active_member,
        glider=glider,
        tow_pilot=member_towpilot,
        towplane=towplane,
        release_altitude=3000,
        launch_time=time(12, 0),
        landing_time=time(13, 0),
    )

    response = client.get(
        reverse("logsheet:edit_logsheet_closeout", args=[logsheet.pk])
    )

    tow_pilots_data = response.context["tow_pilots_data"]
    assert len(tow_pilots_data) == 1

    # Get the pilot's data (dict keys are pilot names)
    pilot_data = list(tow_pilots_data.values())[0]

    # Verify structure
    assert "towplanes" in pilot_data
    assert "total_tows" in pilot_data
    assert "total_feet" in pilot_data

    # Verify aggregation: 2 tows, 5000 total feet
    assert pilot_data["total_tows"] == 2
    assert pilot_data["total_feet"] == 5000

    # Verify towplane breakdown
    assert len(pilot_data["towplanes"]) == 1
    assert pilot_data["towplanes"][0]["tow_count"] == 2
    assert pilot_data["towplanes"][0]["total_feet"] == 5000

    # Verify template renders without errors
    assert b"Tow Pilot Summary" in response.content
    assert b"Towpilot Jones" in response.content
    assert b"Total" in response.content


@pytest.mark.django_db
def test_edit_logsheet_closeout_tow_pilot_multiple_towplanes(
    client, active_member, logsheet, member_towpilot, glider
):
    """Issue #411: Test tow pilot with multiple towplanes - verify grouping"""
    from datetime import time

    from logsheet.models import Flight, Towplane

    client.force_login(active_member)

    # Create two different towplanes
    towplane1 = Towplane.objects.create(n_number="N123AB", make="Piper", model="Pawnee")
    towplane2 = Towplane.objects.create(n_number="N456CD", make="Cessna", model="L-19")

    # Same pilot, different towplanes
    Flight.objects.create(
        logsheet=logsheet,
        pilot=active_member,
        glider=glider,
        tow_pilot=member_towpilot,
        towplane=towplane1,
        release_altitude=2000,
        launch_time=time(10, 0),
        landing_time=time(11, 0),
    )
    Flight.objects.create(
        logsheet=logsheet,
        pilot=active_member,
        glider=glider,
        tow_pilot=member_towpilot,
        towplane=towplane2,
        release_altitude=3000,
        launch_time=time(12, 0),
        landing_time=time(13, 0),
    )

    response = client.get(
        reverse("logsheet:edit_logsheet_closeout", args=[logsheet.pk])
    )

    tow_pilots_data = response.context["tow_pilots_data"]
    assert len(tow_pilots_data) == 1

    pilot_data = list(tow_pilots_data.values())[0]
    assert pilot_data["total_tows"] == 2
    assert pilot_data["total_feet"] == 5000

    # Should have 2 towplane entries
    assert len(pilot_data["towplanes"]) == 2
    towplane_n_numbers = {tp["n_number"] for tp in pilot_data["towplanes"]}
    assert "N123AB" in towplane_n_numbers
    assert "N456CD" in towplane_n_numbers

    # Verify template renders without errors
    assert b"Tow Pilot Summary" in response.content
    assert b"Towpilot Jones" in response.content
    assert b"N123AB" in response.content
    assert b"N456CD" in response.content


@pytest.mark.django_db
def test_edit_logsheet_closeout_tow_pilot_null_release_altitude(
    client, active_member, logsheet, member_towpilot, towplane, glider
):
    """Issue #411: Test NULL release_altitude - verify Sum handles nulls correctly"""
    from datetime import time

    from logsheet.models import Flight

    client.force_login(active_member)

    # Flight with null release_altitude
    Flight.objects.create(
        logsheet=logsheet,
        pilot=active_member,
        glider=glider,
        tow_pilot=member_towpilot,
        towplane=towplane,
        release_altitude=None,
        launch_time=time(10, 0),
        landing_time=time(11, 0),
    )
    # Flight with valid release_altitude
    Flight.objects.create(
        logsheet=logsheet,
        pilot=active_member,
        glider=glider,
        tow_pilot=member_towpilot,
        towplane=towplane,
        release_altitude=2000,
        launch_time=time(12, 0),
        landing_time=time(13, 0),
    )

    response = client.get(
        reverse("logsheet:edit_logsheet_closeout", args=[logsheet.pk])
    )

    tow_pilots_data = response.context["tow_pilots_data"]
    pilot_data = list(tow_pilots_data.values())[0]

    # Should count both tows, total_feet should handle NULL correctly (0 + 2000)
    assert pilot_data["total_tows"] == 2
    assert pilot_data["total_feet"] == 2000

    # Verify template renders without errors
    assert b"Tow Pilot Summary" in response.content
    assert b"Towpilot Jones" in response.content


@pytest.mark.django_db
def test_edit_logsheet_closeout_tow_pilot_empty_names(
    client, active_member, logsheet, towplane, glider
):
    """Issue #411: Test pilots with empty names - verify unique keys and fallback"""
    from datetime import time

    from logsheet.models import Flight
    from members.models import Member

    client.force_login(active_member)

    # Create two pilots with empty names (different IDs)
    pilot1 = Member.objects.create(username="pilot1", first_name="", last_name="")
    pilot2 = Member.objects.create(username="pilot2", first_name="", last_name="")

    # Create flights with different unnamed pilots
    Flight.objects.create(
        logsheet=logsheet,
        pilot=active_member,
        glider=glider,
        tow_pilot=pilot1,
        towplane=towplane,
        release_altitude=2000,
        launch_time=time(10, 0),
        landing_time=time(11, 0),
    )
    Flight.objects.create(
        logsheet=logsheet,
        pilot=active_member,
        glider=glider,
        tow_pilot=pilot2,
        towplane=towplane,
        release_altitude=3000,
        launch_time=time(12, 0),
        landing_time=time(13, 0),
    )

    response = client.get(
        reverse("logsheet:edit_logsheet_closeout", args=[logsheet.pk])
    )

    tow_pilots_data = response.context["tow_pilots_data"]

    # Should have 2 separate entries (not grouped together)
    assert len(tow_pilots_data) == 2

    # Both should be named "Unknown Pilot"
    for pilot_data in tow_pilots_data.values():
        assert pilot_data["name"] == "Unknown Pilot"
        assert pilot_data["total_tows"] == 1

    # Verify template renders without errors and shows "Unknown Pilot"
    assert b"Tow Pilot Summary" in response.content
    assert b"Unknown Pilot" in response.content
    assert b"Unknown Pilot Total" in response.content


@pytest.mark.django_db
def test_view_logsheet_closeout_view(client, active_member, logsheet):
    client.force_login(active_member)
    response = client.get(
        reverse("logsheet:view_logsheet_closeout", args=[logsheet.pk])
    )
    assert response.status_code == 200
    assert "maintenance_issues" in response.context


@pytest.mark.django_db
def test_add_maintenance_issue_success(client, active_member, glider, logsheet):
    client.force_login(active_member)
    response = client.post(
        reverse("logsheet:add_maintenance_issue", args=[logsheet.pk]),
        {
            "description": "Flat tire",
            "glider": glider.pk,
        },
    )
    assert response.status_code == 302
    assert MaintenanceIssue.objects.filter(description="Flat tire").exists()


@pytest.mark.django_db
def test_add_maintenance_issue_ajax_success(client, active_member, glider, logsheet):
    """Test AJAX submission of maintenance issue returns JSON response"""
    client.force_login(active_member)
    response = client.post(
        reverse("logsheet:add_maintenance_issue", args=[logsheet.pk]),
        {"description": "Flat tire on main gear", "glider": glider.pk},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "issue" in data
    assert data["issue"]["description"] == "Flat tire on main gear"
    assert data["issue"]["glider"] == str(glider)
    assert MaintenanceIssue.objects.filter(
        description="Flat tire on main gear"
    ).exists()


@pytest.mark.django_db
def test_add_maintenance_issue_ajax_validation_error(client, active_member, logsheet):
    """Test AJAX submission with missing aircraft returns error"""
    client.force_login(active_member)
    response = client.post(
        reverse("logsheet:add_maintenance_issue", args=[logsheet.pk]),
        {"description": "Issue without aircraft"},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert "error" in data
    assert "errors" in data  # Should include detailed form errors


@pytest.mark.django_db
def test_add_maintenance_issue_ajax_grounded_flag(
    client, active_member, towplane, logsheet
):
    """Test AJAX submission with grounded flag"""
    client.force_login(active_member)
    response = client.post(
        reverse("logsheet:add_maintenance_issue", args=[logsheet.pk]),
        {
            "description": "Engine failure",
            "towplane": towplane.pk,
            "grounded": True,
        },
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["issue"]["grounded"] is True
    issue = MaintenanceIssue.objects.get(description="Engine failure")
    assert issue.grounded is True


@pytest.mark.django_db
def test_equipment_list_view(client, active_member):
    client.force_login(active_member)
    response = client.get(reverse("logsheet:equipment_list"))
    assert response.status_code == 200
    assert "gliders" in response.context


@pytest.mark.django_db
def test_maintenance_issues_view(client, active_member):
    client.force_login(active_member)
    response = client.get(reverse("logsheet:maintenance_issues"))
    assert response.status_code == 200
    assert "open_issues" in response.context


@pytest.mark.django_db
def test_mark_issue_resolved_authorized(client, meister_member, maintenance_issue):
    client.force_login(meister_member)
    response = client.post(
        reverse("logsheet:maintenance_mark_resolved", args=[maintenance_issue.pk]),
        {"resolution_notes": "Fixed brake inspection issue."},
    )
    assert response.status_code == 200
    maintenance_issue.refresh_from_db()
    assert maintenance_issue.resolved is True


@pytest.mark.django_db
def test_resolve_maintenance_issue_post(client, meister_member, maintenance_issue):
    client.force_login(meister_member)
    response = client.post(
        reverse("logsheet:maintenance_mark_resolved", args=[maintenance_issue.pk]),
        {"resolution_notes": "Fixed valve."},
    )
    assert response.status_code == 200
    maintenance_issue.refresh_from_db()
    assert maintenance_issue.resolved is True


@pytest.mark.django_db
def test_maintenance_mark_resolved_requires_notes(
    client, meister_member, maintenance_issue
):
    client.force_login(meister_member)
    response = client.post(
        reverse("logsheet:maintenance_mark_resolved", args=[maintenance_issue.pk]),
        {"resolution_notes": ""},
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_maintenance_mark_resolved_success(client, meister_member, maintenance_issue):
    client.force_login(meister_member)
    response = client.post(
        reverse("logsheet:maintenance_mark_resolved", args=[maintenance_issue.pk]),
        {"resolution_notes": "Patched leak."},
    )
    assert response.status_code == 200
    maintenance_issue.refresh_from_db()
    assert maintenance_issue.resolved is True


@pytest.mark.django_db
def test_maintenance_deadlines_view(client, active_member):
    client.force_login(active_member)
    response = client.get(reverse("logsheet:maintenance_deadlines"))
    assert response.status_code == 200
    assert "deadlines" in response.context


# =============================================================================
# Tests for standalone add maintenance issue (Issue #553)
# =============================================================================


@pytest.mark.django_db
def test_add_maintenance_issue_standalone_success(client, active_member, glider):
    """Test standalone maintenance issue submission without logsheet"""
    client.force_login(active_member)
    response = client.post(
        reverse("logsheet:add_maintenance_issue_standalone"),
        {
            "description": "Canopy latch needs adjustment",
            "glider": glider.pk,
        },
    )
    # Should redirect to maintenance issues page
    assert response.status_code == 302
    assert response.url == reverse("logsheet:maintenance_issues")

    # Verify issue was created
    issue = MaintenanceIssue.objects.get(description="Canopy latch needs adjustment")
    assert issue.glider == glider
    assert issue.reported_by == active_member
    assert issue.logsheet is None  # No logsheet association


@pytest.mark.django_db
def test_add_maintenance_issue_standalone_with_towplane(
    client, active_member, towplane
):
    """Test standalone maintenance issue for towplane"""
    client.force_login(active_member)
    response = client.post(
        reverse("logsheet:add_maintenance_issue_standalone"),
        {
            "description": "Engine running rough",
            "towplane": towplane.pk,
            "grounded": "on",
        },
    )
    assert response.status_code == 302

    issue = MaintenanceIssue.objects.get(description="Engine running rough")
    assert issue.towplane == towplane
    assert issue.grounded is True


@pytest.mark.django_db
def test_add_maintenance_issue_standalone_validation_error(client, active_member):
    """Test standalone submission with missing aircraft shows error"""
    client.force_login(active_member)
    response = client.post(
        reverse("logsheet:add_maintenance_issue_standalone"),
        {"description": "Issue without aircraft"},
    )
    # Should redirect back with error message
    assert response.status_code == 302
    assert response.url == reverse("logsheet:maintenance_issues")
    # Issue should NOT be created
    assert not MaintenanceIssue.objects.filter(
        description="Issue without aircraft"
    ).exists()


@pytest.mark.django_db
def test_add_maintenance_issue_standalone_requires_post(client, active_member):
    """Test standalone endpoint only accepts POST"""
    client.force_login(active_member)
    response = client.get(reverse("logsheet:add_maintenance_issue_standalone"))
    assert response.status_code == 405  # Method not allowed


@pytest.mark.django_db
def test_add_maintenance_issue_standalone_requires_login(client, glider):
    """Test standalone endpoint requires authentication"""
    response = client.post(
        reverse("logsheet:add_maintenance_issue_standalone"),
        {
            "description": "Test issue",
            "glider": glider.pk,
        },
    )
    # Should redirect to login
    assert response.status_code == 302
    assert "/login/" in response.url or "/accounts/login/" in response.url


@pytest.mark.django_db
def test_maintenance_issues_view_includes_aircraft_for_modal(client, active_member):
    """Test maintenance issues view passes gliders and towplanes for Add Issue modal"""
    client.force_login(active_member)
    response = client.get(reverse("logsheet:maintenance_issues"))
    assert response.status_code == 200
    # Issue #553: View should include aircraft for the Add Issue modal
    assert "gliders" in response.context
    assert "towplanes" in response.context
