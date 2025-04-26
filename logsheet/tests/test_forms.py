import pytest
from logsheet.forms import MaintenanceIssueForm
from logsheet.models import Glider

@pytest.mark.django_db
def test_maintenance_issue_form_valid_with_glider(glider):
    form = MaintenanceIssueForm(data={
        "description": "Landing gear squeak",
        "glider": glider.id
    })
    assert form.is_valid()

@pytest.mark.django_db
def test_maintenance_issue_form_valid_with_towplane(towplane):
    form = MaintenanceIssueForm(data={
        "description": "Tow hook fraying",
        "towplane": towplane.id
    })
    assert form.is_valid()

@pytest.mark.django_db
def test_maintenance_issue_form_invalid_without_aircraft():
    form = MaintenanceIssueForm(data={
        "description": "Mystery problem"
    })
    assert not form.is_valid()
    assert "__all__" in form.errors

@pytest.mark.django_db
def test_maintenance_issue_form_invalid_without_description(glider):
    form = MaintenanceIssueForm(data={
        "glider": glider.id
    })
    assert not form.is_valid()
    assert "description" in form.errors

@pytest.mark.django_db
def test_maintenance_issue_form_error_message_without_aircraft():
    form = MaintenanceIssueForm(data={
        "description": "Mystery issue"
    })
    form.is_valid()
    error_messages = form.errors.get("__all__", [])
    assert any("glider or a towplane" in msg.lower() for msg in error_messages)
