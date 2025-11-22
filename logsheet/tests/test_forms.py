from datetime import date

import pytest

from logsheet.forms import (
    CreateLogsheetForm,
    LogsheetDutyCrewForm,
    MaintenanceIssueForm,
)


@pytest.mark.django_db
def test_maintenance_issue_form_valid_with_glider(glider):
    form = MaintenanceIssueForm(
        data={"description": "Landing gear squeak", "glider": glider.id}
    )
    assert form.is_valid()


@pytest.mark.django_db
def test_maintenance_issue_form_valid_with_towplane(towplane):
    form = MaintenanceIssueForm(
        data={"description": "Tow hook fraying", "towplane": towplane.id}
    )
    assert form.is_valid()


@pytest.mark.django_db
def test_maintenance_issue_form_invalid_without_aircraft():
    form = MaintenanceIssueForm(data={"description": "Mystery problem"})
    assert not form.is_valid()
    assert "__all__" in form.errors


@pytest.mark.django_db
def test_maintenance_issue_form_invalid_without_description(glider):
    form = MaintenanceIssueForm(data={"glider": glider.id})
    assert not form.is_valid()
    assert "description" in form.errors


@pytest.mark.django_db
def test_maintenance_issue_form_error_message_without_aircraft():
    form = MaintenanceIssueForm(data={"description": "Mystery issue"})
    form.is_valid()
    error_messages = form.errors.get("__all__", [])
    assert any("glider or a towplane" in msg.lower() for msg in error_messages)


# CreateLogsheetForm validation tests
@pytest.mark.django_db
def test_create_logsheet_form_prevents_duplicate_instructor_surge_instructor(
    member_instructor, airfield
):
    """Test that instructor and surge instructor cannot be the same person"""
    form = CreateLogsheetForm(
        data={
            "log_date": date.today(),
            "airfield": airfield.id,
            "duty_instructor": member_instructor.id,
            "surge_instructor": member_instructor.id,
        }
    )
    assert not form.is_valid()
    assert "__all__" in form.errors
    error_messages = form.errors.get("__all__", [])
    assert any(
        "instructor and surge instructor cannot be the same person" in msg.lower()
        for msg in error_messages
    )


@pytest.mark.django_db
def test_create_logsheet_form_prevents_duplicate_tow_pilot_surge_tow_pilot(
    member_towpilot, airfield
):
    """Test that tow pilot and surge tow pilot cannot be the same person"""
    form = CreateLogsheetForm(
        data={
            "log_date": date.today(),
            "airfield": airfield.id,
            "tow_pilot": member_towpilot.id,
            "surge_tow_pilot": member_towpilot.id,
        }
    )
    assert not form.is_valid()
    assert "__all__" in form.errors
    error_messages = form.errors.get("__all__", [])
    assert any(
        "tow pilot and surge tow pilot cannot be the same person" in msg.lower()
        for msg in error_messages
    )


@pytest.mark.django_db
def test_create_logsheet_form_allows_different_instructors(
    member_instructor, member_instructor2, airfield
):
    """Test that different people can be instructor and surge instructor"""
    form = CreateLogsheetForm(
        data={
            "log_date": date.today(),
            "airfield": airfield.id,
            "duty_instructor": member_instructor.id,
            "surge_instructor": member_instructor2.id,
        }
    )
    assert form.is_valid(), f"Form errors: {form.errors}"


@pytest.mark.django_db
def test_create_logsheet_form_allows_different_tow_pilots(
    member_towpilot, member_towpilot2, airfield
):
    """Test that different people can be tow pilot and surge tow pilot"""
    form = CreateLogsheetForm(
        data={
            "log_date": date.today(),
            "airfield": airfield.id,
            "tow_pilot": member_towpilot.id,
            "surge_tow_pilot": member_towpilot2.id,
        }
    )
    assert form.is_valid(), f"Form errors: {form.errors}"


@pytest.mark.django_db
def test_create_logsheet_form_allows_same_person_different_roles(
    member_instructor_towpilot, airfield
):
    """Test that the same person can serve as both instructor and tow pilot (different role types)"""
    form = CreateLogsheetForm(
        data={
            "log_date": date.today(),
            "airfield": airfield.id,
            "duty_instructor": member_instructor_towpilot.id,
            "tow_pilot": member_instructor_towpilot.id,
        }
    )
    assert form.is_valid(), f"Form errors: {form.errors}"


@pytest.mark.django_db
def test_create_logsheet_form_allows_blank_surge_roles(
    member_instructor, member_towpilot, airfield
):
    """Test that surge roles can be blank without validation errors"""
    form = CreateLogsheetForm(
        data={
            "log_date": date.today(),
            "airfield": airfield.id,
            "duty_instructor": member_instructor.id,
            "tow_pilot": member_towpilot.id,
            # surge_instructor and surge_tow_pilot intentionally omitted
        }
    )
    assert form.is_valid(), f"Form errors: {form.errors}"


# LogsheetDutyCrewForm validation tests
@pytest.mark.django_db
def test_duty_crew_form_prevents_duplicate_instructor_surge_instructor(
    member_instructor,
):
    """Test that instructor and surge instructor cannot be the same person in duty crew form"""
    form = LogsheetDutyCrewForm(
        data={
            "duty_instructor": member_instructor.id,
            "surge_instructor": member_instructor.id,
        }
    )
    assert not form.is_valid()
    assert "__all__" in form.errors
    error_messages = form.errors.get("__all__", [])
    assert any(
        "instructor and surge instructor cannot be the same person" in msg.lower()
        for msg in error_messages
    )


@pytest.mark.django_db
def test_duty_crew_form_prevents_duplicate_tow_pilot_surge_tow_pilot(member_towpilot):
    """Test that tow pilot and surge tow pilot cannot be the same person in duty crew form"""
    form = LogsheetDutyCrewForm(
        data={
            "tow_pilot": member_towpilot.id,
            "surge_tow_pilot": member_towpilot.id,
        }
    )
    assert not form.is_valid()
    assert "__all__" in form.errors
    error_messages = form.errors.get("__all__", [])
    assert any(
        "tow pilot and surge tow pilot cannot be the same person" in msg.lower()
        for msg in error_messages
    )


@pytest.mark.django_db
def test_duty_crew_form_allows_different_instructors(
    member_instructor, member_instructor2
):
    """Test that different people can be instructor and surge instructor in duty crew form"""
    form = LogsheetDutyCrewForm(
        data={
            "duty_instructor": member_instructor.id,
            "surge_instructor": member_instructor2.id,
        }
    )
    assert form.is_valid(), f"Form errors: {form.errors}"


@pytest.mark.django_db
def test_duty_crew_form_allows_different_tow_pilots(member_towpilot, member_towpilot2):
    """Test that different people can be tow pilot and surge tow pilot in duty crew form"""
    form = LogsheetDutyCrewForm(
        data={
            "tow_pilot": member_towpilot.id,
            "surge_tow_pilot": member_towpilot2.id,
        }
    )
    assert form.is_valid(), f"Form errors: {form.errors}"


@pytest.mark.django_db
def test_duty_crew_form_allows_same_person_different_roles(member_instructor_towpilot):
    """Test that the same person can serve as both instructor and tow pilot in duty crew form"""
    form = LogsheetDutyCrewForm(
        data={
            "duty_instructor": member_instructor_towpilot.id,
            "tow_pilot": member_instructor_towpilot.id,
        }
    )
    assert form.is_valid(), f"Form errors: {form.errors}"


# Tests for warning functionality (new dual-role warnings)
@pytest.mark.django_db
def test_create_logsheet_form_warns_duty_officer_instructor(
    member_duty_officer_instructor, airfield
):
    """Test that duty officer = instructor generates a warning but allows form submission"""
    from datetime import timedelta

    future_date = date.today() + timedelta(days=45)  # Avoid conflicts

    form = CreateLogsheetForm(
        data={
            "log_date": future_date,
            "airfield": airfield.id,
            "duty_officer": member_duty_officer_instructor.id,
            "duty_instructor": member_duty_officer_instructor.id,
        }
    )
    assert form.is_valid(), f"Form errors: {form.errors}"
    assert hasattr(form, "warnings")
    assert len(form.warnings) == 1
    assert "serving as both Duty Officer and Instructor" in form.warnings[0]
    assert "historical precedent" in form.warnings[0]


@pytest.mark.django_db
def test_create_logsheet_form_warns_duty_officer_towpilot(
    member_duty_officer_towpilot, airfield
):
    """Test that duty officer = tow pilot generates a warning but allows form submission"""
    from datetime import timedelta

    future_date = date.today() + timedelta(days=46)  # Avoid conflicts

    form = CreateLogsheetForm(
        data={
            "log_date": future_date,
            "airfield": airfield.id,
            "duty_officer": member_duty_officer_towpilot.id,
            "tow_pilot": member_duty_officer_towpilot.id,
        }
    )
    assert form.is_valid(), f"Form errors: {form.errors}"
    assert hasattr(form, "warnings")
    assert len(form.warnings) == 1
    assert "serving as both Duty Officer and Tow Pilot" in form.warnings[0]
    assert "adequate coverage" in form.warnings[0]


@pytest.mark.django_db
def test_create_logsheet_form_multiple_warnings(
    member_duty_officer_instructor, airfield
):
    """Test that multiple warnings can be generated simultaneously"""
    from datetime import timedelta

    future_date = date.today() + timedelta(days=47)  # Avoid conflicts

    # This member is both instructor and tow pilot, serving as duty officer for both
    # But first we need to make them a tow pilot too
    member_duty_officer_instructor.towpilot = True
    member_duty_officer_instructor.save()

    form = CreateLogsheetForm(
        data={
            "log_date": future_date,
            "airfield": airfield.id,
            "duty_officer": member_duty_officer_instructor.id,
            "duty_instructor": member_duty_officer_instructor.id,
            "tow_pilot": member_duty_officer_instructor.id,
        }
    )
    assert form.is_valid(), f"Form errors: {form.errors}"
    assert hasattr(form, "warnings")
    assert len(form.warnings) == 2
    warning_text = " ".join(form.warnings)
    assert "serving as both Duty Officer and Instructor" in warning_text
    assert "serving as both Duty Officer and Tow Pilot" in warning_text


@pytest.mark.django_db
def test_create_logsheet_form_no_warning_duty_officer_assistant(
    member_duty_officer, airfield
):
    """Test that duty officer = assistant duty officer does NOT generate a warning"""
    from datetime import timedelta

    future_date = date.today() + timedelta(days=48)  # Avoid conflicts

    form = CreateLogsheetForm(
        data={
            "log_date": future_date,
            "airfield": airfield.id,
            "duty_officer": member_duty_officer.id,
            "assistant_duty_officer": member_duty_officer.id,
        }
    )
    assert form.is_valid(), f"Form errors: {form.errors}"
    assert not hasattr(form, "warnings") or len(form.warnings) == 0


@pytest.mark.django_db
def test_duty_crew_form_warns_duty_officer_instructor(member_duty_officer_instructor):
    """Test that duty crew form warns for duty officer = instructor"""
    form = LogsheetDutyCrewForm(
        data={
            "duty_officer": member_duty_officer_instructor.id,
            "duty_instructor": member_duty_officer_instructor.id,
        }
    )
    assert form.is_valid(), f"Form errors: {form.errors}"
    assert hasattr(form, "warnings")
    assert len(form.warnings) == 1
    assert "serving as both Duty Officer and Instructor" in form.warnings[0]


@pytest.mark.django_db
def test_duty_crew_form_warns_duty_officer_towpilot(member_duty_officer_towpilot):
    """Test that duty crew form warns for duty officer = tow pilot"""
    form = LogsheetDutyCrewForm(
        data={
            "duty_officer": member_duty_officer_towpilot.id,
            "tow_pilot": member_duty_officer_towpilot.id,
        }
    )
    assert form.is_valid(), f"Form errors: {form.errors}"
    assert hasattr(form, "warnings")
    assert len(form.warnings) == 1
    assert "serving as both Duty Officer and Tow Pilot" in form.warnings[0]


@pytest.mark.django_db
def test_form_warnings_with_blank_duty_officer(
    member_instructor, member_towpilot, airfield
):
    """Test that no warnings are generated when duty officer is blank"""
    from datetime import timedelta

    future_date = date.today() + timedelta(days=49)  # Avoid conflicts

    form = CreateLogsheetForm(
        data={
            "log_date": future_date,
            "airfield": airfield.id,
            "duty_instructor": member_instructor.id,
            "tow_pilot": member_towpilot.id,
            # duty_officer intentionally omitted
        }
    )
    assert form.is_valid(), f"Form errors: {form.errors}"
    assert not hasattr(form, "warnings") or len(form.warnings) == 0


# FlightForm business rule tests (Issue #110)
@pytest.mark.django_db
def test_flight_form_warns_unscheduled_tow_pilot(
    member_towpilot, member_towpilot2, glider, logsheet
):
    """Test that FlightForm warns when tow pilot is not on scheduled list"""
    from logsheet.forms import FlightForm
    from siteconfig.models import SiteConfiguration

    # Create required site configuration
    SiteConfiguration.objects.create(
        club_name="Test Club", domain_name="test.example.com", club_abbreviation="TC"
    )

    # Set up logsheet with scheduled tow pilots
    logsheet.tow_pilot = member_towpilot  # Only this member is scheduled
    logsheet.save()

    # Try to create flight with different tow pilot
    form = FlightForm(
        data={
            "pilot": member_towpilot2.id,
            "glider": glider.id,
            "tow_pilot": member_towpilot2.id,  # Not on scheduled list
            "launch_time": "14:00",
            "release_altitude": 3000,
        },
        logsheet=logsheet,
    )

    assert form.is_valid(), f"Form errors: {form.errors}"
    assert hasattr(form, "warnings")
    assert len(form.warnings) == 1
    warning = form.warnings[0]
    assert "is not on the scheduled tow pilot list" in warning
    assert member_towpilot2.get_full_name() in warning
    assert member_towpilot.get_full_name() in warning


@pytest.mark.django_db
def test_flight_form_no_warning_scheduled_tow_pilot(member_towpilot, glider, logsheet):
    """Test that FlightForm does not warn when tow pilot is on scheduled list"""
    from logsheet.forms import FlightForm
    from siteconfig.models import SiteConfiguration

    # Create required site configuration
    SiteConfiguration.objects.create(
        club_name="Test Club", domain_name="test.example.com", club_abbreviation="TC"
    )

    # Set up logsheet with scheduled tow pilot
    logsheet.tow_pilot = member_towpilot
    logsheet.save()

    # Create flight with scheduled tow pilot
    form = FlightForm(
        data={
            "pilot": member_towpilot.id,
            "glider": glider.id,
            "tow_pilot": member_towpilot.id,  # On scheduled list
            "launch_time": "14:00",
            "release_altitude": 3000,
        },
        logsheet=logsheet,
    )

    assert form.is_valid(), f"Form errors: {form.errors}"
    assert not hasattr(form, "warnings") or len(form.warnings) == 0


@pytest.mark.django_db
def test_flight_form_warns_unscheduled_with_surge_pilot(
    member_towpilot, member_towpilot2, member_instructor_towpilot, glider, logsheet
):
    """Test that FlightForm warns correctly when surge tow pilot is also scheduled"""
    from logsheet.forms import FlightForm
    from siteconfig.models import SiteConfiguration

    # Create required site configuration
    SiteConfiguration.objects.create(
        club_name="Test Club", domain_name="test.example.com", club_abbreviation="TC"
    )

    # Set up logsheet with both regular and surge tow pilots
    logsheet.tow_pilot = member_towpilot
    logsheet.surge_tow_pilot = member_towpilot2
    logsheet.save()

    # Try to create flight with unscheduled tow pilot (different from both scheduled)
    form = FlightForm(
        data={
            "pilot": member_instructor_towpilot.id,
            "glider": glider.id,
            "tow_pilot": member_instructor_towpilot.id,  # Not on either scheduled list
            "launch_time": "14:00",
            "release_altitude": 3000,
        },
        logsheet=logsheet,
    )

    assert form.is_valid(), f"Form errors: {form.errors}"
    assert hasattr(form, "warnings")
    assert len(form.warnings) == 1
    warning = form.warnings[0]
    assert "is not on the scheduled tow pilot list" in warning
    assert member_instructor_towpilot.get_full_name() in warning
    # Both scheduled pilots should be mentioned
    assert member_towpilot.get_full_name() in warning
    assert member_towpilot2.get_full_name() in warning


@pytest.mark.django_db
def test_flight_form_no_warning_no_scheduled_pilots(member_towpilot, glider, logsheet):
    """Test that FlightForm does not warn when no tow pilots are scheduled"""
    from logsheet.forms import FlightForm
    from siteconfig.models import SiteConfiguration

    # Create required site configuration
    SiteConfiguration.objects.create(
        club_name="Test Club", domain_name="test.example.com", club_abbreviation="TC"
    )

    # Logsheet with no scheduled tow pilots
    assert logsheet.tow_pilot is None
    assert logsheet.surge_tow_pilot is None

    # Create flight with any tow pilot
    form = FlightForm(
        data={
            "pilot": member_towpilot.id,
            "glider": glider.id,
            "tow_pilot": member_towpilot.id,
            "launch_time": "14:00",
            "release_altitude": 3000,
        },
        logsheet=logsheet,
    )

    assert form.is_valid(), f"Form errors: {form.errors}"
    assert not hasattr(form, "warnings") or len(form.warnings) == 0
