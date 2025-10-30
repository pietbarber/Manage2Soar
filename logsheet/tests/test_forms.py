import pytest
from datetime import date

from logsheet.forms import MaintenanceIssueForm, CreateLogsheetForm, LogsheetDutyCrewForm


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
def test_create_logsheet_form_prevents_duplicate_instructor_surge_instructor(member_instructor, airfield):
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
    assert any("instructor and surge instructor cannot be the same person" in msg.lower()
               for msg in error_messages)


@pytest.mark.django_db
def test_create_logsheet_form_prevents_duplicate_tow_pilot_surge_tow_pilot(member_towpilot, airfield):
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
    assert any("tow pilot and surge tow pilot cannot be the same person" in msg.lower()
               for msg in error_messages)


@pytest.mark.django_db
def test_create_logsheet_form_allows_different_instructors(member_instructor, member_instructor2, airfield):
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
def test_create_logsheet_form_allows_different_tow_pilots(member_towpilot, member_towpilot2, airfield):
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
def test_create_logsheet_form_allows_same_person_different_roles(member_instructor_towpilot, airfield):
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
def test_create_logsheet_form_allows_blank_surge_roles(member_instructor, member_towpilot, airfield):
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
def test_duty_crew_form_prevents_duplicate_instructor_surge_instructor(member_instructor):
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
    assert any("instructor and surge instructor cannot be the same person" in msg.lower()
               for msg in error_messages)


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
    assert any("tow pilot and surge tow pilot cannot be the same person" in msg.lower()
               for msg in error_messages)


@pytest.mark.django_db
def test_duty_crew_form_allows_different_instructors(member_instructor, member_instructor2):
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
